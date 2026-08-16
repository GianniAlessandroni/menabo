#!/usr/bin/env bash
# =============================================================================
#  menabò — an experiment in human-agent newsroom integration
# -----------------------------------------------------------------------------
#  File:     scripts/setup-mailboxes.sh
#  Purpose:  Provision the seven redazione.local mailboxes on the running
#            mailserver. Idempotent: re-running never duplicates accounts.
#  Author:   Gianni Alessandroni
#  Created:  2026-08-16
#  License:  Apache-2.0 — see LICENSE
#  Part of:  menabò https://github.com/GianniAlessandroni/menabo
# =============================================================================
set -euo pipefail

cd "$(git rev-parse --show-toplevel)/spark-a"
if [[ ! -f .env ]]; then
    echo "spark-a/.env not found: copy .env.example and fill in passwords." >&2
    exit 1
fi
set -a
# shellcheck disable=SC1091
source .env
set +a

declare -A ACCOUNTS=(
    ["gianni@redazione.local"]="${MAIL_PASSWORD_GIANNI:?}"
    ["caporedattore@redazione.local"]="${MAIL_PASSWORD_CAPOREDATTORE:?}"
    ["cronista@redazione.local"]="${MAIL_PASSWORD_CRONISTA:?}"
    ["verificatore@redazione.local"]="${MAIL_PASSWORD_VERIFICATORE:?}"
    ["art-director@redazione.local"]="${MAIL_PASSWORD_ART_DIRECTOR:?}"
    ["impaginatore@redazione.local"]="${MAIL_PASSWORD_IMPAGINATORE:?}"
    ["segreteria@redazione.local"]="${MAIL_PASSWORD_SEGRETERIA:?}"
)

existing="$(docker compose exec -T mail-server setup email list 2>/dev/null || true)"

for address in "${!ACCOUNTS[@]}"; do
    if grep -qF "$address" <<< "$existing"; then
        echo "setup-mailboxes: $address already exists, skipped."
    else
        docker compose exec -T mail-server setup email add "$address" "${ACCOUNTS[$address]}"
        echo "setup-mailboxes: $address created."
    fi
done

echo "setup-mailboxes: done (7 accounts ensured)."
