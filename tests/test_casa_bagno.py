"""Test delle visite al bagno (regole provvisorie): la porta del bagno è il quarto sinistro del corridoio."""

import datetime
from zoneinfo import ZoneInfo

import numpy as np

from contratti.configurazione import Personalizzazione, TelecameraLocale
from contratti.eventi import LETTORE_EVENTO, leggi_evento

from casa.bagno import AnalizzatoreBagno
from casa.percezione import Osservazione, Persona
from casa.principale import Specialisti, crea_analizzatori

ROMA = ZoneInfo("Europe/Rome")
INIZIO = datetime.datetime(2026, 12, 1, 9, 0, tzinfo=ROMA)
CORRIDOIO = TelecameraLocale.model_validate({
    "id": "corridoio", "nome": "Hallway", "stanza": "hallway", "sorgente": "x.mp4", "analizzatori": ["bagno"],
    "zone": [{"id": "porta-bagno", "tipo": "bagno", "punti": [[0, 0], [0.25, 0], [0.25, 1], [0, 1]]}]})


def persona(id_traccia: int, x: float) -> Persona:
    """In piedi con i piedi in (x, 190) di un fotogramma 200×200."""
    return Persona(id_traccia, np.array([x - 15, 110, x + 15, 190], np.float32), 0.8, np.zeros((17, 3), np.float32))


def scena(passi: list) -> list:
    """passi = (secondo, persone viste), in ordine di tempo."""
    analizzatore = AnalizzatoreBagno(CORRIDOIO)
    immagine = np.zeros((200, 200, 3), np.uint8)
    eventi = []
    for secondo, persone in passi:
        ora = INIZIO + datetime.timedelta(seconds=secondo)
        for evento in analizzatore.elabora(Osservazione("corridoio", "hallway", ora, immagine, persone, [])):
            eventi.append(evento)
    for evento in analizzatore.fine():
        eventi.append(evento)
    return eventi


def secondi(numero: float) -> datetime.datetime:
    return INIZIO + datetime.timedelta(seconds=numero)


def entra_ed_esce(dentro: int, x_uscita: float = 20) -> list:
    """In corridoio (x 150) per 3 s, alla porta del bagno (x 20) per 3 s, poi non si vede per `dentro` secondi;
    poi una traccia nuova compare in x_uscita e va verso il corridoio."""
    passi = []
    for secondo in range(3):
        passi.append((secondo, [persona(1, 150)]))
    for secondo in range(3, 6):
        passi.append((secondo, [persona(1, 20)]))
    for secondo in range(6, 6 + dentro):
        passi.append((secondo, []))
    uscita = 6 + dentro
    passi.append((uscita, [persona(2, x_uscita)]))
    for secondo in range(uscita + 1, uscita + 4):
        passi.append((secondo, [persona(2, 150)]))
    return passi


def test_visita_al_bagno():
    eventi = scena(entra_ed_esce(120))
    assert len(eventi) == 1
    evento = eventi[0]
    assert evento.tipo == "visita_bagno"
    assert evento.valori.zona_id == "porta-bagno"
    assert evento.inizio == secondi(5)    # l'ultima volta vista alla porta
    assert evento.fine == secondi(126)    # ricompare alla porta
    assert leggi_evento(LETTORE_EVENTO.dump_python(evento, mode="json")) == evento


def test_visita_troppo_breve_non_conta():
    assert scena(entra_ed_esce(15)) == []


def test_chi_compare_altrove_non_esce_dal_bagno():
    assert scena(entra_ed_esce(120, x_uscita=150)) == []


def test_mai_uscita_niente_evento():
    passi = entra_ed_esce(120)[0:126]   # finisce prima che ricompaia
    assert scena(passi) == []


def test_piu_di_due_ore_niente_evento():
    passi = entra_ed_esce(0)[0:6]
    passi.append((3 * 3600, [persona(2, 20)]))
    assert scena(passi) == []


def test_passare_davanti_alla_porta_non_conta():
    passi = []
    for secondo in range(30):
        passi.append((secondo, [persona(1, 20 + secondo * 5)]))
    assert scena(passi) == []


def test_bagno_solo_con_la_zona_bagno():
    personalizzazione = Personalizzazione.model_validate({"anziano": {"nome": "Anna"}})
    assert isinstance(crea_analizzatori(CORRIDOIO, personalizzazione, Specialisti())[0], AnalizzatoreBagno)
    senza_zona = TelecameraLocale.model_validate({
        "id": "corridoio", "nome": "Hallway", "stanza": "hallway", "sorgente": "x.mp4", "analizzatori": ["bagno"]})
    assert crea_analizzatori(senza_zona, personalizzazione, Specialisti()) == []
