# =============================================================================
#  menabò — an experiment in human-agent newsroom integration
# -----------------------------------------------------------------------------
#  File:     metrics/postfix_log.py
#  Purpose:  Parse Postfix log lines into typed events: delivery-matrix
#            bounces and missing-tag bounces. Pure string functions, no I/O.
#  Author:   Gianni Alessandroni
#  Created:  2026-08-16
#  License:  Apache-2.0 — see LICENSE
#  Part of:  menabò https://github.com/GianniAlessandroni/menabo
# =============================================================================
"""Postfix log parsing for the nightly collector.

Two line families matter, both classified by fixed markers (no heuristics):

- ``NOQUEUE: reject`` from smtpd with "Recipient address rejected" — a
  delivery-matrix violation (``bounce_matrice``).
- ``status=bounced`` relayed through the content filter whose reason quotes
  the Italian no-tag message — a tag bounce (``bounce_tag``).
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum

# Substring of mail_filter.REJECT_REASON_NO_TAG; fixed marker for log parsing.
NO_TAG_MARKER = "Oggetto senza tag articolo"
MATRIX_MARKER = "Recipient address rejected"

_SYSLOG_TS = re.compile(r"^(?P<month>\w{3})\s+(?P<day>\d{1,2})\s+(?P<time>\d{2}:\d{2}:\d{2})")
_ISO_TS = re.compile(r"^(?P<iso>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})")
_FROM_TO = re.compile(r"from=<(?P<sender>[^>]*)>.*?to=<(?P<recipient>[^>]*)>")
_TO_ONLY = re.compile(r"to=<(?P<recipient>[^>]*)>")

_MONTHS = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}


class BounceKind(Enum):
    """Event type value for the `events` table (Italian domain values)."""

    MATRIX = "bounce_matrice"
    TAG = "bounce_tag"


@dataclass(frozen=True)
class BounceEvent:
    """One bounce extracted from the Postfix log."""

    kind: BounceKind
    occurred_at: datetime
    sender: str | None
    recipient: str | None
    detail: str
    source_ref: str


def parse_timestamp(line: str, default_year: int) -> datetime | None:
    """Parse a leading syslog or ISO timestamp; syslog lines take default_year."""
    iso = _ISO_TS.match(line)
    if iso:
        return datetime.fromisoformat(iso.group("iso")).replace(tzinfo=UTC)
    syslog = _SYSLOG_TS.match(line)
    if syslog and syslog.group("month") in _MONTHS:
        hour, minute, second = (int(part) for part in syslog.group("time").split(":"))
        return datetime(
            default_year, _MONTHS[syslog.group("month")], int(syslog.group("day")),
            hour, minute, second, tzinfo=UTC,
        )
    return None


def _line_ref(line: str) -> str:
    return hashlib.sha256(line.encode("utf-8", errors="replace")).hexdigest()[:32]


def parse_postfix_line(line: str, default_year: int) -> BounceEvent | None:
    """Return the bounce event on this line, or None for all other lines."""
    if NO_TAG_MARKER in line and "status=bounced" in line:
        kind = BounceKind.TAG
    elif MATRIX_MARKER in line and "reject" in line:
        kind = BounceKind.MATRIX
    else:
        return None
    occurred_at = parse_timestamp(line, default_year)
    if occurred_at is None:
        return None
    pair = _FROM_TO.search(line)
    if pair:
        sender: str | None = pair.group("sender") or None
        recipient: str | None = pair.group("recipient") or None
    else:
        sender = None
        only = _TO_ONLY.search(line)
        recipient = only.group("recipient") if only else None
    return BounceEvent(
        kind=kind,
        occurred_at=occurred_at,
        sender=sender,
        recipient=recipient,
        detail=line.strip()[:500],
        source_ref=_line_ref(line),
    )
