"""Test dell'analizzatore dell'agitazione (regole provvisorie): un fotogramma al secondo, persone scritte a mano."""

import datetime
from zoneinfo import ZoneInfo

import numpy as np

from contratti.configurazione import TelecameraLocale
from contratti.eventi import LETTORE_EVENTO, leggi_evento

from casa.agitazione import AnalizzatoreAgitazione
from casa.percezione import Osservazione, Persona

ROMA = ZoneInfo("Europe/Rome")
INIZIO = datetime.datetime(2026, 12, 1, 18, 0, tzinfo=ROMA)
SOGGIORNO = TelecameraLocale.model_validate({
    "id": "soggiorno", "nome": "Living room", "stanza": "living room", "sorgente": "x.mp4",
    "analizzatori": ["agitazione"]})
# lo stesso soggiorno con il tavolo nella metà destra
CON_TAVOLO = TelecameraLocale.model_validate({
    "id": "soggiorno", "nome": "Living room", "stanza": "living room", "sorgente": "x.mp4",
    "analizzatori": ["agitazione"],
    "zone": [{"id": "tavolo", "tipo": "tavolo", "punti": [[0.7, 0], [1, 0], [1, 1], [0.7, 1]]}]})


def in_piedi(x: float, id_traccia: int = 1) -> Persona:
    """In piedi con il centro dei piedi in x (box alto 75 px)."""
    return Persona(id_traccia, np.array([x - 20, 20, x + 20, 95], np.float32), 0.8, np.zeros((17, 3), np.float32))


def avanti_e_indietro(secondi: int, da: float = 40, a: float = 160, id_traccia: int = 1) -> list:
    """Cammina tra da e a a 40 px al secondo (0,53 altezze al secondo): un'inversione ogni (a - da) / 40 s."""
    sequenza = []
    x = da
    passo = 40
    for secondo in range(secondi):
        sequenza.append([in_piedi(x, id_traccia)])
        if x + passo > a or x + passo < da:
            passo = -passo
        x = x + passo
    return sequenza


def ferma(secondi: int, x: float = 100) -> list:
    sequenza = []
    for secondo in range(secondi):
        sequenza.append([in_piedi(x)])
    return sequenza


def scena(sequenza: list, telecamera: TelecameraLocale = SOGGIORNO, con_fine: bool = True) -> list:
    analizzatore = AnalizzatoreAgitazione(telecamera)
    immagine = np.zeros((200, 200, 3), np.uint8)
    eventi = []
    for secondo in range(len(sequenza)):
        ora = INIZIO + datetime.timedelta(seconds=secondo)
        osservazione = Osservazione("soggiorno", "living room", ora, immagine, sequenza[secondo], [])
        for evento in analizzatore.elabora(osservazione):
            eventi.append(evento)
    if con_fine:
        for evento in analizzatore.fine():
            eventi.append(evento)
    return eventi


def secondi(numero: float) -> datetime.datetime:
    return INIZIO + datetime.timedelta(seconds=numero)


def test_avanti_e_indietro_per_piu_di_3_minuti():
    # 200 s avanti e indietro, poi ferma dov'era (x = 80): l'episodio si chiude dopo 20 s fermo
    eventi = scena(avanti_e_indietro(200) + ferma(25, 80), con_fine=False)
    assert len(eventi) == 1
    evento = eventi[0]
    assert evento.tipo == "agitazione"
    assert evento.inizio == secondi(0)
    assert evento.fine == secondi(199)
    # un'inversione ogni 3 s
    assert evento.valori.inversioni >= 60
    assert leggi_evento(LETTORE_EVENTO.dump_python(evento, mode="json")) == evento


def test_episodio_ancora_in_corso_a_fine_video():
    eventi = scena(avanti_e_indietro(200))
    assert len(eventi) == 1
    assert eventi[0].fine == secondi(199)


def test_due_minuti_non_bastano():
    assert scena(avanti_e_indietro(120) + ferma(25)) == []


def test_una_pausa_divide_gli_episodi():
    assert scena(avanti_e_indietro(100) + ferma(25) + avanti_e_indietro(100)) == []


def test_camminare_dritto_non_e_agitazione():
    # attraversa la stanza e se ne va, poi cammina a lungo sempre nella stessa direzione (nessuna inversione)
    dritto = []
    for secondo in range(200):
        dritto.append([in_piedi(secondo * 40 % 4000)])
    assert scena(dritto) == []


def test_restare_a_tavola_chiude_l_episodio():
    # 150 s avanti e indietro a sinistra, poi 60 s di movimenti piccoli dentro la zona tavolo (a destra)
    sequenza = avanti_e_indietro(150) + avanti_e_indietro(60, 150, 190)
    assert len(scena(sequenza)) == 1        # senza zona tavolo è un episodio solo di 210 s
    assert scena(sequenza, CON_TAVOLO) == []  # a tavola per 20 s: si chiude a 170 s


def test_il_tracker_cambia_id_a_meta():
    sequenza = avanti_e_indietro(200)
    for secondo in range(100, 200):
        stessa = sequenza[secondo][0]
        sequenza[secondo] = [Persona(2, stessa.box, stessa.confidenza, stessa.keypoint)]
    assert len(scena(sequenza)) == 1
