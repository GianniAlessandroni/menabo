# =============================================================================
#  menabò — an experiment in human-agent newsroom integration
# -----------------------------------------------------------------------------
#  File:     metrics/report.py
#  Purpose:  Weekly summary of the coordination experiment: per-article table
#            plus week-by-week trend, as markdown on stdout.
#  Author:   Gianni Alessandroni
#  Created:  2026-08-16
#  License:  Apache-2.0 — see LICENSE
#  Part of:  menabò https://github.com/GianniAlessandroni/menabo
# =============================================================================
"""Read-only reporting over the metrics database (no dashboard by design)."""

from __future__ import annotations

from typing import Any

from db import MetricsDb

PER_ARTICLE_SQL = """
SELECT a.tag,
       a.status,
       COALESCE(a.title, ''),
       (SELECT COUNT(DISTINCT m.message_id) FROM messages m WHERE m.tag = a.tag),
       (SELECT COALESCE(MAX(m.hop_count), 0) FROM messages m WHERE m.tag = a.tag),
       (SELECT COUNT(*) FROM events e WHERE e.tag = a.tag AND e.type = 'fusibile'),
       (SELECT COUNT(*) FROM director_interventions d WHERE d.tag = a.tag),
       (SELECT COALESCE(MAX(r.cycle_number), 0) FROM revisions r WHERE r.tag = a.tag),
       (SELECT q.quality_score FROM quality_reviews q WHERE q.tag = a.tag)
FROM articles a
ORDER BY a.tag
"""

WEEKLY_SQL = """
SELECT DATE_FORMAT(m.sent_at, '%x-W%v') AS week,
       COUNT(DISTINCT m.message_id),
       COUNT(DISTINCT m.tag),
       COALESCE(SUM(m.size_bytes), 0)
FROM messages m
GROUP BY week
ORDER BY week
"""

EVENTS_SQL = """
SELECT type, COUNT(*) FROM events GROUP BY type ORDER BY type
"""

TOKENS_SQL = """
SELECT agent, SUM(prompt_tokens), SUM(completion_tokens)
FROM token_usage GROUP BY agent ORDER BY agent
"""


def _table(headers: list[str], rows: list[tuple[Any, ...]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "|" + "|".join("---" for _ in headers) + "|",
    ]
    lines.extend(
        "| " + " | ".join("" if cell is None else str(cell) for cell in row) + " |"
        for row in rows
    )
    return "\n".join(lines)


def render_report(db: MetricsDb) -> str:
    """Build the full markdown report."""
    sections = [
        "# menabò — weekly coordination report",
        "",
        "## Articles",
        "",
        _table(
            ["tag", "status", "title", "messages", "max hop", "fuses",
             "director mails", "review cycles", "quality"],
            db.query(PER_ARTICLE_SQL),
        ),
        "",
        "## Weekly traffic",
        "",
        _table(["week", "messages", "active tags", "bytes"], db.query(WEEKLY_SQL)),
        "",
        "## Failure events (failures are data)",
        "",
        _table(["type", "count"], db.query(EVENTS_SQL)),
        "",
        "## Token usage per agent",
        "",
        _table(["agent", "prompt tokens", "completion tokens"], db.query(TOKENS_SQL)),
        "",
    ]
    return "\n".join(sections)


def main() -> None:
    """Print the report to stdout (pipe to a file for the archive)."""
    with MetricsDb.from_env() as db:
        print(render_report(db))


if __name__ == "__main__":
    main()
