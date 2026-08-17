#!/usr/bin/env bash
# =============================================================================
#  menabò — an experiment in human-agent newsroom integration
# -----------------------------------------------------------------------------
#  File:     scripts/setup-env.sh
#  Purpose:  Generate the environment files: first run creates spark-a/.env
#            with random secrets (hosts left for the operator), second run
#            renders the six agent .env files from it. Never overwrites.
#  Author:   Gianni Alessandroni
#  Created:  2026-08-16
#  License:  Apache-2.0 — see LICENSE
#  Part of:  menabò https://github.com/GianniAlessandroni/menabo
# =============================================================================
set -euo pipefail

cd "$(git rev-parse --show-toplevel)/spark-a"

AGENTS=(caporedattore cronista verificatore art-director impaginatore segreteria)

random_secret() { openssl rand -hex 16; }

if [[ ! -f .env ]]; then
    cp .env.example .env
    sed -i \
        -e "s|^MAIL_PASSWORD_GIANNI=.*|MAIL_PASSWORD_GIANNI=$(random_secret)|" \
        -e "s|^MAIL_PASSWORD_CAPOREDATTORE=.*|MAIL_PASSWORD_CAPOREDATTORE=$(random_secret)|" \
        -e "s|^MAIL_PASSWORD_CRONISTA=.*|MAIL_PASSWORD_CRONISTA=$(random_secret)|" \
        -e "s|^MAIL_PASSWORD_VERIFICATORE=.*|MAIL_PASSWORD_VERIFICATORE=$(random_secret)|" \
        -e "s|^MAIL_PASSWORD_ART_DIRECTOR=.*|MAIL_PASSWORD_ART_DIRECTOR=$(random_secret)|" \
        -e "s|^MAIL_PASSWORD_IMPAGINATORE=.*|MAIL_PASSWORD_IMPAGINATORE=$(random_secret)|" \
        -e "s|^MAIL_PASSWORD_SEGRETERIA=.*|MAIL_PASSWORD_SEGRETERIA=$(random_secret)|" \
        -e "s|^MARIADB_ROOT_PASSWORD=.*|MARIADB_ROOT_PASSWORD=$(random_secret)|" \
        -e "s|^WORDPRESS_DB_PASSWORD=.*|WORDPRESS_DB_PASSWORD=$(random_secret)|" \
        -e "s|^METRICS_DB_PASSWORD=.*|METRICS_DB_PASSWORD=$(random_secret)|" \
        -e "s|^WORDPRESS_ADMIN_PASSWORD=.*|WORDPRESS_ADMIN_PASSWORD=$(random_secret)|" \
        -e "s|^GARAGE_RPC_SECRET=.*|GARAGE_RPC_SECRET=$(openssl rand -hex 32)|" \
        -e "s|^SEARXNG_SECRET=.*|SEARXNG_SECRET=$(openssl rand -hex 32)|" \
        .env
    echo "setup-env: spark-a/.env created with generated secrets."
    echo "setup-env: NOW EDIT these host values in spark-a/.env:"
    echo "  - SPARK_B_HOST     (LAN IP of node B)"
    echo "  - STAGING_URL      (how you reach the preview, e.g. http://<spark-a-ip>:8080)"
    echo "  - VLLM_CACHE_ROOT  (model cache directory on this host)"
    echo "then re-run this script to generate the agent .env files."
    exit 0
fi

set -a
# shellcheck disable=SC1091
source .env
set +a

created=0
for agent in "${AGENTS[@]}"; do
    env_file="agents/$agent/.env"
    if [[ -f "$env_file" ]]; then
        echo "setup-env: $env_file already exists, skipped."
        continue
    fi
    var="MAIL_PASSWORD_$(tr '[:lower:]-' '[:upper:]_' <<< "$agent")"
    password="${!var:?missing $var in spark-a/.env}"
    # why: 192.168.1.102 is the node-B placeholder used in every .env.example
    sed -e "s|^EMAIL_PASSWORD=.*|EMAIL_PASSWORD=${password}|" \
        -e "s|192\.168\.1\.102|${SPARK_B_HOST:?}|g" \
        "agents/$agent/.env.example" > "$env_file"
    created=$((created + 1))
    echo "setup-env: $env_file generated (mail password and node-B host set)."
done

# himalaya cannot read EMAIL_PASSWORD from the environment: the Hermes
# terminal tool strips gateway credentials from every subprocess it spawns.
# Project the mail password into a per-agent file instead (mounted read-only
# at /opt/data/.config/himalaya/password; himalaya.toml `cat`s it). Derived
# data, rewritten on every run so it always matches spark-a/.env. The
# segreteria is skipped: no terminal, no proactive channel (SPEC §2.4).
for agent in caporedattore cronista verificatore art-director impaginatore; do
    var="MAIL_PASSWORD_$(tr '[:lower:]-' '[:upper:]_' <<< "$agent")"
    printf '%s\n' "${!var:?missing $var in spark-a/.env}" > "agents/$agent/himalaya-password"
    # why: the agent container reads this as uid 10000 (hermes)
    chmod 0644 "agents/$agent/himalaya-password"
done
echo "setup-env: himalaya password files projected from spark-a/.env."

echo "setup-env: done ($created file(s) generated)."
echo "setup-env: S3 keys are filled in by setup-storage.sh, the WordPress MCP"
echo "setup-env: auth by setup-wordpress.sh — run them after 'docker compose up'."
