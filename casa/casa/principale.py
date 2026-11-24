"""Programma di casa di SAGE: legge le telecamere del file di configurazione, fa la percezione condivisa, passa ogni
osservazione agli analizzatori, salva gli eventi grezzi nel registro locale e li manda al backend.

Uso dalla radice del repo (D6, D23: i video registrati si elaborano sul PC di Marco o su Kaggle):
    uv run python -m casa --configurazione casa/configurazione.json --ora-inizio 2026-12-01T08:00:00+01:00

Ora vera degli eventi (PROVVISORIO, da far scegliere a Marco): ora di inizio + secondi della sorgente. Per i file
video l'ora di inizio è --ora-inizio (l'ora in cui è cominciata la registrazione); senza, e per le telecamere dal
vivo, è l'ora in cui parte il programma.
Indirizzo del backend e token della casa sono variabili d'ambiente, di solito scritte nel file .env (mai nel repo):
    INDIRIZZO_BACKEND=https://...
    TOKEN_CASA=...        (stesso nome che usa il backend)
Senza questi due valori il programma lavora senza rete e salva solo nel registro locale.
"""

import argparse
from dataclasses import dataclass
import datetime
import os
import time
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

from contratti.configurazione import ConfigurazioneCasa, Personalizzazione, TelecameraLocale
from contratti.eventi import TIPI_URGENTI

from casa.alzata_notturna import AnalizzatoreAlzataNotturna, AnalizzatorePresenzaNotturna
from casa.bevuta import AnalizzatoreBevuta
from casa.configurazione import leggi_configurazione
from casa.invio import SECONDI_TRA_LOTTI, Backend, invia_in_sospeso
from casa.percezione import POSA_PREDEFINITA, RILEVATORE_PREDEFINITO, Percezione
from casa.registro import RegistroLocale
from casa.sorgenti import apri_sorgente
from casa.uscita import AnalizzatoreUscita
from casa.zone import zone_del_tipo

# Provvisorio: da far scegliere a Marco con le misure di velocità sulla CPU.
FPS_PREDEFINITI = 5


@dataclass
class Telecamera:
    """Una telecamera mentre il programma gira."""

    id: str
    stanza: str
    sorgente: object      # VideoRegistrato o FlussoDalVivo
    analizzatori: list
    usa_oggetti: bool     # qualche analizzatore ha bisogno del rilevatore di oggetti
    tracker: object = None


def crea_analizzatori(telecamera: TelecameraLocale, personalizzazione: Personalizzazione) -> list:
    analizzatori = []
    for nome in telecamera.analizzatori:
        if nome == "uscita":
            analizzatori.append(AnalizzatoreUscita(telecamera))
        elif nome == "bevuta":
            analizzatori.append(AnalizzatoreBevuta(telecamera, personalizzazione))
        elif nome == "alzata_notturna":
            notte = personalizzazione.regole.orari_notte
            # senza zona letto la telecamera dice solo che di notte qualcuno è passato di qui
            if len(zone_del_tipo(telecamera, "letto")) > 0:
                analizzatori.append(AnalizzatoreAlzataNotturna(telecamera, notte))
            else:
                analizzatori.append(AnalizzatorePresenzaNotturna(telecamera, notte))
        else:
            print("telecamera " + telecamera.id + ": analizzatore " + nome + " non ancora disponibile")
    return analizzatori


def prepara_telecamere(configurazione: ConfigurazioneCasa, fps: float) -> list:
    telecamere = []
    for telecamera_locale in configurazione.telecamere:
        analizzatori = crea_analizzatori(telecamera_locale, configurazione.personalizzazione)
        usa_oggetti = False
        for analizzatore in analizzatori:
            if analizzatore.usa_oggetti:
                usa_oggetti = True
        sorgente = apri_sorgente(telecamera_locale.sorgente, fps, telecamera_locale.id)
        telecamera = Telecamera(telecamera_locale.id, telecamera_locale.stanza, sorgente, analizzatori, usa_oggetti)
        telecamere.append(telecamera)
    return telecamere


def registra(eventi: list, registro: RegistroLocale, backend: Backend | None) -> None:
    """Salva gli eventi grezzi degli analizzatori; se c'è un urgente lo manda subito (allarme Telegram, D10).
    Niente fusione qui: i doppioni tra telecamere li coordina il backend (API.md, Marco 24/11)."""
    c_e_un_urgente = False
    for evento in eventi:
        registro.salva(evento)
        ora = evento.inizio.strftime("%Y-%m-%d %H:%M:%S")
        print(ora + "  " + evento.tipo + "  " + evento.stanza + "  confidenza " + format(evento.confidenza, ".2f"))
        if evento.tipo in TIPI_URGENTI:
            c_e_un_urgente = True
    if c_e_un_urgente and backend is not None:
        invia_in_sospeso(registro, backend, True)


def fine_sorgente(telecamera: Telecamera, registro: RegistroLocale, backend: Backend | None) -> None:
    """La sorgente è finita (fine del video o flusso interrotto): gli analizzatori chiudono quello che è in corso."""
    print("telecamera " + telecamera.id + ": sorgente finita")
    for analizzatore in telecamera.analizzatori:
        registra(analizzatore.fine(), registro, backend)


def elabora(telecamere: list, percezione, registro: RegistroLocale, backend: Backend | None,
            ora_inizio: datetime.datetime) -> None:
    """Ciclo principale: un fotogramma per telecamera a turno, finché tutte le sorgenti sono finite.
    Con i file video le telecamere avanzano insieme nel tempo del video."""
    for telecamera in telecamere:
        telecamera.tracker = percezione.nuovo_tracker()
    ultimo_lotto = time.monotonic()
    while True:
        tutte_finite = True
        elaborato_qualcosa = False
        for telecamera in telecamere:
            if telecamera.sorgente.finita:
                continue
            tutte_finite = False
            fotogramma = telecamera.sorgente.leggi()
            if fotogramma is None:
                if telecamera.sorgente.finita:
                    fine_sorgente(telecamera, registro, backend)
                continue
            elaborato_qualcosa = True
            ora = ora_inizio + datetime.timedelta(seconds=fotogramma.secondi)
            osservazione = percezione.osserva(fotogramma.immagine, telecamera.tracker, telecamera.usa_oggetti,
                                              telecamera.id, telecamera.stanza, ora)
            for analizzatore in telecamera.analizzatori:
                registra(analizzatore.elabora(osservazione), registro, backend)
        if tutte_finite:
            break
        if backend is not None and time.monotonic() - ultimo_lotto >= SECONDI_TRA_LOTTI:
            invia_in_sospeso(registro, backend, False)
            ultimo_lotto = time.monotonic()
        if not elaborato_qualcosa:
            time.sleep(0.01)  # telecamere dal vivo: nessun fotogramma pronto, si aspetta un attimo
    if backend is not None:
        invia_in_sospeso(registro, backend, False)


def leggi_backend(percorso_env: str) -> Backend | None:
    """Backend dalle variabili d'ambiente (il file .env le aggiunge senza sovrascrivere quelle già impostate).
    None (niente rete, solo registro locale) se mancano indirizzo o token. Il token non si stampa mai."""
    load_dotenv(percorso_env)
    indirizzo = os.environ.get("INDIRIZZO_BACKEND")
    token = os.environ.get("TOKEN_CASA")
    if not indirizzo or not token:
        print("mancano INDIRIZZO_BACKEND o TOKEN_CASA: gli eventi restano solo nel registro locale")
        return None
    return Backend(indirizzo, token)


def ora_di_inizio(testo: str | None, fuso: ZoneInfo) -> datetime.datetime:
    """--ora-inizio (ISO 8601; senza fuso vale quello della casa), altrimenti adesso. Sempre nel fuso della casa,
    perché gli orari di notte si confrontano con l'ora locale."""
    if testo is None:
        return datetime.datetime.now(fuso)
    ora = datetime.datetime.fromisoformat(testo)
    if ora.tzinfo is None:
        ora = ora.replace(tzinfo=fuso)
    return ora.astimezone(fuso)


def main(argomenti: list | None = None) -> None:
    lettore = argparse.ArgumentParser(description="Programma di casa di SAGE")
    lettore.add_argument("--configurazione", required=True, help="file JSON nel formato ConfigurazioneCasa")
    lettore.add_argument("--ora-inizio", help="ora vera del primo fotogramma dei video, es. 2026-12-01T08:00+01:00")
    lettore.add_argument("--fps", type=float, default=FPS_PREDEFINITI, help="fotogrammi al secondo per telecamera")
    lettore.add_argument("--registro", default="data/registro_casa.sqlite3", help="registro locale degli eventi")
    lettore.add_argument("--env", default=".env", help="file con INDIRIZZO_BACKEND e TOKEN_CASA")
    scelte = lettore.parse_args(argomenti)

    configurazione = leggi_configurazione(scelte.configurazione)
    fuso = ZoneInfo(configurazione.personalizzazione.fuso_orario)
    if scelte.ora_inizio is None:
        print("senza --ora-inizio i video registrati partono dall'ora attuale")
    ora_inizio = ora_di_inizio(scelte.ora_inizio, fuso)
    registro = RegistroLocale(scelte.registro)
    backend = leggi_backend(scelte.env)
    if backend is not None:
        backend.invia_personalizzazione(configurazione.personalizzazione)
        invia_in_sospeso(registro, backend, False)  # quelli rimasti indietro dall'ultima volta

    telecamere = prepara_telecamere(configurazione, scelte.fps)
    serve_rilevatore = False
    for telecamera in telecamere:
        if telecamera.usa_oggetti:
            serve_rilevatore = True
    percorso_rilevatore = None
    if serve_rilevatore:
        percorso_rilevatore = RILEVATORE_PREDEFINITO
    percezione = Percezione(POSA_PREDEFINITA, percorso_rilevatore)
    elabora(telecamere, percezione, registro, backend, ora_inizio)
    registro.chiudi()
