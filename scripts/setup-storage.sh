#!/usr/bin/env bash
# =============================================================================
#  menabò — an experiment in human-agent newsroom integration
# -----------------------------------------------------------------------------
#  File:     scripts/setup-storage.sh
#  Purpose:  Provision Garage: single-node layout, the four buckets and one
#            least-privilege S3 key per agent. Idempotent; prints new key
#            credentials once (Garage never re-shows secrets).
#  Author:   Gianni Alessandroni
#  Created:  2026-08-16
#  License:  Apache-2.0 — see LICENSE
#  Part of:  menabò https://github.com/GianniAlessandroni/menabo
# =============================================================================
set -euo pipefail

cd "$(git rev-parse --show-toplevel)/spark-a"

garage() { docker compose exec -T garage /garage "$@"; }

# --- layout (first run only) -------------------------------------------------
node_id="$(garage node id -q | cut -d@ -f1)"
if garage layout show | grep -qF "${node_id:0:16}"; then
    echo "setup-storage: layout already assigned, skipped."
else
    garage layout assign -z dc1 -c 50G "$node_id"
    garage layout apply --version 1
    echo "setup-storage: single-node layout applied."
fi

# --- buckets ----------------------------------------------------------------
buckets="$(garage bucket list || true)"
for bucket in piani bozze immagini pubblicati; do
    if grep -qF "$bucket" <<< "$buckets"; then
        echo "setup-storage: bucket $bucket already exists, skipped."
    else
        garage bucket create "$bucket"
        echo "setup-storage: bucket $bucket created."
    fi
done

# --- per-agent keys (least privilege, SPEC §4) ------------------------------
# format: key-name|rw-buckets|ro-buckets
KEY_SPECS=(
    "caporedattore|piani|"
    "cronista|bozze|"
    "verificatore||bozze,immagini,piani"
    "art-director|immagini|"
    "impaginatore||bozze,immagini,piani"
)

keys="$(garage key list || true)"
for spec in "${KEY_SPECS[@]}"; do
    IFS='|' read -r name rw ro <<< "$spec"
    if grep -qF "$name" <<< "$keys"; then
        echo "setup-storage: key $name already exists, skipped (secret shown only at creation)."
    else
        echo "setup-storage: creating key $name — paste these into spark-a/agents/$name/.env:"
        garage key create "$name"
    fi
    IFS=',' read -ra rw_buckets <<< "$rw"
    for bucket in "${rw_buckets[@]:-}"; do
        [[ -n "$bucket" ]] && garage bucket allow --read --write "$bucket" --key "$name"
    done
    IFS=',' read -ra ro_buckets <<< "$ro"
    for bucket in "${ro_buckets[@]:-}"; do
        [[ -n "$bucket" ]] && garage bucket allow --read "$bucket" --key "$name"
    done
done

echo "setup-storage: done (4 buckets, 5 scoped keys ensured)."
