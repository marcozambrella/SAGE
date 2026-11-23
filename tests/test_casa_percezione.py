"""Test della percezione condivisa con i pesi pre-allenati (saltati se pesi/ non c'è: i pesi non sono nel repo)."""

import base64
from pathlib import Path

import cv2
import numpy as np
import pytest

from casa.percezione import CLASSI_OGGETTI, Percezione, foto_prova

RADICE = Path(__file__).resolve().parents[1]
POSA = RADICE / "pesi" / "yolo26n-pose.pt"
RILEVATORE = RADICE / "pesi" / "yolo26n.pt"
mancano_i_pesi = not POSA.exists() or not RILEVATORE.exists()


def immagine_bus() -> np.ndarray:
    """Foto d'esempio che Ultralytics installa insieme al pacchetto (quattro persone davanti a un autobus)."""
    import ultralytics

    percorso = Path(ultralytics.__file__).parent / "assets" / "bus.jpg"
    return cv2.imread(str(percorso))


@pytest.fixture(scope="module")
def percezione():
    return Percezione(str(POSA), str(RILEVATORE))


@pytest.mark.skipif(mancano_i_pesi, reason="pesi pre-allenati non scaricati in pesi/")
def test_persone_tracciate_con_scheletro(percezione):
    immagine = immagine_bus()
    tracker = percezione.nuovo_tracker()
    persone = []
    # il tracker conferma una traccia dopo qualche fotogramma
    for volta in range(4):
        persone = percezione.persone(immagine, tracker)
    assert len(persone) >= 3
    identificativi = set()
    for persona in persone:
        identificativi.add(persona.id_traccia)
        assert persona.keypoint.shape == (17, 3)
        assert 0 <= persona.box[0] < persona.box[2] <= immagine.shape[1]
        assert 0 <= persona.box[1] < persona.box[3] <= immagine.shape[0]
    assert len(identificativi) == len(persone)


@pytest.mark.skipif(mancano_i_pesi, reason="pesi pre-allenati non scaricati in pesi/")
def test_solo_gli_oggetti_che_servono(percezione):
    oggetti = percezione.oggetti(immagine_bus())
    for oggetto in oggetti:
        assert oggetto.classe in CLASSI_OGGETTI


@pytest.mark.skipif(mancano_i_pesi, reason="pesi pre-allenati non scaricati in pesi/")
def test_tracker_senza_compensazione_del_movimento(percezione):
    tracker = percezione.nuovo_tracker()
    assert tracker.args.gmc_method == "none"


def test_foto_prova_piccola():
    immagine = np.zeros((720, 1280, 3), np.uint8)
    testo = foto_prova(immagine)
    dati = np.frombuffer(base64.b64decode(testo), np.uint8)
    riletta = cv2.imdecode(dati, cv2.IMREAD_COLOR)
    assert riletta.shape == (360, 640, 3)
