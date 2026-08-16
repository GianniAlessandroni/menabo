# =============================================================================
#  menabò — an experiment in human-agent newsroom integration
# -----------------------------------------------------------------------------
#  File:     spark-a/mail-server/filters/mail_filter.py
#  Purpose:  Pure decision logic for the after-queue mail filter: article-tag
#            enforcement, hop counting, message-budget fuse. No I/O here, so
#            every rule is testable without a mailserver.
#  Author:   Gianni Alessandroni
#  Created:  2026-08-16
#  License:  Apache-2.0 — see LICENSE
#  Part of:  menabò https://github.com/GianniAlessandroni/menabo
# =============================================================================
"""Deterministic filter rules for newsroom mail.

Security code is deterministic and dumb (CODING-STANDARDS.md §2.2): no
heuristics, no retries. A message either carries a valid article tag or the
``[SERVIZIO]`` flag, or it bounces with a readable reason. Tagged threads that
exceed the message budget are frozen, never trimmed.
"""

from __future__ import annotations

import re
from email.message import Message
from enum import Enum

TAG_PATTERN = re.compile(r"\[ART-\d{4}-\d{3}\]")
SERVICE_FLAG = "[SERVIZIO]"
HOP_HEADER = "X-Redazione-Hop"

# Bounce text is runtime editorial content, hence Italian (CODING-STANDARDS §0).
REJECT_REASON_NO_TAG = (
    "5.7.1 Oggetto senza tag articolo [ART-AAAA-NNN] e senza flag [SERVIZIO]: "
    "aggiungere il tag e reinviare."
)


class Verdict(Enum):
    """Outcome of the subject/budget evaluation for one incoming message."""

    ACCEPT = "accept"
    REJECT_NO_TAG = "reject_no_tag"
    FREEZE = "freeze"


def extract_tag(subject: str | None) -> str | None:
    """Return the first canonical article tag in ``subject``, or ``None``.

    Only the exact shape ``[ART-YYYY-NNN]`` counts; near-misses are treated as
    missing on purpose — a sloppy tag must bounce, not be repaired.
    """
    if subject is None:
        return None
    match = TAG_PATTERN.search(subject)
    return match.group(0) if match else None


def has_service_flag(subject: str | None) -> bool:
    """Return True when the subject carries the literal ``[SERVIZIO]`` flag."""
    return subject is not None and SERVICE_FLAG in subject


def evaluate_subject(subject: str | None, tag_message_count: int, budget: int) -> Verdict:
    """Decide the fate of a message from its subject and the thread's history.

    Args:
        subject: Raw subject line (may be None).
        tag_message_count: Messages already accepted on this tag, before this one.
        budget: Message budget per article (``NEWSROOM_MESSAGE_BUDGET``).

    Returns:
        ``ACCEPT``, ``REJECT_NO_TAG`` (no tag and no service flag), or
        ``FREEZE`` (tag present but the budget is already exhausted).
    """
    tag = extract_tag(subject)
    if tag is None:
        return Verdict.ACCEPT if has_service_flag(subject) else Verdict.REJECT_NO_TAG
    if tag_message_count >= budget:
        return Verdict.FREEZE
    return Verdict.ACCEPT


def increment_hop(message: Message) -> int:
    """Increment ``X-Redazione-Hop`` in place; add it at 0 when absent.

    A first delivery therefore reads hop 0; every re-forward through the
    filter adds one. Returns the value now set on the message. A malformed
    existing value is replaced by 0 — visible in the data, never guessed at.
    """
    raw = message.get(HOP_HEADER)
    if raw is None:
        hop = 0
    else:
        try:
            hop = int(raw.strip()) + 1
        except ValueError:
            hop = 0
    del message[HOP_HEADER]
    message[HOP_HEADER] = str(hop)
    return hop
