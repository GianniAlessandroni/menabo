#!/usr/bin/env bash
# =============================================================================
#  menabò — an experiment in human-agent newsroom integration
# -----------------------------------------------------------------------------
#  File:     scripts/backup.sh
#  Purpose:  Nightly backup of everything git ignores on purpose: databases,
#            maildirs, filter state, Garage objects, agent homes, public
#            status. Writes a dated directory under backups/.
#  Author:   Gianni Alessandroni
#  Created:  2026-08-16
#  License:  Apache-2.0 — see LICENSE
#  Part of:  menabò https://github.com/GianniAlessandroni/menabo
# =============================================================================
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root/spark-a"
set -a
# shellcheck disable=SC1091
source .env
set +a

stamp="$(date -u +%Y-%m-%dT%H%M%SZ)"
target="$repo_root/backups/$stamp"
mkdir -p "$target"

echo "backup: dumping MariaDB (wordpress + metrics)..."
docker compose exec -T mariadb mariadb-dump -uroot -p"${MARIADB_ROOT_PASSWORD:?}" \
    --databases wordpress metrics | gzip > "$target/mariadb.sql.gz"

echo "backup: archiving maildirs and filter state..."
tar -czf "$target/mail-data.tar.gz" -C mail-server data
tar -czf "$target/mail-filter-state.tar.gz" -C mail-server state 2>/dev/null \
    || echo "backup: no filter state yet, skipped."

echo "backup: archiving Garage buckets (raw meta+data)..."
tar -czf "$target/garage.tar.gz" -C garage meta data 2>/dev/null \
    || echo "backup: no garage data yet, skipped."

echo "backup: archiving agent homes and public status..."
tar -czf "$target/agent-homes.tar.gz" -C agents \
    caporedattore/hermes-home cronista/hermes-home verificatore/hermes-home \
    art-director/hermes-home impaginatore/hermes-home segreteria/hermes-home
cp public-status/articles.json "$target/articles.json"

du -sh "$target"
echo "backup: done -> $target"
