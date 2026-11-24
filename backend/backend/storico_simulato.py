"""Storico simulato della casa demo (D22): alcune settimane di eventi plausibili con simulato=True, per i grafici dei
trend e per la web app in sviluppo. Gli eventi passano dalla stessa chiamata del programma di casa.

Riproducibile: con lo stesso seme escono gli stessi eventi con gli stessi id, quindi rimandarli non crea doppioni.
Se la casa demo non ha ancora una personalizzazione, lo script manda quella d'esempio qui sotto.

Uso, con il backend avviato (dalla radice del repo):
    uv run python -m backend.storico_simulato --url http://127.0.0.1:8000
Il token del programma di casa (TOKEN_CASA) si legge da backend/.env, come per il server.

I PARAMETRI qui sotto sono PROPOSTE da confermare con Marco.
"""

import argparse
import datetime
import os
import random
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx2
from dotenv import load_dotenv

from contratti.configurazione import (
    Anziano,
    Contenitore,
    FasciaOraria,
    Farmaco,
    Personalizzazione,
    RegoleAllarmi,
    TelecameraPrevista,
)
from contratti.eventi import LETTORE_EVENTO, EventoBase, leggi_evento

from backend.regole import MINUTI_RITARDO_MASSIMO, dosi_previste, giorno_locale, leggi_ora, ora_nella_fascia

# dà valori tipici (con 42 usciva una sola dose saltata su 84)
SEME_PREDEFINITO = 7
SETTIMANE_PREDEFINITE = 4

# acqua bevuta in un giorno (ml): gaussiana con questa media e variazione, poi tenuta tra minimo e massimo
ACQUA_MEDIA_ML = 1250
ACQUA_VARIAZIONE_ML = 250
ACQUA_MINIMA_ML = 600
ACQUA_MASSIMA_ML = 2000
# 3 giorni di fila con poca acqua (Marco, 24/11): un calo da notare nei trend. Cadono nell'ultima settimana, così
# si vedono sia nel trend settimanale sia in quello mensile.
GIORNI_DI_POCA_ACQUA = 3
FATTORE_POCA_ACQUA = 0.5
BEVUTE_MINIME = 4
BEVUTE_MASSIME = 9

# dosi: le altre sono in orario
PROBABILITA_DOSE_SALTATA = 0.08
PROBABILITA_DOSE_IN_RITARDO = 0.15
# gesto visto ma scatola non riconosciuta (D15)
PROBABILITA_FARMACO_NON_RICONOSCIUTO = 0.05

PROBABILITA_PASTO_SALTATO = 0.05
MANGIATO_MEDIO_PERCENTUALE = 75
MANGIATO_VARIAZIONE_PERCENTUALE = 15

# alzate per notte: 0, 1, 2 o 3 con questi pesi
PESI_ALZATE_PER_NOTTE = [35, 40, 20, 5]
# un numero fisso di cadute in giorni a caso: con una probabilità al giorno potrebbero non essercene (trend vuoti)
CADUTE_PER_SETTIMANA = 0.5
USCITE_PERMESSE_MASSIME = 2
PROBABILITA_USCITA_VIETATA_AL_GIORNO = 1 / 10

# cibi in inglese: finiscono nei report (D13)
COLAZIONI = [["coffee", "biscuits"], ["milk", "bread", "jam"], ["yogurt", "fruit"], ["tea", "toast"]]
PRANZI = [["pasta", "tomato sauce"], ["rice", "vegetables"], ["minestrone"], ["chicken", "salad"],
          ["fish", "potatoes"]]
CENE = [["soup", "bread"], ["omelette", "salad"], ["ham", "cheese", "bread"], ["vegetable soup"], ["pasta", "beans"]]
# (primo minuto, ultimo minuto dalla mezzanotte, menù)
PASTI = [(7 * 60 + 30, 9 * 60, COLAZIONI), (12 * 60, 13 * 60 + 30, PRANZI), (19 * 60, 20 * 60 + 30, CENE)]
STANZE_DELLE_CADUTE = ["bathroom", "kitchen", "living room", "bedroom"]
PERCORSI_NOTTURNI = [["bedroom", "bathroom"], ["bedroom", "bathroom"], ["bedroom", "kitchen"], ["bedroom", "hall"]]

# Usata solo se la casa demo non ha ancora una personalizzazione (di solito la manda il programma di casa).
PERSONALIZZAZIONE_DEMO = Personalizzazione(
    anziano=Anziano(nome="Anna", anno_nascita=1941, obiettivo_acqua_ml=1500),
    farmaci=[
        Farmaco(id="donepezil", nome="Donepezil", dose="1 tablet", orari=["08:00"]),
        Farmaco(id="memantine", nome="Memantine", dose="1 tablet", orari=["08:00", "20:00"]),
    ],
    contenitori=[
        Contenitore(id="bicchiere", nome="Glass", tipo="bicchiere", capienza_ml=250),
        Contenitore(id="bottiglia", nome="Water bottle", tipo="bottiglia", capienza_ml=1500),
    ],
    telecamere=[
        TelecameraPrevista(id="cucina", nome="Kitchen", stanza="kitchen"),
        TelecameraPrevista(id="camera", nome="Bedroom", stanza="bedroom"),
        TelecameraPrevista(id="ingresso", nome="Front door", stanza="hall"),
    ],
    regole=RegoleAllarmi(orari_uscita_vietati=[FasciaOraria(dalle="21:00", alle="07:00")]),
)

# se la personalizzazione non ha contenitori si beve da un bicchiere
BICCHIERE = Contenitore(id="bicchiere", nome="Glass", tipo="bicchiere", capienza_ml=250)


def momento(data: datetime.date, minuti: int, fuso: ZoneInfo) -> datetime.datetime:
    """L'ora locale della casa `minuti` dopo la mezzanotte del giorno `data`."""
    mezzanotte = datetime.datetime.combine(data, datetime.time(0, 0), tzinfo=fuso)
    return mezzanotte + datetime.timedelta(minutes=minuti)


def telecamera_della_stanza(personalizzazione: Personalizzazione, stanza: str) -> str:
    for telecamera in personalizzazione.telecamere:
        if telecamera.stanza == stanza:
            return telecamera.id
    return stanza


def tra(valore: float, minimo: float, massimo: float) -> float:
    """Il valore tenuto tra minimo e massimo."""
    return min(max(valore, minimo), massimo)


def dati_evento(
    rng: random.Random,
    personalizzazione: Personalizzazione,
    tipo: str,
    inizio: datetime.datetime,
    fine: datetime.datetime | None,
    stanza: str,
    valori: dict,
) -> dict:
    """Un evento come lo manderebbe il programma di casa, senza id (lo dà eventi_del_giorno)."""
    confidenza = round(rng.uniform(0.7, 0.98), 2)
    fonte = {
        "telecamera_id": telecamera_della_stanza(personalizzazione, stanza),
        "analizzatore": tipo,
        "confidenza": confidenza,
    }
    fine_testo = None
    if fine is not None:
        fine_testo = fine.isoformat()
    return {
        "tipo": tipo,
        "inizio": inizio.isoformat(),
        "fine": fine_testo,
        "stanza": stanza,
        "confidenza": confidenza,
        "fonti": [fonte],
        "valori": valori,
        "simulato": True,
    }


def minuti_vietati(personalizzazione: Personalizzazione) -> list[int]:
    """I minuti del giorno (dalla mezzanotte) dentro un orario di uscita vietato."""
    minuti = []
    for minuto in range(24 * 60):
        ora = datetime.time(minuto // 60, minuto % 60)
        for fascia in personalizzazione.regole.orari_uscita_vietati:
            if ora_nella_fascia(ora, fascia):
                minuti.append(minuto)
                break
    return minuti


def minuti_permessi(vietati: list[int]) -> list[int]:
    """I minuti di giorno (9:30-18:00) fuori dagli orari vietati: le uscite con chi assiste l'anziano."""
    minuti = []
    for minuto in range(9 * 60 + 30, 18 * 60):
        if minuto not in vietati:
            minuti.append(minuto)
    return minuti


def bevute(
    rng: random.Random, data: datetime.date, personalizzazione: Personalizzazione, fuso: ZoneInfo, poca_acqua: bool
) -> list:
    acqua_del_giorno = tra(rng.gauss(ACQUA_MEDIA_ML, ACQUA_VARIAZIONE_ML), ACQUA_MINIMA_ML, ACQUA_MASSIMA_ML)
    if poca_acqua:
        acqua_del_giorno = acqua_del_giorno * FATTORE_POCA_ACQUA
    numero = rng.randint(BEVUTE_MINIME, BEVUTE_MASSIME)
    contenitori = personalizzazione.contenitori
    if len(contenitori) == 0:
        contenitori = [BICCHIERE]
    eventi = []
    for _ in range(numero):
        contenitore = rng.choice(contenitori)
        voluti_ml = acqua_del_giorno / numero * rng.uniform(0.7, 1.3)
        # calcolo dei ml dalla percentuale di altezza come il programma di casa (D9)
        percentuale = round(min(voluti_ml / contenitore.capienza_ml * 100, 100), 1)
        altezza_px = round(rng.uniform(120, 300), 1)
        valori = {
            "contenitore": contenitore.tipo,
            # come il programma di casa quando riconosce il contenitore: il backend ricalcola i ml con la capienza
            "contenitore_id": contenitore.id,
            "capienza_ml": contenitore.capienza_ml,
            "altezza_contenitore_px": altezza_px,
            "livello_sceso_px": round(percentuale / 100 * altezza_px, 1),
            "percentuale": percentuale,
            "ml": round(percentuale / 100 * contenitore.capienza_ml, 1),
        }
        inizio = momento(data, rng.randint(7 * 60 + 30, 21 * 60 + 30), fuso)
        eventi.append(dati_evento(rng, personalizzazione, "bevuta", inizio, None, "kitchen", valori))
    return eventi


def prese_dei_farmaci(
    rng: random.Random, data: datetime.date, personalizzazione: Personalizzazione, fuso: ZoneInfo
) -> list:
    eventi = []
    for orario, farmaco in dosi_previste(personalizzazione):
        caso = rng.random()
        if caso < PROBABILITA_DOSE_SALTATA:
            continue
        tolleranza = farmaco.tolleranza_minuti
        in_ritardo = caso < PROBABILITA_DOSE_SALTATA + PROBABILITA_DOSE_IN_RITARDO
        # in ritardo ma dentro la finestra della dose (regole.py, D38); con una tolleranza di 2 ore o più non si può
        if in_ritardo and tolleranza < MINUTI_RITARDO_MASSIMO:
            minuti = rng.randint(tolleranza + 1, MINUTI_RITARDO_MASSIMO)
        else:
            minuti = rng.randint(-(tolleranza // 3), tolleranza)
        previsto = leggi_ora(orario)
        inizio = momento(data, previsto.hour * 60 + previsto.minute + minuti, fuso)
        farmaco_id = farmaco.id
        somiglianza = round(rng.uniform(0.75, 0.97), 2)
        if rng.random() < PROBABILITA_FARMACO_NON_RICONOSCIUTO:
            farmaco_id = None
            somiglianza = None
        valori = {
            "farmaco_id": farmaco_id,
            "somiglianza": somiglianza,
            "portapillole_aperto": True,
            "mano_alla_bocca": True,
        }
        eventi.append(dati_evento(rng, personalizzazione, "farmaco", inizio, None, "kitchen", valori))
    return eventi


def pasti(rng: random.Random, data: datetime.date, personalizzazione: Personalizzazione, fuso: ZoneInfo) -> list:
    eventi = []
    for primo_minuto, ultimo_minuto, menu in PASTI:
        if rng.random() < PROBABILITA_PASTO_SALTATO:
            continue
        inizio = momento(data, rng.randint(primo_minuto, ultimo_minuto), fuso)
        fine = inizio + datetime.timedelta(minutes=rng.randint(15, 40))
        mangiato = tra(rng.gauss(MANGIATO_MEDIO_PERCENTUALE, MANGIATO_VARIAZIONE_PERCENTUALE), 10, 100)
        valori = {"cibi": rng.choice(menu), "percentuale_mangiata": round(mangiato)}
        eventi.append(dati_evento(rng, personalizzazione, "pasto", inizio, fine, "kitchen", valori))
    return eventi


def alzate_notturne(
    rng: random.Random, data: datetime.date, personalizzazione: Personalizzazione, fuso: ZoneInfo
) -> list:
    numero = rng.choices([0, 1, 2, 3], weights=PESI_ALZATE_PER_NOTTE)[0]
    eventi = []
    for _ in range(numero):
        # tra le 00:30 e le 05:30: dentro gli orari di notte predefiniti (22:00 → 07:00)
        inizio = momento(data, rng.randint(30, 5 * 60 + 30), fuso)
        fine = inizio + datetime.timedelta(minutes=rng.randint(3, 25))
        valori = {"stanze": rng.choice(PERCORSI_NOTTURNI)}
        eventi.append(dati_evento(rng, personalizzazione, "alzata_notturna", inizio, fine, "bedroom", valori))
    return eventi


def cadute_e_uscite(
    rng: random.Random,
    data: datetime.date,
    personalizzazione: Personalizzazione,
    fuso: ZoneInfo,
    vietati: list[int],
    permessi: list[int],
    con_caduta: bool,
) -> list:
    eventi = []
    if con_caduta:
        inizio = momento(data, rng.randint(8 * 60, 21 * 60), fuso)
        stanza = rng.choice(STANZE_DELLE_CADUTE)
        valori = {"secondi_a_terra": round(rng.uniform(15, 180))}
        eventi.append(dati_evento(rng, personalizzazione, "caduta", inizio, None, stanza, valori))

    if len(permessi) > 0:
        for _ in range(rng.randint(0, USCITE_PERMESSE_MASSIME)):
            inizio = momento(data, rng.choice(permessi), fuso)
            eventi.append(dati_evento(rng, personalizzazione, "uscita", inizio, None, "hall",
                                      {"zona_id": "porta-ingresso"}))

    if len(vietati) > 0 and rng.random() < PROBABILITA_USCITA_VIETATA_AL_GIORNO:
        inizio = momento(data, rng.choice(vietati), fuso)
        eventi.append(dati_evento(rng, personalizzazione, "uscita", inizio, None, "hall",
                                  {"zona_id": "porta-ingresso"}))
    return eventi


def eventi_del_giorno(
    rng: random.Random,
    data: datetime.date,
    personalizzazione: Personalizzazione,
    seme: int,
    vietati: list[int],
    permessi: list[int],
    con_caduta: bool,
    poca_acqua: bool,
) -> list[EventoBase]:
    fuso = ZoneInfo(personalizzazione.fuso_orario)
    tutti = []
    tutti.extend(bevute(rng, data, personalizzazione, fuso, poca_acqua))
    tutti.extend(prese_dei_farmaci(rng, data, personalizzazione, fuso))
    tutti.extend(pasti(rng, data, personalizzazione, fuso))
    tutti.extend(alzate_notturne(rng, data, personalizzazione, fuso))
    tutti.extend(cadute_e_uscite(rng, data, personalizzazione, fuso, vietati, permessi, con_caduta))

    eventi = []
    numero = 0
    for dati in tutti:
        numero = numero + 1
        # id leggibile e sempre uguale con lo stesso seme: rimandare lo storico non crea doppioni
        dati["id"] = "sim-" + str(seme) + "-" + data.isoformat() + "-" + str(numero).zfill(2)
        # leggi_evento controlla che l'evento rispetti il contratto
        eventi.append(leggi_evento(dati))
    return eventi


def genera_storico(
    personalizzazione: Personalizzazione, dal: datetime.date, al: datetime.date, seme: int
) -> list[EventoBase]:
    """Gli eventi simulati dei giorni da `dal` ad `al` compresi."""
    rng = random.Random(seme)
    vietati = minuti_vietati(personalizzazione)
    permessi = minuti_permessi(vietati)
    numero_giorni = (al - dal).days + 1
    numero_cadute = min(round(numero_giorni / 7 * CADUTE_PER_SETTIMANA), numero_giorni)
    # i giorni con una caduta, contati da `dal` (0 = primo giorno)
    giorni_con_caduta = rng.sample(range(numero_giorni), numero_cadute)
    # il primo dei giorni di poca acqua, tutti dentro l'ultima settimana
    primo_minimo = max(numero_giorni - 7, 0)
    primo_massimo = max(numero_giorni - GIORNI_DI_POCA_ACQUA, 0)
    primo_poca_acqua = rng.randint(primo_minimo, primo_massimo)
    eventi = []
    for indice in range(numero_giorni):
        data = dal + datetime.timedelta(days=indice)
        con_caduta = indice in giorni_con_caduta
        poca_acqua = primo_poca_acqua <= indice < primo_poca_acqua + GIORNI_DI_POCA_ACQUA
        eventi.extend(eventi_del_giorno(rng, data, personalizzazione, seme, vietati, permessi, con_caduta,
                                        poca_acqua))
    return eventi


def personalizzazione_della_casa(client: httpx2.Client, intestazioni: dict) -> Personalizzazione:
    """Quella della casa demo; se non c'è ancora si manda quella d'esempio."""
    risposta = client.get("/demo/personalizzazione")
    if risposta.status_code == 200:
        return Personalizzazione.model_validate(risposta.json())
    if risposta.status_code != 404:
        risposta.raise_for_status()
    dati = PERSONALIZZAZIONE_DEMO.model_dump(mode="json")
    risposta = client.put("/programma-casa/personalizzazione", json=dati, headers=intestazioni)
    risposta.raise_for_status()
    return Personalizzazione.model_validate(risposta.json())


def carica_storico(
    client: httpx2.Client, token: str, settimane: int, seme: int, fino_al: datetime.date | None
) -> dict:
    """Genera lo storico fino a `fino_al` compreso (None: fino a ieri) e lo manda al backend; dà {ricevuti, nuovi}."""
    intestazioni = {"Authorization": "Bearer " + token}
    personalizzazione = personalizzazione_della_casa(client, intestazioni)
    if fino_al is None:
        # fino a ieri: oggi è dei risultati veri dei modelli sui video registrati (D22)
        oggi = giorno_locale(datetime.datetime.now(datetime.UTC), personalizzazione.fuso_orario)
        fino_al = oggi - datetime.timedelta(days=1)
    dal = fino_al - datetime.timedelta(days=settimane * 7 - 1)
    eventi = genera_storico(personalizzazione, dal, fino_al, seme)

    dati_eventi = []
    for evento in eventi:
        dati_eventi.append(LETTORE_EVENTO.dump_python(evento, mode="json"))
    risposta = client.post("/programma-casa/eventi", json=dati_eventi, headers=intestazioni)
    risposta.raise_for_status()
    return risposta.json()


def main() -> None:
    parser = argparse.ArgumentParser(description="Manda al backend lo storico simulato della casa demo (D22).")
    parser.add_argument("--url", default="http://127.0.0.1:8000", help="indirizzo del backend")
    parser.add_argument("--seme", type=int, default=SEME_PREDEFINITO)
    parser.add_argument("--settimane", type=int, default=SETTIMANE_PREDEFINITE)
    parser.add_argument("--fino-al", type=datetime.date.fromisoformat, default=None,
                        help="ultimo giorno simulato, AAAA-MM-GG (predefinito: ieri)")
    argomenti = parser.parse_args()

    load_dotenv(Path(__file__).parent.parent / ".env")
    token = os.environ.get("TOKEN_CASA", "")
    if token == "":
        print("Manca TOKEN_CASA (in backend/.env o nell'ambiente).", file=sys.stderr)
        sys.exit(1)

    with httpx2.Client(base_url=argomenti.url, timeout=60) as client:
        risultato = carica_storico(client, token, argomenti.settimane, argomenti.seme, argomenti.fino_al)
    print("Eventi simulati ricevuti:", risultato["ricevuti"], "- nuovi:", risultato["nuovi"])


if __name__ == "__main__":
    main()
