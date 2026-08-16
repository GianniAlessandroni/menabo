# =============================================================================
#  menabò — an experiment in human-agent newsroom integration
# -----------------------------------------------------------------------------
#  File:     metrics/collector.py
#  Purpose:  Nightly collector: BCC maildir + Postfix logs + filter state +
#            Hermes session logs -> MariaDB metrics. Idempotent on Message-ID;
#            safe to re-run.
#  Author:   Gianni Alessandroni
#  Created:  2026-08-16
#  License:  Apache-2.0 — see LICENSE
#  Part of:  menabò https://github.com/GianniAlessandroni/menabo
# =============================================================================
"""Orchestrates one collection run (see docs/RUNBOOK.it.md for the cron entry).

Sources, in order:
1. the director's BCC maildir — delivered messages, articles, interventions,
   review cycles;
2. the Postfix log — matrix bounces and tag bounces;
3. the mail filter's SQLite state — budget-fuse events;
4. Hermes session logs — token usage per agent/day (article attribution is
   not derivable from these logs; documented limit, see schema.sql).
"""

from __future__ import annotations

import argparse
import json
import logging
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, time
from pathlib import Path

from db import MetricsDb
from hermes_log import scan_agent_sessions
from maildir_reader import MessageRecord, read_maildir, title_from_subject
from postfix_log import parse_postfix_line

LOG = logging.getLogger("collector")

DIRECTOR_LOCAL_PART = "gianni"
VERIFICATORE_LOCAL_PART = "verificatore"
UNKNOWN_PHASE = "sconosciuta"


@dataclass(frozen=True)
class PublicArticleStatus:
    """Status entry from spark-a/public-status/articles.json."""

    tag: str
    status: str
    published_at: datetime | None


def load_public_statuses(articles_json: Path) -> list[PublicArticleStatus]:
    """Read the caporedattore-maintained public status file."""
    payload = json.loads(articles_json.read_text(encoding="utf-8"))
    statuses: list[PublicArticleStatus] = []
    for entry in payload.get("articles", []):
        published_raw = entry.get("published_at")
        published_at = (
            datetime.fromisoformat(published_raw.replace("Z", "+00:00"))
            if isinstance(published_raw, str)
            else None
        )
        statuses.append(
            PublicArticleStatus(
                tag=str(entry["tag"]), status=str(entry["status"]), published_at=published_at
            )
        )
    return statuses


def agent_name(address: str) -> str:
    """Local part of a newsroom address: 'cronista@redazione.local' -> 'cronista'."""
    return address.split("@", 1)[0].lower()


def collect_maildir(db: MetricsDb, maildir_path: Path) -> int:
    """Store delivered messages plus everything derivable from them."""
    records = sorted(read_maildir(maildir_path), key=lambda record: record.sent_at)
    revision_cycles: dict[str, int] = {}
    for record in records:
        _store_message(db, record, revision_cycles)
    return len(records)


def _store_message(
    db: MetricsDb, record: MessageRecord, revision_cycles: dict[str, int]
) -> None:
    if record.tag is not None:
        db.upsert_article(
            record.tag, title_from_subject(record.subject, record.tag), record.sent_at
        )
    for recipient in record.recipients or ("",):
        db.insert_message(
            record.tag, record.sender, recipient, record.sent_at, record.hop_count,
            record.size_bytes, record.message_id, record.in_reply_to,
        )
    sender_agent = agent_name(record.sender)
    if sender_agent == DIRECTOR_LOCAL_PART:
        db.insert_intervention(record.tag, record.sent_at, UNKNOWN_PHASE)
    # Deterministic review-cycle rule (schema.sql): every verificatore mail on
    # a tag is one cycle step, numbered in delivery order.
    if sender_agent == VERIFICATORE_LOCAL_PART and record.tag and record.recipients:
        cycle = revision_cycles.get(record.tag, 0) + 1
        revision_cycles[record.tag] = cycle
        db.insert_revision(
            record.tag, cycle, sender_agent, agent_name(record.recipients[0]), record.sent_at
        )


def collect_postfix_log(db: MetricsDb, log_path: Path, default_year: int) -> int:
    """Store bounce events from the Postfix log."""
    count = 0
    with log_path.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            event = parse_postfix_line(line, default_year)
            if event is None:
                continue
            db.insert_event(
                event.kind.value, event.occurred_at, event.detail, None, event.source_ref
            )
            count += 1
    return count


def collect_fuse_events(db: MetricsDb, filter_state_db: Path) -> int:
    """Store `fusibile` events from the filter's state: stage-1 warnings
    (grace zone entered) and stage-2 freezes."""
    connection = sqlite3.connect(f"file:{filter_state_db}?mode=ro", uri=True)
    try:
        frozen = connection.execute("SELECT tag, frozen_at FROM frozen_threads").fetchall()
        try:
            warned = connection.execute("SELECT tag, warned_at FROM warned_threads").fetchall()
        except sqlite3.OperationalError:
            # State DBs written before the two-stage fuse have no warned table.
            LOG.warning("filter state has no warned_threads table (pre two-stage fuse)")
            warned = []
    finally:
        connection.close()
    stages = [
        ("fuse-warn", "entered the grace zone (stage 1 warning)", warned),
        ("fuse", "frozen over message budget (stage 2)", frozen),
    ]
    count = 0
    for ref_prefix, description, rows in stages:
        for tag, moment in rows:
            occurred_at = datetime.fromisoformat(str(moment))
            db.upsert_article(str(tag), None, occurred_at)
            db.insert_event(
                "fusibile", occurred_at, f"thread {tag} {description}",
                str(tag), f"{ref_prefix}:{tag}",
            )
            count += 1
    return count


def collect_token_usage(db: MetricsDb, hermes_root: Path) -> int:
    """Store per-agent daily token rollups from every agent's Hermes home."""
    count = 0
    for agent_dir in sorted(path for path in hermes_root.iterdir() if path.is_dir()):
        for usage in scan_agent_sessions(agent_dir / "hermes-home", agent_dir.name):
            db.upsert_daily_token_usage(
                usage.agent,
                datetime.combine(usage.day, time.min, tzinfo=UTC),
                usage.prompt_tokens,
                usage.completion_tokens,
            )
            count += 1
    return count


def sync_public_statuses(db: MetricsDb, articles_json: Path) -> int:
    """Mirror article statuses from the public status file into `articles`."""
    statuses = load_public_statuses(articles_json)
    for status in statuses:
        db.upsert_article(status.tag, None, status.published_at or datetime.now(tz=UTC))
        db.set_article_status(status.tag, status.status, status.published_at)
    return len(statuses)


def main() -> None:
    """Run one collection pass over all configured sources."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    parser = argparse.ArgumentParser(description="menabò nightly metrics collector")
    parser.add_argument("--maildir", type=Path, help="director BCC maildir")
    parser.add_argument("--mail-log", type=Path, help="Postfix log file")
    parser.add_argument("--filter-state", type=Path, help="mail filter state.db")
    parser.add_argument("--hermes-root", type=Path, help="spark-a/agents directory")
    parser.add_argument("--articles-json", type=Path, help="public status file")
    parser.add_argument(
        "--log-year", type=int, default=datetime.now(tz=UTC).year,
        help="year assumed for syslog timestamps without one",
    )
    args = parser.parse_args()

    with MetricsDb.from_env() as db:
        if args.maildir:
            LOG.info("maildir: %d messages", collect_maildir(db, args.maildir))
        if args.mail_log:
            LOG.info(
                "postfix log: %d bounce events",
                collect_postfix_log(db, args.mail_log, args.log_year),
            )
        if args.filter_state and args.filter_state.exists():
            LOG.info("filter state: %d fuse events", collect_fuse_events(db, args.filter_state))
        if args.hermes_root:
            LOG.info("hermes logs: %d daily rollups", collect_token_usage(db, args.hermes_root))
        if args.articles_json and args.articles_json.exists():
            LOG.info("public status: %d articles", sync_public_statuses(db, args.articles_json))


if __name__ == "__main__":
    main()
