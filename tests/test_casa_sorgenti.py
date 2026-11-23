"""Test del programma di casa: file di configurazione, fasce orarie, sorgenti video con limite di fotogrammi al secondo."""

import datetime
from pathlib import Path
import time

import cv2
import numpy as np
import pytest

from contratti.configurazione import FasciaOraria
from casa.configurazione import dentro_fascia, leggi_configurazione
from casa.sorgenti import FlussoDalVivo, VideoRegistrato, apri_sorgente, e_dal_vivo

ESEMPIO = Path(__file__).resolve().parents[1] / "casa" / "configurazione.esempio.json"


def scrivi_video(percorso: Path, numero_fotogrammi: int, fps: float) -> None:
    """Video sintetico 64×48: il fotogramma i ha tutti i pixel uguali a i×5 (per riconoscerlo)."""
    scrittore = cv2.VideoWriter(str(percorso), cv2.VideoWriter_fourcc(*"mp4v"), fps, (64, 48))
    for indice in range(numero_fotogrammi):
        immagine = np.full((48, 64, 3), indice * 5, np.uint8)
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


def test_flusso_dal_vivo_da_l_ultimo_fotogramma_e_rispetta_il_turno(tmp_path):
    percorso = tmp_path / "prova.mp4"
    scrivi_video(percorso, 20, 25)
    # un file aperto come flusso dal vivo: il thread lo legge tutto subito, come una telecamera più veloce di noi
    flusso = FlussoDalVivo(str(percorso), 10, "prova")
    flusso.lettore.join(timeout=10)
    fotogramma = flusso.leggi()
    assert fotogramma is not None
    # resta solo l'ultimo fotogramma (pixel 19×5 = 95, a meno della compressione)
    assert abs(int(fotogramma.immagine[0, 0, 0]) - 95) < 10
    # subito dopo non è il suo turno
    assert flusso.leggi() is None
    time.sleep(0.15)
    # turno arrivato ma nessun fotogramma nuovo e flusso interrotto: finito
    assert flusso.leggi() is None
    assert flusso.finita


def test_apri_sorgente_sceglie_il_tipo(tmp_path):
    percorso = tmp_path / "prova.mp4"
    scrivi_video(percorso, 5, 25)
    assert isinstance(apri_sorgente(str(percorso), 5, "prova"), VideoRegistrato)
