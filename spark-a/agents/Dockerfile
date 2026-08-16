# =============================================================================
#  menabò — an experiment in human-agent newsroom integration
# -----------------------------------------------------------------------------
#  File:     spark-a/agents/Dockerfile
#  Purpose:  Newsroom agent image: official Hermes Agent runtime plus the two
#            CLIs the agents' skills need — himalaya (proactive SMTP) and
#            the AWS CLI (Garage S3 shares, presigned URLs).
#  Author:   Gianni Alessandroni
#  Created:  2026-08-16
#  License:  Apache-2.0 — see LICENSE
#  Part of:  menabò https://github.com/GianniAlessandroni/menabo
# =============================================================================

FROM nousresearch/hermes-agent:v2026.8.13

USER root

# why: awscli talks S3 to Garage; curl/jq serve the SearXNG JSON API and the
# public status file edits. Versions come from the pinned debian 13 base.
RUN apt-get update \
    && apt-get install -y --no-install-recommends awscli curl jq ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# why: the bundled Hermes email skill drives the external himalaya CLI;
# pinned release, aarch64 build (this stack is ARM64-only). Release assets
# use short platform names (himalaya.aarch64-linux.tgz), not target triples.
ARG HIMALAYA_VERSION=v1.1.0
RUN curl -fsSL -o /tmp/himalaya.tgz \
      "https://github.com/pimalaya/himalaya/releases/download/${HIMALAYA_VERSION}/himalaya.aarch64-linux.tgz" \
    && tar -xzf /tmp/himalaya.tgz -C /usr/local/bin himalaya \
    && chmod 0755 /usr/local/bin/himalaya \
    && rm /tmp/himalaya.tgz

# why: the gateway's SMTP STARTTLS verifies certificates, so the internal
# mail CA must live in the system trust store (himalaya reads it too).
# ca.crt is produced by scripts/setup-tls.sh — run it before building.
COPY ca.crt /usr/local/share/ca-certificates/menabo-mail-ca.crt
RUN update-ca-certificates

# hermes runs as UID 10000 (image convention); never run agents as root
USER hermes
