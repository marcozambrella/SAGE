"""Test dell'analizzatore caduta (regole provvisorie dalla geometria dello scheletro) con scheletri sintetici."""

import datetime
from zoneinfo import ZoneInfo

import numpy as np

from contratti.configurazione import TelecameraLocale
from contratti.eventi import LETTORE_EVENTO, TIPI_URGENTI, leggi_evento

from casa.caduta import AnalizzatoreCaduta
from casa.percezione import Osservazione, Persona

ROMA = ZoneInfo("Europe/Rome")
INIZIO = datetime.datetime(2026, 12, 1, 11, 0, tzinfo=ROMA)
SOGGIORNO = TelecameraLocale.model_validate({
    "id": "soggiorno", "nome": "Living room", "stanza": "living room", "sorgente": "x.mp4",
    "analizzatori": ["caduta"],
})
# camera da letto: il letto occupa la metà bassa del fotogramma 200×200
CAMERA = TelecameraLocale.model_validate({
    "id": "camera-letto", "nome": "Bedroom", "stanza": "bedroom", "sorgente": "x.mp4", "analizzatori": ["caduta"],
    "zone": [{"id": "letto", "tipo": "letto", "punti": [[0, 0.5], [1, 0.5], [1, 1], [0, 1]]}],
})


def persona(spalle: list, anche: list, box: list, visibile: float = 0.9) -> Persona:
    keypoint = np.zeros((17, 3), np.float32)
    keypoint[5] = [spalle[0][0], spalle[0][1], visibile]
    keypoint[6] = [spalle[1][0], spalle[1][1], visibile]
    keypoint[11] = [anche[0][0], anche[0][1], visibile]
    keypoint[12] = [anche[1][0], anche[1][1], visibile]
    return Persona(1, np.array(box, np.float32), 0.8, keypoint)


IN_PIEDI = persona([[100, 40], [120, 40]], [[102, 90], [118, 90]], [90, 20, 130, 90])
# a terra in mezzo alla stanza (sopra la metà del fotogramma, fuori dal letto della camera)
A_TERRA = persona([[40, 70], [40, 85]], [[90, 72], [90, 87]], [20, 60, 160, 95])
CHINATA = persona([[130, 70], [130, 85]], [[95, 72], [95, 87]], [90, 40, 140, 98])
A_META = persona([[100, 50], [120, 50]], [[80, 80], [100, 80]], [70, 30, 130, 90])
NEL_LETTO = persona([[40, 150], [40, 165]], [[90, 152], [90, 167]], [20, 140, 160, 175])


def scena(telecamera: TelecameraLocale, sequenza: list) -> list:
    """Un passo al secondo: sequenza[i] = la persona al secondo i (None: non vista)."""
    analizzatore = AnalizzatoreCaduta(telecamera)
    immagine = np.zeros((200, 200, 3), np.uint8)
    eventi = []
    for secondo in range(len(sequenza)):
        persone = []
        if sequenza[secondo] is not None:
            persone.append(sequenza[secondo])
        ora = INIZIO + datetime.timedelta(seconds=secondo)
        for evento in analizzatore.elabora(Osservazione(telecamera.id, telecamera.stanza, ora, immagine, persone,
                                                        [])):
            eventi.append(evento)
    for evento in analizzatore.fine():
        eventi.append(evento)
    return eventi


def ripeti(persona_vista: Persona | None, quante: int) -> list:
    sequenza = []
    for volta in range(quante):
        sequenza.append(persona_vista)
    return sequenza


def test_caduta_allarme_subito_poi_secondi_a_terra():
    eventi = scena(SOGGIORNO, ripeti(IN_PIEDI, 3) + ripeti(A_TERRA, 6) + ripeti(IN_PIEDI, 5))
    assert len(eventi) == 2
    allarme = eventi[0]
    assert allarme.tipo == "caduta"
    assert "caduta" in TIPI_URGENTI
    assert allarme.inizio == INIZIO + datetime.timedelta(seconds=3)
    assert allarme.fine is None
    assert allarme.valori.secondi_a_terra is None
    assert allarme.foto_prova is not None
    assert allarme.confidenza == 0.8
    assert leggi_evento(LETTORE_EVENTO.dump_python(allarme, mode="json")) == allarme
    # rialzata: stesso inizio (il backend lo coordina con l'allarme), fine e secondi a terra
    rialzata = eventi[1]
    assert rialzata.inizio == allarme.inizio
    assert rialzata.fine == INIZIO + datetime.timedelta(seconds=9)
    assert rialzata.valori.secondi_a_terra == 6


def test_ancora_a_terra_a_fine_video():
    eventi = scena(SOGGIORNO, ripeti(IN_PIEDI, 3) + ripeti(A_TERRA, 20))
    assert len(eventi) == 1
    assert eventi[0].valori.secondi_a_terra is None


def test_sdraiarsi_piano_non_e_caduta():
    assert scena(SOGGIORNO, ripeti(IN_PIEDI, 3) + ripeti(A_META, 5) + ripeti(A_TERRA, 10)) == []


def test_chinarsi_non_e_caduta():
    assert scena(SOGGIORNO, ripeti(IN_PIEDI, 3) + ripeti(CHINATA, 10)) == []


def test_un_attimo_a_terra_non_e_caduta():
    assert scena(SOGGIORNO, ripeti(IN_PIEDI, 3) + ripeti(A_TERRA, 1) + ripeti(IN_PIEDI, 10)) == []


def test_sdraiarsi_nel_letto_non_e_caduta():
    assert scena(CAMERA, ripeti(IN_PIEDI, 3) + ripeti(NEL_LETTO, 10)) == []
    # a terra fuori dal letto, nella stessa camera, invece sì
    assert len(scena(CAMERA, ripeti(IN_PIEDI, 3) + ripeti(A_TERRA, 10))) == 1


def test_senza_scheletro_conta_il_box():
    in_piedi = persona([[0, 0], [0, 0]], [[0, 0], [0, 0]], [90, 20, 130, 180], visibile=0)
    a_terra = persona([[0, 0], [0, 0]], [[0, 0], [0, 0]], [20, 60, 160, 95], visibile=0)
    assert len(scena(SOGGIORNO, ripeti(in_piedi, 3) + ripeti(a_terra, 5))) == 1
