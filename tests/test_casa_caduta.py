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
# a terra ma con il busto a 65° (sopra i 60° di "a terra", sotto i 70° per l'allarme confermato)
SEMI_SDRAIATA = persona([[60, 60], [60, 75]], [[102.9, 80], [102.9, 95]], [40, 50, 160, 100])


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
    # rialzata: stesso inizio (il backend lo coordina con l'allarme), fine e secondi a terra; in piedi dal secondo 9,
    # per l'isteresi non è più a terra dal secondo 10
    rialzata = eventi[1]
    assert rialzata.inizio == allarme.inizio
    assert rialzata.fine == INIZIO + datetime.timedelta(seconds=10)
    assert rialzata.valori.secondi_a_terra == 7


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


class ClassificatoreFinto:
    """Vede una caduta se `vede_caduta` (o dalla finestra numero `da_finestra` in poi); ricorda le finestre."""

    soglia = 0.5

    def __init__(self, vede_caduta: bool, fps: float, secondi: float, finestre_di_fila: int = 1,
                 da_finestra: int = 0):
        self.vede_caduta = vede_caduta
        self.finestre_di_fila = finestre_di_fila
        self.da_finestra = da_finestra
        self.fps = fps
        self.secondi = secondi
        self.lunghezza = int(round(fps * secondi))
        self.finestre = []

    def probabilita_caduta(self, finestra: np.ndarray) -> float:
        self.finestre.append(finestra)
        if self.vede_caduta and len(self.finestre) > self.da_finestra:
            return 0.9
        return 0.1


def scena_ibrida(classificatore: ClassificatoreFinto, sequenza: list, passo: float = 1.0) -> list:
    analizzatore = AnalizzatoreCaduta(SOGGIORNO, classificatore)
    immagine = np.zeros((200, 200, 3), np.uint8)
    eventi = []
    for indice in range(len(sequenza)):
        ora = INIZIO + datetime.timedelta(seconds=indice * passo)
        osservazione = Osservazione("soggiorno", "living room", ora, immagine, [sequenza[indice]], [])
        for evento in analizzatore.elabora(osservazione):
            eventi.append(evento)
    return eventi


def test_caduta_confermata_dal_classificatore():
    eventi = scena_ibrida(ClassificatoreFinto(True, 5, 3), [IN_PIEDI] * 3 + [A_TERRA] * 5)
    assert len(eventi) == 1
    assert eventi[0].inizio == INIZIO + datetime.timedelta(seconds=3)


def test_senza_conferma_niente_allarme_se_si_rialza():
    # la geometria vede una caduta ma il classificatore no (es. si sdraia sul tappeto in fretta): niente allarme
    assert scena_ibrida(ClassificatoreFinto(False, 5, 3), [IN_PIEDI] * 3 + [A_TERRA] * 10 + [IN_PIEDI] * 10) == []


def test_senza_conferma_allarme_dopo_30_secondi_a_terra():
    eventi = scena_ibrida(ClassificatoreFinto(False, 5, 3), [IN_PIEDI] * 3 + [A_TERRA] * 35)
    assert len(eventi) == 1
    assert eventi[0].tipo == "caduta"


def test_il_classificatore_da_solo_non_fa_partire_niente():
    # il classificatore vede sempre una caduta ma la persona resta in piedi
    assert scena_ibrida(ClassificatoreFinto(True, 5, 3), [IN_PIEDI] * 40) == []


def test_una_finestra_ogni_mezzo_secondo_della_lunghezza_giusta():
    # 3 s a 10 fotogrammi al secondo (es. durante una bevuta): finestre a 0; 0,5; ...; 2,5 s, sempre a 5 al secondo
    classificatore = ClassificatoreFinto(False, 5, 3)
    scena_ibrida(classificatore, [IN_PIEDI] * 30, 0.1)
    assert len(classificatore.finestre) == 6
    assert classificatore.finestre[0].shape == (15, 17, 3)


def test_conferma_solo_con_k_finestre_di_fila():
    # una finestra al secondo; a terra dal secondo 3, la geometria è pronta al secondo 5; il classificatore vede la
    # caduta dalla quinta finestra (secondo 4): con 1 finestra conferma al secondo 5, con 3 di fila al secondo 6
    una = ClassificatoreFinto(True, 5, 3, finestre_di_fila=1, da_finestra=4)
    assert len(scena_ibrida(una, [IN_PIEDI] * 3 + [A_TERRA] * 3)) == 1
    tre = ClassificatoreFinto(True, 5, 3, finestre_di_fila=3, da_finestra=4)
    assert scena_ibrida(tre, [IN_PIEDI] * 3 + [A_TERRA] * 3) == []
    tre = ClassificatoreFinto(True, 5, 3, finestre_di_fila=3, da_finestra=4)
    assert len(scena_ibrida(tre, [IN_PIEDI] * 3 + [A_TERRA] * 4)) == 1


def test_con_la_conferma_serve_il_busto_a_70_gradi():
    # il classificatore conferma ma il busto è a 65°: niente allarme finché non arriva a 70° o passano 30 s
    assert scena_ibrida(ClassificatoreFinto(True, 5, 3), [IN_PIEDI] * 3 + [SEMI_SDRAIATA] * 10) == []
    eventi = scena_ibrida(ClassificatoreFinto(True, 5, 3), [IN_PIEDI] * 3 + [SEMI_SDRAIATA] * 4 + [A_TERRA] * 2)
    assert len(eventi) == 1
    assert eventi[0].inizio == INIZIO + datetime.timedelta(seconds=3)
    assert len(scena_ibrida(ClassificatoreFinto(True, 5, 3), [IN_PIEDI] * 3 + [SEMI_SDRAIATA] * 31)) == 1
    # senza classificatore il busto a 65° basta, come prima
    assert len(scena(SOGGIORNO, ripeti(IN_PIEDI, 3) + ripeti(SEMI_SDRAIATA, 5))) == 1


def test_busto_non_visto_non_blocca_la_conferma():
    in_piedi = persona([[0, 0], [0, 0]], [[0, 0], [0, 0]], [90, 20, 130, 180], visibile=0)
    a_terra = persona([[0, 0], [0, 0]], [[0, 0], [0, 0]], [20, 60, 160, 95], visibile=0)
    assert len(scena_ibrida(ClassificatoreFinto(True, 5, 3), [in_piedi] * 3 + [a_terra] * 3)) == 1


def test_un_fotogramma_in_piedi_non_fa_uscire_da_a_terra():
    # a terra ai secondi 3-4, al secondo 5 la posa sbaglia e la vede in piedi: è ancora a terra, l'allarme parte lì
    eventi = scena(SOGGIORNO, ripeti(IN_PIEDI, 3) + ripeti(A_TERRA, 2) + ripeti(IN_PIEDI, 1))
    assert len(eventi) == 1
    # a terra solo al secondo 3, poi in piedi: esce da "a terra" al secondo 5 (1 s in piedi), a 2 s non ci arriva
    assert scena(SOGGIORNO, ripeti(IN_PIEDI, 3) + ripeti(A_TERRA, 1) + ripeti(IN_PIEDI, 5)) == []
