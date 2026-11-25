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
from collections import deque
import copy
from dataclasses import dataclass, field
import datetime
import os
from pathlib import Path
import time
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

from contratti.configurazione import ConfigurazioneCasa, Personalizzazione, TelecameraLocale
from contratti.eventi import TIPI_URGENTI

from casa.alzata_notturna import AnalizzatoreAlzataNotturna, AnalizzatorePresenzaNotturna
from casa.bevuta import AnalizzatoreBevuta
from casa.caduta import AnalizzatoreCaduta
from casa.configurazione import leggi_configurazione
from casa.farmaco import AnalizzatoreFarmaco
from casa.invio import SECONDI_TRA_LOTTI, Backend, invia_in_sospeso
from casa.pasto import AnalizzatorePasto, ModelloPiatto
from casa.percezione import POSA_PREDEFINITA, RILEVATORE_PREDEFINITO, Percezione
from casa.registro import RegistroLocale
from casa.riconoscimento_farmaci import RiconoscitoreFarmaci, crea_riconoscitore
from casa.segni import RilevatoreSegni
from casa.sorgenti import Fotogramma, apri_sorgente
from casa.uscita import AnalizzatoreUscita, ModelloPorta
from casa.zone import zone_del_tipo

# Fotogrammi al secondo (Marco, 25/11): le sorgenti si leggono a 10 al secondo e se ne analizza uno su due (5 al
# secondo). Al primo segno di un evento (segni.py) si torna indietro di 5 fotogrammi analizzati (1 s) e si analizzano
# tutti, fino a qualche secondo dopo l'ultimo segno; poi di nuovo 5 al secondo.
FPS_LETTURA = 10
FPS_NORMALI = 5
# si analizza un fotogramma se dall'ultimo analizzato è passato almeno questo: uno su due a 10 al secondo, tutti con
# un video a 5 al secondo; mezzo passo di tolleranza per i tempi irregolari dei flussi dal vivo
SECONDI_TRA_ANALIZZATI = 1 / FPS_NORMALI - 0.5 / FPS_LETTURA
PASSI_INDIETRO = 5
FOTOGRAMMI_IN_MEMORIA = 11         # l'ultimo secondo letto a 10 al secondo, più quello di adesso
SECONDI_DOPO_IL_SEGNO = 3.0        # si resta a 10 al secondo fino a tanto dopo l'ultimo segno

# Modelli specialisti allenati (25/11), grandezza n come consiglia l'agente di allenamento: stessa precisione della s
# a metà del tempo. Pesi copiati da runs/ del worktree allenamento (mai nel repo).
PESI_PORTA = "pesi/porta_yolo26n.pt"
PESI_CIBO = "pesi/cibo_yolo26n.pt"


@dataclass
class Specialisti:
    """Modelli che girano solo quando servono. None se mancano i pesi: allora resta la regola provvisoria."""

    riconoscitore: RiconoscitoreFarmaci | None = None
    porta: ModelloPorta | None = None
    piatto: ModelloPiatto | None = None


def carica_specialisti(configurazione: ConfigurazioneCasa) -> Specialisti:
    """Carica una volta sola i modelli che servono alle telecamere della configurazione."""
    nomi = []
    for telecamera_locale in configurazione.telecamere:
        for nome in telecamera_locale.analizzatori:
            nomi.append(nome)
    specialisti = Specialisti()
    if "farmaco" in nomi:
        specialisti.riconoscitore = crea_riconoscitore(configurazione.personalizzazione,
                                                       configurazione.cartella_foto_farmaci)
    if "uscita" in nomi:
        if Path(PESI_PORTA).exists():
            specialisti.porta = ModelloPorta(PESI_PORTA)
        else:
            print("pesi della porta mancanti (" + PESI_PORTA + "): porta aperta dalla regola dell'aspetto")
    if "pasto" in nomi:
        if Path(PESI_CIBO).exists():
            specialisti.piatto = ModelloPiatto(PESI_CIBO)
        else:
            print("pesi del cibo mancanti (" + PESI_CIBO + "): quanto ha mangiato non si misura")
    return specialisti


@dataclass
class StatoTelecamera:
    """Quello che cambia a ogni fotogramma analizzato: si copia per poterci tornare."""

    tracker: object
    analizzatori: list
    segni: RilevatoreSegni


@dataclass
class Letto:
    numero: int               # quanti fotogrammi la sorgente aveva già dato prima di questo
    fotogramma: Fotogramma


@dataclass
class Passo:
    """Un fotogramma analizzato dell'ultimo secondo: lo stato di prima, per tornarci, e gli eventi che ha dato. Gli
    eventi partono solo quando il passo esce dall'ultimo secondo, perché un ritorno indietro li rifà."""

    numero: int
    stato: StatoTelecamera
    eventi: list


@dataclass
class Telecamera:
    """Una telecamera mentre il programma gira."""

    id: str
    stanza: str
    sorgente: object      # VideoRegistrato o FlussoDalVivo
    analizzatori: list
    usa_oggetti: bool     # qualche analizzatore ha bisogno del rilevatore di oggetti
    segni: RilevatoreSegni
    tracker: object = None
    letti: deque = field(default_factory=deque)   # ultimi FOTOGRAMMI_IN_MEMORIA fotogrammi letti (Letto)
    passi: deque = field(default_factory=deque)   # ultimi PASSI_INDIETRO + 1 fotogrammi analizzati (Passo)
    letti_finora: int = 0
    secondi_ultimo_analizzato: float | None = None
    veloce_fino_a: datetime.datetime | None = None  # 10 al secondo fino a quest'ora


def crea_analizzatori(telecamera: TelecameraLocale, personalizzazione: Personalizzazione,
                      specialisti: Specialisti) -> list:
    analizzatori = []
    for nome in telecamera.analizzatori:
        if nome == "uscita":
            analizzatori.append(AnalizzatoreUscita(telecamera, specialisti.porta))
        elif nome == "caduta":
            analizzatori.append(AnalizzatoreCaduta(telecamera))
        elif nome == "bevuta":
            analizzatori.append(AnalizzatoreBevuta(telecamera, personalizzazione))
        elif nome == "farmaco":
            analizzatori.append(AnalizzatoreFarmaco(telecamera, specialisti.riconoscitore))
        elif nome == "pasto":
            analizzatori.append(AnalizzatorePasto(telecamera, specialisti.piatto))
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


def prepara_telecamere(configurazione: ConfigurazioneCasa, fps: float, specialisti: Specialisti) -> list:
    telecamere = []
    for telecamera_locale in configurazione.telecamere:
        analizzatori = crea_analizzatori(telecamera_locale, configurazione.personalizzazione, specialisti)
        usa_oggetti = False
        for analizzatore in analizzatori:
            if analizzatore.usa_oggetti:
                usa_oggetti = True
        sorgente = apri_sorgente(telecamera_locale.sorgente, fps, telecamera_locale.id)
        segni = RilevatoreSegni(telecamera_locale)
        telecamera = Telecamera(telecamera_locale.id, telecamera_locale.stanza, sorgente, analizzatori, usa_oggetti,
                                segni)
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
    """La sorgente è finita (fine del video o flusso interrotto): partono gli eventi dell'ultimo secondo e gli
    analizzatori chiudono quello che è in corso."""
    print("telecamera " + telecamera.id + ": sorgente finita")
    for passo in telecamera.passi:
        registra(passo.eventi, registro, backend)
    telecamera.passi.clear()
    for analizzatore in telecamera.analizzatori:
        registra(analizzatore.fine(), registro, backend)


def copia_dello_stato(telecamera: Telecamera) -> StatoTelecamera:
    # meno di 1 ms; i modelli dentro gli analizzatori non si copiano (__deepcopy__ che ridà sé stesso)
    stato = StatoTelecamera(telecamera.tracker, telecamera.analizzatori, telecamera.segni)
    return copy.deepcopy(stato)


def analizza(telecamera: Telecamera, letto: Letto, percezione, ora_inizio: datetime.datetime,
             registro: RegistroLocale, backend: Backend | None) -> bool:
    """Percezione e analizzatori su un fotogramma letto. True se c'è il segno di un evento."""
    stato_prima = copia_dello_stato(telecamera)
    fotogramma = letto.fotogramma
    ora = ora_inizio + datetime.timedelta(seconds=fotogramma.secondi)
    osservazione = percezione.osserva(fotogramma.immagine, telecamera.tracker, telecamera.usa_oggetti,
                                      telecamera.id, telecamera.stanza, ora)
    eventi = []
    for analizzatore in telecamera.analizzatori:
        for evento in analizzatore.elabora(osservazione):
            eventi.append(evento)
    segno = telecamera.segni.c_e_un_segno(osservazione)
    if segno:
        telecamera.veloce_fino_a = ora + datetime.timedelta(seconds=SECONDI_DOPO_IL_SEGNO)
    telecamera.secondi_ultimo_analizzato = fotogramma.secondi
    telecamera.passi.append(Passo(letto.numero, stato_prima, eventi))
    if len(telecamera.passi) > PASSI_INDIETRO + 1:
        uscito = telecamera.passi.popleft()
        registra(uscito.eventi, registro, backend)
    return segno


def torna_indietro(telecamera: Telecamera, percezione, ora_inizio: datetime.datetime, registro: RegistroLocale,
                   backend: Backend | None) -> None:
    """Primo segno di un evento: si riparte dallo stato di PASSI_INDIETRO fotogrammi analizzati fa (1 s) e si
    rianalizzano, in ordine di tempo, tutti i fotogrammi letti da lì. Tracker e analizzatori vedono così i fotogrammi
    sempre in avanti. Gli eventi di quei passi si buttano: li rifà il ripasso."""
    primo = telecamera.passi[0]
    telecamera.tracker = primo.stato.tracker
    telecamera.analizzatori = primo.stato.analizzatori
    telecamera.segni = primo.stato.segni
    telecamera.passi.clear()
    da_ripassare = []
    for letto in telecamera.letti:
        if letto.numero >= primo.numero:
            da_ripassare.append(letto)
    for letto in da_ripassare:
        analizza(telecamera, letto, percezione, ora_inizio, registro, backend)


def nuovo_fotogramma(telecamera: Telecamera, fotogramma: Fotogramma, percezione, ora_inizio: datetime.datetime,
                     registro: RegistroLocale, backend: Backend | None) -> None:
    letto = Letto(telecamera.letti_finora, fotogramma)
    telecamera.letti_finora = telecamera.letti_finora + 1
    telecamera.letti.append(letto)
    if len(telecamera.letti) > FOTOGRAMMI_IN_MEMORIA:
        telecamera.letti.popleft()
    ora = ora_inizio + datetime.timedelta(seconds=fotogramma.secondi)
    veloce = telecamera.veloce_fino_a is not None and ora <= telecamera.veloce_fino_a
    if not veloce and telecamera.secondi_ultimo_analizzato is not None:
        if fotogramma.secondi - telecamera.secondi_ultimo_analizzato < SECONDI_TRA_ANALIZZATI:
            return  # a 5 al secondo: questo si tiene solo in memoria
    segno = analizza(telecamera, letto, percezione, ora_inizio, registro, backend)
    if segno and not veloce:
        torna_indietro(telecamera, percezione, ora_inizio, registro, backend)


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
            nuovo_fotogramma(telecamera, fotogramma, percezione, ora_inizio, registro, backend)
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
    lettore.add_argument("--fps", type=float, default=FPS_LETTURA,
                         help="fotogrammi letti al secondo per telecamera (se ne analizzano 5, 10 durante gli eventi)")
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

    telecamere = prepara_telecamere(configurazione, scelte.fps, carica_specialisti(configurazione))
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
