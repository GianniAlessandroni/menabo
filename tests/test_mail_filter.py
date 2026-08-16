# =============================================================================
#  menabò — an experiment in human-agent newsroom integration
# -----------------------------------------------------------------------------
#  File:     tests/test_mail_filter.py
#  Purpose:  Behavioural tests for the pure filter rules: tag enforcement,
#            [SERVIZIO] exemption, hop counting, budget fuse boundary.
#  Author:   Gianni Alessandroni
#  Created:  2026-08-16
#  License:  Apache-2.0 — see LICENSE
#  Part of:  menabò https://github.com/GianniAlessandroni/menabo
# =============================================================================
"""Tests for mail_filter.py (no mailserver required, per CODING-STANDARDS §4)."""

from email.message import EmailMessage

from mail_filter import (
    HOP_HEADER,
    REJECT_REASON_NO_TAG,
    Verdict,
    evaluate_subject,
    extract_tag,
    grace_margin,
    has_service_flag,
    increment_hop,
)

BUDGET = 60
HARD_LIMIT = BUDGET + grace_margin(BUDGET)


def test_tag_extraction_finds_canonical_tag() -> None:
    assert extract_tag("Re: [ART-2026-001] bozza pronta") == "[ART-2026-001]"


def test_tag_extraction_rejects_malformed_tags() -> None:
    assert extract_tag("[ART-26-1] bozza") is None
    assert extract_tag("[art-2026-001] bozza") is None
    assert extract_tag("ART-2026-001 senza parentesi") is None
    assert extract_tag(None) is None


def test_mail_without_tag_is_bounced_with_reason() -> None:
    assert evaluate_subject("ciao, novita'?", 0, BUDGET) is Verdict.REJECT_NO_TAG
    assert "[ART-AAAA-NNN]" in REJECT_REASON_NO_TAG


def test_mail_with_service_flag_is_accepted_without_tag() -> None:
    assert has_service_flag("[SERVIZIO] riunione di redazione")
    assert evaluate_subject("[SERVIZIO] riunione di redazione", 0, BUDGET) is Verdict.ACCEPT


def test_tagged_mail_within_budget_is_accepted() -> None:
    assert evaluate_subject("[ART-2026-001] bozza", 0, BUDGET) is Verdict.ACCEPT
    assert evaluate_subject("[ART-2026-001] bozza", BUDGET - 1, BUDGET) is Verdict.ACCEPT


def test_grace_margin_is_half_the_budget() -> None:
    assert grace_margin(60) == 30
    assert grace_margin(7) == 3


def test_message_over_budget_enters_grace_zone_with_warning() -> None:
    # The 61st message (60 already accepted) is still delivered, but warned.
    assert evaluate_subject("[ART-2026-001] bozza", BUDGET, BUDGET) is Verdict.ACCEPT_WARN
    # The whole grace zone keeps the ACCEPT_WARN verdict (warn-once is state's job).
    assert evaluate_subject("[ART-2026-001] bozza", HARD_LIMIT - 1, BUDGET) is Verdict.ACCEPT_WARN


def test_message_past_grace_margin_freezes_thread() -> None:
    # The 91st message (60 budget + 30 grace already accepted) trips stage 2.
    assert evaluate_subject("[ART-2026-001] bozza", HARD_LIMIT, BUDGET) is Verdict.FREEZE


def test_hop_header_is_added_at_zero_when_absent() -> None:
    message = EmailMessage()
    assert increment_hop(message) == 0
    assert message[HOP_HEADER] == "0"


def test_hop_header_is_incremented_when_present() -> None:
    message = EmailMessage()
    message[HOP_HEADER] = "3"
    assert increment_hop(message) == 4
    assert message.get_all(HOP_HEADER) == ["4"]


def test_malformed_hop_header_is_reset_to_zero() -> None:
    message = EmailMessage()
    message[HOP_HEADER] = "not-a-number"
    assert increment_hop(message) == 0
    assert message[HOP_HEADER] == "0"
