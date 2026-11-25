"""Test dell'analizzatore farmaco (regole provvisorie) e del riconoscimento dalle foto, con un incorporatore finto al
posto di CLIP (il colore medio dell'immagine): così il test non carica modelli."""

import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import cv2
import numpy as np
import pytest

from contratti.configurazione import Personalizzazione, TelecameraLocale
from contratti.eventi import LETTORE_EVENTO, leggi_evento

from casa.aspetto_zona import AreaZona
from casa.farmaco import AnalizzatoreFarmaco, ModelloFarmaci
from casa.percezione import Oggetto, Osservazione, Persona
from casa.principale import PESI_FARMACI
from casa.riconoscimento_farmaci import RiconoscitoreFarmaci, crea_riconoscitore

ROMA = ZoneInfo("Europe/Rome")
INIZIO = datetime.datetime(2026, 12, 1, 8, 0, tzinfo=ROMA)
# portapillole sul tavolo: pixel 140-160 × 100-120 di un fotogramma 200×200
CUCINA = TelecameraLocale.model_validate({
    "id": "cucina", "nome": "Kitchen", "stanza": "kitchen", "sorgente": "x.mp4", "analizzatori": ["farmaco"],
    "zone": [{"id": "portapillole", "tipo": "portapillole", "punti": [[0.7, 0.5], [0.8, 0.5], [0.8, 0.6],
                                                                       [0.7, 0.6]]}],
})
PERSONALIZZAZIONE = Personalizzazione.model_validate({
    "anziano": {"nome": "Anna"},
    "farmaci": [
        {"id": "donepezil", "nome": "Donepezil", "dose": "1 tablet", "orari": ["08:00"], "foto_ids": ["scatola-rossa"]},
        {"id": "memantina", "nome": "Memantine", "dose": "1 tablet", "orari": ["20:00"], "foto_ids": ["scatola-blu",
                                                                                                    "manca"]},
    ],
})


class IncorporatoreFinto:
    """Al posto di CLIP: il vettore è il colore medio dell'immagine, normalizzato."""

    def incorpora(self, immagini: list) -> np.ndarray:
        vettori = []
        for immagine in immagini:
            vettori.append(immagine.reshape(-1, 3).mean(axis=0))
        vettori = np.array(vettori, np.float32)
        return vettori / np.linalg.norm(vettori, axis=1, keepdims=True)


@pytest.fixture
def riconoscitore(tmp_path):
    cv2.imwrite(str(tmp_path / "scatola-rossa.jpg"), np.full((60, 90, 3), (0, 0, 200), np.uint8))
    cv2.imwrite(str(tmp_path / "scatola-blu.jpg"), np.full((60, 90, 3), (200, 0, 0), np.uint8))
    return RiconoscitoreFarmaci(IncorporatoreFinto(), PERSONALIZZAZIONE, str(tmp_path))


def test_riconoscimento_dalle_foto(riconoscitore):
    rossiccio = np.full((40, 40, 3), (40, 40, 180), np.uint8)
    riconoscimento = riconoscitore.riconosci([np.full((40, 40, 3), 80, np.uint8), rossiccio])
    assert riconoscimento.farmaco_id == "donepezil"
    assert 0.75 <= riconoscimento.somiglianza <= 1
    # un ritaglio grigio non somiglia abbastanza a nessuna scatola
    assert riconoscitore.riconosci([np.full((40, 40, 3), 80, np.uint8)]) is None
    assert riconoscitore.riconosci([]) is None


def test_senza_foto_niente_riconoscitore(tmp_path):
    senza_foto = Personalizzazione.model_validate({"anziano": {"nome": "Anna"}, "farmaci": [
        {"id": "f", "nome": "F", "dose": "1", "orari": ["08:00"]}]})
    assert crea_riconoscitore(senza_foto, str(tmp_path)) is None


def persona(mano: str) -> Persona:
    """Seduta al tavolo (naso in 110, 40; spalle larghe 40 px). mano: "giu", "portapillole" o "bocca"."""
    keypoint = np.zeros((17, 3), np.float32)
    keypoint[0] = [110, 40, 0.9]
    keypoint[5] = [90, 60, 0.9]
    keypoint[6] = [130, 60, 0.9]
    keypoint[9] = [90, 150, 0.9]
    keypoint[10] = [130, 150, 0.9]
    if mano == "portapillole":
        keypoint[10] = [150, 110, 0.9]
    if mano == "bocca":
        keypoint[10] = [112, 48, 0.9]
    return Persona(1, np.array([80, 20, 160, 190], np.float32), 0.85, keypoint)


def fotogramma(portapillole_aperto: bool, scatola_rossa_in_mano: bool) -> np.ndarray:
    immagine = np.full((200, 200, 3), 80, np.uint8)
    immagine[100:120, 140:160] = 120
    if portapillole_aperto:
        immagine[100:120, 140:160] = 220
    if scatola_rossa_in_mano:
        immagine[95:125, 135:165] = (0, 0, 200)
    return immagine


def scena(sequenza: list, riconoscitore=None) -> list:
    """Un passo al secondo: sequenza[i] = (mano, portapillole aperto, scatola rossa in mano, oggetti)."""
    analizzatore = AnalizzatoreFarmaco(CUCINA, riconoscitore)
    eventi = []
    for secondo in range(len(sequenza)):
        passo = sequenza[secondo]
        ora = INIZIO + datetime.timedelta(seconds=secondo)
        osservazione = Osservazione("cucina", "kitchen", ora, fotogramma(passo[1], passo[2]), [persona(passo[0])],
                                    passo[3])
        for evento in analizzatore.elabora(osservazione):
            eventi.append(evento)
    for evento in analizzatore.fine():
        eventi.append(evento)
    return eventi


def ripeti(mano: str, aperto: bool, quante: int, scatola: bool = False, oggetti: list | None = None) -> list:
    if oggetti is None:
        oggetti = []
    sequenza = []
    for volta in range(quante):
        sequenza.append((mano, aperto, scatola, oggetti))
    return sequenza


def test_presa_dal_portapillole_e_mano_alla_bocca(riconoscitore):
    sequenza = (ripeti("giu", False, 3) + ripeti("portapillole", True, 2, scatola=True) + ripeti("giu", True, 2)
                + ripeti("bocca", True, 1) + ripeti("giu", True, 3))
    eventi = scena(sequenza, riconoscitore)
    assert len(eventi) == 1
    evento = eventi[0]
    assert evento.tipo == "farmaco"
    assert evento.inizio == INIZIO + datetime.timedelta(seconds=3)
    assert evento.fine == INIZIO + datetime.timedelta(seconds=7)
    assert evento.valori.portapillole_aperto
    assert evento.valori.mano_alla_bocca
    assert evento.valori.farmaco_id == "donepezil"
    assert evento.valori.somiglianza >= 0.75
    assert evento.confidenza == pytest.approx(0.85)
    assert leggi_evento(LETTORE_EVENTO.dump_python(evento, mode="json")) == evento


def test_senza_riconoscitore_farmaco_non_riconosciuto():
    sequenza = ripeti("giu", False, 3) + ripeti("portapillole", False, 2) + ripeti("bocca", False, 1)
    eventi = scena(sequenza)
    assert len(eventi) == 1
    assert eventi[0].valori.farmaco_id is None
    assert eventi[0].valori.somiglianza is None
    assert not eventi[0].valori.portapillole_aperto


def test_mano_alla_bocca_senza_presa_non_e_farmaco():
    assert scena(ripeti("giu", False, 3) + ripeti("bocca", False, 3)) == []


def test_presa_senza_bocca_entro_due_minuti_non_conta():
    sequenza = ripeti("giu", False, 3) + ripeti("portapillole", False, 2) + ripeti("giu", False, 125)
    sequenza = sequenza + ripeti("bocca", False, 1)
    assert scena(sequenza) == []


def test_bere_non_e_la_pillola_alla_bocca():
    bottiglia_alla_bocca = [Oggetto("bottle", np.array([105, 30, 120, 90], np.float32), 0.7)]
    sequenza = (ripeti("giu", False, 3) + ripeti("portapillole", False, 2)
                + ripeti("bocca", False, 2, oggetti=bottiglia_alla_bocca))
    assert scena(sequenza) == []
    # dopo aver bevuto, la pillola alla bocca conta
    assert len(scena(sequenza + ripeti("giu", False, 1) + ripeti("bocca", False, 1))) == 1


class ModelloFarmaciFinto:
    """Vede la scatola rossa del fotogramma (box 135-165 × 95-125) se c'è; ricorda le chiamate."""

    def __init__(self):
        self.chiamate = 0

    def scatole_e_blister(self, immagine: np.ndarray, area) -> list:
        self.chiamate = self.chiamate + 1
        if immagine[110, 150, 2] != 200:
            return []
        return [np.array([135, 95, 165, 125], np.float32)]


class RiconoscitoreCheRicorda:
    def __init__(self):
        self.ritagli = None

    def riconosci(self, ritagli: list):
        self.ritagli = ritagli
        return None


def scena_con_rilevatore(sequenza: list, modello: ModelloFarmaciFinto, riconoscitore) -> list:
    analizzatore = AnalizzatoreFarmaco(CUCINA, riconoscitore, modello)
    eventi = []
    for secondo in range(len(sequenza)):
        passo = sequenza[secondo]
        ora = INIZIO + datetime.timedelta(seconds=secondo)
        osservazione = Osservazione("cucina", "kitchen", ora, fotogramma(passo[1], passo[2]), [persona(passo[0])],
                                    passo[3])
        for evento in analizzatore.elabora(osservazione):
            eventi.append(evento)
    return eventi


def test_ritagli_dal_rilevatore_dei_farmaci():
    modello = ModelloFarmaciFinto()
    riconoscitore = RiconoscitoreCheRicorda()
    sequenza = (ripeti("giu", False, 3) + ripeti("portapillole", True, 2, scatola=True) + ripeti("giu", True, 2)
                + ripeti("bocca", True, 1))
    eventi = scena_con_rilevatore(sequenza, modello, riconoscitore)
    assert len(eventi) == 1
    # il rilevatore gira solo con il polso vicino al portapillole (2 s), non con la mano giù o alla bocca
    assert modello.chiamate == 2
    # al riconoscimento vanno i box della scatola con un decimo di bordo: 30 px + 3 px per lato
    assert len(riconoscitore.ritagli) == 2
    assert riconoscitore.ritagli[0].shape == (36, 36, 3)


def test_senza_scatole_viste_i_ritagli_della_mano():
    modello = ModelloFarmaciFinto()
    riconoscitore = RiconoscitoreCheRicorda()
    sequenza = ripeti("giu", False, 3) + ripeti("portapillole", True, 2) + ripeti("bocca", True, 1)
    scena_con_rilevatore(sequenza, modello, riconoscitore)
    assert len(riconoscitore.ritagli) == 2
    assert riconoscitore.ritagli[0].shape == (40, 40, 3)  # lato = larghezza delle spalle intorno al polso


@pytest.mark.skipif(not Path(PESI_FARMACI).exists(), reason="pesi dei farmaci non presenti (fuori dal repo)")
def test_modello_vero_dei_farmaci():
    modello = ModelloFarmaci(PESI_FARMACI)
    nomi = list(modello.modello.names.values())
    assert nomi == ["pillola", "blister", "scatola_farmaco", "portapillole", "scomparto"]
    immagine = np.full((200, 200, 3), 128, np.uint8)
    area = AreaZona(CUCINA.zone[0], immagine)
    assert modello.scatole_e_blister(immagine, area) == []
