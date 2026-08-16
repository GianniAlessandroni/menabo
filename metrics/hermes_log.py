# =============================================================================
#  menabò — an experiment in human-agent newsroom integration
# -----------------------------------------------------------------------------
#  File:     metrics/hermes_log.py
#  Purpose:  Extract per-agent daily token usage from Hermes session logs
#            (JSONL). Per-article attribution is not derivable from these
#            logs, so usage is rolled up per agent/day — a documented limit.
#  Author:   Gianni Alessandroni
#  Created:  2026-08-16
#  License:  Apache-2.0 — see LICENSE
#  Part of:  menabò https://github.com/GianniAlessandroni/menabo
# =============================================================================
"""Tolerant JSONL scanning for Hermes token counters.

Hermes writes session transcripts under ``/opt/data/sessions/``. Records that
carry a ``usage`` object (or top-level ``prompt_tokens``/``completion_tokens``)
are summed per UTC day; anything else is skipped silently — absence of usage
data is visible in the report as zero, not guessed at.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path


@dataclass(frozen=True)
class DailyUsage:
    """Token totals for one agent on one UTC day."""

    agent: str
    day: date
    prompt_tokens: int
    completion_tokens: int


def _usage_fields(record: dict[str, object]) -> tuple[int, int] | None:
    source = record.get("usage") if isinstance(record.get("usage"), dict) else record
    if not isinstance(source, dict):
        return None
    prompt = source.get("prompt_tokens")
    completion = source.get("completion_tokens")
    if isinstance(prompt, int) and isinstance(completion, int):
        return prompt, completion
    return None


def _record_day(record: dict[str, object], fallback: date) -> date:
    for key in ("timestamp", "created_at", "ts"):
        value = record.get(key)
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
            except ValueError:
                continue
        if isinstance(value, int | float):
            return datetime.fromtimestamp(value, tz=UTC).date()
    return fallback


def scan_session_lines(lines: list[str], agent: str, fallback_day: date) -> list[DailyUsage]:
    """Sum usage records in one session file's lines into per-day totals."""
    totals: dict[date, tuple[int, int]] = {}
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(record, dict):
            continue
        usage = _usage_fields(record)
        if usage is None:
            continue
        day = _record_day(record, fallback_day)
        prompt, completion = totals.get(day, (0, 0))
        totals[day] = (prompt + usage[0], completion + usage[1])
    return [
        DailyUsage(agent=agent, day=day, prompt_tokens=prompt, completion_tokens=completion)
        for day, (prompt, completion) in sorted(totals.items())
    ]


def scan_agent_sessions(agent_data_dir: Path, agent: str) -> list[DailyUsage]:
    """Scan all JSONL session files of one agent's Hermes data directory."""
    sessions_dir = agent_data_dir / "sessions"
    if not sessions_dir.is_dir():
        return []
    per_day: dict[date, tuple[int, int]] = {}
    for session_file in sorted(sessions_dir.rglob("*.jsonl")):
        fallback = datetime.fromtimestamp(session_file.stat().st_mtime, tz=UTC).date()
        for usage in scan_session_lines(
            session_file.read_text(encoding="utf-8", errors="replace").splitlines(),
            agent,
            fallback,
        ):
            prompt, completion = per_day.get(usage.day, (0, 0))
            per_day[usage.day] = (
                prompt + usage.prompt_tokens,
                completion + usage.completion_tokens,
            )
    return [
        DailyUsage(agent=agent, day=day, prompt_tokens=prompt, completion_tokens=completion)
        for day, (prompt, completion) in sorted(per_day.items())
    ]
