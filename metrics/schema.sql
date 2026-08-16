-- =============================================================================
--  menabò — an experiment in human-agent newsroom integration
-- -----------------------------------------------------------------------------
--  File:     metrics/schema.sql
--  Purpose:  Schema of the `metrics` database: every table that measures the
--            coordination cost of the email-only newsroom. Applied once at
--            MariaDB first boot; later changes go to metrics/migrations/.
--  Author:   Gianni Alessandroni
--  Created:  2026-08-16
--  License:  Apache-2.0 — see LICENSE
--  Part of:  menabò https://github.com/GianniAlessandroni/menabo
-- =============================================================================

-- Identifiers are English; domain values stay Italian (docs/GLOSSARY.md).
-- All timestamps are UTC, ISO 8601 in transit, DATETIME here, suffix `_at`.

CREATE DATABASE IF NOT EXISTS metrics
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE metrics;

CREATE TABLE IF NOT EXISTS articles (
    tag          VARCHAR(14) NOT NULL PRIMARY KEY
                 COMMENT 'Article tag, canonical form [ART-YYYY-NNN]',
    title        VARCHAR(500) NULL COMMENT 'Working title, from the first subject seen',
    created_at   DATETIME NOT NULL COMMENT 'First message ever seen on this tag (UTC)',
    published_at DATETIME NULL,
    status       ENUM('in_lavorazione', 'in_verifica', 'in_attesa_pubblicazione', 'pubblicato')
                 NOT NULL DEFAULT 'in_lavorazione'
                 COMMENT 'Mirrors spark-a/public-status/articles.json (Italian domain values)'
) COMMENT 'One row per article tag assigned by the caporedattore';

CREATE TABLE IF NOT EXISTS messages (
    id          BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    tag         VARCHAR(14) NULL COMMENT 'NULL for [SERVIZIO] mail',
    sender      VARCHAR(255) NOT NULL,
    recipient   VARCHAR(255) NOT NULL COMMENT 'One row per declared recipient (To/Cc)',
    sent_at     DATETIME NOT NULL,
    hop_count   INT NULL COMMENT 'X-Redazione-Hop as delivered; NULL when header absent',
    size_bytes  INT NOT NULL,
    message_id  VARCHAR(255) NOT NULL,
    in_reply_to VARCHAR(255) NULL,
    UNIQUE KEY uq_messages_msgid_recipient (message_id, recipient),
    KEY idx_messages_tag (tag),
    KEY idx_messages_sent_at (sent_at),
    CONSTRAINT fk_messages_article FOREIGN KEY (tag) REFERENCES articles (tag)
) COMMENT 'Every delivered mail, from the director BCC maildir; dedupe on Message-ID';

CREATE TABLE IF NOT EXISTS director_interventions (
    id          BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    tag         VARCHAR(14) NULL,
    occurred_at DATETIME NOT NULL,
    phase       VARCHAR(50) NOT NULL
                COMMENT 'Article status at intervention time; sconosciuta when unknown',
    UNIQUE KEY uq_interventions_tag_time (tag, occurred_at),
    CONSTRAINT fk_interventions_article FOREIGN KEY (tag) REFERENCES articles (tag)
) COMMENT 'Every mail the director sends into the newsroom';

CREATE TABLE IF NOT EXISTS events (
    id          BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    tag         VARCHAR(14) NULL COMMENT 'NULL when the log line carries no tag',
    occurred_at DATETIME NOT NULL,
    type        ENUM('fusibile', 'bounce_matrice', 'bounce_tag', 'errore_agente') NOT NULL
                COMMENT 'Italian domain values, see docs/GLOSSARY.md',
    detail      TEXT NOT NULL,
    source_ref  VARCHAR(64) NULL COMMENT 'Idempotency key (log-line hash or fuse:tag)',
    UNIQUE KEY uq_events_source_ref (source_ref),
    KEY idx_events_tag (tag),
    CONSTRAINT fk_events_article FOREIGN KEY (tag) REFERENCES articles (tag)
) COMMENT 'Failures are data: bounces, fuses, agent errors';

CREATE TABLE IF NOT EXISTS revisions (
    id           BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    tag          VARCHAR(14) NOT NULL,
    cycle_number INT NOT NULL,
    from_agent   VARCHAR(20) NOT NULL COMMENT 'One of the six Italian agent names',
    to_agent     VARCHAR(20) NOT NULL,
    occurred_at  DATETIME NOT NULL,
    UNIQUE KEY uq_revisions_step (tag, occurred_at, from_agent, to_agent),
    CONSTRAINT fk_revisions_article FOREIGN KEY (tag) REFERENCES articles (tag)
) COMMENT 'Deterministic rule: each verificatore mail on a tag is one review cycle';

CREATE TABLE IF NOT EXISTS token_usage (
    id                BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    tag               VARCHAR(14) NULL
                      COMMENT 'NULL: Hermes session logs attribute per agent/day, not per article',
    agent             VARCHAR(20) NOT NULL,
    used_at           DATETIME NOT NULL COMMENT 'Day granularity (00:00 UTC) for daily rollups',
    prompt_tokens     BIGINT NOT NULL,
    completion_tokens BIGINT NOT NULL,
    source_ref        VARCHAR(64) NULL COMMENT 'Idempotency key, e.g. agent:YYYY-MM-DD',
    UNIQUE KEY uq_token_usage_source_ref (source_ref),
    CONSTRAINT fk_token_usage_article FOREIGN KEY (tag) REFERENCES articles (tag)
) COMMENT 'From Hermes session logs; re-collected totals overwrite the same day';

CREATE TABLE IF NOT EXISTS quality_reviews (
    tag                    VARCHAR(14) NOT NULL PRIMARY KEY,
    reviewed_at            DATETIME NOT NULL,
    quality_score          TINYINT NOT NULL COMMENT '1 (poor) to 5 (excellent)',
    editing                ENUM('leggero', 'sostanziale', 'riscrittura') NOT NULL,
    diff_percent           DECIMAL(5, 2) NOT NULL
                           COMMENT 'Changed lines draft -> final, 0-100',
    misunderstandings_count INT NOT NULL,
    readability_score      TINYINT NOT NULL COMMENT '1 to 5',
    phone_call_needed      BOOLEAN NOT NULL
                           COMMENT 'Would a phone call have avoided the email back-and-forth?',
    notes                  TEXT NULL,
    CONSTRAINT fk_quality_reviews_article FOREIGN KEY (tag) REFERENCES articles (tag)
) COMMENT 'Compiled by the director via metrics/quality_review.py before publishing';
