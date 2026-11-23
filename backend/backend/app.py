"""API del backend SAGE (contratti/API.md): lettura pubblica della casa demo per la web app e chiamate del
programma di casa con il suo token. Documentazione automatica su /docs.

Avvio in sviluppo, dalla radice del repo:  uv run uvicorn backend.app:app --reload
Variabili d'ambiente (in sviluppo nel file backend/.env, mai nel repo; online nelle impostazioni del servizio):
- TOKEN_CASA: il token "Bearer" del programma di casa, lo stesso che ha nel suo .env.
- DATABASE_URL: l'indirizzo PostgreSQL (Neon) online; se manca si usa il file SQLite backend/sage.sqlite3.
"""

import base64
import datetime
from contextlib import asynccontextmanager
import os
import secrets
from pathlib import Path
from typing import Annotated, Literal

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from contratti.configurazione import Personalizzazione
from contratti.eventi import Evento, EventoBase
from contratti.report import ReportGiornaliero, ReportPeriodo

from backend.allarmi import messaggio_allarme, scrivi_allarme_nel_log, serve_allarme
from backend.archivio import ArchivioDatabase
from backend.regole import FUSO_ORARIO_PREDEFINITO, errore_nella_personalizzazione
from backend.report import (
    calcola_report_giornaliero,
    calcola_report_periodo,
    giorni_del_mese,
    giorni_della_settimana,
    inizio_del_giorno,
)

CARTELLA_BACKEND = Path(__file__).parent.parent
# il database di sviluppo, ignorato da git
SQLITE_PREDEFINITO = CARTELLA_BACKEND / "sage.sqlite3"


@asynccontextmanager
async def ciclo_di_vita(app: FastAPI):
    """All'avvio del server: segreti e database (FastAPI vuole un generatore: prima di yield l'avvio, dopo la
    chiusura). I test non lo fanno partire: mettono loro nello stato un database di prova e token di prova."""
    # backend/.env; le variabili già impostate (es. sul server online) hanno la precedenza
    load_dotenv(CARTELLA_BACKEND / ".env")
    app.state.token_casa = os.environ.get("TOKEN_CASA", "")
    indirizzo_database = os.environ.get("DATABASE_URL", "")
    if indirizzo_database == "":
        indirizzo_database = str(SQLITE_PREDEFINITO)
    app.state.archivio = ArchivioDatabase(indirizzo_database)
    # riceve (testo, foto JPEG o None); il bot Telegram lo sostituirà
    app.state.invia_allarme = scrivi_allarme_nel_log
    yield


app = FastAPI(title="SAGE backend", description="Safety Alert Guardian Engine: demo home API", lifespan=ciclo_di_vita)
# CORS aperto: la web app sta su un altro indirizzo e legge solo i dati pubblici della casa demo (D27)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# auto_error=False: senza token la risposta la decide controlla_token_casa (401)
lettore_token = HTTPBearer(auto_error=False)


class RispostaEventi(BaseModel):
    ricevuti: int
    # quelli con un id mai visto prima: gli altri sono stati ignorati
    nuovi: int


def adesso() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


def controlla_token_casa(
    request: Request,
    credenziali: Annotated[HTTPAuthorizationCredentials | None, Depends(lettore_token)],
) -> None:
    """Le chiamate /programma-casa/* vogliono il token del programma di casa (API.md)."""
    token_atteso = request.app.state.token_casa
    # senza TOKEN_CASA configurato nessuno può scrivere
    if credenziali is None or token_atteso == "":
        raise HTTPException(status_code=401, detail="Missing home token")
    # confronto a tempo costante: non dice quanti caratteri del token sono giusti
    if not secrets.compare_digest(credenziali.credentials.encode(), token_atteso.encode()):
        raise HTTPException(status_code=401, detail="Invalid home token")


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
    """Gli eventi dei giorni da `dal` ad `al` compresi, contati nel fuso orario della casa. None: nessun limite."""
    inizio = None
    if dal is not None:
        inizio = inizio_del_giorno(dal, fuso_orario)
    fine = None
    if al is not None:
        fine = inizio_del_giorno(al + datetime.timedelta(days=1), fuso_orario)
    return archivio.leggi_eventi(inizio, fine, tipo)


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
    foto = request.app.state.archivio.leggi_foto(id_evento)
    if foto is None:
        raise HTTPException(status_code=404, detail="No photo for this event")
    return Response(content=foto, media_type="image/jpeg")


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
def ricevi_eventi(request: Request, eventi: list[Evento]) -> RispostaEventi:
    """Salva gli eventi nuovi (un id già visto viene ignorato) e fa partire subito gli allarmi urgenti."""
    archivio = request.app.state.archivio
    # prima si leggono tutte le foto: se una è sbagliata non si salva niente
    foto_degli_eventi = []
    for evento in eventi:
        foto_degli_eventi.append(leggi_foto_prova(evento))

    personalizzazione = archivio.leggi_personalizzazione()
    sono_nuovi = archivio.aggiungi_eventi(eventi, foto_degli_eventi)
    nuovi = 0
    for evento, foto, nuovo in zip(eventi, foto_degli_eventi, sono_nuovi):
        if not nuovo:
            continue
        nuovi = nuovi + 1
        # solo gli eventi nuovi: un evento rimandato non fa ripartire l'allarme
        if serve_allarme(evento, personalizzazione):
            messaggio = messaggio_allarme(evento, personalizzazione)
            request.app.state.invia_allarme(messaggio, foto)
    return RispostaEventi(ricevuti=len(eventi), nuovi=nuovi)
