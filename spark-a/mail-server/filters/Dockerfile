# =============================================================================
#  menabò — an experiment in human-agent newsroom integration
# -----------------------------------------------------------------------------
#  File:     spark-a/mail-server/filters/Dockerfile
#  Purpose:  Image for the after-queue mail filter daemon (smtp_proxy.py).
#            One dependency, no build step: security code stays inspectable.
#  Author:   Gianni Alessandroni
#  Created:  2026-08-16
#  License:  Apache-2.0 — see LICENSE
#  Part of:  menabò https://github.com/GianniAlessandroni/menabo
# =============================================================================

FROM python:3.12.8-slim

# why: single pinned runtime dependency; version matches requirements.txt
RUN pip install --no-cache-dir aiosmtpd==1.4.6

WORKDIR /app
COPY mail_filter.py thread_state.py smtp_proxy.py /app/

# why: state (SQLite counters + hold dir) must survive restarts via a volume
VOLUME ["/var/lib/mail-filter"]

CMD ["python", "/app/smtp_proxy.py"]
