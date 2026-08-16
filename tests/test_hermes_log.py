# =============================================================================
#  menabò — an experiment in human-agent newsroom integration
# -----------------------------------------------------------------------------
#  File:     tests/test_hermes_log.py
#  Purpose:  Tests for Hermes session-log scanning: tolerant JSONL parsing
#            and per-day rollups.
#  Author:   Gianni Alessandroni
#  Created:  2026-08-16
#  License:  Apache-2.0 — see LICENSE
#  Part of:  menabò https://github.com/GianniAlessandroni/menabo
# =============================================================================
"""Tests for hermes_log.py with synthetic session lines."""

from datetime import date

from hermes_log import scan_session_lines

FALLBACK = date(2026, 8, 16)


def test_usage_records_are_summed_per_day() -> None:
    lines = [
        '{"timestamp": "2026-08-15T09:00:00+00:00", "usage":'
        ' {"prompt_tokens": 100, "completion_tokens": 20}}',
        '{"timestamp": "2026-08-15T10:00:00+00:00", "usage":'
        ' {"prompt_tokens": 50, "completion_tokens": 5}}',
        '{"timestamp": "2026-08-16T08:00:00+00:00", "usage":'
        ' {"prompt_tokens": 7, "completion_tokens": 3}}',
    ]
    usage = scan_session_lines(lines, "cronista", FALLBACK)
    assert [(u.day.isoformat(), u.prompt_tokens, u.completion_tokens) for u in usage] == [
        ("2026-08-15", 150, 25),
        ("2026-08-16", 7, 3),
    ]


def test_records_without_usage_or_invalid_json_are_skipped() -> None:
    lines = [
        "not json at all",
        '{"role": "assistant", "content": "ciao"}',
        '{"usage": {"prompt_tokens": 10, "completion_tokens": 1}}',
        "",
    ]
    usage = scan_session_lines(lines, "segreteria", FALLBACK)
    assert len(usage) == 1
    assert usage[0].agent == "segreteria"
    assert usage[0].day == FALLBACK  # no timestamp -> fallback day
    assert usage[0].prompt_tokens == 10


def test_top_level_token_fields_are_accepted() -> None:
    lines = ['{"ts": 1755302400, "prompt_tokens": 5, "completion_tokens": 2}']
    usage = scan_session_lines(lines, "verificatore", FALLBACK)
    assert len(usage) == 1
    assert usage[0].prompt_tokens == 5
    assert usage[0].completion_tokens == 2
