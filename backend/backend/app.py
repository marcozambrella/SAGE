"""API del backend SAGE (contratti/API.md): lettura pubblica della casa demo per la web app, chiamate del
programma di casa con il suo token, chiamata per il cron esterno e webhook di Telegram. Documentazione su /docs.

Avvio in sviluppo, dalla radice del repo:  uv run uvicorn backend.app:app --reload
Variabili d'ambiente (in sviluppo nel file backend/.env, mai nel repo; online nelle impostazioni del servizio):
- TOKEN_CASA: il token "Bearer" del programma di casa, lo stesso che ha nel suo .env.
- TOKEN_CRON: il token "Bearer" del cron esterno che chiama /cron/controlli (D39).
- DATABASE_URL: l'indirizzo PostgreSQL (Neon) online; se manca si usa il file SQLite backend/sage.sqlite3.
- le variabili TELEGRAM_* del bot: vedi bot_telegram.py.
"""

import base64
import datetime
import logging
import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Literal

from dotenv import load_dotenv
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from telegram import Update

from contratti.configurazione import Personalizzazione
from contratti.eventi import TIPI_URGENTI, Evento, EventoBase
from contratti.report import ReportGiornaliero, ReportPeriodo

from backend.allarmi import messaggio_allarme, promemoria_da_mandare, scrivi_allarme_nel_log, serve_allarme
from backend.archivio import ArchivioDatabase
from backend.bot_telegram import avvia_bot, ferma_bot, manda_a_tutte_le_chat
from backend.coordinatore import Coordinato, coordina, fine_o_inizio
from backend.regole import (
    FUSO_ORARIO_PREDEFINITO,
    con_regole_del_backend,
    errore_nella_personalizzazione,
    giorno_locale,
)
from backend.report import (
    calcola_report_giornaliero,
    calcola_report_periodo,
    giorni_del_mese,
    giorni_della_settimana,
    inizio_del_giorno,
)

CARTELLA_BACKEND = Path(__file__).parent.parent
# Per coordinare i grezzi ai bordi di un intervallo se ne leggono anche un po' prima e dopo: basta per i doppioni
# (pochi secondi) e per gli eventi lunghi fino a un'ora.
MARGINE_COORDINAMENTO = datetime.timedelta(hours=1)
# il database di sviluppo, ignorato da git
SQLITE_PREDEFINITO = CARTELLA_BACKEND / "sage.sqlite3"


@asynccontextmanager
async def ciclo_di_vita(app: FastAPI):
    """All'avvio del server: segreti, database e bot Telegram; alla chiusura si ferma il bot (FastAPI vuole un
    generatore: prima di yield l'avvio, dopo la chiusura). I test non lo fanno partire: mettono loro nello stato un
    database di prova, token di prova e un finto bot."""
    # i messaggi informativi di SAGE nel log del server (senza, Python mostra solo gli avvisi)
    logging.basicConfig(format="%(levelname)s: %(name)s: %(message)s")
    logging.getLogger("sage").setLevel(logging.INFO)
    # backend/.env; le variabili già impostate (es. sul server online) hanno la precedenza
    load_dotenv(CARTELLA_BACKEND / ".env")
    app.state.token_casa = os.environ.get("TOKEN_CASA", "")
    app.state.token_cron = os.environ.get("TOKEN_CRON", "")
    app.state.segreto_webhook = os.environ.get("TELEGRAM_SEGRETO_WEBHOOK", "")
    indirizzo_database = os.environ.get("DATABASE_URL", "")
    if indirizzo_database == "":
        indirizzo_database = str(SQLITE_PREDEFINITO)
    app.state.archivio = ArchivioDatabase(indirizzo_database)
    # None se il bot non è configurato: allarmi e promemoria finiscono solo nel log
    app.state.telegram = await avvia_bot(app.state.archivio)
    yield
    await ferma_bot(app.state.telegram)


app = FastAPI(title="SAGE backend", description="Safety Alert Guardian Engine: demo home API", lifespan=ciclo_di_vita)
# CORS aperto: la web app sta su un altro indirizzo e legge solo i dati pubblici della casa demo (D27)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# auto_error=False: senza token la risposta la decidono le funzioni controlla_token_* (401)
lettore_token = HTTPBearer(auto_error=False)


class RispostaEventi(BaseModel):
    ricevuti: int
    # quelli con un id mai visto prima: gli altri sono stati ignorati
    nuovi: int


class PeriodoDemo(BaseModel):
    # primo e ultimo giorno con eventi nella casa demo, None se non ce ne sono (API.md)
    dal: datetime.date | None
    al: datetime.date | None


class RispostaControlli(BaseModel):
    # promemoria delle dosi mandati in questo giro
    promemoria: int


def adesso() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


def segreto_giusto(ricevuto: str, atteso: str) -> bool:
    # senza segreto configurato nessuno passa
    if atteso == "":
        return False
    # confronto a tempo costante: non dice quanti caratteri del segreto sono giusti
    return secrets.compare_digest(ricevuto.encode(), atteso.encode())


def controlla_token_casa(
    request: Request,
    credenziali: Annotated[HTTPAuthorizationCredentials | None, Depends(lettore_token)],
) -> None:
    """Le chiamate /programma-casa/* vogliono il token del programma di casa (API.md)."""
    if credenziali is None or not segreto_giusto(credenziali.credentials, request.app.state.token_casa):
        raise HTTPException(status_code=401, detail="Missing or invalid home token")


def controlla_token_cron(
    request: Request,
    credenziali: Annotated[HTTPAuthorizationCredentials | None, Depends(lettore_token)],
) -> None:
    """/cron/controlli vuole il token del cron esterno (D39)."""
    if credenziali is None or not segreto_giusto(credenziali.credentials, request.app.state.token_cron):
        raise HTTPException(status_code=401, detail="Missing or invalid cron token")


async def manda_su_telegram(app: FastAPI, testo: str, foto: bytes | None, pulsanti_uscita: bool) -> None:
    """Gira subito dopo la risposta (BackgroundTasks): chi chiama non aspetta Telegram."""
    applicazione = app.state.telegram
    if applicazione is None:
        scrivi_allarme_nel_log(testo, foto)
        return
    await manda_a_tutte_le_chat(applicazione.bot, app.state.archivio, testo, foto, pulsanti_uscita)


def personalizzazione_o_404(archivio: ArchivioDatabase) -> Personalizzazione:
    personalizzazione = archivio.leggi_personalizzazione()
    if personalizzazione is None:
        raise HTTPException(status_code=404, detail="The demo home is not configured yet")
    return personalizzazione


def fuso_della_casa(archivio: ArchivioDatabase) -> str:
    personalizzazione = archivio.leggi_personalizzazione()
    if personalizzazione is None:
        return FUSO_ORARIO_PREDEFINITO
    return personalizzazione.fuso_orario


def eventi_dei_giorni(
    archivio: ArchivioDatabase,
    dal: datetime.date | None,
    al: datetime.date | None,
    fuso_orario: str,
    tipo: str | None,
) -> list[EventoBase]:
    """Gli eventi coordinati dei giorni da `dal` ad `al` compresi, contati nel fuso orario della casa.
    None: nessun limite."""
    inizio = None
    if dal is not None:
        inizio = inizio_del_giorno(dal, fuso_orario)
    fine = None
    if al is not None:
        fine = inizio_del_giorno(al + datetime.timedelta(days=1), fuso_orario)
    eventi = []
    for coordinato in leggi_coordinati(archivio, inizio, fine, tipo):
        eventi.append(coordinato.evento)
    return eventi


def leggi_coordinati(
    archivio: ArchivioDatabase,
    dal: datetime.datetime | None,
    al: datetime.datetime | None,
    tipo: str | None,
) -> list[Coordinato]:
    """Gli eventi coordinati con inizio da `dal` (compreso) ad `al` (escluso), dai grezzi salvati (API.md:
    web app, report e Telegram usano solo questi)."""
    inizio_lettura = None
    if dal is not None:
        inizio_lettura = dal - MARGINE_COORDINAMENTO
    fine_lettura = None
    if al is not None:
        fine_lettura = al + MARGINE_COORDINAMENTO
    grezzi = archivio.leggi_grezzi(inizio_lettura, fine_lettura, tipo)
    personalizzazione = archivio.leggi_personalizzazione()
    scelti = []
    for coordinato in coordina(grezzi):
        if dal is not None and coordinato.evento.inizio < dal:
            continue
        if al is not None and coordinato.evento.inizio >= al:
            continue
        coordinato.evento = con_regole_del_backend(coordinato.evento, personalizzazione)
        scelti.append(coordinato)
    return scelti


def coordinato_del_grezzo(archivio: ArchivioDatabase, id_grezzo: str) -> Coordinato | None:
    """L'evento coordinato di cui fa parte un grezzo (l'id di un coordinato è quello del suo primo grezzo)."""
    grezzo = archivio.leggi_grezzo(id_grezzo)
    if grezzo is None:
        return None
    dal = grezzo.inizio - MARGINE_COORDINAMENTO
    al = fine_o_inizio(grezzo) + MARGINE_COORDINAMENTO
    for coordinato in coordina(archivio.leggi_grezzi(dal, al, grezzo.tipo)):
        if id_grezzo in coordinato.grezzi:
            coordinato.evento = con_regole_del_backend(coordinato.evento, archivio.leggi_personalizzazione())
            return coordinato
    return None


def report_di_periodo(
    archivio: ArchivioDatabase,
    tipo: Literal["settimanale", "mensile"],
    dal: datetime.date,
    al: datetime.date,
) -> ReportPeriodo:
    personalizzazione = personalizzazione_o_404(archivio)
    # un giorno in più prima e dopo: le dosi vicine alla mezzanotte si possono prendere nel giorno accanto
    un_giorno = datetime.timedelta(days=1)
    eventi = eventi_dei_giorni(archivio, dal - un_giorno, al + un_giorno, personalizzazione.fuso_orario, None)
    return calcola_report_periodo(tipo, dal, al, eventi, personalizzazione, adesso())


def leggi_foto_prova(evento: EventoBase) -> bytes | None:
    """La foto di prova arriva in base64 (contratti/eventi.py); None se l'evento non ce l'ha."""
    if evento.foto_prova is None:
        return None
    try:
        return base64.b64decode(evento.foto_prova, validate=True)
    except ValueError:
        # anche binascii.Error è un ValueError; un carattere non ASCII dà un ValueError semplice
        raise HTTPException(status_code=422, detail="foto_prova of event " + evento.id + " is not valid base64")


# --- casa demo: lettura pubblica per la web app ---

@app.get("/demo/personalizzazione", response_model=Personalizzazione)
def personalizzazione_demo(request: Request) -> Personalizzazione:
    return personalizzazione_o_404(request.app.state.archivio)


@app.get("/demo/periodo", response_model=PeriodoDemo)
def periodo_demo(request: Request) -> PeriodoDemo:
    """Primo e ultimo giorno con eventi: la web app ci apre lo storico e i trend."""
    archivio = request.app.state.archivio
    primo, ultimo = archivio.inizio_primo_e_ultimo()
    if primo is None:
        return PeriodoDemo(dal=None, al=None)
    fuso_orario = fuso_della_casa(archivio)
    return PeriodoDemo(dal=giorno_locale(primo, fuso_orario), al=giorno_locale(ultimo, fuso_orario))


@app.get("/demo/eventi", response_model=list[Evento])
def eventi_demo(
    request: Request,
    dal: datetime.date | None = None,
    al: datetime.date | None = None,
    tipo: str | None = None,
) -> list[EventoBase]:
    """Eventi dei giorni da `dal` ad `al` compresi, in ordine di inizio; `foto_prova` sempre null (c'è /foto)."""
    archivio = request.app.state.archivio
    return eventi_dei_giorni(archivio, dal, al, fuso_della_casa(archivio), tipo)


@app.get(
    "/demo/eventi/{id_evento}/foto",
    response_class=Response,
    responses={200: {"content": {"image/jpeg": {}}}, 404: {"description": "No photo for this event"}},
)
def foto_evento_demo(request: Request, id_evento: str) -> Response:
    """La foto dell'evento coordinato: quella del suo grezzo più sicuro che ne ha una."""
    archivio = request.app.state.archivio
    coordinato = coordinato_del_grezzo(archivio, id_evento)
    if coordinato is None or coordinato.id_foto is None:
        raise HTTPException(status_code=404, detail="No photo for this event")
    return Response(content=archivio.leggi_foto(coordinato.id_foto), media_type="image/jpeg")


@app.get("/demo/report/giornaliero", response_model=ReportGiornaliero)
def report_giornaliero_demo(request: Request, data: datetime.date) -> ReportGiornaliero:
    archivio = request.app.state.archivio
    personalizzazione = personalizzazione_o_404(archivio)
    # anche il giorno prima e dopo: le dosi vicine alla mezzanotte si possono prendere nel giorno accanto
    un_giorno = datetime.timedelta(days=1)
    eventi = eventi_dei_giorni(archivio, data - un_giorno, data + un_giorno, personalizzazione.fuso_orario, None)
    return calcola_report_giornaliero(data, eventi, personalizzazione, adesso())


@app.get("/demo/report/settimanale", response_model=ReportPeriodo)
def report_settimanale_demo(request: Request, dal: datetime.date) -> ReportPeriodo:
    primo, ultimo = giorni_della_settimana(dal)
    return report_di_periodo(request.app.state.archivio, "settimanale", primo, ultimo)


@app.get("/demo/report/mensile", response_model=ReportPeriodo)
def report_mensile_demo(
    request: Request,
    mese: Annotated[str, Query(pattern=r"^\d{4}-\d{2}$", examples=["2026-12"])],
) -> ReportPeriodo:
    anno = int(mese[0:4])
    numero_mese = int(mese[5:7])
    try:
        primo, ultimo = giorni_del_mese(anno, numero_mese)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid month: " + mese)
    return report_di_periodo(request.app.state.archivio, "mensile", primo, ultimo)


# --- programma di casa: con il suo token ---

@app.put(
    "/programma-casa/personalizzazione",
    response_model=Personalizzazione,
    dependencies=[Depends(controlla_token_casa)],
)
def ricevi_personalizzazione(request: Request, personalizzazione: Personalizzazione) -> Personalizzazione:
    errore = errore_nella_personalizzazione(personalizzazione)
    if errore is not None:
        raise HTTPException(status_code=422, detail=errore)
    return request.app.state.archivio.salva_personalizzazione(personalizzazione)


@app.post("/programma-casa/eventi", response_model=RispostaEventi, dependencies=[Depends(controlla_token_casa)])
def ricevi_eventi(request: Request, eventi: list[Evento], compiti: BackgroundTasks) -> RispostaEventi:
    """Salva i grezzi nuovi (un id già visto viene ignorato) e fa partire subito gli allarmi urgenti, uno per
    evento coordinato (API.md, "Coordinamento degli eventi")."""
    archivio = request.app.state.archivio
    # prima si leggono tutte le foto: se una è sbagliata non si salva niente
    foto_degli_eventi = []
    for evento in eventi:
        foto_degli_eventi.append(leggi_foto_prova(evento))

    personalizzazione = archivio.leggi_personalizzazione()
    sono_nuovi = archivio.aggiungi_grezzi(eventi, foto_degli_eventi)
    nuovi = 0
    for evento, nuovo in zip(eventi, sono_nuovi):
        # un grezzo rimandato non fa ripartire l'allarme
        if not nuovo:
            continue
        nuovi = nuovi + 1
        if evento.tipo in TIPI_URGENTI:
            controlla_allarme(request.app, evento.id, personalizzazione, compiti)
    return RispostaEventi(ricevuti=len(eventi), nuovi=nuovi)


def controlla_allarme(
    app: FastAPI, id_grezzo: str, personalizzazione: Personalizzazione | None, compiti: BackgroundTasks
) -> None:
    """Un allarme per evento coordinato: un doppione (da un'altra telecamera o arrivato dopo) aggiorna l'evento
    coordinato ma non rimanda il messaggio."""
    archivio = app.state.archivio
    coordinato = coordinato_del_grezzo(archivio, id_grezzo)
    if not serve_allarme(coordinato.evento, personalizzazione):
        return
    if archivio.allarme_gia_mandato(coordinato.grezzi):
        return
    archivio.segna_allarme(id_grezzo)
    foto = None
    if coordinato.id_foto is not None:
        foto = archivio.leggi_foto(coordinato.id_foto)
    messaggio = messaggio_allarme(coordinato.evento, personalizzazione)
    # i pulsanti pausa / spegni solo sui messaggi di uscita (D16)
    pulsanti_uscita = coordinato.evento.tipo == "uscita"
    compiti.add_task(manda_su_telegram, app, messaggio, foto, pulsanti_uscita)


# --- cron esterno ogni 5-10 minuti (D39): promemoria delle dosi e server sveglio ---

@app.post("/cron/controlli", response_model=RispostaControlli, dependencies=[Depends(controlla_token_cron)])
def controlli_periodici(request: Request, compiti: BackgroundTasks) -> RispostaControlli:
    archivio = request.app.state.archivio
    personalizzazione = archivio.leggi_personalizzazione()
    if personalizzazione is None:
        return RispostaControlli(promemoria=0)
    momento = adesso()
    oggi = giorno_locale(momento, personalizzazione.fuso_orario)
    # da due giorni fa: le dosi di ieri possono essere prese (o saltate) a cavallo della mezzanotte
    due_giorni_fa = oggi - datetime.timedelta(days=2)
    eventi = eventi_dei_giorni(archivio, due_giorni_fa, oggi, personalizzazione.fuso_orario, None)
    mandati = 0
    for chiave, testo in promemoria_da_mandare(personalizzazione, eventi, momento):
        # segnato prima di mandarlo: con il cron ogni pochi minuti lo stesso promemoria non parte due volte
        if archivio.segna_promemoria(chiave):
            compiti.add_task(manda_su_telegram, request.app, testo, None, False)
            mandati = mandati + 1
    return RispostaControlli(promemoria=mandati)


# --- webhook di Telegram (D37, D39): comandi e pulsanti quando il server è online ---

@app.post("/telegram/webhook", include_in_schema=False)
async def webhook_telegram(request: Request) -> Response:
    # Telegram rimanda il segreto dato con set_webhook: così nessun altro può fingersi Telegram
    segreto = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if not segreto_giusto(segreto, request.app.state.segreto_webhook):
        raise HTTPException(status_code=401, detail="Invalid webhook secret")
    applicazione = request.app.state.telegram
    if applicazione is None:
        raise HTTPException(status_code=503, detail="Telegram bot not configured")
    dati = await request.json()
    await applicazione.process_update(Update.de_json(dati, applicazione.bot))
    return Response(status_code=200)
