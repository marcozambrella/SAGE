"""Test dell'inattività: osservazioni di due telecamere scritte a mano, una al minuto."""

import datetime
from zoneinfo import ZoneInfo

import numpy as np

from contratti.configurazione import ConfigurazioneCasa, RegoleAllarmi
from contratti.eventi import LETTORE_EVENTO, TIPI_URGENTI, leggi_evento

from casa.inattivita import AnalizzatoreInattivita
from casa.percezione import Osservazione, Persona
from casa.principale import Specialisti, prepara_telecamere
from test_casa_sorgenti import scrivi_video

ROMA = ZoneInfo("Europe/Rome")
IMMAGINE = np.zeros((48, 64, 3), np.uint8)
PERSONA = Persona(1, np.array([10, 10, 20, 40], np.float32), 0.9, np.zeros((17, 3), np.float32))


def alle(giorno: int, ore: int, minuti: int = 0) -> datetime.datetime:
    return datetime.datetime(2026, 12, giorno, ore, minuti, tzinfo=ROMA)


def osservazione(ora: datetime.datetime, telecamera_id: str, con_persona: bool) -> Osservazione:
    persone = []
    if con_persona:
        persone.append(PERSONA)
    stanze = {"cucina": "kitchen", "camera": "bedroom"}
    return Osservazione(telecamera_id, stanze[telecamera_id], ora, IMMAGINE, persone, [])


def scena(dalle: datetime.datetime, minuti: int, viste: dict) -> list:
    """Un'osservazione al minuto per telecamera (cucina e camera); viste: minuto → telecamera con la persona."""
    analizzatore = AnalizzatoreInattivita(RegoleAllarmi())
    eventi = []
    for minuto in range(minuti):
        ora = dalle + datetime.timedelta(minutes=minuto)
        for telecamera_id in ("cucina", "camera"):
            con_persona = viste.get(minuto) == telecamera_id
            for evento in analizzatore.elabora(osservazione(ora, telecamera_id, con_persona)):
                eventi.append(evento)
    return eventi


def test_tre_ore_di_giorno_senza_nessuno():
    # vista in cucina alle 10, poi nessuno: allarme alle 13; ricompare in camera alle 13:30, la fine
    eventi = scena(alle(1, 10), 240, {0: "cucina", 210: "camera"})
    assert len(eventi) == 2
    allarme = eventi[0]
    assert allarme.tipo == "inattivita"
    assert "inattivita" in TIPI_URGENTI
    assert allarme.inizio == alle(1, 10)
    assert allarme.fine is None
    assert allarme.valori.ultima_telecamera_id == "cucina"
    assert allarme.stanza == "kitchen"
    assert allarme.foto_prova is not None
    assert leggi_evento(LETTORE_EVENTO.dump_python(allarme, mode="json")) == allarme
    fine = eventi[1]
    assert fine.inizio == allarme.inizio
    assert fine.fine == alle(1, 13, 30)
    assert fine.valori.ultima_telecamera_id == "cucina"


def test_vista_da_un_altra_telecamera_azzera():
    # vista in camera alle 11: fino alle 14 niente allarme
    assert scena(alle(1, 10), 230, {0: "cucina", 60: "camera"}) == []
    assert len(scena(alle(1, 10), 250, {0: "cucina", 60: "camera"})) == 1


def test_le_ore_si_contano_dalla_fine_della_notte():
    # vista alle 21, poi nessuno: la notte (22-7) non conta, allarme alle 10 del mattino
    eventi = scena(alle(1, 21), 14 * 60, {0: "cucina"})
    assert len(eventi) == 1
    assert eventi[0].inizio == alle(1, 21)
    # 13 ore senza nessuno ma l'ultima osservazione è alle 9:59: niente allarme
    assert scena(alle(1, 21), 13 * 60, {0: "cucina"}) == []


def test_di_notte_niente_allarme():
    assert scena(alle(1, 22, 30), 8 * 60, {0: "cucina"}) == []


def test_mai_vista_conta_dall_avvio():
    assert len(scena(alle(1, 9), 181, {})) == 1


def test_una_inattivita_per_tutta_la_casa(tmp_path):
    scrivi_video(tmp_path / "a.mp4", 5, 5)
    scrivi_video(tmp_path / "b.mp4", 5, 5)
    configurazione = ConfigurazioneCasa.model_validate({
        "telecamere": [
            {"id": "cucina", "nome": "Kitchen", "stanza": "kitchen", "sorgente": str(tmp_path / "a.mp4"),
             "analizzatori": ["inattivita"]},
            {"id": "camera", "nome": "Bedroom", "stanza": "bedroom", "sorgente": str(tmp_path / "b.mp4"),
             "analizzatori": ["alzata_notturna"]},
        ],
        "personalizzazione": {"anziano": {"nome": "Anna"}},
        "cartella_foto_farmaci": "data/foto_farmaci",
    })
    telecamere = prepara_telecamere(configurazione, 5, Specialisti())
    assert telecamere[0].inattivita is not None
    assert telecamere[1].inattivita is telecamere[0].inattivita
    # non è un analizzatore della telecamera
    assert telecamere[0].analizzatori == []
