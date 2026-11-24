"""Test dell'analizzatore pasto (regole provvisorie) con un tavolo sintetico: piatto bianco, cibo arancione."""

import datetime
from zoneinfo import ZoneInfo

import numpy as np
import pytest

from contratti.configurazione import TelecameraLocale
from contratti.eventi import LETTORE_EVENTO, leggi_evento

from casa.pasto import AnalizzatorePasto, quanto_mangiato
from casa.percezione import Oggetto, Osservazione, Persona

ROMA = ZoneInfo("Europe/Rome")
INIZIO = datetime.datetime(2026, 12, 1, 12, 30, tzinfo=ROMA)
# tavolo: pixel 40-160 × 100-180 di un fotogramma 200×200
SALA = TelecameraLocale.model_validate({
    "id": "sala", "nome": "Dining room", "stanza": "dining room", "sorgente": "x.mp4", "analizzatori": ["pasto"],
    "zone": [{"id": "tavolo", "tipo": "tavolo", "punti": [[0.2, 0.5], [0.8, 0.5], [0.8, 0.9], [0.2, 0.9]]}],
})
PIATTO = Oggetto("bowl", np.array([80, 120, 120, 160], np.float32), 0.6)
PIZZA = Oggetto("pizza", np.array([85, 122, 115, 140], np.float32), 0.5)
SEDUTA = Persona(1, np.array([60, 40, 140, 140], np.float32), 0.85, np.zeros((17, 3), np.float32))


def fotogramma(righe_di_cibo: int) -> np.ndarray:
    """Tavolo grigio con il piatto bianco (40×40 px) e il cibo arancione nelle prime righe del piatto."""
    immagine = np.full((200, 200, 3), 150, np.uint8)
    immagine[120:160, 80:120] = 230
    immagine[120:120 + righe_di_cibo, 80:120] = (30, 120, 220)
    return immagine


def scena(sequenza: list) -> list:
    """Un passo ogni 10 secondi: sequenza[i] = (persona seduta?, righe di cibo, oggetti visti)."""
    analizzatore = AnalizzatorePasto(SALA)
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
    # piatto pieno al 60% (24 righe su 40) senza nessuno, 3 minuti a tavola, poi piatto al 15% (6 righe): 75%
    sequenza = (ripeti(False, 24, 3, [PIATTO, PIZZA]) + ripeti(True, 20, 18, [PIATTO, PIZZA])
                + ripeti(False, 6, 10, [PIATTO]))
    eventi = scena(sequenza)
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
    # niente "prima" senza nessuno: si usano le prime e le ultime misure durante il pasto
    sequenza = ripeti(True, 24, 10, [PIATTO]) + ripeti(True, 6, 10, [PIATTO])
    eventi = scena(sequenza)
    assert len(eventi) == 1
    assert eventi[0].valori.cibi == []
    # con la persona davanti si vedono solo le righe del piatto sotto il suo box (140-160): lì il cibo non c'è più
    assert eventi[0].valori.quanto_mangiato in ["meno_di_meta", "meta", "tutto"]


def test_piatto_non_misurato():
    # quasi niente cibo all'inizio: quanto ha mangiato non si misura, confidenza dimezzata
    eventi = scena(ripeti(False, 0, 3, [PIATTO]) + ripeti(True, 0, 18, [PIATTO]) + ripeti(False, 0, 10, [PIATTO]))
    assert len(eventi) == 1
    assert eventi[0].valori.quanto_mangiato is None
    assert eventi[0].confidenza == pytest.approx(0.425)
