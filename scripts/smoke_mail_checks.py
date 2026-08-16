# =============================================================================
#  menabò — an experiment in human-agent newsroom integration
# -----------------------------------------------------------------------------
#  File:     scripts/smoke_mail_checks.py
#  Purpose:  SMTP/IMAP primitives for the smoke test: send (optionally
#            expecting refusal), flood a tag, await or rule out delivery.
#            Stdlib only, so it runs on any host with Python 3.11+.
#  Author:   Gianni Alessandroni
#  Created:  2026-08-16
#  License:  Apache-2.0 — see LICENSE
#  Part of:  menabò https://github.com/GianniAlessandroni/menabo
# =============================================================================
"""CLI used by smoke-test.sh; every subcommand exits 0 on expected behaviour."""

from __future__ import annotations

import argparse
import email
import imaplib
import os
import smtplib
import sys
import time
from email.message import EmailMessage

HOST = os.environ.get("SMOKE_MAIL_HOST", "127.0.0.1")
SMTP_PORT = int(os.environ.get("SMOKE_SMTP_PORT", "587"))
IMAP_PORT = int(os.environ.get("SMOKE_IMAP_PORT", "143"))
HOP_HEADER = "X-Redazione-Hop"


def _build(sender: str, recipient: str, subject: str, body: str) -> EmailMessage:
    message = EmailMessage()
    message["From"] = sender
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body)
    return message


def cmd_send(args: argparse.Namespace) -> int:
    """Send one authenticated message; honour --expect-refused."""
    message = _build(args.mail_from, args.rcpt, args.subject, args.body)
    try:
        with smtplib.SMTP(HOST, SMTP_PORT, timeout=30) as client:
            client.login(args.user, args.password)
            client.send_message(message)
    except smtplib.SMTPRecipientsRefused as refusal:
        if args.expect_refused:
            print(f"OK refused as expected: {refusal.recipients}")
            return 0
        print(f"FAIL unexpected refusal: {refusal.recipients}")
        return 1
    if args.expect_refused:
        print("FAIL delivery was accepted but a refusal was expected")
        return 1
    print(f"OK sent: {args.subject!r} -> {args.rcpt}")
    return 0


def cmd_flood(args: argparse.Namespace) -> int:
    """Send N numbered messages on one connection (budget-fuse test)."""
    with smtplib.SMTP(HOST, SMTP_PORT, timeout=60) as client:
        client.login(args.user, args.password)
        for n in range(1, args.count + 1):
            message = _build(
                args.mail_from, args.rcpt, f"{args.subject} n.{n}", f"messaggio di prova {n}"
            )
            client.send_message(message)
    print(f"OK flooded {args.count} messages with subject base {args.subject!r}")
    return 0


def _search_inbox(
    user: str, password: str, subject_part: str, from_part: str | None, in_body: bool = False
) -> email.message.Message | None:
    # in_body: match subject_part anywhere in the raw message instead of the
    # Subject header — bounces carry the original subject only inside the
    # attached original message ("Undelivered Mail Returned to Sender").
    section = "(BODY.PEEK[])" if in_body else "(BODY.PEEK[HEADER])"
    with imaplib.IMAP4(HOST, IMAP_PORT) as client:
        client.login(user, password)
        client.select("INBOX", readonly=True)
        _, data = client.search(None, "ALL")
        for uid in reversed(data[0].split()):
            _, fetched = client.fetch(uid, section)
            payload = fetched[0]
            if not isinstance(payload, tuple):
                continue
            message = email.message_from_bytes(payload[1])
            if in_body:
                if subject_part not in payload[1].decode("utf-8", errors="replace"):
                    continue
            elif subject_part not in str(message.get("Subject", "")):
                continue
            if from_part and from_part not in str(message.get("From", "")):
                continue
            return message
    return None


def cmd_await(args: argparse.Namespace) -> int:
    """Poll a mailbox until a matching message (dis)appears."""
    deadline = time.monotonic() + args.timeout
    found: email.message.Message | None = None
    while time.monotonic() < deadline:
        found = _search_inbox(
            args.user, args.password, args.subject_contains, args.from_contains, args.in_body
        )
        if found is not None:
            break
        time.sleep(3)
    if args.expect_absent:
        if found is None:
            print(f"OK not delivered (as expected): {args.subject_contains!r}")
            return 0
        print(f"FAIL message was delivered but should not have been: {args.subject_contains!r}")
        return 1
    if found is None:
        print(f"FAIL not found within {args.timeout}s: {args.subject_contains!r}")
        return 1
    if args.expect_hop is not None:
        hop = str(found.get(HOP_HEADER, "missing")).strip()
        if hop != str(args.expect_hop):
            print(f"FAIL {HOP_HEADER}={hop!r}, expected {args.expect_hop}")
            return 1
    print(f"OK found: {args.subject_contains!r}")
    return 0


def main() -> int:
    """Dispatch the requested smoke primitive."""
    parser = argparse.ArgumentParser(description="menabò smoke-test mail primitives")
    subparsers = parser.add_subparsers(dest="command", required=True)

    send = subparsers.add_parser("send")
    send.add_argument("--user", required=True)
    send.add_argument("--password", required=True)
    send.add_argument("--mail-from", required=True)
    send.add_argument("--rcpt", required=True)
    send.add_argument("--subject", required=True)
    send.add_argument("--body", default="messaggio di prova dello smoke test")
    send.add_argument("--expect-refused", action="store_true")
    send.set_defaults(handler=cmd_send)

    flood = subparsers.add_parser("flood")
    flood.add_argument("--user", required=True)
    flood.add_argument("--password", required=True)
    flood.add_argument("--mail-from", required=True)
    flood.add_argument("--rcpt", required=True)
    flood.add_argument("--subject", required=True)
    flood.add_argument("--count", type=int, required=True)
    flood.set_defaults(handler=cmd_flood)

    await_parser = subparsers.add_parser("await")
    await_parser.add_argument("--user", required=True)
    await_parser.add_argument("--password", required=True)
    await_parser.add_argument("--subject-contains", required=True)
    await_parser.add_argument("--from-contains", default=None)
    await_parser.add_argument("--timeout", type=int, default=90)
    await_parser.add_argument("--expect-hop", type=int, default=None)
    await_parser.add_argument("--expect-absent", action="store_true")
    await_parser.add_argument("--in-body", action="store_true")
    await_parser.set_defaults(handler=cmd_await)

    args = parser.parse_args()
    return int(args.handler(args))


if __name__ == "__main__":
    sys.exit(main())
