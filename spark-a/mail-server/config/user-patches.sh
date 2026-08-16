#!/usr/bin/env bash
# =============================================================================
#  menabò — an experiment in human-agent newsroom integration
# -----------------------------------------------------------------------------
#  File:     spark-a/mail-server/config/user-patches.sh
#  Purpose:  docker-mailserver hook (runs before daemons start): add the
#            re-injection listener the content filter delivers back to.
#  Author:   Gianni Alessandroni
#  Created:  2026-08-16
#  License:  Apache-2.0 — see LICENSE
#  Part of:  menabò https://github.com/GianniAlessandroni/menabo
# =============================================================================
set -euo pipefail

# Re-injection listener on 10026: only the mail-filter container (static IP
# 172.28.0.7) may use it, with no content_filter (no loop) and no sender
# checks (filtered mail re-enters with agent senders, unauthenticated).
postconf -M "10026/inet=10026 inet n - n - - smtpd"
postconf -P "10026/inet/content_filter="
postconf -P "10026/inet/smtpd_sender_restrictions="
postconf -P "10026/inet/smtpd_recipient_restrictions=permit_mynetworks,reject"
postconf -P "10026/inet/smtpd_relay_restrictions=permit_mynetworks,reject"
postconf -P "10026/inet/mynetworks=172.28.0.7/32"
# why: dual-mode submission (see RUNBOOK §7) — STARTTLS offered for the
# Hermes gateway and himalaya, cleartext AUTH still accepted on the isolated
# network for the director's client and the smoke test. DMS would otherwise
# demand TLS before AUTH on 587 as soon as SSL_TYPE is set.
postconf -P "submission/inet/smtpd_tls_security_level=may"
postconf -P "submission/inet/smtpd_tls_auth_only=no"

echo "user-patches.sh: re-injection listener on 10026 configured."
