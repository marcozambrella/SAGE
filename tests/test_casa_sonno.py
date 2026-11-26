"""Test dell'analizzatore del sonno (regole provvisorie): persone scritte a mano, un fotogramma al secondo."""

import datetime
from zoneinfo import ZoneInfo

import numpy as np

from contratti.configurazione import Personalizzazione, TelecameraLocale
from contratti.eventi import LETTORE_EVENTO, leggi_evento

from casa.percezione import Osservazione, Persona
from casa.principale import Specialisti, crea_analizzatori
from casa.segni import RilevatoreSegni
from casa.sonno import AnalizzatoreSonno

ROMA = ZoneInfo("Europe/Rome")
INIZIO = datetime.datetime(2026, 12, 1, 22, 0, tzinfo=ROMA)
# camera da letto 200×200: il letto è la metà destra
CAMERA = TelecameraLocale.model_validate({
    "id": "camera", "nome": "Bedroom", "stanza": "bedroom", "sorgente": "x.mp4", "analizzatori": ["sonno"],
    "zone": [{"id": "letto", "tipo": "letto", "punti": [[0.5, 0], [1, 0], [1, 1], [0.5, 1]]}],
})


def persona(id_traccia: int, spalle: list, anche: list, box: list) -> Persona:
    keypoint = np.zeros((17, 3), np.float32)
    keypoint[5] = [spalle[0][0], spalle[0][1], 0.9]
    keypoint[6] = [spalle[1][0], spalle[1][1], 0.9]
    keypoint[11] = [anche[0][0], anche[0][1], 0.9]
    keypoint[12] = [anche[1][0], anche[1][1], 0.9]
    return Persona(id_traccia, np.array(box, np.float32), 0.8, keypoint)


def sdraiata(spostamento: float = 0.0) -> Persona:
    """Sdraiata nel letto (busto orizzontale, box alto 35 px), spostata a destra di `spostamento` pixel."""
    dx = spostamento
    return persona(1, [[120 + dx, 100], [120 + dx, 115]], [[170 + dx, 102], [170 + dx, 117]],
                   [110 + dx, 90, 190 + dx, 125])


SEDUTA = persona(1, [[150, 40], [170, 40]], [[152, 90], [168, 90]], [140, 20, 180, 95])
# in piedi nella metà sinistra, fuori dal letto
FUORI = persona(3, [[40, 40], [60, 40]], [[42, 90], [58, 90]], [30, 20, 70, 95])


def ripeti(persone: list, quante: int) -> list:
    sequenza = []
    for volta in range(quante):
        sequenza.append(persone)
    return sequenza


def girarsi(secondi: int) -> list:
    """Si muove nel letto: 10 px avanti e indietro ogni secondo (10/35 altezze al secondo)."""
    sequenza = []
    for secondo in range(secondi):
        if secondo % 2 == 0:
            sequenza.append([sdraiata(10)])
        else:
            sequenza.append([sdraiata(0)])
    return sequenza


def scena(sequenza: list, con_fine: bool = True) -> list:
    """sequenza[i] = le persone viste al secondo i."""
    analizzatore = AnalizzatoreSonno(CAMERA)
    immagine = np.zeros((200, 200, 3), np.uint8)
    eventi = []
    for secondo in range(len(sequenza)):
        ora = INIZIO + datetime.timedelta(seconds=secondo)
        osservazione = Osservazione("camera", "bedroom", ora, immagine, sequenza[secondo], [])
        for evento in analizzatore.elabora(osservazione):
            eventi.append(evento)
    if con_fine:
        for evento in analizzatore.fine():
            eventi.append(evento)
    return eventi


def secondi(numero: float) -> datetime.datetime:
    return INIZIO + datetime.timedelta(seconds=numero)


def test_un_pezzo_di_sonno():
    # in giro 10 s, ferma a letto 20 minuti, poi seduta: dorme dal secondo 10, si sveglia al 1210 (quando si siede)
    eventi = scena(ripeti([FUORI], 10) + ripeti([sdraiata()], 1200) + ripeti([SEDUTA], 70))
    assert len(eventi) == 1
    evento = eventi[0]
    assert evento.tipo == "sonno"
    assert evento.valori.zona_id == "letto"
    assert evento.inizio == secondi(10)
    assert evento.fine == secondi(1210)
    assert evento.confidenza == 0.8
    assert leggi_evento(LETTORE_EVENTO.dump_python(evento, mode="json")) == evento


def test_ferma_per_meno_di_5_minuti_non_e_sonno():
    assert scena(ripeti([sdraiata()], 240) + ripeti([SEDUTA], 70)) == []


def test_seduta_per_poco_non_sveglia():
    # seduta 30 s e di nuovo giù: il pezzo continua (esce a fine video con fine None)
    eventi = scena(ripeti([sdraiata()], 400) + ripeti([SEDUTA], 30) + ripeti([sdraiata()], 100))
    assert len(eventi) == 1
    assert eventi[0].fine is None


def test_girarsi_nel_sonno_non_sveglia():
    eventi = scena(ripeti([sdraiata()], 400) + girarsi(10) + ripeti([sdraiata()], 100), con_fine=False)
    assert eventi == []


def test_muoversi_tanto_sveglia():
    eventi = scena(ripeti([sdraiata()], 400) + girarsi(70), con_fine=False)
    assert len(eventi) == 1
    assert eventi[0].inizio == secondi(0)
    assert eventi[0].fine == secondi(400)


def test_sotto_le_coperte_dorme_ancora():
    # la posa non la vede per mezz'ora: non è sveglia, il pezzo esce solo a fine video
    sequenza = ripeti([sdraiata()], 400) + ripeti([], 1800) + ripeti([sdraiata()], 10)
    assert scena(sequenza, con_fine=False) == []
    eventi = scena(sequenza)
    assert len(eventi) == 1
    assert eventi[0].inizio == secondi(0)
    assert eventi[0].fine is None


def test_alzata_fuori_dal_letto():
    # sparisce sotto le coperte, poi qualcuno è fuori dal letto per 10 s: sveglia da quando è fuori
    eventi = scena(ripeti([sdraiata()], 400) + ripeti([], 20) + ripeti([FUORI], 10), con_fine=False)
    assert len(eventi) == 1
    assert eventi[0].fine == secondi(420)


def test_fuori_per_un_attimo_non_sveglia():
    eventi = scena(ripeti([sdraiata()], 400) + ripeti([FUORI], 3) + ripeti([], 20), con_fine=False)
    assert eventi == []


def test_il_compagno_in_giro_non_sveglia():
    eventi = scena(ripeti([sdraiata()], 400) + ripeti([sdraiata(), FUORI], 120), con_fine=False)
    assert eventi == []


def test_due_pezzi_con_un_alzata_in_mezzo():
    eventi = scena(ripeti([sdraiata()], 400) + ripeti([FUORI], 60) + ripeti([sdraiata()], 400))
    assert len(eventi) == 2
    assert eventi[0].inizio == secondi(0)
    assert eventi[0].fine == secondi(400)
    assert eventi[1].inizio == secondi(460)
    assert eventi[1].fine is None


def test_sonno_solo_con_la_zona_letto_e_non_e_un_primo_segno():
    personalizzazione = Personalizzazione.model_validate({"anziano": {"nome": "Anna"}})
    analizzatori = crea_analizzatori(CAMERA, personalizzazione, Specialisti())
    assert len(analizzatori) == 1
    assert isinstance(analizzatori[0], AnalizzatoreSonno)
    senza_letto = TelecameraLocale.model_validate({
        "id": "soggiorno", "nome": "Living room", "stanza": "living room", "sorgente": "x.mp4",
        "analizzatori": ["sonno"]})
    assert crea_analizzatori(senza_letto, personalizzazione, Specialisti()) == []
    # chi dorme non fa passare a 10 fotogrammi al secondo
    osservazione = Osservazione("camera", "bedroom", INIZIO, np.zeros((200, 200, 3), np.uint8), [sdraiata()], [])
    assert not RilevatoreSegni(CAMERA, None).c_e_un_segno(osservazione)
