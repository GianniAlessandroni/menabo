# =============================================================================
#  menabò — an experiment in human-agent newsroom integration
# -----------------------------------------------------------------------------
#  File:     tests/test_maildir_reader.py
#  Purpose:  Tests for delivered-mail parsing: records, titles, hop counts,
#            and the tag-grammar lockstep with the mail filter.
#  Author:   Gianni Alessandroni
#  Created:  2026-08-16
#  License:  Apache-2.0 — see LICENSE
#  Part of:  menabò https://github.com/GianniAlessandroni/menabo
# =============================================================================
"""Tests for maildir_reader.py on in-memory email messages."""

from email.message import EmailMessage

import mail_filter
import maildir_reader
from maildir_reader import parse_message, title_from_subject


def make_message(subject: str, hop: str | None = "0") -> EmailMessage:
    message = EmailMessage()
    message["Message-ID"] = "<abc123@redazione.local>"
    message["From"] = "cronista@redazione.local"
    message["To"] = "Verificatore <verificatore@redazione.local>, caporedattore@redazione.local"
    message["Date"] = "Sat, 16 Aug 2026 12:30:00 +0200"
    message["Subject"] = subject
    if hop is not None:
        message["X-Redazione-Hop"] = hop
    message.set_content("corpo del messaggio\n\n-- cronista (agente IA)")
    return message


def test_tag_grammar_matches_the_mail_filter() -> None:
    # The collector and the filter must agree on what counts as a tag.
    assert maildir_reader.TAG_PATTERN.pattern == mail_filter.TAG_PATTERN.pattern


def test_delivered_message_is_parsed_into_a_record() -> None:
    record = parse_message(make_message("[ART-2026-001] bozza pronta"))
    assert record is not None
    assert record.message_id == "abc123@redazione.local"
    assert record.tag == "[ART-2026-001]"
    assert record.sender == "cronista@redazione.local"
    assert record.recipients == (
        "verificatore@redazione.local", "caporedattore@redazione.local",
    )
    assert record.sent_at.isoformat() == "2026-08-16T10:30:00+00:00"  # normalised to UTC
    assert record.hop_count == 0
    assert record.size_bytes > 0


def test_message_without_message_id_is_skipped() -> None:
    message = make_message("[ART-2026-001] bozza")
    del message["Message-ID"]
    assert parse_message(message) is None


def test_missing_hop_header_stays_null() -> None:
    record = parse_message(make_message("[SERVIZIO] avviso", hop=None))
    assert record is not None
    assert record.tag is None
    assert record.hop_count is None


def test_title_strips_reply_prefixes_and_tag() -> None:
    assert (
        title_from_subject("Re: Re: [ART-2026-001] Cronaca del consiglio", "[ART-2026-001]")
        == "Cronaca del consiglio"
    )
