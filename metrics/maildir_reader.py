# =============================================================================
#  menabò — an experiment in human-agent newsroom integration
# -----------------------------------------------------------------------------
#  File:     metrics/maildir_reader.py
#  Purpose:  Turn the director's BCC maildir into typed message records:
#            tag, sender, recipients, hop count, threading headers.
#  Author:   Gianni Alessandroni
#  Created:  2026-08-16
#  License:  Apache-2.0 — see LICENSE
#  Part of:  menabò https://github.com/GianniAlessandroni/menabo
# =============================================================================
"""Parsing of delivered mail for the collector.

The BCC maildir is the authoritative record of what was actually delivered
(spec §6.2: the director's observation does not depend on agent behaviour).
Parse functions take ``email.message.Message`` objects, not sockets, so tests
run without a mailserver.
"""

from __future__ import annotations

import mailbox
import re
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from email.message import Message
from email.utils import getaddresses, parsedate_to_datetime
from pathlib import Path

# why: kept identical to TAG_PATTERN in spark-a/mail-server/filters/mail_filter.py;
# the two deployment units must agree on the tag grammar (guarded by a test).
TAG_PATTERN = re.compile(r"\[ART-\d{4}-\d{3}\]")
HOP_HEADER = "X-Redazione-Hop"

_PREFIX = re.compile(r"^\s*((re|fwd?|i)\s*:\s*)+", re.IGNORECASE)


@dataclass(frozen=True)
class MessageRecord:
    """One delivered mail, normalised for the `messages` table."""

    message_id: str
    in_reply_to: str | None
    tag: str | None
    subject: str
    sender: str
    recipients: tuple[str, ...]
    sent_at: datetime
    hop_count: int | None
    size_bytes: int


def _strip_angle(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip().strip("<>").strip()
    return stripped or None


def title_from_subject(subject: str, tag: str | None) -> str:
    """Derive a working article title: subject minus reply prefixes and the tag."""
    title = subject
    if tag:
        title = title.replace(tag, "")
    title = _PREFIX.sub("", title)
    return title.strip(" -:") or subject.strip()


def parse_message(message: Message) -> MessageRecord | None:
    """Build a record from one delivered mail; None when it has no Message-ID."""
    message_id = _strip_angle(message.get("Message-ID"))
    if message_id is None:
        return None
    subject = str(message.get("Subject", ""))
    tag_match = TAG_PATTERN.search(subject)
    sender_addresses = getaddresses([str(message.get("From", ""))])
    sender = sender_addresses[0][1].lower() if sender_addresses else ""
    recipients = tuple(
        address.lower()
        for _, address in getaddresses(
            [str(value) for key in ("To", "Cc") for value in message.get_all(key, [])]
        )
        if address
    )
    raw_date = message.get("Date")
    try:
        sent_at = parsedate_to_datetime(str(raw_date)).astimezone(UTC) if raw_date else None
    except ValueError:
        sent_at = None
    if sent_at is None:
        return None
    raw_hop = message.get(HOP_HEADER)
    try:
        hop_count = int(str(raw_hop).strip()) if raw_hop is not None else None
    except ValueError:
        hop_count = None
    return MessageRecord(
        message_id=message_id,
        in_reply_to=_strip_angle(message.get("In-Reply-To")),
        tag=tag_match.group(0) if tag_match else None,
        subject=subject,
        sender=sender,
        recipients=recipients,
        sent_at=sent_at,
        hop_count=hop_count,
        size_bytes=len(message.as_bytes()),
    )


def read_maildir(maildir_path: Path) -> Iterator[MessageRecord]:
    """Yield a record for every parseable message in the maildir."""
    maildir = mailbox.Maildir(str(maildir_path), create=False)
    for message in maildir:
        record = parse_message(message)
        if record is not None:
            yield record
