# =============================================================================
#  menabò — an experiment in human-agent newsroom integration
# -----------------------------------------------------------------------------
#  File:     metrics/db.py
#  Purpose:  Thin persistence layer over the `metrics` MariaDB database.
#            All idempotency (ON DUPLICATE KEY) lives here so the collector
#            can be re-run safely at any time.
#  Author:   Gianni Alessandroni
#  Created:  2026-08-16
#  License:  Apache-2.0 — see LICENSE
#  Part of:  menabò https://github.com/GianniAlessandroni/menabo
# =============================================================================
"""MariaDB access for the metrics suite (PyMySQL, no ORM)."""

from __future__ import annotations

import os
from datetime import datetime
from types import TracebackType
from typing import Any

import pymysql


def _to_db(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%d %H:%M:%S")


class MetricsDb:
    """Connection wrapper with one method per table, all idempotent."""

    def __init__(self, connection: Any) -> None:
        self._conn = connection

    @classmethod
    def from_env(cls) -> MetricsDb:
        """Connect using NEWSROOM_DB_HOST/PORT/USER/PASSWORD/NAME."""
        connection = pymysql.connect(
            host=os.environ.get("NEWSROOM_DB_HOST", "127.0.0.1"),
            port=int(os.environ.get("NEWSROOM_DB_PORT", "3306")),
            user=os.environ["NEWSROOM_DB_USER"],
            password=os.environ["NEWSROOM_DB_PASSWORD"],
            database=os.environ.get("NEWSROOM_DB_NAME", "metrics"),
            charset="utf8mb4",
            autocommit=False,
        )
        return cls(connection)

    def __enter__(self) -> MetricsDb:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if exc is None:
            self._conn.commit()
        else:
            self._conn.rollback()
        self._conn.close()

    def _execute(self, query: str, params: tuple[Any, ...]) -> None:
        with self._conn.cursor() as cursor:
            cursor.execute(query, params)

    def upsert_article(self, tag: str, title: str | None, created_at: datetime) -> None:
        """Create the article row if new; keep the earliest created_at and first title."""
        self._execute(
            "INSERT INTO articles (tag, title, created_at) VALUES (%s, %s, %s)"
            " ON DUPLICATE KEY UPDATE"
            " created_at = LEAST(created_at, VALUES(created_at)),"
            " title = COALESCE(title, VALUES(title))",
            (tag, title, _to_db(created_at)),
        )

    def set_article_status(
        self, tag: str, status: str, published_at: datetime | None
    ) -> None:
        """Sync status/published_at from the public status file."""
        self._execute(
            "UPDATE articles SET status = %s, published_at = %s WHERE tag = %s",
            (status, _to_db(published_at) if published_at else None, tag),
        )

    def insert_message(
        self,
        tag: str | None,
        sender: str,
        recipient: str,
        sent_at: datetime,
        hop_count: int | None,
        size_bytes: int,
        message_id: str,
        in_reply_to: str | None,
    ) -> None:
        """Insert one (message, recipient) row; duplicates are silently kept as-is."""
        self._execute(
            "INSERT INTO messages"
            " (tag, sender, recipient, sent_at, hop_count, size_bytes, message_id, in_reply_to)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"
            " ON DUPLICATE KEY UPDATE id = id",
            (tag, sender, recipient, _to_db(sent_at), hop_count, size_bytes,
             message_id, in_reply_to),
        )

    def insert_intervention(self, tag: str | None, occurred_at: datetime, phase: str) -> None:
        """Record a director mail; the (tag, occurred_at) key makes re-runs no-ops."""
        self._execute(
            "INSERT INTO director_interventions (tag, occurred_at, phase)"
            " VALUES (%s, %s, %s) ON DUPLICATE KEY UPDATE id = id",
            (tag, _to_db(occurred_at), phase),
        )

    def insert_event(
        self,
        event_type: str,
        occurred_at: datetime,
        detail: str,
        tag: str | None,
        source_ref: str | None,
    ) -> None:
        """Record a bounce/fuse/error event, deduplicated on source_ref."""
        self._execute(
            "INSERT INTO events (tag, occurred_at, type, detail, source_ref)"
            " VALUES (%s, %s, %s, %s, %s) ON DUPLICATE KEY UPDATE id = id",
            (tag, _to_db(occurred_at), event_type, detail[:2000], source_ref),
        )

    def insert_revision(
        self, tag: str, cycle_number: int, from_agent: str, to_agent: str, occurred_at: datetime
    ) -> None:
        """Record one review cycle step; natural key keeps re-runs idempotent."""
        self._execute(
            "INSERT INTO revisions (tag, cycle_number, from_agent, to_agent, occurred_at)"
            " VALUES (%s, %s, %s, %s, %s) ON DUPLICATE KEY UPDATE cycle_number ="
            " VALUES(cycle_number)",
            (tag, cycle_number, from_agent, to_agent, _to_db(occurred_at)),
        )

    def upsert_daily_token_usage(
        self, agent: str, day: datetime, prompt_tokens: int, completion_tokens: int
    ) -> None:
        """Overwrite the per-agent/per-day rollup (article attribution unavailable)."""
        source_ref = f"{agent}:{day.strftime('%Y-%m-%d')}"
        self._execute(
            "INSERT INTO token_usage"
            " (tag, agent, used_at, prompt_tokens, completion_tokens, source_ref)"
            " VALUES (NULL, %s, %s, %s, %s, %s)"
            " ON DUPLICATE KEY UPDATE prompt_tokens = VALUES(prompt_tokens),"
            " completion_tokens = VALUES(completion_tokens)",
            (agent, _to_db(day), prompt_tokens, completion_tokens, source_ref),
        )

    def insert_quality_review(
        self,
        tag: str,
        reviewed_at: datetime,
        quality_score: int,
        editing: str,
        diff_percent: float,
        misunderstandings_count: int,
        readability_score: int,
        phone_call_needed: bool,
        notes: str | None,
    ) -> None:
        """Insert or replace the single review row for an article."""
        self._execute(
            "REPLACE INTO quality_reviews (tag, reviewed_at, quality_score, editing,"
            " diff_percent, misunderstandings_count, readability_score, phone_call_needed, notes)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (tag, _to_db(reviewed_at), quality_score, editing, diff_percent,
             misunderstandings_count, readability_score, phone_call_needed, notes),
        )

    def query(self, sql: str, params: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
        """Run a read-only query (report.py) and return all rows."""
        with self._conn.cursor() as cursor:
            cursor.execute(sql, params)
            return list(cursor.fetchall())
