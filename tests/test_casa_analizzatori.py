"""Test di zone, uscita e alzata notturna con osservazioni sintetiche (persone finte, nessun modello)."""

import datetime
from zoneinfo import ZoneInfo

import numpy as np

from contratti.configurazione import FasciaOraria, TelecameraLocale
from contratti.eventi import LETTORE_EVENTO, leggi_evento

from casa.alzata_notturna import SECONDI_CONFERMA, AnalizzatoreAlzataNotturna
from casa.percezione import Osservazione, Persona
from casa.uscita import SECONDI_SPARIZIONE, AnalizzatoreUscita
from casa.zone import dentro_zona, zona_della_persona

ROMA = ZoneInfo("Europe/Rome")
LARGHEZZA = 200
ALTEZZA = 100
NOTTE = FasciaOraria(dalle="22:00", alle="07:00")

# porta: quarto sinistro del fotogramma; letto: metà destra
INGRESSO = TelecameraLocale.model_validate({
    "id": "ingresso", "nome": "Front door", "stanza": "hall", "sorgente": "x.mp4", "analizzatori": ["uscita"],
    "zone": [{"id": "porta-ingresso", "tipo": "porta", "punti": [[0, 0], [0.25, 0], [0.25, 1], [0, 1]]}],
})
CAMERA = TelecameraLocale.model_validate({
    "id": "camera-letto", "nome": "Bedroom", "stanza": "bedroom", "sorgente": "x.mp4",
    "analizzatori": ["alzata_notturna"],
    "zone": [{"id": "letto", "tipo": "letto", "punti": [[0.5, 0], [1, 0], [1, 1], [0.5, 1]]}],
})


def persona(id_traccia: int, x_piedi: float, confidenza: float = 0.9) -> Persona:
    """Persona con i piedi in (x_piedi, 90) pixel."""
    box = np.array([x_piedi - 10, 20, x_piedi + 10, 90], np.float32)
    return Persona(id_traccia, box, confidenza, np.zeros((17, 3), np.float32))


def osservazione(ora: datetime.datetime, persone: list, stanza: str = "hall") -> Osservazione:
    immagine = np.zeros((ALTEZZA, LARGHEZZA, 3), np.uint8)
    return Osservazione("prova", stanza, ora, immagine, persone, [])


def scena(analizzatore, ora_inizio: datetime.datetime, posizioni: list, secondi_per_passo: float = 1.0):
    """Fa passare una scena: posizioni[i] = lista di persone al passo i. Restituisce tutti gli eventi, fine compresa."""
    eventi = []
    for passo in range(len(posizioni)):
        ora = ora_inizio + datetime.timedelta(seconds=passo * secondi_per_passo)
        for evento in analizzatore.elabora(osservazione(ora, posizioni[passo])):
            eventi.append(evento)
    for evento in analizzatore.fine():
        eventi.append(evento)
    return eventi


def test_punto_nel_poligono():
    zona = INGRESSO.zone[0]
    assert dentro_zona(10, 50, zona, LARGHEZZA, ALTEZZA)
    assert dentro_zona(50, 50, zona, LARGHEZZA, ALTEZZA)  # sul bordo
    assert not dentro_zona(60, 50, zona, LARGHEZZA, ALTEZZA)
    assert zona_della_persona(persona(1, 20), INGRESSO.zone, LARGHEZZA, ALTEZZA).id == "porta-ingresso"
    assert zona_della_persona(persona(1, 150), INGRESSO.zone, LARGHEZZA, ALTEZZA) is None


def test_uscita_dalla_porta():
    inizio = datetime.datetime(2026, 12, 1, 15, 0, tzinfo=ROMA)
    # cammina dalla stanza verso la porta, ci entra e sparisce
    posizioni = [[persona(1, 150)], [persona(1, 100)], [persona(1, 30, 0.8)]]
    for passo in range(int(SECONDI_SPARIZIONE) + 2):
        posizioni.append([])
    eventi = scena(AnalizzatoreUscita(INGRESSO), inizio, posizioni)
    assert len(eventi) == 1
    evento = eventi[0]
    assert evento.tipo == "uscita"
    assert evento.valori.zona_id == "porta-ingresso"
    assert evento.inizio == inizio + datetime.timedelta(seconds=2)  # ultima volta vista nella porta
    assert evento.stanza == "hall"
    assert evento.confidenza == 0.8
    assert evento.fonti[0].telecamera_id == "ingresso"
    assert evento.foto_prova is not None
    # rispetta il contratto in andata e ritorno JSON
    assert leggi_evento(LETTORE_EVENTO.dump_python(evento, mode="json")) == evento


def test_sparire_lontano_dalla_porta_non_e_uscita():
    inizio = datetime.datetime(2026, 12, 1, 15, 0, tzinfo=ROMA)
    posizioni = [[persona(1, 150)], [persona(1, 120)]]
    for passo in range(int(SECONDI_SPARIZIONE) + 2):
        posizioni.append([])
    assert scena(AnalizzatoreUscita(INGRESSO), inizio, posizioni) == []


def test_fermo_nella_porta_non_e_uscita():
    inizio = datetime.datetime(2026, 12, 1, 15, 0, tzinfo=ROMA)
    posizioni = []
    for passo in range(20):
        posizioni.append([persona(1, 30)])
    assert scena(AnalizzatoreUscita(INGRESSO), inizio, posizioni) == []


def test_sparizione_breve_nella_porta_non_e_uscita():
    # coperta un attimo dalla porta e ritrovata con lo stesso id: niente uscita
    inizio = datetime.datetime(2026, 12, 1, 15, 0, tzinfo=ROMA)
    posizioni = [[persona(1, 30)], [], [], [persona(1, 30)], [persona(1, 150)]]
    for passo in range(int(SECONDI_SPARIZIONE) + 2):
        posizioni.append([])
    assert scena(AnalizzatoreUscita(INGRESSO), inizio, posizioni) == []


def passi(persone: list, quanti: int) -> list:
    posizioni = []
    for passo in range(quanti):
        posizioni.append(persone)
    return posizioni


def test_alzata_notturna_e_ritorno():
    inizio = datetime.datetime(2026, 12, 2, 2, 0, tzinfo=ROMA)
    conferma = int(SECONDI_CONFERMA)
    a_letto = [persona(1, 150, 0.7)]
    in_piedi = [persona(2, 60)]  # vicino al letto ma con i piedi fuori
    posizioni = passi(a_letto, conferma + 5) + passi(in_piedi, 30) + passi([], 60) + passi(a_letto, conferma + 5)
    eventi = scena(AnalizzatoreAlzataNotturna(CAMERA, NOTTE), inizio, posizioni)
    assert len(eventi) == 1
    evento = eventi[0]
    assert evento.tipo == "alzata_notturna"
    assert evento.inizio == inizio + datetime.timedelta(seconds=conferma + 5)
    assert evento.fine == inizio + datetime.timedelta(seconds=conferma + 5 + 90)
    assert evento.valori.stanze == ["bedroom"]
    assert evento.confidenza == 0.7
    assert leggi_evento(LETTORE_EVENTO.dump_python(evento, mode="json")) == evento


def test_di_giorno_non_e_alzata_notturna():
    inizio = datetime.datetime(2026, 12, 2, 14, 0, tzinfo=ROMA)
    a_letto = [persona(1, 150)]
    posizioni = passi(a_letto, 15) + passi([], 60) + passi(a_letto, 15)
    assert scena(AnalizzatoreAlzataNotturna(CAMERA, NOTTE), inizio, posizioni) == []


def test_buco_breve_della_posa_non_e_alzata():
    inizio = datetime.datetime(2026, 12, 2, 2, 0, tzinfo=ROMA)
    a_letto = [persona(1, 150)]
    buco = int(SECONDI_CONFERMA) - 2
    posizioni = passi(a_letto, 15) + passi([], buco) + passi(a_letto, 15)
    assert scena(AnalizzatoreAlzataNotturna(CAMERA, NOTTE), inizio, posizioni) == []


def test_letto_vuoto_all_inizio_non_e_alzata():
    inizio = datetime.datetime(2026, 12, 2, 2, 0, tzinfo=ROMA)
    posizioni = passi([], 30) + passi([persona(1, 150)], 15)
    assert scena(AnalizzatoreAlzataNotturna(CAMERA, NOTTE), inizio, posizioni) == []


def test_alzata_ancora_in_corso_a_fine_video():
    inizio = datetime.datetime(2026, 12, 1, 23, 30, tzinfo=ROMA)
    posizioni = passi([persona(1, 150)], 15) + passi([], 40)
    eventi = scena(AnalizzatoreAlzataNotturna(CAMERA, NOTTE), inizio, posizioni)
    assert len(eventi) == 1
    assert eventi[0].inizio == inizio + datetime.timedelta(seconds=15)
    assert eventi[0].fine is None
