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

step "0/9 repo hygiene (headers)"
scripts/check-headers.sh

step "1/9 vLLM endpoints answer"
curl -fsS "http://127.0.0.1:8000/v1/models" >/dev/null && echo "OK writer (node A)"
curl -fsS "http://${SPARK_B_HOST:?}:8000/v1/models" >/dev/null && echo "OK verifier (node B)"

TAG="[ART-2099-901]"
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
    --subject "prova senza etichetta"
$MAIL await --user cronista@redazione.local --password "$MAIL_PASSWORD_CRONISTA" \
    --subject-contains "prova senza etichetta" --from-contains "MAILER-DAEMON" --timeout 120
echo "OK bounce with reason came back to the sender"

TAG2="[ART-2099-902]"
step "5/9 message budget: the 61st mail is held and the director notified"
$MAIL flood --user cronista@redazione.local --password "$MAIL_PASSWORD_CRONISTA" \
    --mail-from cronista@redazione.local --rcpt verificatore@redazione.local \
    --subject "$TAG2 riempimento budget" --count 60
$MAIL send --user cronista@redazione.local --password "$MAIL_PASSWORD_CRONISTA" \
    --mail-from cronista@redazione.local --rcpt verificatore@redazione.local \
    --subject "$TAG2 messaggio oltre budget"
$MAIL await --user gianni@redazione.local --password "$MAIL_PASSWORD_GIANNI" \
    --subject-contains "Fusibile scattato" --timeout 180
$MAIL await --user verificatore@redazione.local --password "$MAIL_PASSWORD_VERIFICATORE" \
    --subject-contains "messaggio oltre budget" --expect-absent --timeout 20

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

step "7/9 WordPress: Contributor can draft, cannot publish"
wp_basic="$(grep '^WORDPRESS_MCP_BASIC_AUTH=' spark-a/agents/impaginatore/.env | cut -d= -f2)"
wp_creds="$(printf '%s' "$wp_basic" | base64 -d)"
draft_id="$($PY - "$wp_creds" "$STAGING_URL" <<'PYEOF'
import json, sys, urllib.request, base64
creds, base = sys.argv[1], sys.argv[2].rstrip("/")
auth = base64.b64encode(creds.encode()).decode()
def call(method, path, payload):
    req = urllib.request.Request(base + path, method=method,
        data=json.dumps(payload).encode(),
        headers={"Authorization": "Basic " + auth, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as err:
        return err.code, {}
status, body = call("POST", "/wp-json/wp/v2/posts",
                    {"title": "smoke draft", "status": "draft"})
assert status == 201, f"draft creation failed: HTTP {status}"
status, _ = call("POST", f"/wp-json/wp/v2/posts/{body['id']}", {"status": "publish"})
assert status in (401, 403), f"publish was NOT blocked: HTTP {status}"
print(body["id"])
PYEOF
)"
echo "OK draft #$draft_id created; publish attempt was rejected (Contributor gate)"

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
