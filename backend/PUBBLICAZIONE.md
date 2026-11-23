# Backend SAGE: come pubblicarlo (Render + Neon) e collegare Telegram

Scelte di Marco (diario D36-D39): server su **Render** (gratis), database **PostgreSQL su Neon** (gratis),
Telegram con **webhook**, un **cron esterno** ogni 5 minuti per i promemoria delle dosi e per tenere sveglio il
server. Gli account li crea Marco. Tempo stimato: 30-40 minuti.

## Variabili d'ambiente

| Variabile | Dove serve | Valore |
|---|---|---|
| `DATABASE_URL` | Render | indirizzo PostgreSQL di Neon (passo 1). In locale non serve: si usa `backend/sage.sqlite3` |
| `TOKEN_CASA` | Render, `backend/.env`, `.env` del programma di casa | lo **stesso** valore ovunque (è già in `backend/.env`) |
| `TOKEN_CRON` | Render e cron-job.org | già in `backend/.env` |
| `TELEGRAM_TOKEN` | Render, `backend/.env` | token del bot da BotFather (già in `backend/.env`) |
| `TELEGRAM_CODICE_COLLEGAMENTO` | Render, `backend/.env` | il codice da scrivere dopo `/start` (già in `backend/.env`) |
| `TELEGRAM_WEBHOOK_URL` | solo Render | `https://<nome-servizio>.onrender.com/telegram/webhook` (passo 3) |
| `TELEGRAM_SEGRETO_WEBHOOK` | solo Render | un valore nuovo a caso (vedi sotto) |
| `TELEGRAM_POLLING` | solo in locale, se serve | `1` per provare il bot sul PC senza webhook |

Per vedere i valori già pronti, sul PC: `grep -v TELEGRAM_TOKEN backend/.env` (il token del bot lo copi a mano da
BotFather o dal file). Per creare un valore a caso:
`python3 -c "import secrets; print(secrets.token_urlsafe(32))"`.

## 1. Neon (database)

1. Vai su <https://neon.com> → **Sign up** (anche con GitHub).
2. **Create project**: nome `sage`, versione di Postgres quella proposta, regione **AWS Europe Central 1
   (Frankfurt)** (vicina a Render Frankfurt).
3. Nella pagina del progetto premi **Connect**: lascia acceso **Connection pooling** e copia l'indirizzo
   (`postgresql://...-pooler...neon.tech/neondb?sslmode=require&channel_binding=require`). È il `DATABASE_URL`.
4. Le tabelle le crea il backend da solo al primo avvio.

Facoltativo, per provare il codice PostgreSQL prima di pubblicare (non l'ho potuto provare: sul PC non c'è
PostgreSQL): in Neon crea un **secondo database** `prova` (Databases → New database), copia il suo indirizzo e lancia
`SAGE_POSTGRES_DI_PROVA='<indirizzo del database prova>' uv run pytest tests/test_backend_archivio.py`.
**Attenzione:** quei test cancellano le tabelle, quindi mai con l'indirizzo del database vero.

## 2. Render (server)

Prima: il codice del backend deve essere su `main` su GitHub (Render pubblica da lì).

1. Vai su <https://render.com> → **Get Started** con GitHub; dai accesso al repo `marcozambrella/SAGE`.
2. **New → Web Service** → scegli il repo `SAGE`.
3. Compila:
   - **Name**: `sage-backend` (l'indirizzo sarà `https://sage-backend.onrender.com`, o simile se il nome è preso)
   - **Region**: Frankfurt (EU Central)
   - **Branch**: `main`
   - **Root Directory**: vuoto (la radice del repo, dove sta `uv.lock`: così Render usa uv)
   - **Language**: Python 3
   - **Build Command**: `uv sync --frozen --no-dev --package backend`
   - **Start Command**: `uv run --frozen --no-dev --package backend uvicorn backend.app:app --host 0.0.0.0 --port $PORT`
   - **Instance Type**: **Free**
4. **Environment Variables**: aggiungi `DATABASE_URL`, `TOKEN_CASA`, `TOKEN_CRON`, `TELEGRAM_TOKEN`,
   `TELEGRAM_CODICE_COLLEGAMENTO`, `TELEGRAM_SEGRETO_WEBHOOK` (tabella sopra). `TELEGRAM_WEBHOOK_URL` al passo 3.
5. Facoltativo, in **Advanced → Build Filters → Included Paths**: `backend/**`, `contratti/**`, `uv.lock`,
   `pyproject.toml` (così le modifiche alla web app non ripubblicano il backend).
6. **Deploy Web Service**. Il build installa solo `backend` + `contratti` (circa 32 MB, niente PyTorch).
7. Prova: apri `https://<nome-servizio>.onrender.com/docs`: deve comparire la documentazione delle API.

## 3. Telegram (webhook)

1. Su Render, nel servizio → **Environment** → aggiungi
   `TELEGRAM_WEBHOOK_URL = https://<nome-servizio>.onrender.com/telegram/webhook` → **Save, rebuild, and deploy**.
2. Nei **Logs** di Render deve comparire `INFO: sage.telegram: Telegram: webhook impostato`.
   Se c'è `Telegram non raggiungibile`, il bot è spento fino al prossimo riavvio: **Manual Deploy → Restart service**.
3. Su Telegram scrivi al bot `/start <codice>` (il valore di `TELEGRAM_CODICE_COLLEGAMENTO`). Risposta attesa:
   *"This chat is now linked to the SAGE demo home..."*. Ogni familiare può collegarsi allo stesso modo.

## 4. Cron esterno (promemoria e server sveglio)

1. Vai su <https://cron-job.org> → **Sign up** (gratis).
2. **Create cronjob**:
   - **URL**: `https://<nome-servizio>.onrender.com/cron/controlli`
   - **Execution schedule**: every 5 minutes
   - **Advanced → Request method**: `POST`
   - **Advanced → Headers**: `Authorization` = `Bearer <TOKEN_CRON>`
3. Salva. Risposta attesa: `{"promemoria":0}` (o il numero di promemoria mandati). Il primo giro con il server
   addormentato può andare in timeout (cron-job.org aspetta 30 secondi, Render circa 1 minuto per svegliarsi): il
   giro dopo lo trova sveglio.

Nota: Render gratis dà 750 ore al mese per tutto l'account; un servizio sempre sveglio ne usa 744 a dicembre.
Altri servizi gratuiti sullo stesso account consumerebbero le stesse ore.

## 5. Dati della casa demo

- Storico simulato (dal PC, con lo stesso `TOKEN_CASA` di Render in `backend/.env`):
  `uv run python -m backend.storico_simulato --url https://<nome-servizio>.onrender.com`
- La web app legge da `https://<nome-servizio>.onrender.com/demo/...`.
- Il programma di casa manda personalizzazione ed eventi a `https://<nome-servizio>.onrender.com/programma-casa/...`
  con lo stesso `TOKEN_CASA`.

## Provare il bot sul PC (senza pubblicare)

```
TELEGRAM_POLLING=1 uv run uvicorn backend.app:app
```

Nel log: `Telegram: polling avviato`; poi scrivi `/start <codice>` al bot. Il database è `backend/sage.sqlite3`.
**Attenzione:** il polling cancella il webhook. Se il server online è già pubblicato, dopo la prova fai su Render
**Manual Deploy → Restart service**, così il webhook viene rimesso.
