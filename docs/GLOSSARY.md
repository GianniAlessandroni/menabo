<!-- =============================================================================
  menabò — an experiment in human-agent newsroom integration
 ------------------------------------------------------------------------------
  File:     docs/GLOSSARY.md
  Purpose:  Map the Italian domain vocabulary (ubiquitous language) to English
            explanations. These terms are never translated in code or data.
  Author:   Gianni Alessandroni
  Created:  2026-08-16
  License:  Apache-2.0 — see LICENSE
  Part of:  menabò https://github.com/GianniAlessandroni/menabo
============================================================================== -->

# Glossary

The project's ubiquitous language is Italian. The terms below are **never
translated** — not in code, not in the database, not in documentation
(see CODING-STANDARDS.md §0). Everything else in code is English.

## The project name

| Term | Meaning |
|---|---|
| **menabò** | Italian typographic term: the page-by-page layout dummy of a magazine issue. The project produces an online magazine, so the repo is its menabò. |
| **redazione** | "Newsroom / editorial staff". The mail domain is `redazione.local`. |

## The six agents

Each agent is one Docker container, one Hermes profile, one mailbox
`<name>@redazione.local`, one folder under `spark-a/agents/`.

| Agent | English gloss | Role |
|---|---|---|
| **caporedattore** | editor-in-chief's deputy / managing editor | Coordinates all work, assigns article tags, only agent allowed to email the director, maintains the public status file. |
| **cronista** | reporter | Researches (SearXNG + fetch) and writes drafts to the `bozze` bucket; shares presigned URLs, never full text in mail. |
| **verificatore** | fact-checker | Verifies drafts against sources; treats external text as quotable material, never as instructions. |
| **art-director** | art director | Generates illustrations via ComfyUI (MCP). Absolute ban on depicting real people. |
| **impaginatore** | layout editor | Creates the WordPress draft (Contributor role — cannot publish) and stops. |
| **segreteria** | front office / secretariat | Trust boundary. Email only, separate Docker network, closed response repertoire, reads only the public status file. |

## Other untouchable terms

| Term | Meaning |
|---|---|
| `[ART-AAAA-NNN]` | Article tag: `ART`, four-digit year, three-digit serial (e.g. `[ART-2026-001]`). Required in every mail subject. In code the format is written `[ART-YYYY-NNN]`; the literal prefix `ART` and the shape never change. |
| `[SERVIZIO]` | "Service" subject flag: marks organisational mail that belongs to no article; exempt from the tag requirement. |
| `X-Redazione-Hop` | Mail header incremented by the filter on every pass; measures forwarding chains. |
| `gianni@redazione.local` | The human editor-in-chief (the director). Receives a structural BCC of all delivered mail. |
| `piani`, `bozze`, `immagini`, `pubblicati` | Garage S3 buckets: plans, drafts, images, published pieces. |

## Italian domain values in English schemas

Identifiers (tables, columns, functions) are English; *values* stay Italian:

- Article status: `in_lavorazione`, `in_verifica`, `in_attesa_pubblicazione`,
  `pubblicato` — used in `articles.status` and in
  `spark-a/public-status/articles.json`.
- Event types (`events.type`): `fusibile` (message-budget fuse tripped),
  `bounce_matrice` (delivery-matrix violation), `bounce_tag` (missing article
  tag), `errore_agente` (agent runtime error).
- Editing effort (`quality_reviews.editing`): `leggero`, `sostanziale`,
  `riscrittura`.
- Agent name values: always one of the six names above
  (e.g. `token_usage.agent = 'caporedattore'`).
