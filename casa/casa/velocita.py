"""Velocità sulla CPU.

1. Percezione condivisa: millisecondi per fotogramma di una telecamera per ogni configurazione (grandezza dei
   modelli, rilevatore di oggetti sì/no, lato dell'immagine).
       uv run python -m casa.velocita --video data/video/prova.mp4 --fotogrammi 60 --giri 2
2. Ciclo intero (con --configurazione): il programma vero (lettura a 10 al secondo, analisi a 5 e a 10 durante gli
   eventi, ritorni indietro, analizzatori, specialisti) su tutto il video, con posa n e con posa s (ognuna con il
   suo classificatore delle cadute); poi il costo di ogni specialista da solo.
       uv run python -m casa.velocita --configurazione prova.json

Le configurazioni si provano una dopo l'altra e per più giri: in ARGO i tempi sul portatile cambiavano del ±20% a
seconda di cosa faceva Marco, quindi si confrontano solo misure fatte in fila.
"""

import argparse
from dataclasses import dataclass
import datetime
import statistics
import time
from zoneinfo import ZoneInfo

import numpy as np

from casa.aspetto_zona import AreaZona
from casa.classificatore_cadute import ClassificatoreCadute
from casa.configurazione import leggi_configurazione
from casa.farmaco import ModelloFarmaci
from casa.pasto import ModelloPiatto
from casa.percezione import RILEVATORE_PREDEFINITO, Percezione
from casa.principale import (FPS_LETTURA, PESI_CADUTE, PESI_CIBO, PESI_FARMACI, PESI_PORTA, Specialisti, elabora,
                             prepara_telecamere)
from casa.registro import RegistroLocale
from casa.riconoscimento_farmaci import crea_riconoscitore
from casa.sorgenti import VideoRegistrato
from casa.uscita import ModelloPorta
from casa.zone import zone_del_tipo


@dataclass
class Configurazione:
    nome: str
    posa: str
    rilevatore: str | None  # None: senza rilevatore di oggetti
    lato: int               # lato dell'immagine data ai modelli


CONFIGURAZIONI = [
    Configurazione("posa n 640", "pesi/yolo26n-pose.pt", None, 640),
    Configurazione("posa n + oggetti n 640", "pesi/yolo26n-pose.pt", "pesi/yolo26n.pt", 640),
    Configurazione("posa s 640", "pesi/yolo26s-pose.pt", None, 640),
    Configurazione("posa s + oggetti s 640", "pesi/yolo26s-pose.pt", "pesi/yolo26s.pt", 640),
    Configurazione("posa n 480", "pesi/yolo26n-pose.pt", None, 480),
    Configurazione("posa n + oggetti n 480", "pesi/yolo26n-pose.pt", "pesi/yolo26n.pt", 480),
    Configurazione("posa n 320", "pesi/yolo26n-pose.pt", None, 320),
]
FOTOGRAMMI_DI_RISCALDAMENTO = 3


def leggi_fotogrammi(percorso: str, fps: float, quanti: int) -> list:
    video = VideoRegistrato(percorso, fps, "velocita")
    immagini = []
    while len(immagini) < quanti:
        fotogramma = video.leggi()
        if fotogramma is None:
            break
        immagini.append(fotogramma.immagine)
    return immagini


def misura(configurazione: Configurazione, immagini: list) -> list:
    """Millisecondi per fotogramma (posa + tracking + eventuale rilevatore), uno per fotogramma."""
    percezione = Percezione(configurazione.posa, configurazione.rilevatore, lato_immagine=configurazione.lato)
    con_oggetti = configurazione.rilevatore is not None
    ora = datetime.datetime.now(datetime.timezone.utc)
    tracker = percezione.nuovo_tracker()
    for indice in range(FOTOGRAMMI_DI_RISCALDAMENTO):
        percezione.osserva(immagini[indice], tracker, con_oggetti, "velocita", "prova", ora)
    tracker = percezione.nuovo_tracker()
    tempi = []
    for immagine in immagini:
        partenza = time.perf_counter()
        percezione.osserva(immagine, tracker, con_oggetti, "velocita", "prova", ora)
        tempi.append((time.perf_counter() - partenza) * 1000)
    return tempi


class PercezioneContata(Percezione):
    """La percezione vera che conta i fotogrammi analizzati e il loro tempo."""

    def __init__(self, percorso_posa: str, percorso_rilevatore: str | None):
        super().__init__(percorso_posa, percorso_rilevatore)
        self.analizzati = 0
        self.secondi = 0.0

    def osserva(self, immagine, tracker, con_oggetti, telecamera_id, stanza, ora):
        partenza = time.perf_counter()
        osservazione = super().osserva(immagine, tracker, con_oggetti, telecamera_id, stanza, ora)
        self.secondi = self.secondi + time.perf_counter() - partenza
        self.analizzati = self.analizzati + 1
        return osservazione


def carica_specialisti_per_la_prova(configurazione, posa: str) -> Specialisti:
    specialisti = Specialisti()
    specialisti.riconoscitore = crea_riconoscitore(configurazione.personalizzazione,
                                                   configurazione.cartella_foto_farmaci)
    specialisti.porta = ModelloPorta(PESI_PORTA)
    specialisti.piatto = ModelloPiatto(PESI_CIBO)
    specialisti.farmaci = ModelloFarmaci(PESI_FARMACI)
    pesi = PESI_CADUTE[posa]
    specialisti.cadute = ClassificatoreCadute(pesi.percorso, pesi.soglia, pesi.finestre_di_fila)
    return specialisti


def ciclo_intero(percorso_configurazione: str, posa: str, cartella: str) -> None:
    configurazione = leggi_configurazione(percorso_configurazione)
    specialisti = carica_specialisti_per_la_prova(configurazione, posa)
    telecamere = prepara_telecamere(configurazione, FPS_LETTURA, specialisti)
    percezione = PercezioneContata(posa, RILEVATORE_PREDEFINITO)
    registro = RegistroLocale(cartella + "/velocita_" + str(time.time_ns()) + ".sqlite3")
    ora_inizio = datetime.datetime(2026, 12, 1, 10, 0, tzinfo=ZoneInfo(configurazione.personalizzazione.fuso_orario))
    partenza = time.perf_counter()
    elabora(telecamere, percezione, registro, None, ora_inizio)
    secondi_totali = time.perf_counter() - partenza
    registro.chiudi()
    secondi_video = 0.0
    for telecamera in telecamere:
        secondi_video = secondi_video + telecamera.letti_finora / FPS_LETTURA
    riga = posa.ljust(24) + str(percezione.analizzati) + " fotogrammi analizzati per " + format(secondi_video, ".0f")
    riga = riga + " s di video letti: " + format(secondi_totali * 1000 / percezione.analizzati, "5.0f")
    riga = riga + " ms a fotogramma analizzato (percezione " + format(percezione.secondi * 1000 / percezione.analizzati,
                                                                     "4.0f")
    riga = riga + " ms), " + format(secondi_totali / secondi_video, "4.2f") + " s di CPU per secondo di video"
    print(riga, flush=True)


def millisecondi(funzione, argomento, volte: int) -> float:
    funzione(argomento)  # riscaldamento
    tempi = []
    for volta in range(volte):
        partenza = time.perf_counter()
        funzione(argomento)
        tempi.append((time.perf_counter() - partenza) * 1000)
    return statistics.median(tempi)


def specialisti_da_soli(percorso_configurazione: str) -> None:
    """Costo di una chiamata di ogni specialista su un fotogramma vero del video, ritagliato come nel programma."""
    configurazione = leggi_configurazione(percorso_configurazione)
    telecamera = configurazione.telecamere[0]
    specialisti = carica_specialisti_per_la_prova(configurazione, "pesi/yolo26n-pose.pt")
    immagine = leggi_fotogrammi(telecamera.sorgente, 1, 1)[0]
    righe = []
    for tipo in ["porta", "tavolo", "portapillole"]:
        zone = zone_del_tipo(telecamera, tipo)
        if len(zone) == 0:
            continue
        area = AreaZona(zone[0], immagine)
        ritaglio = np.ascontiguousarray(area.ritaglio(immagine))
        lato = str(ritaglio.shape[1]) + "×" + str(ritaglio.shape[0])
        if tipo == "porta":
            tempo = millisecondi(specialisti.porta.aperta, ritaglio, 10)
            righe.append("porta (ritaglio " + lato + ")  " + format(tempo, ".0f") + " ms")
        if tipo == "tavolo":
            tempo = millisecondi(specialisti.piatto.maschera_cibo, ritaglio, 10)
            righe.append("piatto (ritaglio " + lato + ")  " + format(tempo, ".0f") + " ms")
        if tipo == "portapillole":
            tempi = []
            for volta in range(11):
                partenza = time.perf_counter()
                specialisti.farmaci.scatole_e_blister(immagine, area)
                tempi.append((time.perf_counter() - partenza) * 1000)
            tempo = statistics.median(tempi[1:])  # il primo è di riscaldamento
            righe.append("farmaci (ritaglio " + lato + ")  " + format(tempo, ".0f") + " ms")
    finestra = np.zeros((specialisti.cadute.lunghezza, 17, 3), np.float32)
    righe.append("classificatore cadute (una finestra)  " + format(
        millisecondi(specialisti.cadute.probabilita_caduta, finestra, 50), ".1f") + " ms")
    if specialisti.riconoscitore is not None:
        ritagli = []
        for numero in range(8):
            ritagli.append(immagine[0:120, 0:120].copy())
        righe.append("CLIP (8 ritagli, una volta a presa)  " + format(
            millisecondi(specialisti.riconoscitore.riconosci, ritagli, 3), ".0f") + " ms")
    for riga in righe:
        print(riga, flush=True)


def main(argomenti: list | None = None) -> None:
    lettore = argparse.ArgumentParser(description="Velocità sulla CPU")
    lettore.add_argument("--video")
    lettore.add_argument("--fotogrammi", type=int, default=60)
    lettore.add_argument("--fps", type=float, default=5, help="fotogrammi al secondo presi dal video")
    lettore.add_argument("--giri", type=int, default=2)
    lettore.add_argument("--configurazione", help="ciclo intero: configurazione con tutti gli analizzatori")
    lettore.add_argument("--cartella", default="data", help="dove scrivere i registri di prova")
    scelte = lettore.parse_args(argomenti)

    if scelte.configurazione is not None:
        for giro in range(scelte.giri):
            print("giro " + str(giro + 1))
            ciclo_intero(scelte.configurazione, "pesi/yolo26n-pose.pt", scelte.cartella)
            ciclo_intero(scelte.configurazione, "pesi/yolo26s-pose.pt", scelte.cartella)
        specialisti_da_soli(scelte.configurazione)
        return

    immagini = leggi_fotogrammi(scelte.video, scelte.fps, scelte.fotogrammi)
    altezza = immagini[0].shape[0]
    larghezza = immagini[0].shape[1]
    print(str(len(immagini)) + " fotogrammi " + str(larghezza) + "×" + str(altezza))
    for giro in range(scelte.giri):
        print("giro " + str(giro + 1))
        for configurazione in CONFIGURAZIONI:
            tempi = misura(configurazione, immagini)
            mediana = statistics.median(tempi)
            media = statistics.mean(tempi)
            fotogrammi_al_secondo = 1000 / media
            riga = configurazione.nome.ljust(26)
            riga = riga + "mediana " + format(mediana, "6.1f") + " ms   media " + format(media, "6.1f") + " ms"
            riga = riga + "   → " + format(fotogrammi_al_secondo, "4.1f") + " fotogrammi/s per una telecamera"
            print(riga, flush=True)


if __name__ == "__main__":
    main()
