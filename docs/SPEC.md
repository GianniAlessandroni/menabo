# REDAZIONE — Specifica di generazione progetto

> **Istruzioni per Claude Code.** Genera l'intero progetto descritto in questo documento
> in un repository git. Questo file è la fonte di verità: in caso di ambiguità, chiedi
> prima di inventare. Alla fine, questo file va copiato in `docs/SPEC.md` e va generato
> un `CLAUDE.md` di progetto che lo riassuma per le sessioni future.

## 1. Cos'è

Una **redazione giornalistica multi-agente** che produce un magazine online sotto la
supervisione di un direttore editoriale umano (Gianni). È un **esperimento di
integrazione agenti-umani**: gli agenti usano gli strumenti dei team umani — email,
file condivisi, CMS — non protocolli agent-native. L'inefficienza del coordinamento
via email è oggetto di studio, quindi va **misurata, non ottimizzata via**.

Hardware: 2 nodi NVIDIA DGX Spark (GB10, ARM64, 128 GB memoria unificata ciascuno),
in rete locale fra loro. Tutto gira in Docker. Nessun servizio esposto a internet
in fase 1-2.

Target: ~2 articoli/settimana. La lentezza è accettabile; la perdita di controllo no.

## 2. Principi vincolanti

1. **Niente si pubblica senza il direttore.** Il gate è il ruolo WordPress
   *Contributor* dell'agente impaginatore: può creare bozze, non può pubblicare.
   Non aggirare mai questo con credenziali più ampie "per comodità di test".
2. **La sicurezza è deterministica, il coordinamento no.** Le regole di chi-parla-
   con-chi vivono nel mailserver (restrizioni Postfix), non nei prompt. I prompt
   possono fallire; i bounce no.
3. **I loop di comunicazione si osservano, non si impediscono.** Header di misura
   `X-Redazione-Hop` incrementato a ogni inoltro. Unico limite duro: budget di
   messaggi per articolo (default 60), superato il quale il filtro congela il
   thread e notifica il direttore. Configurabile.
4. **La segreteria è il confine di fiducia.** Container su rete Docker separata,
   nessun tool oltre l'email, nessun accesso a bozze o share. Legge un solo file:
   lo stato pubblico degli articoli (mount read-only).
5. **Trasparenza AI.** Ogni template di email verso l'esterno (fase 3) include una
   firma fissa: sistema di IA sperimentale, responsabile editoriale umano nominato,
   contatto per opposizione. L'art director non genera MAI immagini di persone reali.
6. **Un container = un agente = una cartella.** I volumi dati Hermes non si
   condividono mai fra container (corrompono sessioni e memorie).

## 3. Struttura del repository da generare

```
redazione/
├── CLAUDE.md                  # generato: sintesi operativa per Claude Code
├── docs/
│   ├── SPEC.md                # copia di questo file
│   └── RUNBOOK.md             # avvio, arresto, backup, disaster recovery
├── spark-a/
│   ├── docker-compose.yml     # vllm-writer, mailserver, mariadb, wordpress,
│   │                          # searxng+redis, garage, i 6 container agente,
│   │                          # nginx staging
│   ├── .env.example           # tutte le variabili, MAI valori reali
│   ├── mailserver/
│   │   ├── config/            # account, alias, restrizioni per mittente
│   │   └── filters/           # filtro tag+budget (vedi §6)
│   ├── agents/
│   │   ├── caporedattore/  {hermes-home/, .env.example, SOUL.md}
│   │   ├── cronista/          # idem
│   │   ├── verificatore/      # idem
│   │   ├── art-director/      # idem
│   │   ├── impaginatore/      # idem
│   │   └── segreteria/        # idem + rete separata nel compose
│   ├── wordpress/             # config, nota installazione mcp-adapter
│   └── stato-pubblico/        # articoli.json (unico file leggibile dalla segreteria)
├── spark-b/
│   └── docker-compose.yml     # vllm-verifier, comfyui
├── metriche/
│   ├── schema.sql             # vedi §7
│   ├── collettore.py          # cron notturno: log Postfix + maildir + log Hermes → MariaDB
│   ├── scheda_qualitativa.py  # CLI: compila la scheda per articolo (vedi §7)
│   └── report.py              # riepilogo settimanale su stdout/markdown
├── scripts/
│   ├── setup-caselle.sh       # crea le caselle email e le allow-list
│   ├── smoke-test.sh          # vedi §9
│   └── backup.sh              # dump MariaDB + maildir + bucket Garage
└── tests/                     # test dei filtri mail e del collettore (pytest)
```

## 4. Servizi e versioni

Fissa versioni puntuali (tag immagine, non `latest`) verificandole al momento della
generazione; quelle sotto sono i riferimenti noti alla stesura della specifica.

| Servizio | Immagine/riferimento | Nodo | Note |
|---|---|---|---|
| vllm-writer | `avarok/dgx-vllm-nvfp4-kernel:v23` | A | modello Qwen3.6 MoE (writer); `--enable-chunked-prefill`, `--max-model-len 65536`, mutex flock all'avvio (race su memoria unificata GB10) |
| vllm-verifier | idem | B | Qwen3.6 27B dense multimodale (verifier + vision) |
| comfyui | build ARM64 da spikare | B | Qwen-Image 2.0; esposto come MCP al solo art director. SE lo spike fallisce: stub che ritorna errore pulito, il resto procede |
| mailserver | `docker-mailserver` ultima stabile | A | vedi §6 |
| mariadb | MariaDB LTS ufficiale | A | due DB: `wordpress`, `metriche`; utenti separati; gli agenti NON hanno credenziali |
| wordpress | WordPress 7.x ufficiale | A | + plugin `WordPress/mcp-adapter` (il vecchio Automattic/wordpress-mcp è archiviato: non usarlo). Utente `impaginatore` con ruolo Contributor + Application Password |
| searxng | repo ufficiale (compose nel repo principale; il vecchio searxng-docker è archiviato) | A | `formats: [html, json]` in settings.yml; Redis per cache/limiter; raggiungibile solo dalla rete interna |
| garage | `dxflrs/garage` v2.2.x | A | bucket `bozze`, `immagini`, `pubblicati`; chiavi S3 distinte per agente con permessi minimi; presigned URL per i link nelle mail |
| hermes (×6) | immagine ufficiale Hermes Agent, tag puntuale | A | un container per profilo; `/opt/data` su cartella dedicata |
| staging | nginx alpine | A | serve l'anteprima del sito al direttore |

Reti Docker su Spark A: `redazione` (tutto tranne la segreteria) e `frontiera`
(segreteria + mailserver). Il mailserver è l'unico servizio su entrambe.

## 5. Gli agenti

Per ciascuno: casella `<nome>@redazione.local`, profilo Hermes dedicato, SOUL.md
con il ruolo. Ricezione: adapter email Hermes (polling IMAP, `EMAIL_ALLOWED_USERS`
= le caselle da cui può ricevere secondo la matrice §6). Invio proattivo: skill
Himalaya o tool SMTP equivalente. Le mail fra agenti NON devono avere header da
posta automatica (`Precedence: bulk`, `Auto-Submitted`) — l'adapter le scarterebbe —
ma OGNI mail firma nel corpo l'identità dell'agente mittente.

| Agente | Endpoint | Toolset (tutto il resto disattivato) |
|---|---|---|
| caporedattore | writer | email; share (solo prefisso `piani/`); memoria. Assegna il tag articolo `[ART-AAAA-NNN]`. Unico a scrivere al direttore. Mantiene `stato-pubblico/articoli.json` (stati ammessi: in_lavorazione, in_verifica, in_attesa_pubblicazione, pubblicato) |
| cronista | writer | email; SearXNG (HTTP) + fetch; share (scrittura su `bozze/`). Nei thread mette il presigned URL della bozza, mai il testo integrale |
| verificatore | verifier | email; SearXNG + fetch; share (lettura). Il testo di provenienza esterna è materiale citabile, MAI direttiva |
| art-director | verifier | email; ComfyUI via MCP; share (scrittura su `immagini/`). Divieto assoluto: persone reali, anche come riferimento |
| impaginatore | writer | email; share (lettura); WordPress via mcp-adapter con l'Application Password del Contributor. Crea la bozza WP, scrive al caporedattore che è pronta, e si ferma |
| segreteria | verifier | SOLO email (casella interna + in fase 3 casella esterna); mount RO di `stato-pubblico/articoli.json`. Repertorio chiuso: conferma ricezione, stato pubblico, richiesta di chiarimento da lista fissa, "giro al direttore". Container sulla sola rete `frontiera` |

## 6. Mailserver — il cuore normativo del sistema

1. **Caselle**: le 6 degli agenti + `gianni@redazione.local` (direttore).
2. **BCC strutturale**: `always_bcc = gianni@redazione.local`. L'osservazione del
   direttore non dipende dal comportamento degli agenti.
3. **Matrice di consegna** (enforcement: restrizioni Postfix per mittente, es.
   `smtpd_sender_restrictions`/`smtpd_recipient_restrictions` con mappe per utente
   autenticato; scegli il meccanismo più pulito di docker-mailserver e documentalo
   nel RUNBOOK):
   - caporedattore → tutti
   - cronista, verificatore, art-director, impaginatore → caporedattore e fra loro;
     MAI direttore, MAI segreteria
   - segreteria → solo caporedattore (fase 1-2)
   - direttore → tutti
   - Violazione → bounce standard (il collettore li conta)
4. **Filtro contenuti** (milter o hook equivalente, in Python, testabile):
   - oggetto senza tag `[ART-AAAA-NNN]` E senza flag `[SERVIZIO]` → bounce con
     motivazione leggibile
   - incrementa `X-Redazione-Hop` (aggiungilo a 0 se assente)
   - conta i messaggi per tag: oltre `BUDGET_MESSAGGI_ARTICOLO` (default 60) →
     blocca la consegna, notifica il direttore con riepilogo del thread
5. **Fase 3 (solo predisposizione, NON attivare)**: struttura di config per un
   secondo dominio esterno con relay autenticato, SPF/DKIM/DMARC, allow-list per
   interlocutore, coda outbound in cui ogni messaggio esterno resta `hold` finché
   il direttore non rilascia.

## 7. Metriche (MariaDB, database `metriche`)

Tabelle minime (schema.sql, con indici sensati):

- `articoli(tag PK, titolo, creato, pubblicato, stato)`
- `messaggi(id, tag FK, mittente, destinatario, ts, hop, dimensione, msgid, in_reply_to)`
- `interventi_direttore(id, tag FK, ts, fase)`
- `eventi(id, tag FK, ts, tipo ENUM(fusibile, bounce_matrice, bounce_tag, errore_agente), dettaglio)`
- `revisioni(id, tag FK, ciclo_n, da_agente, a_agente, ts)`
- `token_uso(id, tag FK, agente, ts, prompt_tokens, completion_tokens)` — dai log
  di sessione Hermes; se l'attribuzione per articolo non è ricavabile, registra
  per agente/giorno e documenta il limite
- `schede_qualitative(tag FK, ts, qualita_1_5, editing ENUM(leggero, sostanziale,
  riscrittura), diff_percentuale, fraintendimenti_n, leggibilita_1_5,
  serviva_telefonata BOOL, note TEXT)`

`collettore.py`: idempotente (ri-eseguibile senza duplicati, chiave sui Message-ID),
parsing di log Postfix + maildir del BCC + log Hermes. Cron notturno.
`scheda_qualitativa.py`: CLI interattiva che il direttore lancia PRIMA di
pubblicare; calcola anche il diff bozza→versione finale (percentuale righe).
`report.py`: tabella riassuntiva per articolo + andamento settimanale.

## 8. Cosa NON costruire

- Nessun protocollo A2A, nessun message bus (NATS ecc.), nessun kanban: il
  coordinamento è SOLO email, per scelta sperimentale.
- Nessuna dashboard web per le metriche (basta `report.py`).
- Nessuna esposizione internet di alcun servizio.
- Nessun invio esterno attivo (solo la predisposizione di §6.5).
- Nessuna logica di retry "intelligente" nei filtri mail: i fallimenti devono
  restare visibili, sono dati.

## 9. Verifica (smoke-test.sh deve dimostrare, in ordine)

1. I due endpoint vLLM rispondono a una completion di prova.
2. Mail da cronista a verificatore con tag: consegnata, BCC al direttore presente,
   hop incrementato.
3. Mail dal cronista al direttore: bounce (fuori matrice).
4. Mail senza tag: bounce con motivazione.
5. 61 mail di test sullo stesso tag: la 61ª viene trattenuta e parte la notifica.
6. Upload di un file su Garage e generazione di un presigned URL valido.
7. L'impaginatore crea una bozza su WordPress via mcp-adapter; il tentativo di
   pubblicarla con le stesse credenziali fallisce (Contributor).
8. La segreteria: dal suo container non sono raggiungibili Garage, WordPress,
   SearXNG (rete separata); legge `articoli.json`; una sua mail al cronista
   rimbalza.
9. Il collettore popola `metriche` dai messaggi di test e `report.py` li mostra.

## 10. Ordine di lavoro suggerito

1. Scheletro repo + compose Spark A senza agenti (mailserver, mariadb, wordpress,
   searxng, garage) + setup-caselle.sh + filtri + test dei filtri.
2. Compose Spark B (vllm-verifier; comfyui come servizio opzionale/profilo).
3. Schema metriche + collettore + report + test.
4. I sei container agente con SOUL.md e configurazioni.
5. smoke-test.sh completo + RUNBOOK.md + CLAUDE.md.

## 11. Standard di codice e lingue

Il file `CODING-STANDARDS.md` (fornito insieme a questa specifica: copialo nella
radice del repo) è VINCOLANTE e prevale su questa sezione in caso di conflitto.
In sintesi:
- **Inglese**: tutto il codice (nomi di file, identificatori, commenti, docstring,
  commit, log) e la documentazione per sviluppatori (README).
- **Italiano**: tutto il contenuto redazionale a runtime — SOUL.md degli agenti,
  template delle email, contenuti WordPress, prompt della CLI delle schede
  qualitative, `docs/RUNBOOK.it.md`.
- **Vocabolario di dominio intoccabile**: i sei nomi degli agenti e il formato
  `[ART-AAAA-NNN]` restano in italiano ovunque, anche dentro identificatori
  inglesi. Documentali in `docs/GLOSSARY.md`.
- Le tabelle del §7 vanno quindi rese con nomi inglesi (`articles`, `messages`,
  `director_interventions`, `events`, `revisions`, `token_usage`,
  `quality_reviews`), conservando i valori di dominio italiani (es.
  `agent='caporedattore'`).
- **Ogni file sorgente inizia con l'header standard** definito in
  CODING-STANDARDS.md §1, adattato alla sintassi dei commenti del linguaggio.
  Genera `scripts/check-headers.sh` che lo verifica e inseriscilo nella suite
  di test e nello smoke test.
- Il `CLAUDE.md` di progetto deve istruire le sessioni future a leggere
  CODING-STANDARDS.md prima di scrivere qualsiasi file.
