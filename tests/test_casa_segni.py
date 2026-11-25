"""Test dei primi segni di un evento e del ritorno indietro di un secondo a 10 fotogrammi al secondo (Marco, 25/11)."""

import datetime
import uuid
from zoneinfo import ZoneInfo

import numpy as np

from contratti.configurazione import TelecameraLocale
from contratti.eventi import EventoCaduta, Fonte, ValoriCaduta

from casa.caduta import AnalizzatoreCaduta
from casa.percezione import Oggetto, Osservazione, Persona
from casa.principale import Telecamera, elabora
from casa.registro import RegistroLocale
from casa.segni import RilevatoreSegni
from casa.sorgenti import Fotogramma

ROMA = ZoneInfo("Europe/Rome")
INIZIO = datetime.datetime(2026, 12, 2, 10, 0, tzinfo=ROMA)
CUCINA = TelecameraLocale.model_validate({
    "id": "cucina", "nome": "Kitchen", "stanza": "kitchen", "sorgente": "x.mp4",
    "analizzatori": ["uscita", "farmaco", "bevuta", "caduta"],
    "zone": [
        {"id": "porta", "tipo": "porta", "punti": [[0, 0], [0.25, 0], [0.25, 1], [0, 1]]},
        {"id": "pillole", "tipo": "portapillole", "punti": [[0.75, 0], [1, 0], [1, 0.25], [0.75, 0.25]]},
    ],
})
IMMAGINE = np.zeros((100, 200, 3), np.uint8)


def persona(x: float, gradi_busto: float = 0, polso: tuple = (100, 70)) -> Persona:
    """Persona in piedi a metà immagine (piedi in x, 90), spalle larghe 20 px, busto inclinato di gradi_busto."""
    keypoint = np.zeros((17, 3), np.float32)
    anche = np.array([x, 60], np.float32)
    angolo = np.radians(gradi_busto)
    spalle = anche + 30 * np.array([np.sin(angolo), -np.cos(angolo)], np.float32)
    keypoint[0] = [spalle[0], spalle[1] - 10, 0.9]       # naso
    keypoint[5] = [spalle[0] - 10, spalle[1], 0.9]       # spalle
    keypoint[6] = [spalle[0] + 10, spalle[1], 0.9]
    keypoint[11] = [anche[0] - 5, anche[1], 0.9]         # anche
    keypoint[12] = [anche[0] + 5, anche[1], 0.9]
    keypoint[9] = [polso[0], polso[1], 0.9]              # polsi
    keypoint[10] = [polso[0], polso[1], 0.9]
    return Persona(1, np.array([x - 10, 20, x + 10, 90], np.float32), 0.9, keypoint)


def osservazione(secondi: float, persone: list, oggetti: list = []) -> Osservazione:
    ora = INIZIO + datetime.timedelta(seconds=secondi)
    return Osservazione("cucina", "kitchen", ora, IMMAGINE, persone, oggetti)


def test_nessun_segno_in_mezzo_alla_stanza():
    segni = RilevatoreSegni(CUCINA)
    assert not segni.c_e_un_segno(osservazione(0, [persona(100)]))
    assert not segni.c_e_un_segno(osservazione(0, []))


def test_persona_nella_zona_porta():
    assert RilevatoreSegni(CUCINA).c_e_un_segno(osservazione(0, [persona(20)]))


def test_mano_nella_zona_portapillole():
    assert RilevatoreSegni(CUCINA).c_e_un_segno(osservazione(0, [persona(100, polso=(180, 10))]))


def test_contenitore_in_mano():
    in_mano = Oggetto("cup", np.array([95, 65, 105, 80], np.float32), 0.8)
    sul_tavolo = Oggetto("cup", np.array([150, 65, 160, 80], np.float32), 0.8)
    assert RilevatoreSegni(CUCINA).c_e_un_segno(osservazione(0, [persona(100)], [in_mano]))
    assert not RilevatoreSegni(CUCINA).c_e_un_segno(osservazione(0, [persona(100)], [sul_tavolo]))


def test_una_caduta_non_e_un_primo_segno():
    # il busto va da in piedi a 60 gradi in 0,6 s: chi è caduto resta a terra e si vede anche a 5 al secondo
    segni = RilevatoreSegni(CUCINA)
    for passo in range(11):
        secondi = passo / 10 * 0.6
        assert not segni.c_e_un_segno(osservazione(secondi, [persona(100, 60 * passo / 10)]))


def test_solo_i_segni_degli_analizzatori_accesi():
    solo_pasto = CUCINA.model_copy(update={"analizzatori": ["pasto"]})
    segni = RilevatoreSegni(solo_pasto)
    assert not segni.c_e_un_segno(osservazione(0, [persona(20, polso=(180, 10))]))


class VideoFinto:
    """12 s a 10 fotogrammi al secondo."""

    def __init__(self):
        self.numero = 0
        self.finita = False

    def leggi(self) -> Fotogramma | None:
        if self.numero >= 120:
            self.finita = True
            return None
        fotogramma = Fotogramma(IMMAGINE, self.numero / 10)
        self.numero = self.numero + 1
        return fotogramma


class TrackerFinto:
    def __init__(self):
        self.secondi = []


class PercezioneFinta:
    """Qualcuno nella zona porta da 5 a 5,3 s, se no in mezzo alla stanza. Il tracker ricorda i fotogrammi visti."""

    def osserva(self, immagine, tracker, con_oggetti, telecamera_id, stanza, ora) -> Osservazione:
        secondi = (ora - INIZIO).total_seconds()
        tracker.secondi.append(round(secondi, 1))
        if 5 <= secondi < 5.35:
            return osservazione(secondi, [persona(20)])
        return osservazione(secondi, [persona(100)])


class AnalizzatoreFinto:
    """Ricorda i fotogrammi visti e dà un evento a 4,6 s, cioè nel secondo prima del segno (lo vede due volte)."""

    usa_oggetti = False

    def __init__(self):
        self.secondi = []

    def elabora(self, osservazione: Osservazione) -> list:
        secondi = round((osservazione.ora - INIZIO).total_seconds(), 1)
        self.secondi.append(secondi)
        if secondi != 4.6:
            return []
        fonte = Fonte(telecamera_id="cucina", analizzatore="finto", confidenza=0.9)
        evento = EventoCaduta(id=str(uuid.uuid4()), tipo="caduta", inizio=osservazione.ora, stanza="kitchen",
                              confidenza=0.9, fonti=[fonte], valori=ValoriCaduta())
        return [evento]

    def fine(self) -> list:
        return []


def secondi_attesi() -> list:
    """5 al secondo fino a 4 s (1 s prima del segno a 5 s), 10 al secondo fino a 5 s dopo l'ultimo segno (5,3 s),
    poi di nuovo 5 al secondo (0,2 s dopo l'ultimo analizzato)."""
    attesi = []
    for decimo in range(0, 40, 2):
        attesi.append(decimo / 10)
    for decimo in range(40, 104):
        attesi.append(decimo / 10)
    for decimo in range(105, 120, 2):
        attesi.append(decimo / 10)
    return attesi


def test_dal_primo_segno_10_al_secondo_da_un_secondo_prima(tmp_path):
    analizzatore = AnalizzatoreFinto()
    telecamera = Telecamera("cucina", "kitchen", VideoFinto(), [analizzatore], False, RilevatoreSegni(CUCINA))
    registro = RegistroLocale(str(tmp_path / "registro.sqlite3"))
    percezione = PercezioneFinta()
    percezione.nuovo_tracker = TrackerFinto
    elabora([telecamera], percezione, registro, None, INIZIO)
    # dopo il ritorno indietro tracker e analizzatori sono le copie di un secondo fa: hanno visto i fotogrammi solo
    # in avanti, a 5 al secondo e a 10 durante l'evento
    assert telecamera.analizzatori[0].secondi == secondi_attesi()
    assert telecamera.tracker.secondi == secondi_attesi()
    # l'evento a 4,6 s è venuto due volte (prima e dopo il ritorno indietro) ma parte una volta sola
    assert len(registro.tutti()) == 1
    registro.chiudi()


class CadutaFinta:
    """Classificatore delle cadute che vede sempre una caduta."""

    fps = 5.0
    secondi = 3.0
    lunghezza = 15
    soglia = 0.5

    def probabilita_caduta(self, finestra: np.ndarray) -> float:
        return 0.9


class PercezioneSoggiorno:
    """Una persona in mezzo alla stanza."""

    def nuovo_tracker(self):
        return TrackerFinto()

    def osserva(self, immagine, tracker, con_oggetti, telecamera_id, stanza, ora) -> Osservazione:
        secondi = round((ora - INIZIO).total_seconds(), 1)
        tracker.secondi.append(secondi)
        return osservazione(secondi, [persona(100)])


def test_il_classificatore_delle_cadute_non_fa_passare_a_10_al_secondo(tmp_path):
    soggiorno = CUCINA.model_copy(update={"analizzatori": ["caduta"], "zone": []})
    analizzatore = AnalizzatoreCaduta(soggiorno, CadutaFinta())
    telecamera = Telecamera("cucina", "kitchen", VideoFinto(), [analizzatore], False, RilevatoreSegni(soggiorno))
    registro = RegistroLocale(str(tmp_path / "registro.sqlite3"))
    elabora([telecamera], PercezioneSoggiorno(), registro, None, INIZIO)
    registro.chiudi()
    attesi = []
    for decimo in range(0, 120, 2):
        attesi.append(decimo / 10)
    assert telecamera.tracker.secondi == attesi
