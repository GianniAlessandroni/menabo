<!-- =============================================================================
  menabò — an experiment in human-agent newsroom integration
 ------------------------------------------------------------------------------
  File:     docs/RUNBOOK.it.md
  Purpose:  Operations manual for the editor-in-chief (Italian: runtime
            audience). Start/stop, provisioning, daily ritual, backup, DR.
  Author:   Gianni Alessandroni
  Created:  2026-08-16
  License:  Apache-2.0 — see LICENSE
  Part of:  menabò https://github.com/GianniAlessandroni/menabo
============================================================================== -->

# RUNBOOK — la redazione menabò

Manuale operativo per il direttore. Tutti i comandi si lanciano dalla radice
del repository, salvo dove indicato.

## 1. Prerequisiti

- Due DGX Spark in rete locale: **Spark A** (redazione) e **Spark B**
  (verifier + immagini). Docker e il runtime NVIDIA su entrambi.
- Sul host di Spark A: `python3` (3.11+), `git`, `curl`. Per collettore e
  schede: `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`.
- Nessun servizio è esposto a internet: tutto vive su LAN e reti Docker.

## 2. Primo avvio (in ordine)

### Spark B

    cd spark-b
    cp .env.example .env            # sistemare VLLM_CACHE_ROOT
    docker compose up -d vllm-verifier
    docker compose --profile comfyui up -d    # opzionale: generazione immagini

### Spark A — infrastruttura

    cd spark-a
    cp .env.example .env            # compilare TUTTE le password e SPARK_B_HOST
    docker compose up -d vllm-writer mail-server mail-filter mariadb wordpress \
                         searxng valkey garage staging

### Provisioning (idempotente, ripetibile)

    ../scripts/setup-mailboxes.sh   # crea le 7 caselle
    ../scripts/setup-storage.sh     # layout Garage, 4 bucket, chiavi per agente
    ../scripts/setup-wordpress.sh   # core WP, mcp-adapter, utente Contributor

I due ultimi script **stampano credenziali una sola volta** (chiavi S3 e
Application Password): incollarle subito nei rispettivi
`spark-a/agents/<nome>/.env` (partendo dai `.env.example`).

### Gli agenti

    for a in caporedattore cronista verificatore art-director impaginatore segreteria; do
        cp agents/$a/.env.example agents/$a/.env   # poi compilare
    done
    docker compose up -d --build caporedattore cronista verificatore \
                                 art-director impaginatore segreteria

### Verifica finale

    ../scripts/smoke-test.sh        # le 9 prove della SPEC §9, in ordine

## 3. Il rituale quotidiano del direttore

- **Posta**: casella `gianni@redazione.local`, client IMAP verso Spark A,
  porta 143 (SMTP 587). Ricevi in BCC ogni mail consegnata in redazione:
  l'osservazione non dipende dagli agenti.
- **Anteprima**: `http://<spark-a>:8080` (nginx staging davanti a WordPress).
- **Assegnare un pezzo**: mail al caporedattore con oggetto `[SERVIZIO]`
  (il tag lo assegna lui e te lo comunica).
- **Prima di pubblicare** (obbligatorio, alimenta l'esperimento):

      .venv/bin/python metrics/quality_review.py \
          --tag "[ART-2026-001]" --draft bozza.md --final finale.md

  poi pubblichi tu dalla bacheca WordPress (l'impaginatore non può).
  Infine chiedi al caporedattore di portare lo stato a `pubblicato`.
- **Report settimanale**:

      NEWSROOM_DB_HOST=127.0.0.1 NEWSROOM_DB_USER=metrics_collector \
      NEWSROOM_DB_PASSWORD=... .venv/bin/python metrics/report.py

## 4. Cron notturno (host di Spark A)

    # crontab -e
    10 3 * * *  cd /home/gionni/Source/menabo && NEWSROOM_DB_HOST=127.0.0.1 \
      NEWSROOM_DB_USER=metrics_collector NEWSROOM_DB_PASSWORD=<pw> \
      .venv/bin/python metrics/collector.py \
      --maildir spark-a/mail-server/data/mail-data/redazione.local/gianni \
      --mail-log spark-a/mail-server/data/mail-logs/mail.log \
      --filter-state spark-a/mail-server/state/state.db \
      --hermes-root spark-a/agents \
      --articles-json spark-a/public-status/articles.json >> collector.log 2>&1
    40 3 * * *  cd /home/gionni/Source/menabo && ./scripts/backup.sh >> backup.log 2>&1

Il collettore è idempotente (chiave sui Message-ID): rilanciarlo non duplica.

## 5. Il fusibile: thread congelati

Quando un tag supera il budget (default 60, variabile
`NEWSROOM_MESSAGE_BUDGET`), il filtro trattiene i messaggi e ti manda una mail
`[SERVIZIO] Fusibile scattato`. I messaggi trattenuti sono in
`spark-a/mail-server/state/hold/<TAG>/` (file `.eml`, leggibili).

Per **scongelare** un thread, dopo aver deciso come sbloccarlo:

    sqlite3 spark-a/mail-server/state/state.db \
        "DELETE FROM frozen_threads WHERE tag = '[ART-2026-001]';"

I messaggi già trattenuti NON vengono reinviati automaticamente (scelta
deliberata: il fallimento resta visibile). Se servono, rimandali a mano dal
tuo client copiandoli dagli `.eml`. L'evento resta registrato in `metrics`.

## 6. Guasti e ripristino

- **Un container non parte**: `docker compose logs <servizio>`. I filtri e la
  matrice non hanno retry: un errore di config si vede subito nei log.
- **Restore completo**: i backup datati sono in `backups/`.
  1. `docker compose down` su Spark A;
  2. ripristinare le cartelle `spark-a/mail-server/data`, `spark-a/garage/{meta,data}`,
     gli `hermes-home` e `public-status/articles.json` dagli archivi tar;
  3. `zcat backups/<data>/mariadb.sql.gz | docker compose exec -T mariadb mariadb -uroot -p<root-pw>`;
  4. `docker compose up -d` e `scripts/smoke-test.sh`.
- **Ricostruire un agente da zero**: fermare il container, svuotare il suo
  `hermes-home/` (perde sessioni e memoria, il resto no), riavviare.
  Mai condividere un `hermes-home` fra due container (SPEC §2.6).

## 7. Decisioni, deviazioni e limiti noti

| Tema | Stato |
|---|---|
| **TLS interno** | Spento in fase 1-2 (rete isolata): IMAP 143 / SMTP 587 in chiaro, `auth_allow_cleartext` in Dovecot. Da rivedere in fase 3. |
| **Qwen-Image 2.0** | Non ha pesi pubblici (solo API): lo spike ha sostituito con **Qwen-Image-2512** (pesi aperti, supporto ComfyUI nativo, template "Qwen-Image-2512"; file fp8 da Comfy-Org in `models/`). |
| **vLLM su Spark A** | Tag `cu130-nightly` congelato de-facto (non più aggiornato): è la configurazione provata su questo nodo. Percorso di upgrade: `v0.27.1(-aarch64)`; se l'output MoE degrada, fallback `--moe-backend=marlin`. |
| **vLLM su Spark B** | `v0.27.1-aarch64`: il checkpoint 27B NVFP4 richiede vLLM ≥ 0.24. |
| **comfyui-mcp** | Flag `--http/--port` da verificare al primo avvio del profilo `comfyui` (release npm molto frequenti). |
| **config.yaml degli agenti** | Montati in sola lettura: gli agenti non possono auto-modificarsi la configurazione (voluto). Se Hermes richiedesse scrittura all'avvio, rimuovere `:ro` e segnalarlo qui. |
| **Token per articolo** | I log Hermes non attribuiscono i token al singolo articolo: `token_usage` registra per agente/giorno (limite documentato in `metrics/schema.sql`). |
| **Isolamento segreteria** | Garantito per nomi-servizio Docker (smoke test §8). La rete `frontiera` ha uscita LAN (le serve per il modello su Spark B): non pubblicare sull'host servizi non necessari. |
| **URL presigned** | Firmati per l'endpoint interno `garage:3900`: valgono fra agenti. Dal host del direttore: `aws --endpoint-url http://127.0.0.1:3900 s3 ...` con una chiave dedicata. |
| **Bucket `piani`** | La SPEC elencava 3 bucket; `piani` è il quarto, per dare al caporedattore una chiave a privilegio minimo senza aprirgli `bozze`. |
| **Filtro contenuti** | After-queue (`content_filter` → proxy Python → reinserimento su 10026, riservato all'IP del filtro). Il rimbalzo "senza tag" arriva quindi come mail di MAILER-DAEMON, non come rifiuto immediato. |

## 8. Fase 3 (solo predisposizione — NON attivare)

La struttura per il dominio esterno è in
`spark-a/mail-server/phase3/postfix-external.cf.example`: relay autenticato,
SPF/DKIM/DMARC, allow-list per interlocutore e coda `hold` in cui ogni
messaggio esterno resta fermo finché non lo rilasci tu (`postsuper -H`).
L'attivazione è una decisione editoriale, non tecnica: quando sarà il momento,
seguire i passi commentati nel file e aggiornare questo runbook.
