# =============================================================================
#  menabò — an experiment in human-agent newsroom integration
# -----------------------------------------------------------------------------
#  File:     tests/test_thread_state.py
#  Purpose:  Tests for the SQLite thread state: counters, freeze-once
#            semantics, and the summary used in director notifications.
#  Author:   Gianni Alessandroni
#  Created:  2026-08-16
#  License:  Apache-2.0 — see LICENSE
#  Part of:  menabò https://github.com/GianniAlessandroni/menabo
# =============================================================================
"""Tests for thread_state.py using a temporary database."""

from pathlib import Path

from thread_state import ThreadState

TAG = "[ART-2026-001]"


def make_state(tmp_path: Path) -> ThreadState:
    return ThreadState(tmp_path / "state.db")


def test_message_count_grows_with_recorded_messages(tmp_path: Path) -> None:
    state = make_state(tmp_path)
    assert state.message_count(TAG) == 0
    state.record_message(TAG, "cronista@redazione.local", "verificatore@redazione.local",
                         f"{TAG} bozza", "2026-08-16T10:00:00+00:00")
    assert state.message_count(TAG) == 1
    assert state.message_count("[ART-2026-002]") == 0


def test_freeze_returns_true_only_once(tmp_path: Path) -> None:
    state = make_state(tmp_path)
    assert not state.is_frozen(TAG)
    assert state.freeze(TAG, "2026-08-16T10:00:00+00:00") is True
    assert state.freeze(TAG, "2026-08-16T10:01:00+00:00") is False
    assert state.is_frozen(TAG)
    assert state.frozen_threads() == [(TAG, "2026-08-16T10:00:00+00:00")]


def test_warn_returns_true_only_once(tmp_path: Path) -> None:
    state = make_state(tmp_path)
    assert state.warn(TAG, "2026-08-16T09:00:00+00:00") is True
    assert state.warn(TAG, "2026-08-16T09:05:00+00:00") is False
    assert state.warned_threads() == [(TAG, "2026-08-16T09:00:00+00:00")]


def test_thread_summary_returns_most_recent_messages_oldest_first(tmp_path: Path) -> None:
    state = make_state(tmp_path)
    for n in range(25):
        state.record_message(TAG, "cronista@redazione.local", "caporedattore@redazione.local",
                             f"{TAG} messaggio {n}", f"2026-08-16T10:{n:02d}:00+00:00")
    summary = state.thread_summary(TAG, limit=20)
    assert len(summary) == 20
    assert summary[0].subject.endswith("messaggio 5")
    assert summary[-1].subject.endswith("messaggio 24")
