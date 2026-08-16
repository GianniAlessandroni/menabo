# =============================================================================
#  menabò — an experiment in human-agent newsroom integration
# -----------------------------------------------------------------------------
#  File:     spark-a/mail-server/filters/thread_state.py
#  Purpose:  Persistent per-tag message counters and freeze flags for the mail
#            filter, on SQLite (stdlib). Also the collector's read-only source
#            for budget-fuse events.
#  Author:   Gianni Alessandroni
#  Created:  2026-08-16
#  License:  Apache-2.0 — see LICENSE
#  Part of:  menabò https://github.com/GianniAlessandroni/menabo
# =============================================================================
"""SQLite-backed thread state for the mail filter.

One row per accepted message keeps the raw material for the freeze
notification (participants, subjects); ``frozen_threads`` guarantees the
director is notified exactly once per tag.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS thread_messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    tag         TEXT NOT NULL,
    sender      TEXT NOT NULL,
    recipients  TEXT NOT NULL,
    subject     TEXT NOT NULL,
    received_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_thread_messages_tag ON thread_messages (tag);
CREATE TABLE IF NOT EXISTS frozen_threads (
    tag       TEXT PRIMARY KEY,
    frozen_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS warned_threads (
    tag       TEXT PRIMARY KEY,
    warned_at TEXT NOT NULL
);
"""


@dataclass(frozen=True)
class ThreadEntry:
    """One accepted message on a tagged thread, as stored for reporting."""

    sender: str
    recipients: str
    subject: str
    received_at: str


class ThreadState:
    """Message counters and freeze flags, persisted under the state directory."""

    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        """Close the underlying connection."""
        self._conn.close()

    def message_count(self, tag: str) -> int:
        """Return how many messages have been accepted on ``tag`` so far."""
        row = self._conn.execute(
            "SELECT COUNT(*) FROM thread_messages WHERE tag = ?", (tag,)
        ).fetchone()
        return int(row[0])

    def record_message(
        self, tag: str, sender: str, recipients: str, subject: str, received_at: str
    ) -> None:
        """Append one accepted message to the thread history."""
        self._conn.execute(
            "INSERT INTO thread_messages (tag, sender, recipients, subject, received_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (tag, sender, recipients, subject, received_at),
        )
        self._conn.commit()

    def is_frozen(self, tag: str) -> bool:
        """Return True when ``tag`` has already tripped the budget fuse."""
        row = self._conn.execute(
            "SELECT 1 FROM frozen_threads WHERE tag = ?", (tag,)
        ).fetchone()
        return row is not None

    def freeze(self, tag: str, frozen_at: str) -> bool:
        """Mark ``tag`` frozen; return True only on the first call for the tag.

        The boolean drives notify-once semantics: only the caller that wins the
        insert sends the director notification.
        """
        cursor = self._conn.execute(
            "INSERT OR IGNORE INTO frozen_threads (tag, frozen_at) VALUES (?, ?)",
            (tag, frozen_at),
        )
        self._conn.commit()
        return cursor.rowcount == 1

    def frozen_threads(self) -> list[tuple[str, str]]:
        """Return all frozen tags with their freeze timestamps (for the collector)."""
        rows = self._conn.execute(
            "SELECT tag, frozen_at FROM frozen_threads ORDER BY frozen_at"
        ).fetchall()
        return [(str(tag), str(frozen_at)) for tag, frozen_at in rows]

    def warn(self, tag: str, warned_at: str) -> bool:
        """Mark ``tag`` as warned (stage 1); return True only on the first call.

        The boolean drives notify-once semantics for the caporedattore
        warning, mirroring :meth:`freeze` for the stage-2 fuse.
        """
        cursor = self._conn.execute(
            "INSERT OR IGNORE INTO warned_threads (tag, warned_at) VALUES (?, ?)",
            (tag, warned_at),
        )
        self._conn.commit()
        return cursor.rowcount == 1

    def warned_threads(self) -> list[tuple[str, str]]:
        """Return all warned tags with their warning timestamps (for the collector)."""
        rows = self._conn.execute(
            "SELECT tag, warned_at FROM warned_threads ORDER BY warned_at"
        ).fetchall()
        return [(str(tag), str(warned_at)) for tag, warned_at in rows]

    def thread_summary(self, tag: str, limit: int = 20) -> list[ThreadEntry]:
        """Return the most recent ``limit`` messages on ``tag``, oldest first."""
        rows = self._conn.execute(
            "SELECT sender, recipients, subject, received_at FROM thread_messages"
            " WHERE tag = ? ORDER BY id DESC LIMIT ?",
            (tag, limit),
        ).fetchall()
        return [ThreadEntry(*row) for row in reversed(rows)]
