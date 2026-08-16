<!-- =============================================================================
  menabò — an experiment in human-agent newsroom integration
 ------------------------------------------------------------------------------
  File:     CLAUDE.md
  Purpose:  Operating instructions for Claude Code sessions in this repo.
  Author:   Gianni Alessandroni
  Created:  2026-08-16
  License:  Apache-2.0 — see LICENSE
  Part of:  menabò https://github.com/GianniAlessandroni/menabo
============================================================================== -->

# CLAUDE.md — menabò

Multi-agent editorial newsroom (6 Hermes agents + human director) coordinating
**only via email**, with the inefficiency measured, not optimized away. Two DGX
Spark nodes, everything in Docker, nothing exposed to the internet.

## Before writing ANY file

1. **Read `CODING-STANDARDS.md`** — binding, and it prevails over the SPEC on
   conflicts. Above all §2.2: *security code is deterministic and dumb* — no
   heuristics, no retries, no smart recovery in mail routing, the publication
   gate or the budget fuse. Failures stay visible; they are data.
2. Read `docs/SPEC.md` (Italian, immutable founding spec) for intent and
   `docs/GLOSSARY.md` for the untouchable Italian vocabulary: the six agent
   names, `[ART-AAAA-NNN]`, bucket names, status values — never translated.
3. Language split: **English** for code, identifiers, comments, commits, dev
   docs. **Italian** for runtime editorial content: `SOUL.md`, mail templates,
   `docs/RUNBOOK.it.md`, the quality-review CLI prompts.
4. Every source file starts with the standard header (CODING-STANDARDS §1);
   `Created:` is set once, never updated; no version/last-modified lines.

## Hard invariants (never "fix" these away)

- The impaginatore's WordPress user stays **Contributor** — drafts only.
- The delivery matrix lives in `spark-a/mail-server/config/` Postfix maps,
  never in prompts.
- `always_bcc` to the director stays.
- The segreteria container stays on `frontier-net` only, toolset `file` only.
- Image tags stay pinned; `latest` is forbidden.
- No A2A protocols, no message bus, no metrics dashboard, no external sending
  (phase 3 is scaffolding under `spark-a/mail-server/phase3/`, inactive).

## Before declaring any task done

```bash
scripts/check-headers.sh
python3 -m pytest -q          # needs: pip install -r requirements.txt
ruff check . && mypy          # what CI runs, run it locally
```

On the real hardware, `scripts/smoke-test.sh` must pass on every commit to
`main` (SPEC §9 — nine checks, in order). Conventional Commits, English,
imperative; scopes = top-level dirs or service names.
