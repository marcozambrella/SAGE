"""Sorgenti delle telecamere lette con OpenCV (D2): file video (video registrati della demo, D6), RTSP,
telefono come telecamera IP, webcam.

Ogni sorgente dà al massimo `fps` fotogrammi al secondo, ognuno con i secondi passati dall'inizio della sorgente:
il programma li trasforma in ore vere sommandoli all'ora di inizio (vedi principale.py).
Gli indirizzi delle sorgenti restano sul PC di casa: non finiscono mai negli eventi né nei messaggi (D21).
"""

from dataclasses import dataclass
import threading
import time

import cv2
import numpy as np

PREFISSI_DAL_VIVO = ("rtsp://", "rtsps://", "http://", "https://")


@dataclass
class Fotogramma:
    immagine: np.ndarray  # BGR, (altezza, larghezza, 3)
    secondi: float        # dall'inizio della sorgente


def e_dal_vivo(sorgente: str) -> bool:
    """Webcam ("0", "1", ...) o flusso di rete (RTSP, telefono come telecamera IP); altrimenti è un file video."""
    if sorgente.isdigit():
        return True
    for prefisso in PREFISSI_DAL_VIVO:
        if sorgente.startswith(prefisso):
            return True
    return False


def apri_cattura(sorgente: str, telecamera_id: str) -> cv2.VideoCapture:
    if sorgente.isdigit():
        cattura = cv2.VideoCapture(int(sorgente))
    else:
        cattura = cv2.VideoCapture(sorgente)
    if not cattura.isOpened():
        # solo l'id nel messaggio: l'indirizzo può contenere utente e password della telecamera
        raise RuntimeError("telecamera " + telecamera_id + ": sorgente non apribile")
    return cattura


class VideoRegistrato:
    """File video: si prende un fotogramma ogni 1/fps secondi del video, senza aspettare il tempo vero
    (si elabora veloce quanto la CPU, D23). Il tempo viene dal file, quindi vale anche per i video del telefono
    con frequenza variabile."""

    def __init__(self, percorso: str, fps: float, telecamera_id: str):
        self.cattura = apri_cattura(percorso, telecamera_id)
        self.passo = 1.0 / fps
        self.prossimo_secondo = 0.0
        self.finita = False

    def leggi(self) -> Fotogramma | None:
        """Il prossimo fotogramma da elaborare; None a fine video (e da lì `finita` è True)."""
        while not self.finita:
            # grab senza retrieve: i fotogrammi saltati non vengono convertiti in immagine
            if not self.cattura.grab():
                self.finita = True
                self.cattura.release()
                break
            secondi = self.cattura.get(cv2.CAP_PROP_POS_MSEC) / 1000.0
            # un millesimo di tolleranza: i tempi del file sono arrotondati al millisecondo
            if secondi + 0.001 >= self.prossimo_secondo:
                riuscito, immagine = self.cattura.retrieve()
                if not riuscito:
                    continue
                self.prossimo_secondo = self.prossimo_secondo + self.passo
                # se il video ha meno fotogrammi al secondo di `fps` il turno non deve restare indietro
                if self.prossimo_secondo < secondi:
                    self.prossimo_secondo = secondi + self.passo
                return Fotogramma(immagine, secondi)
        return None


class FlussoDalVivo:
    """RTSP, telefono o webcam. Un thread legge di continuo e tiene solo l'ultimo fotogramma: così il ritardo non
    cresce quando l'elaborazione è più lenta della telecamera. `leggi` non aspetta mai, perché lo stesso ciclo
    serve tutte le telecamere."""

    def __init__(self, sorgente: str, fps: float, telecamera_id: str):
        self.cattura = apri_cattura(sorgente, telecamera_id)
        self.passo = 1.0 / fps
        self.inizio = time.monotonic()
        self.ultimo_dato = None          # time.monotonic() dell'ultimo fotogramma dato
        self.ultima_immagine = None
        self.numero_arrivato = 0         # fotogrammi letti dal thread
        self.numero_dato = 0             # numero dell'ultimo fotogramma dato (per non ridare lo stesso)
        self.interrotto = False          # il thread ha smesso di ricevere
        self.finita = False
        self.serratura = threading.Lock()
        self.lettore = threading.Thread(target=self.ricevi, daemon=True)
        self.lettore.start()

    def ricevi(self) -> None:
        while True:
            riuscito, immagine = self.cattura.read()
            if not riuscito:
                break
            with self.serratura:
                self.ultima_immagine = immagine
                self.numero_arrivato = self.numero_arrivato + 1
        self.cattura.release()
        self.interrotto = True

    def leggi(self) -> Fotogramma | None:
        """L'ultimo fotogramma arrivato se è il suo turno (al massimo fps al secondo), altrimenti None."""
        adesso = time.monotonic()
        if self.ultimo_dato is not None and adesso - self.ultimo_dato < self.passo:
            return None
        # si guarda `interrotto` prima di leggere il numero: un ultimo fotogramma arrivato in mezzo non va perso
        interrotto = self.interrotto
        with self.serratura:
            nuovo = self.numero_arrivato > self.numero_dato
            immagine = self.ultima_immagine
            numero = self.numero_arrivato
        if not nuovo:
            if interrotto:
                self.finita = True
            return None
        self.numero_dato = numero
        self.ultimo_dato = adesso
        return Fotogramma(immagine, adesso - self.inizio)


def apri_sorgente(sorgente: str, fps: float, telecamera_id: str):
    """VideoRegistrato o FlussoDalVivo: tutte e due hanno `leggi()` e `finita`."""
    if e_dal_vivo(sorgente):
        return FlussoDalVivo(sorgente, fps, telecamera_id)
    return VideoRegistrato(sorgente, fps, telecamera_id)
