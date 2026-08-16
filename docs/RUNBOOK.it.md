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

### Spark A — segreti e configurazioni

    cd spark-a
    ../scripts/setup-env.sh         # 1ª esecuzione: crea .env con segreti casuali
    # editare in spark-a/.env i soli valori host:
    #   SPARK_B_HOST, STAGING_URL, VLLM_CACHE_ROOT
    ../scripts/setup-env.sh         # 2ª esecuzione: genera i .env dei sei agenti

Le password sono generate a caso e propagate automaticamente; nessun
copia-incolla. I file `.env` esistenti non vengono mai sovrascritti.

### Spark A — cartelle dati e permessi

    ../scripts/setup-dirs.sh

Crea le cartelle dati dei bind mount con il proprietario che i container si
aspettano: gli agenti girano come uid 10000 (`hermes`) e WordPress come
`www-data` — senza questo passaggio non possono scrivere nei propri volumi.
Idempotente: si può rilanciare in qualsiasi momento (a container fermi).

### Spark A — infrastruttura

    docker compose up -d vllm-writer mail-server mail-filter mariadb wordpress \
                         searxng valkey garage staging

### Provisioning (idempotente, ripetibile)

    ../scripts/setup-mailboxes.sh   # crea le 7 caselle (password dal .env)
    ../scripts/setup-storage.sh     # layout Garage, 4 bucket, chiavi S3 per agente
    ../scripts/setup-wordpress.sh   # core WP, mcp-adapter, ruolo impaginatore

Gli ultimi due script **scrivono da soli le credenziali** (chiavi S3,
Application Password MCP) nei `.env` degli agenti. Attenzione: Garage non
rimostra mai i segreti — se cancelli un `.env` dopo la creazione delle
chiavi, la chiave va eliminata e ricreata.

### Gli agenti

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

## 5. Il fusibile a due stadi: thread oltre budget

Il budget per articolo è `NEWSROOM_MESSAGE_BUDGET` (default 60). Il fusibile
scatta in due stadi:

1. **Avviso (al budget)**: il filtro manda al caporedattore una mail
   `[SERVIZIO] Budget superato` (tu la vedi in BCC). Il thread continua a
   funzionare per un **margine di grazia del 50%** del budget (default: altri
   30 messaggi), in cui il caporedattore deve chiudere il lavoro.
2. **Congelamento (a budget + 50%)**: i messaggi successivi vengono trattenuti
   in `spark-a/mail-server/state/hold/<TAG>/` (file `.eml`, leggibili) e
   ricevi la mail `[SERVIZIO] Fusibile scattato`. Da qui si esce solo a mano.

Entrambi gli scatti finiscono nelle metriche come eventi `fusibile`.

Per **scongelare** un thread, dopo aver deciso come sbloccarlo (il contatore
va azzerato, altrimenti il primo messaggio successivo ricongela subito):

    sqlite3 spark-a/mail-server/state/state.db "
        DELETE FROM frozen_threads  WHERE tag = '[ART-2026-001]';
        DELETE FROM warned_threads  WHERE tag = '[ART-2026-001]';
        DELETE FROM thread_messages WHERE tag = '[ART-2026-001]';"

(Il collettore ha già copiato i dati in `metrics`: azzerare qui non perde
nulla.) I messaggi trattenuti NON vengono reinviati automaticamente (scelta
deliberata: il fallimento resta visibile). Se servono, rimandali a mano dal
tuo client copiandoli dagli `.eml`.

## 6. Guasti e ripristino

- **Un container non parte**: `docker compose logs <servizio>`. I filtri e la
  matrice non hanno retry: un errore di config si vede subito nei log.
- **`Permission denied` su `/opt/data` (agenti) o `wp-content` (WordPress)**:
  proprietari sbagliati sulle cartelle dei bind mount. Fermare i container
  coinvolti e rilanciare `../scripts/setup-dirs.sh` da `spark-a/`. Dopo il
  restore da backup, rilanciarlo sempre: gli archivi tar non conservano gli
  uid dei container.
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
| **Fusibile a due stadi** | Decisione del 2026-08-16 (deroga a SPEC §6.4, che congelava subito al budget): avviso al caporedattore al budget, congelamento a budget + 50%. Deterministico, senza re-invii automatici (SPEC §8 rispettata). |
| **Ruolo WP impaginatore** | Decisione del 2026-08-16: ruolo dedicato `impaginatore` = clone di Contributor + `upload_files`. La redazione consegna la bozza completa di immagini (con licenza e attribuzione in didascalia); `publish_posts` resta assente: pubblica solo il direttore. |

## 8. Fase 3 (solo predisposizione — NON attivare)

La struttura per il dominio esterno è in
`spark-a/mail-server/phase3/postfix-external.cf.example`: relay autenticato,
SPF/DKIM/DMARC, allow-list per interlocutore e coda `hold` in cui ogni
messaggio esterno resta fermo finché non lo rilasci tu (`postsuper -H`).
L'attivazione è una decisione editoriale, non tecnica: quando sarà il momento,
seguire i passi commentati nel file e aggiornare questo runbook.
