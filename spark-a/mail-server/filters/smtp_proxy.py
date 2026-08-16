# =============================================================================
#  menabò — an experiment in human-agent newsroom integration
# -----------------------------------------------------------------------------
#  File:     spark-a/mail-server/filters/smtp_proxy.py
#  Purpose:  After-queue content filter daemon: receives every message Postfix
#            queues, applies mail_filter rules, and either re-injects, bounces,
#            or freezes the thread and notifies the director.
#  Author:   Gianni Alessandroni
#  Created:  2026-08-16
#  License:  Apache-2.0 — see LICENSE
#  Part of:  menabò https://github.com/GianniAlessandroni/menabo
# =============================================================================
"""SMTP proxy glueing the pure filter rules to Postfix.

Flow: Postfix ``content_filter`` -> this daemon (port 10025) -> re-injection
into Postfix (port 10026, no filter, BCC applied there). Rejections happen at
end-of-DATA, so Postfix bounces to the sender with our reason. Frozen threads
are accepted, stored under the hold directory, and never delivered — going
silent is the point of the fuse; the director gets one summary mail per tag.
"""

from __future__ import annotations

import asyncio
import logging
import os
import smtplib
from datetime import UTC, datetime
from email import message_from_bytes
from email.message import EmailMessage, Message
from pathlib import Path
from typing import Any

from aiosmtpd.controller import Controller
from aiosmtpd.smtp import SMTP, Envelope, Session
from mail_filter import (
    REJECT_REASON_NO_TAG,
    Verdict,
    evaluate_subject,
    extract_tag,
    increment_hop,
)
from thread_state import ThreadEntry, ThreadState

LOG = logging.getLogger("mail-filter")


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


class FilterConfig:
    """Runtime configuration, read once from the environment."""

    def __init__(self) -> None:
        self.budget = int(_env("NEWSROOM_MESSAGE_BUDGET", "60"))
        self.listen_host = _env("NEWSROOM_FILTER_LISTEN_HOST", "0.0.0.0")
        self.listen_port = int(_env("NEWSROOM_FILTER_LISTEN_PORT", "10025"))
        self.reinject_host = _env("NEWSROOM_REINJECT_HOST", "mail-server")
        self.reinject_port = int(_env("NEWSROOM_REINJECT_PORT", "10026"))
        self.state_dir = Path(_env("NEWSROOM_FILTER_STATE_DIR", "/var/lib/mail-filter"))
        self.director_address = _env("NEWSROOM_DIRECTOR_ADDRESS", "gianni@redazione.local")
        self.notifier_address = _env("NEWSROOM_FILTER_ADDRESS", "postmaster@redazione.local")


def build_freeze_notification(
    tag: str, entries: list[ThreadEntry], budget: int, sender: str, director: str
) -> EmailMessage:
    """Build the Italian director notification for a frozen thread."""
    lines = [
        f"Il thread {tag} ha superato il budget di {budget} messaggi ed e' stato congelato.",
        "Nessun altro messaggio su questo tag verra' consegnato finche' non intervieni.",
        "I messaggi trattenuti sono nella cartella hold del filtro.",
        "",
        f"Ultimi messaggi del thread {tag}:",
    ]
    lines.extend(
        f"- {entry.received_at} | {entry.sender} -> {entry.recipients} | {entry.subject}"
        for entry in entries
    )
    notification = EmailMessage()
    notification["From"] = sender
    notification["To"] = director
    notification["Subject"] = f"[SERVIZIO] Fusibile scattato: thread {tag} congelato"
    notification.set_content("\n".join(lines))
    return notification


class FilterHandler:
    """aiosmtpd handler applying the newsroom rules to each message."""

    def __init__(self, config: FilterConfig, state: ThreadState) -> None:
        self._config = config
        self._state = state
        self._hold_dir = config.state_dir / "hold"
        self._hold_dir.mkdir(parents=True, exist_ok=True)
        self._hold_counter = 0

    async def handle_DATA(  # noqa: N802 (aiosmtpd contract)
        self, server: SMTP, session: Session, envelope: Envelope
    ) -> str:
        content = envelope.original_content or b""
        message = message_from_bytes(content)
        subject = str(message.get("Subject", ""))
        sender = envelope.mail_from or ""
        recipients = list(envelope.rcpt_tos)

        tag = extract_tag(subject)
        count = self._state.message_count(tag) if tag else 0
        verdict = evaluate_subject(subject, count, self._config.budget)

        if verdict is Verdict.REJECT_NO_TAG:
            LOG.info("reject (no tag): from=%s to=%s subject=%r", sender, recipients, subject)
            return f"550 {REJECT_REASON_NO_TAG}"

        now = datetime.now(tz=UTC).isoformat()
        if tag is not None and self._state.is_frozen(tag):
            self._hold(message, tag)
            LOG.info("hold (frozen thread %s): from=%s to=%s", tag, sender, recipients)
            return "250 Message held (thread frozen)"

        if verdict is Verdict.FREEZE:
            assert tag is not None  # FREEZE only exists for tagged mail
            self._hold(message, tag)
            if self._state.freeze(tag, now):
                self._notify_director(tag)
            LOG.warning("fuse tripped: tag=%s frozen at %s messages", tag, count)
            return "250 Message held (budget exceeded, thread frozen)"

        hop = increment_hop(message)
        if tag is not None:
            self._state.record_message(tag, sender, ", ".join(recipients), subject, now)
        self._reinject(sender, recipients, message)
        LOG.info("accept: tag=%s hop=%d from=%s to=%s", tag, hop, sender, recipients)
        return "250 OK"

    def _hold(self, message: Message, tag: str) -> None:
        tag_dir = self._hold_dir / tag.strip("[]")
        tag_dir.mkdir(parents=True, exist_ok=True)
        self._hold_counter += 1
        stamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%S")
        (tag_dir / f"{stamp}-{self._hold_counter:04d}.eml").write_bytes(message.as_bytes())

    def _reinject(self, sender: str, recipients: list[str], message: Message) -> None:
        with smtplib.SMTP(self._config.reinject_host, self._config.reinject_port) as client:
            client.send_message(message, from_addr=sender, to_addrs=recipients)

    def _notify_director(self, tag: str) -> None:
        notification = build_freeze_notification(
            tag,
            self._state.thread_summary(tag),
            self._config.budget,
            self._config.notifier_address,
            self._config.director_address,
        )
        self._reinject(
            self._config.notifier_address, [self._config.director_address], notification
        )


def main() -> None:
    """Run the filter daemon until terminated."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    config = FilterConfig()
    state = ThreadState(config.state_dir / "state.db")
    controller: Any = Controller(
        FilterHandler(config, state), hostname=config.listen_host, port=config.listen_port
    )
    controller.start()
    LOG.info(
        "mail filter listening on %s:%d (budget=%d, reinject=%s:%d)",
        config.listen_host,
        config.listen_port,
        config.budget,
        config.reinject_host,
        config.reinject_port,
    )
    try:
        asyncio.get_event_loop().run_forever()
    except KeyboardInterrupt:
        controller.stop()
        state.close()


if __name__ == "__main__":
    main()
