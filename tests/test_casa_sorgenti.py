"""Test del programma di casa: file di configurazione, fasce orarie, sorgenti video con limite di fotogrammi."""

import datetime
from pathlib import Path
import time

import cv2
import numpy as np
import pytest

from contratti.configurazione import FasciaOraria
from casa import sorgenti
from casa.configurazione import dentro_fascia, leggi_configurazione
from casa.sorgenti import FlussoDalVivo, VideoRegistrato, apri_sorgente, e_dal_vivo, prossima_attesa

ESEMPIO = Path(__file__).resolve().parents[1] / "casa" / "configurazione.esempio.json"


def scrivi_video(percorso: Path, numero_fotogrammi: int, fps: float) -> None:
    """Video sintetico 64×48: il fotogramma i ha tutti i pixel uguali a i×5 modulo 256 (per riconoscerlo)."""
    scrittore = cv2.VideoWriter(str(percorso), cv2.VideoWriter_fourcc(*"mp4v"), fps, (64, 48))
    for indice in range(numero_fotogrammi):
        immagine = np.full((48, 64, 3), (indice * 5) % 256, np.uint8)
        scrittore.write(immagine)
    scrittore.release()


def test_configurazione_di_esempio_si_legge():
    configurazione = leggi_configurazione(str(ESEMPIO))
    assert len(configurazione.telecamere) == 3
    assert configurazione.telecamere[1].zone[0].tipo == "porta"
    assert configurazione.personalizzazione.regole.orari_notte.dalle == "22:00"


def test_fascia_che_passa_la_mezzanotte():
    notte = FasciaOraria(dalle="22:00", alle="07:00")
    assert dentro_fascia(datetime.datetime(2026, 12, 1, 23, 0), notte)
    assert dentro_fascia(datetime.datetime(2026, 12, 1, 6, 59), notte)
    assert dentro_fascia(datetime.datetime(2026, 12, 1, 22, 0), notte)
    assert not dentro_fascia(datetime.datetime(2026, 12, 1, 7, 0), notte)
    assert not dentro_fascia(datetime.datetime(2026, 12, 1, 12, 0), notte)


def test_fascia_di_giorno():
    giorno = FasciaOraria(dalle="09:00", alle="17:30")
    assert dentro_fascia(datetime.datetime(2026, 12, 1, 17, 29), giorno)
    assert not dentro_fascia(datetime.datetime(2026, 12, 1, 17, 30), giorno)
    assert not dentro_fascia(datetime.datetime(2026, 12, 1, 8, 0), giorno)


def test_riconosce_le_sorgenti_dal_vivo():
    assert e_dal_vivo("0")
    assert e_dal_vivo("rtsp://utente:password@192.168.1.20:554/stream1")
    assert e_dal_vivo("http://192.168.1.30:8080/video")
    assert not e_dal_vivo("data/video/cucina.mp4")


def test_video_registrato_a_5_fotogrammi_al_secondo(tmp_path):
    percorso = tmp_path / "prova.mp4"
    scrivi_video(percorso, 50, 25)  # 2 secondi
    video = VideoRegistrato(str(percorso), 5, "prova")
    secondi = []
    while True:
        fotogramma = video.leggi()
        if fotogramma is None:
            break
        secondi.append(fotogramma.secondi)
        assert fotogramma.immagine.shape == (48, 64, 3)
    assert video.finita
    # uno ogni 5 fotogrammi del file: 0, 0.2, ..., 1.8 secondi
    assert len(secondi) == 10
    assert secondi == pytest.approx([0.0, 0.2, 0.4, 0.6, 0.8, 1.0, 1.2, 1.4, 1.6, 1.8])


def test_video_con_meno_fotogrammi_di_quelli_chiesti(tmp_path):
    percorso = tmp_path / "lento.mp4"
    scrivi_video(percorso, 10, 5)
    video = VideoRegistrato(str(percorso), 25, "prova")
    numero = 0
    while video.leggi() is not None:
        numero = numero + 1
    # non si inventano fotogrammi: si danno tutti quelli del file
    assert numero == 10


def test_sorgente_non_apribile_senza_indirizzo_nel_messaggio(tmp_path):
    percorso = str(tmp_path / "manca.mp4")
    with pytest.raises(RuntimeError) as errore:
        VideoRegistrato(percorso, 5, "cucina")
    assert "cucina" in str(errore.value)
    assert percorso not in str(errore.value)


class CatturaFinta:
    """Telecamera finta al posto di cv2.VideoCapture: dà `quanti` fotogrammi 4×4 (il pixel vale base + numero del
    fotogramma) e poi cade. Con aperta=False è una riapertura non riuscita."""

    def __init__(self, base: int, quanti: int, aperta: bool = True):
        self.base = base
        self.quanti = quanti
        self.letti = 0
        self.aperta = aperta

    def isOpened(self) -> bool:
        return self.aperta

    def read(self):
        if not self.aperta or self.letti >= self.quanti:
            return False, None
        immagine = np.full((4, 4, 3), self.base + self.letti, np.uint8)
        self.letti = self.letti + 1
        time.sleep(0.002)  # come una telecamera vera: un fotogramma alla volta
        return True, immagine

    def release(self) -> None:
        self.aperta = False


class AperturaFinta:
    """Al posto di sorgenti.nuova_cattura: dà le catture finte nell'ordine (poi sempre l'ultima)."""

    def __init__(self, catture: list):
        self.catture = catture
        self.aperture = 0

    def apri(self, sorgente: str) -> CatturaFinta:
        indice = min(self.aperture, len(self.catture) - 1)
        self.aperture = self.aperture + 1
        return self.catture[indice]


@pytest.fixture
def attese_brevi(monkeypatch):
    # nei test la riconnessione aspetta millisecondi invece di secondi
    monkeypatch.setattr(sorgenti, "ATTESA_MINIMA_SECONDI", 0.01)
    monkeypatch.setattr(sorgenti, "ATTESA_MASSIMA_SECONDI", 0.04)


def aspetta_fotogramma(flusso: FlussoDalVivo, valore_minimo: int):
    """Il primo fotogramma con il pixel almeno uguale a valore_minimo (None se non arriva entro 5 s)."""
    scadenza = time.monotonic() + 5
    while time.monotonic() < scadenza:
        fotogramma = flusso.leggi()
        if fotogramma is not None and int(fotogramma.immagine[0, 0, 0]) >= valore_minimo:
            return fotogramma
        time.sleep(0.005)
    return None


def test_flusso_dal_vivo_da_l_ultimo_fotogramma_e_rispetta_il_turno(monkeypatch, attese_brevi):
    apertura = AperturaFinta([CatturaFinta(0, 20), CatturaFinta(0, 0, aperta=False)])
    monkeypatch.setattr(sorgenti, "nuova_cattura", apertura.apri)
    flusso = FlussoDalVivo("rtsp://telecamera-finta", 10, "prova")
    time.sleep(0.3)  # la telecamera finta manda i suoi 20 fotogrammi più veloce di quanto li leggiamo
    fotogramma = flusso.leggi()
    # resta solo l'ultimo fotogramma
    assert int(fotogramma.immagine[0, 0, 0]) == 19
    # subito dopo non è il suo turno
    assert flusso.leggi() is None
    time.sleep(0.15)
    # turno arrivato ma nessun fotogramma nuovo (telecamera caduta): niente, ma il flusso non è finito
    assert flusso.leggi() is None
    assert not flusso.finita
    flusso.ferma()


def test_flusso_caduto_si_ricollega(monkeypatch, capsys, attese_brevi):
    # cade dopo 3 fotogrammi, la prima riapertura non riesce, la seconda sì
    catture = [CatturaFinta(0, 3), CatturaFinta(0, 0, aperta=False), CatturaFinta(100, 100)]
    apertura = AperturaFinta(catture)
    monkeypatch.setattr(sorgenti, "nuova_cattura", apertura.apri)
    flusso = FlussoDalVivo("rtsp://telecamera-finta", 1000, "ingresso")
    fotogramma = aspetta_fotogramma(flusso, 100)
    flusso.ferma()
    assert fotogramma is not None
    assert apertura.aperture >= 3
    assert not flusso.finita
    registro = capsys.readouterr().out
    assert "telecamera ingresso: persa, nuovo tentativo tra 0.01 s" in registro
    assert "telecamera ingresso: persa, nuovo tentativo tra 0.02 s" in registro
    assert "telecamera ingresso: di nuovo collegata" in registro
    # mai l'indirizzo nel registro
    assert "rtsp://" not in registro


def test_attesa_crescente_con_tetto():
    assert prossima_attesa(1) == 2
    assert prossima_attesa(16) == 32
    assert prossima_attesa(32) == 60
    assert prossima_attesa(60) == 60


def test_apri_sorgente_sceglie_il_tipo(tmp_path):
    percorso = tmp_path / "prova.mp4"
    scrivi_video(percorso, 5, 25)
    assert isinstance(apri_sorgente(str(percorso), 5, "prova"), VideoRegistrato)
