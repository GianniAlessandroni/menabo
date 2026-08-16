# =============================================================================
#  menabò — an experiment in human-agent newsroom integration
# -----------------------------------------------------------------------------
#  File:     metrics/quality_review.py
#  Purpose:  Interactive CLI the director runs BEFORE publishing an article:
#            computes the draft->final diff and records the quality review.
#  Author:   Gianni Alessandroni
#  Created:  2026-08-16
#  License:  Apache-2.0 — see LICENSE
#  Part of:  menabò https://github.com/GianniAlessandroni/menabo
# =============================================================================
"""Qualitative review CLI (prompts in Italian: runtime editorial content).

Usage:
    python quality_review.py --tag "[ART-2026-001]" --draft bozza.md --final finale.md
"""

from __future__ import annotations

import argparse
import difflib
from datetime import UTC, datetime
from pathlib import Path

from db import MetricsDb

EDITING_LEVELS = {"l": "leggero", "s": "sostanziale", "r": "riscrittura"}


def diff_percent(draft_lines: list[str], final_lines: list[str]) -> float:
    """Changed-lines percentage between draft and final (0.0-100.0).

    Defined as ``(1 - SequenceMatcher line ratio) * 100`` — deterministic and
    order-sensitive, which is what "how much did the director rewrite" means.
    """
    if not draft_lines and not final_lines:
        return 0.0
    ratio = difflib.SequenceMatcher(None, draft_lines, final_lines).ratio()
    return round((1.0 - ratio) * 100.0, 2)


def _ask_int(prompt: str, minimum: int, maximum: int) -> int:
    while True:
        raw = input(prompt).strip()
        if raw.isdigit() and minimum <= int(raw) <= maximum:
            return int(raw)
        print(f"Valore non valido: inserire un numero da {minimum} a {maximum}.")


def _ask_choice(prompt: str, choices: dict[str, str]) -> str:
    keys = "/".join(choices)
    while True:
        raw = input(f"{prompt} [{keys}] ").strip().lower()
        if raw in choices:
            return choices[raw]
        print(f"Scelta non valida: usare una tra {keys}.")


def _ask_bool(prompt: str) -> bool:
    while True:
        raw = input(f"{prompt} [s/n] ").strip().lower()
        if raw in {"s", "n"}:
            return raw == "s"
        print("Rispondere s oppure n.")


def main() -> None:
    """Compile and store the review for one article."""
    parser = argparse.ArgumentParser(description="Scheda qualitativa di un articolo")
    parser.add_argument("--tag", required=True, help="tag articolo, es. [ART-2026-001]")
    parser.add_argument("--draft", required=True, type=Path, help="file della bozza dell'agente")
    parser.add_argument("--final", required=True, type=Path, help="file della versione finale")
    args = parser.parse_args()

    percent = diff_percent(
        args.draft.read_text(encoding="utf-8").splitlines(),
        args.final.read_text(encoding="utf-8").splitlines(),
    )

    print(f"\nScheda qualitativa per {args.tag}")
    print(f"Diff bozza -> finale: {percent}% delle righe modificate.\n")
    quality = _ask_int("Qualita' complessiva (1=scarsa, 5=eccellente): ", 1, 5)
    editing = _ask_choice(
        "Editing richiesto: (l)eggero, (s)ostanziale, (r)iscrittura?", EDITING_LEVELS
    )
    misunderstandings = _ask_int("Numero di fraintendimenti dell'agente (0-99): ", 0, 99)
    readability = _ask_int("Leggibilita' (1=faticosa, 5=scorrevole): ", 1, 5)
    phone_call = _ask_bool("Una telefonata avrebbe evitato il giro di email?")
    notes = input("Note (invio per saltare): ").strip() or None

    with MetricsDb.from_env() as db:
        db.insert_quality_review(
            args.tag, datetime.now(tz=UTC), quality, editing, percent,
            misunderstandings, readability, phone_call, notes,
        )
    print(f"\nScheda registrata per {args.tag}. Ora puoi pubblicare.")


if __name__ == "__main__":
    main()
