#!/usr/bin/env bash
# =============================================================================
#  menabò — an experiment in human-agent newsroom integration
# -----------------------------------------------------------------------------
#  File:     scripts/smoke-test.sh
#  Purpose:  End-to-end proof of the running system, in the SPEC §9 order.
#            Orchestration only: mail logic lives in smoke_mail_checks.py.
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
cd "$repo_root"

PY=python3
MAIL="$PY scripts/smoke_mail_checks.py"
export SMOKE_MAIL_HOST="${SMOKE_MAIL_HOST:-127.0.0.1}"
compose() { docker compose -f spark-a/docker-compose.yml "$@"; }

step() { echo; echo "=== SMOKE $1 ==="; }

# Wait until the filter has counted <n> accepted messages for <tag>. A flood
# returns when submission has QUEUED the mail, not when the filter has seen
# it: without this barrier the boundary message can overtake part of the
# flood and meet a counter below the fuse threshold.
await_filter_count() { # <tag> <n>
    for _ in $(seq 1 60); do
        got="$(compose exec -T mail-filter python3 -c "import sqlite3
print(sqlite3.connect('/var/lib/mail-filter/state.db').execute(
    'SELECT COUNT(*) FROM thread_messages WHERE tag = ?', ('$1',)).fetchone()[0])")"
        if [ "$got" -ge "$2" ]; then
            echo "OK filter counted $got/$2 messages for $1"
            return 0
        fi
        sleep 2
    done
    echo "FAIL filter stuck at $got/$2 messages for $1"
    return 1
}

step "0/9 repo hygiene (headers)"
scripts/check-headers.sh

step "1/9 vLLM endpoints answer"
curl -fsS "http://127.0.0.1:8000/v1/models" >/dev/null && echo "OK writer (node A)"
curl -fsS "http://${SPARK_B_HOST:?}:8000/v1/models" >/dev/null && echo "OK verifier (node B)"

# --- per-run isolation ------------------------------------------------------
# Now that the agents are live they answer smoke mail, and every reply keeps
# the tag in the subject: fixed tags accumulated fuse counters across runs
# until the thread froze and check 2 could never pass again. Three measures:
#   1. unique tags per run (years 2090-2099 = smoke namespace, never real
#      articles), so filter notifications and awaited subjects are unique too;
#   2. leftover smoke state wiped, so the serial wrap (~3 days) stays safe;
#   3. agents stopped for the mail checks 2-5 (exact fuse arithmetic needs a
#      quiet line) and restarted before 6-8, which exec into them. On restart
#      the adapter re-baselines the mailbox, so smoke mail is never answered.
serial=$(( $(date +%s) / 60 % 4500 ))
TAG="[ART-$((2090 + serial / 450))-$((100 + serial % 450))]"
TAG2="[ART-$((2090 + serial / 450))-$((550 + serial % 450))]"
NONCE="$(date +%s)"
AGENTS="caporedattore cronista verificatore art-director impaginatore segreteria"

step "prep: quiet agents, clean smoke residue"
# shellcheck disable=SC2064  # why: expand $AGENTS now, it never changes
trap "compose start $AGENTS >/dev/null" EXIT
compose stop $AGENTS
compose exec -T mail-filter python3 - <<'PYEOF'
from pathlib import Path
import shutil
import sqlite3

db = sqlite3.connect("/var/lib/mail-filter/state.db")
for table in ("thread_messages", "frozen_threads", "warned_threads"):
    db.execute(f"DELETE FROM {table} WHERE tag LIKE '[ART-209%'")  # noqa: S608
db.commit()
for tag_dir in Path("/var/lib/mail-filter/hold").glob("ART-209*"):
    shutil.rmtree(tag_dir)
print("OK smoke tags wiped from filter state and hold dir")
PYEOF

step "2/9 tagged mail cronista -> verificatore: delivered, BCC'd, hop set"
$MAIL send --user cronista@redazione.local --password "$MAIL_PASSWORD_CRONISTA" \
    --mail-from cronista@redazione.local --rcpt verificatore@redazione.local \
    --subject "$TAG prova di consegna"
$MAIL await --user verificatore@redazione.local --password "$MAIL_PASSWORD_VERIFICATORE" \
    --subject-contains "$TAG prova di consegna" --expect-hop 0
$MAIL await --user gianni@redazione.local --password "$MAIL_PASSWORD_GIANNI" \
    --subject-contains "$TAG prova di consegna" --expect-hop 0
echo "OK structural BCC reached the director"

step "3/9 cronista -> director bounces (delivery matrix)"
$MAIL send --user cronista@redazione.local --password "$MAIL_PASSWORD_CRONISTA" \
    --mail-from cronista@redazione.local --rcpt gianni@redazione.local \
    --subject "$TAG tentativo fuori matrice" --expect-refused

step "4/9 mail without tag bounces with a readable reason"
$MAIL send --user cronista@redazione.local --password "$MAIL_PASSWORD_CRONISTA" \
    --mail-from cronista@redazione.local --rcpt verificatore@redazione.local \
    --subject "prova senza etichetta $NONCE"
# why: the bounce's own subject is "Undelivered Mail Returned to Sender";
# the nonce only appears in the attached original, hence --in-body.
$MAIL await --user cronista@redazione.local --password "$MAIL_PASSWORD_CRONISTA" \
    --subject-contains "prova senza etichetta $NONCE" --from-contains "MAILER-DAEMON" \
    --in-body --timeout 120
echo "OK bounce with reason came back to the sender"

step "5/9 two-stage budget fuse: warning at 60, freeze past the 50% grace margin"
$MAIL flood --user cronista@redazione.local --password "$MAIL_PASSWORD_CRONISTA" \
    --mail-from cronista@redazione.local --rcpt verificatore@redazione.local \
    --subject "$TAG2 riempimento budget" --count 60
await_filter_count "$TAG2" 60
$MAIL send --user cronista@redazione.local --password "$MAIL_PASSWORD_CRONISTA" \
    --mail-from cronista@redazione.local --rcpt verificatore@redazione.local \
    --subject "$TAG2 messaggio in zona di grazia"
$MAIL await --user caporedattore@redazione.local --password "$MAIL_PASSWORD_CAPOREDATTORE" \
    --subject-contains "thread $TAG2 in margine di grazia" --timeout 120
$MAIL await --user verificatore@redazione.local --password "$MAIL_PASSWORD_VERIFICATORE" \
    --subject-contains "messaggio in zona di grazia" --timeout 60
echo "OK stage 1: caporedattore warned, grace-zone mail still delivered"
$MAIL flood --user cronista@redazione.local --password "$MAIL_PASSWORD_CRONISTA" \
    --mail-from cronista@redazione.local --rcpt verificatore@redazione.local \
    --subject "$TAG2 riempimento margine" --count 29
await_filter_count "$TAG2" 90
$MAIL send --user cronista@redazione.local --password "$MAIL_PASSWORD_CRONISTA" \
    --mail-from cronista@redazione.local --rcpt verificatore@redazione.local \
    --subject "$TAG2 messaggio oltre margine"
$MAIL await --user gianni@redazione.local --password "$MAIL_PASSWORD_GIANNI" \
    --subject-contains "Fusibile scattato: thread $TAG2" --timeout 180
$MAIL await --user verificatore@redazione.local --password "$MAIL_PASSWORD_VERIFICATORE" \
    --subject-contains "messaggio oltre margine" --expect-absent --timeout 20
echo "OK stage 2: 91st message held, director notified"

step "agents back online (checks 6-8 exec into them)"
compose start $AGENTS

step "6/9 Garage upload + working presigned URL (from the cronista container)"
# shellcheck disable=SC2016  # why: variables must expand inside the container
compose exec -T cronista bash -c '
    set -e
    echo "contenuto di prova" > /tmp/smoke.txt
    aws --endpoint-url "$AWS_ENDPOINT_URL" s3 cp /tmp/smoke.txt "s3://bozze/smoke/smoke.txt"
    url="$(aws --endpoint-url "$AWS_ENDPOINT_URL" s3 presign "s3://bozze/smoke/smoke.txt" --expires-in 600)"
    curl -fsS "$url" | grep -q "contenuto di prova"
'
echo "OK presigned URL served the object"

step "7/9 WordPress: impaginatore role can draft and upload media, cannot publish"
wp_basic="$(grep '^WORDPRESS_MCP_BASIC_AUTH=' spark-a/agents/impaginatore/.env | cut -d= -f2)"
wp_creds="$(printf '%s' "$wp_basic" | base64 -d)"
draft_id="$($PY - "$wp_creds" "$STAGING_URL" <<'PYEOF'
import json, sys, urllib.request, base64
creds, base = sys.argv[1], sys.argv[2].rstrip("/")
auth = base64.b64encode(creds.encode()).decode()
def call(method, path, payload, content_type="application/json", extra=None):
    data = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
    headers = {"Authorization": "Basic " + auth, "Content-Type": content_type}
    headers.update(extra or {})
    req = urllib.request.Request(base + path, method=method, data=data, headers=headers)
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as err:
        return err.code, {}
status, body = call("POST", "/wp-json/wp/v2/posts",
                    {"title": "smoke draft", "status": "draft"})
assert status == 201, f"draft creation failed: HTTP {status}"
png = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8"
    "z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")
status, _ = call("POST", "/wp-json/wp/v2/media", png, content_type="image/png",
                 extra={"Content-Disposition": 'attachment; filename="smoke.png"'})
assert status == 201, f"media upload failed: HTTP {status} (upload_files missing?)"
status, _ = call("POST", f"/wp-json/wp/v2/posts/{body['id']}", {"status": "publish"})
assert status in (401, 403), f"publish was NOT blocked: HTTP {status}"
print(body["id"])
PYEOF
)"
echo "OK draft #$draft_id + media upload accepted; publish attempt rejected (gate holds)"

step "8/9 segreteria isolation: no services, only articles.json and email"
for target in garage:3900 wordpress:80 searxng:8080; do
    if compose exec -T segreteria curl -m 3 -s "http://$target" >/dev/null 2>&1; then
        echo "FAIL segreteria reached $target"; exit 1
    fi
    echo "OK segreteria cannot reach $target"
done
compose exec -T segreteria cat /opt/data/home/articles.json >/dev/null
echo "OK segreteria reads articles.json"
$MAIL send --user segreteria@redazione.local --password "$MAIL_PASSWORD_SEGRETERIA" \
    --mail-from segreteria@redazione.local --rcpt cronista@redazione.local \
    --subject "[SERVIZIO] tentativo fuori matrice" --expect-refused

step "9/9 collector fills the metrics DB and report.py shows them"
export NEWSROOM_DB_HOST=127.0.0.1 NEWSROOM_DB_PORT=3306 NEWSROOM_DB_NAME=metrics
export NEWSROOM_DB_USER=metrics_collector NEWSROOM_DB_PASSWORD="$METRICS_DB_PASSWORD"
PYTHONPATH=metrics $PY metrics/collector.py \
    --maildir spark-a/mail-server/data/mail-data/redazione.local/gianni \
    --mail-log spark-a/mail-server/data/mail-logs/mail.log \
    --filter-state spark-a/mail-server/state/state.db \
    --articles-json spark-a/public-status/articles.json
PYTHONPATH=metrics $PY metrics/report.py | head -n 25

echo
echo "SMOKE TEST: all 9 checks passed."
