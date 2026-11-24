"""Test di zone, uscita e alzata notturna con osservazioni sintetiche (persone finte, nessun modello)."""

import datetime
from zoneinfo import ZoneInfo

import numpy as np

from contratti.configurazione import FasciaOraria, TelecameraLocale
from contratti.eventi import LETTORE_EVENTO, leggi_evento

from casa.alzata_notturna import AnalizzatoreAlzataNotturna, AnalizzatorePresenzaNotturna
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


A_LETTO = [persona(1, 150)]
IN_PIEDI = [persona(2, 60, 0.8)]  # vicino al letto ma con i piedi fuori


def alzata(posizioni: list, ora_inizio: datetime.datetime) -> list:
    return scena(AnalizzatoreAlzataNotturna(CAMERA, NOTTE), ora_inizio, posizioni)


def test_alzata_notturna_e_ritorno():
    inizio = datetime.datetime(2026, 12, 2, 2, 0, tzinfo=ROMA)
    posizioni = passi(A_LETTO, 10) + passi(IN_PIEDI, 5) + passi([], 40) + passi(A_LETTO, 10)
    eventi = alzata(posizioni, inizio)
    assert len(eventi) == 1
    evento = eventi[0]
    assert evento.tipo == "alzata_notturna"
    assert evento.inizio == inizio + datetime.timedelta(seconds=10)  # visto fuori dal letto
    assert evento.fine == inizio + datetime.timedelta(seconds=55)    # di nuovo a letto
    assert evento.valori.stanze == ["bedroom"]
    assert evento.confidenza == 0.8
    assert evento.foto_prova is not None
    assert leggi_evento(LETTORE_EVENTO.dump_python(evento, mode="json")) == evento


def test_fuori_dal_letto_meno_di_30_secondi_non_e_alzata():
    inizio = datetime.datetime(2026, 12, 2, 2, 0, tzinfo=ROMA)
    posizioni = passi(A_LETTO, 10) + passi(IN_PIEDI, 5) + passi([], 10) + passi(A_LETTO, 10)
    assert alzata(posizioni, inizio) == []


def test_di_giorno_non_e_alzata_notturna():
    inizio = datetime.datetime(2026, 12, 2, 14, 0, tzinfo=ROMA)
    posizioni = passi(A_LETTO, 10) + passi(IN_PIEDI, 5) + passi([], 40) + passi(A_LETTO, 10)
    assert alzata(posizioni, inizio) == []


def test_persona_non_vista_sotto_le_coperte_non_e_alzata():
    # per un minuto la posa non vede nessuno, ma nessuno è visto fuori dal letto
    inizio = datetime.datetime(2026, 12, 2, 2, 0, tzinfo=ROMA)
    posizioni = passi(A_LETTO, 10) + passi([], 60) + passi(A_LETTO, 10)
    assert alzata(posizioni, inizio) == []


def test_due_persone_a_letto_una_si_alza():
    inizio = datetime.datetime(2026, 12, 2, 2, 0, tzinfo=ROMA)
    tutte_e_due = [persona(1, 120), persona(3, 170)]
    resta = [persona(3, 170)]
    alzata_una = [persona(3, 170), persona(2, 60, 0.7)]
    posizioni = passi(tutte_e_due, 10) + passi(alzata_una, 5) + passi(resta, 40) + passi(tutte_e_due, 10)
    eventi = alzata(posizioni, inizio)
    assert len(eventi) == 1
    assert eventi[0].inizio == inizio + datetime.timedelta(seconds=10)
    assert eventi[0].fine == inizio + datetime.timedelta(seconds=55)


def test_letto_vuoto_all_inizio_non_e_alzata():
    inizio = datetime.datetime(2026, 12, 2, 2, 0, tzinfo=ROMA)
    posizioni = passi([], 10) + passi(IN_PIEDI, 40) + passi(A_LETTO, 10)
    assert alzata(posizioni, inizio) == []


def test_ritorno_breve_non_chiude_l_alzata():
    # torna a letto per 2 secondi e si rialza: è la stessa alzata
    inizio = datetime.datetime(2026, 12, 2, 2, 0, tzinfo=ROMA)
    posizioni = (passi(A_LETTO, 10) + passi(IN_PIEDI, 5) + passi([], 20) + passi(A_LETTO, 2) + passi(IN_PIEDI, 2)
                 + passi([], 18) + passi(A_LETTO, 10))
    eventi = alzata(posizioni, inizio)
    assert len(eventi) == 1
    assert eventi[0].inizio == inizio + datetime.timedelta(seconds=10)
    assert eventi[0].fine == inizio + datetime.timedelta(seconds=57)


def test_alzata_ancora_in_corso_a_fine_video():
    inizio = datetime.datetime(2026, 12, 1, 23, 30, tzinfo=ROMA)
    eventi = alzata(passi(A_LETTO, 10) + passi(IN_PIEDI, 5) + passi([], 40), inizio)
    assert len(eventi) == 1
    assert eventi[0].inizio == inizio + datetime.timedelta(seconds=10)
    assert eventi[0].fine is None
    # fuori da meno di 30 s quando finisce il video: non si sa ancora
    assert alzata(passi(A_LETTO, 10) + passi(IN_PIEDI, 5) + passi([], 10), inizio) == []


SOGGIORNO = TelecameraLocale.model_validate({
    "id": "soggiorno", "nome": "Living room", "stanza": "living room", "sorgente": "x.mp4",
    "analizzatori": ["alzata_notturna"],
})


def presenza(posizioni: list, ora_inizio: datetime.datetime) -> list:
    return scena(AnalizzatorePresenzaNotturna(SOGGIORNO, NOTTE), ora_inizio, posizioni)


def test_presenza_notturna_in_una_stanza_senza_letto():
    inizio = datetime.datetime(2026, 12, 2, 3, 0, tzinfo=ROMA)
    eventi = presenza(passi([], 5) + passi([persona(4, 60, 0.6)], 10) + passi([], 70), inizio)
    assert len(eventi) == 1
    assert eventi[0].inizio == inizio + datetime.timedelta(seconds=5)
    assert eventi[0].fine == inizio + datetime.timedelta(seconds=14)
    assert eventi[0].valori.stanze == ["living room"]
    assert eventi[0].stanza == "living room"


def test_presenza_breve_o_di_giorno_non_conta():
    notte = datetime.datetime(2026, 12, 2, 3, 0, tzinfo=ROMA)
    assert presenza(passi([persona(4, 60)], 1) + passi([], 70), notte) == []
    giorno = datetime.datetime(2026, 12, 2, 15, 0, tzinfo=ROMA)
    assert presenza(passi([persona(4, 60)], 10) + passi([], 70), giorno) == []


def test_presenza_notturna_a_fine_video():
    inizio = datetime.datetime(2026, 12, 2, 3, 0, tzinfo=ROMA)
    eventi = presenza(passi([persona(4, 60)], 10), inizio)
    assert len(eventi) == 1
    assert eventi[0].fine == inizio + datetime.timedelta(seconds=9)
