"""Velocità della percezione condivisa sulla CPU: millisecondi per fotogramma di una telecamera per ogni
configurazione (grandezza dei modelli, rilevatore di oggetti sì/no, lato dell'immagine).

Le configurazioni si provano una dopo l'altra sugli stessi fotogrammi e per più giri: in ARGO i tempi sul portatile
cambiavano del ±20% a seconda di cosa faceva Marco, quindi si confrontano solo misure fatte in fila.

    uv run python -m casa.velocita --video data/video/prova.mp4 --fotogrammi 60 --giri 2
"""

import argparse
from dataclasses import dataclass
import datetime
import statistics
import time

from casa.percezione import Percezione
from casa.sorgenti import VideoRegistrato


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


def main(argomenti: list | None = None) -> None:
    lettore = argparse.ArgumentParser(description="Velocità della percezione condivisa sulla CPU")
    lettore.add_argument("--video", required=True)
    lettore.add_argument("--fotogrammi", type=int, default=60)
    lettore.add_argument("--fps", type=float, default=5, help="fotogrammi al secondo presi dal video")
    lettore.add_argument("--giri", type=int, default=2)
    scelte = lettore.parse_args(argomenti)

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
