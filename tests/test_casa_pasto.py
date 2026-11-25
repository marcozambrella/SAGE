"""Test dell'analizzatore pasto con un tavolo sintetico (piatto bianco, cibo arancione) e un modello del piatto finto
che vede il cibo dai pixel colorati; una prova dei pesi veri se ci sono."""

import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import cv2
import numpy as np
import pytest

from contratti.configurazione import TelecameraLocale
from contratti.eventi import LETTORE_EVENTO, leggi_evento

from casa.pasto import AnalizzatorePasto, ModelloPiatto, quanto_mangiato
from casa.percezione import Oggetto, Osservazione, Persona
from casa.principale import PESI_CIBO

ROMA = ZoneInfo("Europe/Rome")
INIZIO = datetime.datetime(2026, 12, 1, 12, 30, tzinfo=ROMA)
# tavolo: pixel 40-160 × 100-180 di un fotogramma 200×200
SALA = TelecameraLocale.model_validate({
    "id": "sala", "nome": "Dining room", "stanza": "dining room", "sorgente": "x.mp4", "analizzatori": ["pasto"],
    "zone": [{"id": "tavolo", "tipo": "tavolo", "punti": [[0.2, 0.5], [0.8, 0.5], [0.8, 0.9], [0.2, 0.9]]}],
})
PIATTO = Oggetto("bowl", np.array([80, 120, 120, 160], np.float32), 0.6)
PIZZA = Oggetto("pizza", np.array([85, 122, 115, 140], np.float32), 0.5)
# seduta dietro il tavolo: il suo box tocca la zona tavolo ma non copre il piatto
SEDUTA = Persona(1, np.array([60, 40, 140, 115], np.float32), 0.85, np.zeros((17, 3), np.float32))
SENZA_PIATTO = -1


class ModelloPiattoFinto:
    """Il cibo sono i pixel colorati (il piatto è bianco, il tavolo grigio); ricorda quante volte l'hanno chiamato."""

    def __init__(self):
        self.chiamate = 0

    def maschera_cibo(self, ritaglio: np.ndarray) -> np.ndarray:
        self.chiamate = self.chiamate + 1
        hsv = cv2.cvtColor(ritaglio, cv2.COLOR_BGR2HSV)
        return hsv[:, :, 1] >= 60


def fotogramma(righe_di_cibo: int) -> np.ndarray:
    """Tavolo grigio con il piatto bianco (40×40 px) e il cibo arancione nelle prime righe del piatto."""
    immagine = np.full((200, 200, 3), 150, np.uint8)
    if righe_di_cibo == SENZA_PIATTO:
        return immagine
    immagine[120:160, 80:120] = 230
    immagine[120:120 + righe_di_cibo, 80:120] = (30, 120, 220)
    return immagine


def scena(sequenza: list, modello=None) -> list:
    """Un passo ogni 10 secondi: sequenza[i] = (persona seduta?, righe di cibo, oggetti visti)."""
    if modello is None:
        modello = ModelloPiattoFinto()
    analizzatore = AnalizzatorePasto(SALA, modello)
    eventi = []
    for passo in range(len(sequenza)):
        seduta = sequenza[passo][0]
        persone = []
        if seduta:
            persone.append(SEDUTA)
        ora = INIZIO + datetime.timedelta(seconds=passo * 10)
        osservazione = Osservazione("sala", "dining room", ora, fotogramma(sequenza[passo][1]), persone,
                                    sequenza[passo][2])
        for evento in analizzatore.elabora(osservazione):
            eventi.append(evento)
    for evento in analizzatore.fine():
        eventi.append(evento)
    return eventi


def ripeti(seduta: bool, righe_di_cibo: int, quante: int, oggetti: list) -> list:
    sequenza = []
    for volta in range(quante):
        sequenza.append((seduta, righe_di_cibo, oggetti))
    return sequenza


def test_quanto_mangiato_tre_categorie():
    assert quanto_mangiato(0) == "meno_di_meta"
    assert quanto_mangiato(34.9) == "meno_di_meta"
    assert quanto_mangiato(35) == "meta"
    assert quanto_mangiato(75) == "meta"
    assert quanto_mangiato(75.1) == "tutto"
    assert quanto_mangiato(100) == "tutto"


def test_pasto_con_quanto_mangiato():
    # a tavola il piatto è pieno al 60% (24 righe su 40), dopo 3 minuti si alza e lascia il piatto al 15%: 75%
    sequenza = (ripeti(False, 24, 3, [PIATTO, PIZZA]) + ripeti(True, 24, 18, [PIATTO, PIZZA])
                + ripeti(False, 6, 10, [PIATTO]))
    modello = ModelloPiattoFinto()
    eventi = scena(sequenza, modello)
    # il modello gira solo all'inizio (3 misure) e alla fine (3 misure)
    assert modello.chiamate == 6
    assert len(eventi) == 1
    evento = eventi[0]
    assert evento.tipo == "pasto"
    assert evento.inizio == INIZIO + datetime.timedelta(seconds=30)
    assert evento.fine == INIZIO + datetime.timedelta(seconds=200)
    assert evento.valori.cibi == ["pizza"]
    assert evento.valori.quanto_mangiato == "meta"
    assert evento.confidenza == pytest.approx(0.85)
    assert evento.foto_prova is not None
    assert leggi_evento(LETTORE_EVENTO.dump_python(evento, mode="json")) == evento


def test_seduta_senza_piatto_non_e_pasto():
    assert scena(ripeti(False, 0, 3, []) + ripeti(True, 0, 30, []) + ripeti(False, 0, 10, [])) == []


def test_seduta_poco_non_e_pasto():
    assert scena(ripeti(False, 24, 3, [PIATTO]) + ripeti(True, 24, 6, [PIATTO]) + ripeti(False, 6, 10, [PIATTO])) == []


def test_pasto_ancora_in_corso_a_fine_video():
    # nessun "dopo": la fine è l'ultimo momento a tavola (6 righe di 24)
    sequenza = ripeti(True, 24, 10, [PIATTO]) + ripeti(True, 6, 10, [PIATTO])
    eventi = scena(sequenza)
    assert len(eventi) == 1
    assert eventi[0].valori.cibi == []
    assert eventi[0].valori.quanto_mangiato == "meta"


def test_piatto_portato_via_alzandosi():
    # finisce metà piatto (da 24 a 12 righe) e si porta via il piatto: conta l'ultimo momento a tavola, non "tutto"
    sequenza = (ripeti(True, 24, 10, [PIATTO]) + ripeti(True, 12, 8, [PIATTO])
                + ripeti(False, SENZA_PIATTO, 10, []))
    eventi = scena(sequenza)
    assert len(eventi) == 1
    assert eventi[0].valori.quanto_mangiato == "meta"


def test_cibo_visto_solo_dal_modello_del_piatto():
    # il rilevatore COCO non vede né piatto né cibo (es. un piatto piano): il pasto lo dice il modello del piatto
    # mangia tutto a tavola e lascia il piatto vuoto
    sequenza = ripeti(True, 24, 10, []) + ripeti(True, 0, 8, []) + ripeti(False, 0, 10, [])
    eventi = scena(sequenza)
    assert len(eventi) == 1
    assert eventi[0].valori.quanto_mangiato == "tutto"


def test_senza_pesi_del_piatto_non_misurato():
    analizzatore = AnalizzatorePasto(SALA, None)
    sequenza = ripeti(True, 24, 18, [PIATTO]) + ripeti(False, 6, 10, [PIATTO])
    eventi = []
    for passo in range(len(sequenza)):
        persone = []
        if sequenza[passo][0]:
            persone.append(SEDUTA)
        ora = INIZIO + datetime.timedelta(seconds=passo * 10)
        osservazione = Osservazione("sala", "dining room", ora, fotogramma(sequenza[passo][1]), persone, [PIATTO])
        for evento in analizzatore.elabora(osservazione):
            eventi.append(evento)
    assert len(eventi) == 1
    assert eventi[0].valori.quanto_mangiato is None


@pytest.mark.skipif(not Path(PESI_CIBO).exists(), reason="pesi del cibo non presenti (fuori dal repo)")
def test_modello_vero_del_piatto():
    modello = ModelloPiatto(PESI_CIBO)
    assert list(modello.modello.names.values()) == ["cibo"]
    ritaglio = np.full((120, 160, 3), 128, np.uint8)
    maschera = modello.maschera_cibo(ritaglio)
    assert maschera.shape == (120, 160)
    assert maschera.dtype == bool


def test_piatto_non_misurato():
    # quasi niente cibo all'inizio: quanto ha mangiato non si misura, confidenza dimezzata
    eventi = scena(ripeti(False, 0, 3, [PIATTO]) + ripeti(True, 0, 18, [PIATTO]) + ripeti(False, 0, 10, [PIATTO]))
    assert len(eventi) == 1
    assert eventi[0].valori.quanto_mangiato is None
    assert eventi[0].confidenza == pytest.approx(0.425)
