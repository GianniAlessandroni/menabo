<!-- =============================================================================
  menabò — an experiment in human-agent newsroom integration
 ------------------------------------------------------------------------------
  File:     CODING-STANDARDS.md
  Purpose:  Binding coding standards for every contributor, human or AI.
            Prevails over docs/SPEC.md wherever the two conflict.
  Author:   Gianni Alessandroni
  Created:  2026-08-16
  License:  Apache-2.0 — see LICENSE
  Part of:  menabò https://github.com/GianniAlessandroni/menabo
============================================================================== -->

# Coding Standards

> This document defines how code is written in this project. It is binding for
> every contributor, human or AI. Claude Code: read this before writing any file,
> and re-read it at the start of every session (it is referenced from `CLAUDE.md`).

## 0. Language policy

This project has two audiences: an international open-source audience and an
Italian-speaking newsroom of agents. The split is strict:

- **English**: all code — file names, identifiers, comments, docstrings, commit
  messages, log messages, test names — plus `README.md`, this document, and all
  developer-facing documentation.
- **Italian**: all *runtime editorial content* — agent role prompts (`SOUL.md`),
  email templates the agents exchange, WordPress content, the qualitative review
  CLI prompts shown to the editor-in-chief, and `docs/RUNBOOK.it.md`.
- **Domain vocabulary exception**: the six agent names (`caporedattore`,
  `cronista`, `verificatore`, `art-director`, `impaginatore`, `segreteria`) and
  the article tag format `[ART-YYYY-NNN]` are the project's ubiquitous language.
  They are NEVER translated — not in code, not in the database, not in docs.
  `docs/GLOSSARY.md` maps each term to an English explanation. A function is
  therefore named `route_mail_from_caporedattore()`, not
  `route_mail_from_editor_in_chief()`.

## 1. The file header

Every source file starts with this header, adapted to the comment syntax of its
language. It is not decoration: it states what the file is for without opening
it in an editor, and it carries the license.

Python / Bash / YAML / TOML / SQL (`#` or `--` comments):

```
# =============================================================================
#  <PROJECT NAME> — an experiment in human-agent newsroom integration
# -----------------------------------------------------------------------------
#  File:     metrics/collector.py
#  Purpose:  Nightly collector: Postfix logs + BCC maildir -> MariaDB metrics.
#            Idempotent on Message-ID; safe to re-run.
#  Author:   Gianni Alessandroni
#  Created:  2026-08-XX
#  License:  <SPDX id> — see LICENSE
#  Part of:  <PROJECT NAME> <repository URL>
# =============================================================================
```

Rules:
- `Purpose` is one to three lines, written for a stranger, stating *why the file
  exists* — not a paraphrase of the filename.
- `Created` is set once and never updated. There is **no** `Last modified` line
  and **no** version line: git owns history, and hand-maintained modification
  dates always end up lying.
- Markdown files use an HTML comment (`<!-- ... -->`) with the same fields.
  Dockerfiles and `.env.example` use the `#` form.
- Generated files (if any) get an extra line: `Generated: do not edit by hand
  (source: <path>)`.
- `scripts/check-headers.sh` verifies presence and shape of the header in every
  tracked source file and runs in the test suite. A file without a header fails CI.

## 2. General principles

1. **Boring and readable beats clever.** This repo will be read by people
   studying the experiment, not just running it.
2. **Security code is deterministic and dumb.** Mail routing rules, the
   publication gate, budget fuses: no heuristics, no retries, no "smart"
   recovery. Failures must remain visible — they are data.
3. **Small files, single purpose.** If a module needs a plural in its Purpose
   line ("parses logs AND sends notifications"), split it.
4. **No dead code, no commented-out code, no TODO without an issue reference.**
5. **Comments explain *why*, never *what*.** The code says what. A comment that
   paraphrases the next line gets deleted in review.

## 3. Naming

| Thing | Convention | Example |
|---|---|---|
| Python modules/packages | `snake_case.py`, short nouns | `collector.py`, `mail_filter.py` |
| Python functions | `snake_case`, verb first | `parse_postfix_line()`, `freeze_thread()` |
| Python classes | `PascalCase`, noun | `ArticleThread`, `DeliveryMatrix` |
| Constants | `UPPER_SNAKE` | `MESSAGE_BUDGET_PER_ARTICLE` |
| Shell scripts | `kebab-case.sh`, verb first | `setup-mailboxes.sh`, `check-headers.sh` |
| Docker services | `kebab-case` | `vllm-writer`, `mail-server` |
| Docker networks/volumes | `kebab-case`, prefixed | `newsroom-net`, `frontier-net` |
| Env variables | `UPPER_SNAKE`, prefixed | `NEWSROOM_MESSAGE_BUDGET` |
| MariaDB tables | `snake_case`, plural English | `messages`, `articles`, `quality_reviews` |
| MariaDB columns | `snake_case`, no table prefix | `sender`, `hop_count`, `created_at` |
| Git branches | `type/short-topic` | `feat/mail-filter-budget` |
| Directories | `kebab-case` | `spark-a/`, `mail-server/` |

Agent names (domain vocabulary) stay Italian even inside English identifiers:
`SEGRETERIA_ALLOWED_SENDERS`, `table agents(name='caporedattore')`.

Timestamps: UTC in storage, ISO 8601 everywhere, column suffix `_at`.

## 4. Python

- Python 3.11+. Full type hints on every public function; `mypy --strict` clean.
- Format and lint with `ruff` (line length 100); no other formatter.
- Docstrings: Google style, one-line summary first, in English.
- `logging` module only — never `print()` outside CLI entry points.
- No bare `except:` and no `except Exception: pass`. Every caught exception is
  either handled meaningfully or re-raised with context.
- Dependencies pinned in `requirements.txt` (exact `==`); standard library
  preferred whenever reasonable.
- Tests: `pytest`, files `test_<module>.py`, test names describe behaviour:
  `test_mail_without_tag_is_bounced_with_reason()`. The mail filter and the
  collector must be testable without a running mailserver (parse functions take
  strings/paths, not sockets).

## 5. Bash

- `#!/usr/bin/env bash` + `set -euo pipefail` in every script, right after the
  header. `shellcheck` clean.
- Scripts are idempotent where meaningful (`setup-mailboxes.sh` re-run must not
  duplicate accounts) and say what they did on stdout.
- Anything longer than ~80 lines or needing data structures becomes Python.

## 6. Docker & configuration

- Image tags are always pinned to a specific version. `latest` is forbidden —
  in compose files, Dockerfiles and documentation examples alike.
- Every non-obvious compose line carries a `# why:` comment
  (e.g. `# why: GB10 unified memory races on concurrent vLLM startup`).
- Secrets never enter the repo: `.env.example` documents every variable with a
  fake value and a one-line English comment; `.env` is gitignored. The
  `check-headers.sh` run also greps staged files for obvious secret patterns.
- One compose file per node (`spark-a/`, `spark-b/`); no compose overrides
  unless the RUNBOOK documents why.

## 7. SQL

- Schema lives in `metrics/schema.sql`, plain SQL, no ORM.
- Schema changes are additive migration files `metrics/migrations/NNN_verb_noun.sql`
  once the schema is first deployed; never edit `schema.sql` retroactively after
  deployment — regenerate it only as documentation.
- Every table and non-obvious column gets a `COMMENT`.
- Only the metrics collector user has write access; agents have no DB
  credentials at all (enforced by grants, not convention).

## 8. Git

- Conventional Commits, English, imperative: `feat(mail-filter): freeze thread
  over message budget`, `fix(collector): dedupe on Message-ID`, `docs(runbook): ...`.
- Scopes match top-level directories or service names.
- One logical change per commit; the smoke test must pass on every commit to `main`.
- No force-push on `main`. Experiment data (maildirs, DB dumps, logs) never
  enters git — gitignored, backed up by `scripts/backup.sh`.

## 9. Documentation files

- `README.md` (English): what the project is, the research question, an
  architecture diagram, quickstart, link to the SPEC and to this file.
- `docs/SPEC.md` (Italian, historical): the founding specification, immutable.
- `docs/RUNBOOK.it.md` (Italian): operations for the editor-in-chief.
- `docs/GLOSSARY.md` (English): the Italian domain vocabulary, explained.
- `CLAUDE.md`: short operating instructions for Claude Code — read SPEC and this
  file, respect §2.2 of this document above all, run `scripts/check-headers.sh`
  and the test suite before declaring any task done.

## 10. Licensing note

The repository will be published under a single OSI-approved license APACHE-2.0. 
The SPDX identifier in
every file header must match `LICENSE`. Third-party licenses (AGPL components
like Garage and SearXNG run as unmodified services in containers) are listed in
`docs/THIRD-PARTY.md`.

Website of the project is https://github.com/GianniAlessandroni/menabo

