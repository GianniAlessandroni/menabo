# =============================================================================
#  menabò — an experiment in human-agent newsroom integration
# -----------------------------------------------------------------------------
#  File:     tests/test_postfix_log.py
#  Purpose:  Tests for Postfix log parsing: matrix bounces, tag bounces,
#            timestamp handling, and non-event lines.
#  Author:   Gianni Alessandroni
#  Created:  2026-08-16
#  License:  Apache-2.0 — see LICENSE
#  Part of:  menabò https://github.com/GianniAlessandroni/menabo
# =============================================================================
"""Tests for postfix_log.py using realistic log lines as plain strings."""

from postfix_log import BounceKind, parse_postfix_line

MATRIX_LINE = (
    "Aug 16 10:15:03 mail postfix/smtpd[311]: NOQUEUE: reject: RCPT from "
    "unknown[172.20.0.9]: 554 5.7.1 <gianni@redazione.local>: Recipient address "
    "rejected: Access denied; from=<cronista@redazione.local> "
    "to=<gianni@redazione.local> proto=ESMTP helo=<cronista>"
)

TAG_BOUNCE_LINE = (
    "Aug 16 10:16:44 mail postfix/smtp[380]: 4XYZ12AB34: to=<verificatore@redazione.local>, "
    "relay=mail-filter[172.20.0.7]:10025, delay=0.2, status=bounced (host "
    "mail-filter[172.20.0.7] said: 550 5.7.1 Oggetto senza tag articolo [ART-AAAA-NNN] "
    "e senza flag [SERVIZIO]: aggiungere il tag e reinviare.)"
)

DELIVERED_LINE = (
    "Aug 16 10:17:00 mail postfix/lmtp[402]: 4XYZ12AB35: "
    "to=<caporedattore@redazione.local>, status=sent (250 2.0.0 Ok)"
)


def test_matrix_violation_is_classified_with_sender_and_recipient() -> None:
    event = parse_postfix_line(MATRIX_LINE, default_year=2026)
    assert event is not None
    assert event.kind is BounceKind.MATRIX
    assert event.sender == "cronista@redazione.local"
    assert event.recipient == "gianni@redazione.local"
    assert event.occurred_at.isoformat() == "2026-08-16T10:15:03+00:00"


def test_missing_tag_bounce_is_classified_as_tag_bounce() -> None:
    event = parse_postfix_line(TAG_BOUNCE_LINE, default_year=2026)
    assert event is not None
    assert event.kind is BounceKind.TAG
    assert event.recipient == "verificatore@redazione.local"


def test_delivered_mail_produces_no_event() -> None:
    assert parse_postfix_line(DELIVERED_LINE, default_year=2026) is None


def test_source_ref_is_stable_for_identical_lines() -> None:
    first = parse_postfix_line(MATRIX_LINE, default_year=2026)
    second = parse_postfix_line(MATRIX_LINE, default_year=2026)
    assert first is not None and second is not None
    assert first.source_ref == second.source_ref


def test_iso_timestamps_are_supported() -> None:
    line = MATRIX_LINE.replace("Aug 16 10:15:03", "2026-08-16T10:15:03")
    event = parse_postfix_line(line, default_year=1999)
    assert event is not None
    assert event.occurred_at.year == 2026
