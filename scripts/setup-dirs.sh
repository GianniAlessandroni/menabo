#!/usr/bin/env bash
# =============================================================================
#  menabò — an experiment in human-agent newsroom integration
# -----------------------------------------------------------------------------
#  File:     scripts/setup-dirs.sh
#  Purpose:  Pre-create every bind-mount data directory with the owner the
#            container expects, so non-root containers (agents: uid 10000,
#            WordPress: www-data) can write. Idempotent; run before first up.
#  Author:   Gianni Alessandroni
#  Created:  2026-08-16
#  License:  Apache-2.0 — see LICENSE
#  Part of:  menabò https://github.com/GianniAlessandroni/menabo
# =============================================================================
set -euo pipefail

cd "$(git rev-parse --show-toplevel)/spark-a"

# In-container uids, fixed by the images: hermes-agent runs as 10000
# (spark-a/agents/Dockerfile), wordpress serves as www-data (33).
HERMES_UID=10000
WWW_DATA_UID=33

# why: chown must happen inside the container user namespace so the uid lands
# correctly under rootful AND rootless Docker alike — a host-side chown would
# miss the subuid mapping. The image is valkey, already pinned in
# spark-a/docker-compose.yml (keep the two tags in sync).
CHOWN_IMAGE=valkey/valkey:9.1.1-alpine

AGENTS=(caporedattore cronista verificatore art-director impaginatore segreteria)

chown_in_namespace() { # <uid> <dir relative to spark-a/>
    docker run --rm --user 0 --volume "$PWD/$2:/target" "$CHOWN_IMAGE" \
        chown -R "$1:$1" /target
    echo "setup-dirs: $2 -> uid $1"
}

# Directories whose containers run as root in-container and manage their own
# permissions; pre-created only so 'docker compose up' never invents them.
mkdir -p mail-server/data/mail-data mail-server/data/mail-state \
    mail-server/data/mail-logs mail-server/state \
    mariadb/data garage/meta garage/data wordpress/data

for agent in "${AGENTS[@]}"; do
    mkdir -p "agents/$agent/hermes-home"
    chown_in_namespace "$HERMES_UID" "agents/$agent/hermes-home"
done

# The caporedattore (uid 10000) maintains the public status file; the chown
# must also cover articles.json itself, which is seeded from git.
chown_in_namespace "$HERMES_UID" public-status

chown_in_namespace "$WWW_DATA_UID" wordpress/data

echo "setup-dirs: done."
