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
# Riconnessione di un flusso dal vivo caduto: attesa che raddoppia a ogni tentativo, al massimo un minuto.
ATTESA_MINIMA_SECONDI = 1.0
ATTESA_MASSIMA_SECONDI = 60.0


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


def nuova_cattura(sorgente: str) -> cv2.VideoCapture:
    """Apre la sorgente con OpenCV (può non riuscire: va controllato isOpened)."""
    if sorgente.isdigit():
        return cv2.VideoCapture(int(sorgente))
    return cv2.VideoCapture(sorgente)


def apri_cattura(sorgente: str, telecamera_id: str) -> cv2.VideoCapture:
    cattura = nuova_cattura(sorgente)
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


def prossima_attesa(attesa: float) -> float:
    """Attesa prima del tentativo dopo: doppia ogni volta, fino al tetto."""
    return min(attesa * 2, ATTESA_MASSIMA_SECONDI)


class FlussoDalVivo:
    """RTSP, telefono o webcam. Un thread legge di continuo e tiene solo l'ultimo fotogramma: così il ritardo non
    cresce quando l'elaborazione è più lenta della telecamera. `leggi` non aspetta mai, perché lo stesso ciclo
    serve tutte le telecamere.

    Un flusso dal vivo non finisce: se cade (rete, telecamera spenta, webcam staccata) il thread riapre la sorgente
    con attese crescenti (1, 2, 4, ... fino a 60 s) e intanto la telecamera risulta "persa" nel log."""

    def __init__(self, sorgente: str, fps: float, telecamera_id: str):
        self.sorgente = sorgente
        self.telecamera_id = telecamera_id
        self.cattura = apri_cattura(sorgente, telecamera_id)
        self.passo = 1.0 / fps
        self.inizio = time.monotonic()
        self.ultimo_dato = None          # time.monotonic() dell'ultimo fotogramma dato
        self.ultima_immagine = None
        self.numero_arrivato = 0         # fotogrammi letti dal thread
        self.numero_dato = 0             # numero dell'ultimo fotogramma dato (per non ridare lo stesso)
        self.persa = False               # caduta e non ancora ricollegata
        self.finita = False              # resta False: c'è solo per avere la stessa interfaccia di VideoRegistrato
        self.serratura = threading.Lock()
        self.fermo = threading.Event()   # per fermare il thread (anche mentre aspetta un nuovo tentativo)
        self.lettore = threading.Thread(target=self.ricevi, daemon=True)
        self.lettore.start()

    def ricevi(self) -> None:
        attesa = ATTESA_MINIMA_SECONDI
        while not self.fermo.is_set():
            riuscito, immagine = self.cattura.read()
            if riuscito:
                if self.persa:
                    print("telecamera " + self.telecamera_id + ": di nuovo collegata")
                    self.persa = False
                    attesa = ATTESA_MINIMA_SECONDI
                with self.serratura:
                    self.ultima_immagine = immagine
                    self.numero_arrivato = self.numero_arrivato + 1
                continue
            # caduta (o riapertura non riuscita): si chiude, si aspetta e si riprova
            self.persa = True
            print("telecamera " + self.telecamera_id + ": persa, nuovo tentativo tra " + format(attesa, "g") + " s")
            self.cattura.release()
            self.fermo.wait(attesa)
            attesa = prossima_attesa(attesa)
            self.cattura = nuova_cattura(self.sorgente)
        self.cattura.release()

    def ferma(self) -> None:
        self.fermo.set()
        self.lettore.join(timeout=5)

    def leggi(self) -> Fotogramma | None:
        """L'ultimo fotogramma arrivato se è il suo turno (al massimo fps al secondo), altrimenti None."""
        adesso = time.monotonic()
        if self.ultimo_dato is not None and adesso - self.ultimo_dato < self.passo:
            return None
        with self.serratura:
            nuovo = self.numero_arrivato > self.numero_dato
            immagine = self.ultima_immagine
            numero = self.numero_arrivato
        if not nuovo:
            return None
        self.numero_dato = numero
        self.ultimo_dato = adesso
        return Fotogramma(immagine, adesso - self.inizio)


def apri_sorgente(sorgente: str, fps: float, telecamera_id: str):
    """VideoRegistrato o FlussoDalVivo: tutte e due hanno `leggi()` e `finita`."""
    if e_dal_vivo(sorgente):
        return FlussoDalVivo(sorgente, fps, telecamera_id)
    return VideoRegistrato(sorgente, fps, telecamera_id)
