#!/usr/bin/env bash
# =============================================================================
#  menabò — an experiment in human-agent newsroom integration
# -----------------------------------------------------------------------------
#  File:     scripts/setup-tls.sh
#  Purpose:  Generate the internal mail CA and the mail-server certificate.
#            The Hermes email adapter only speaks TLS (IMAP implicit, SMTP
#            STARTTLS with verification), so phase 1-2 needs these after all.
#  Author:   Gianni Alessandroni
#  Created:  2026-08-16
#  License:  Apache-2.0 — see LICENSE
#  Part of:  menabò https://github.com/GianniAlessandroni/menabo
# =============================================================================
set -euo pipefail

cd "$(git rev-parse --show-toplevel)/spark-a"

TLS_DIR=mail-server/tls

# Never overwrite: rotating the CA invalidates the trust baked into the agent
# image; delete $TLS_DIR by hand first if a rotation is really intended.
if [[ -f "$TLS_DIR/ca.crt" ]]; then
    echo "setup-tls: $TLS_DIR/ca.crt already exists, skipped."
else
    mkdir -p "$TLS_DIR"
    openssl req -x509 -newkey rsa:4096 -sha256 -days 3650 -nodes \
        -keyout "$TLS_DIR/ca.key" -out "$TLS_DIR/ca.crt" \
        -subj "/O=menabo/CN=menabo internal mail CA" \
        -addext "basicConstraints=critical,CA:TRUE" \
        -addext "keyUsage=critical,keyCertSign,cRLSign"
    openssl req -newkey rsa:4096 -sha256 -nodes \
        -keyout "$TLS_DIR/mail.key" -out "$TLS_DIR/mail.csr" \
        -subj "/O=menabo/CN=mail.redazione.local"
    # why: SAN carries every name the clients dial — the agents use the
    # compose service name, the director's LAN client the mail hostname.
    openssl x509 -req -sha256 -days 3650 \
        -in "$TLS_DIR/mail.csr" -CA "$TLS_DIR/ca.crt" -CAkey "$TLS_DIR/ca.key" \
        -CAcreateserial -out "$TLS_DIR/mail.crt" \
        -extfile <(printf 'subjectAltName=DNS:mail-server,DNS:mail.redazione.local,DNS:localhost') \
        2>/dev/null
    rm -f "$TLS_DIR/mail.csr" "$TLS_DIR/ca.srl"
    chmod 0600 "$TLS_DIR/ca.key" "$TLS_DIR/mail.key"
    echo "setup-tls: CA and mail-server certificate generated in $TLS_DIR/."
fi

# The agent image bakes the CA into its trust store at build time
# (spark-a/agents/Dockerfile) — keep the build-context copy in sync.
cp "$TLS_DIR/ca.crt" agents/ca.crt
echo "setup-tls: CA copied to agents/ca.crt — rebuild the agent image"
echo "setup-tls: ('docker compose build') if it was already built."
