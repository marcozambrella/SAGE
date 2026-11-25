"""Oggetti vicino alla testa (regola dei gesti), CPU: rilevatore COCO sui video di Charades a 5 fotogrammi al secondo.

Serve a tarare FRAZIONE_ALTEZZA_OGGETTO_TESTA del programma di casa (casa/casa/casa/scheletro.py): distanza tra il
naso e il box dell'oggetto, in altezze del box della persona. Rilevatore, classi, confidenza e lato dell'immagine sono
quelli di casa (casa/casa/casa/percezione.py); gli scheletri sono già in `sage-gesti-scheletri-n`.
- Solo i video di validazione e test della divisione di gesti_stgcn (1.065, circa 8,6 ore di video): la regola non si
  allena, quindi i video di train non servono.
- Due kernel CPU in parallelo (coordinatore, 25/11): oggetti_charades_1 e oggetti_charades_2 prendono un video sì e
  uno no. Circa 3 h ciascuno: 68 ms a fotogramma sul PC di Marco, circa il doppio sulla CPU di Kaggle.
- Dall'archivio di AI2 (16,3 GB) si leggono solo i video che servono, a pezzi (remotezip).
- Ogni video si salva appena finito; dopo ORE_MASSIME il kernel smette e chiude senza errori.
Uscita: oggetti/<id>.npz con fotogramma (a 5 al secondo: istante = fotogramma / 5), classe (nome COCO), box (x1, y1,
x2, y2 in pixel), conf, numero_frame, larghezza, altezza.
"""
import csv
import json
import random
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

subprocess.run([sys.executable, "-m", "pip", "install", "-q", "ultralytics>=8.4", "remotezip"], check=True)
if shutil.which("ffprobe") is None:   # build statica di ffmpeg se l'immagine di Kaggle non l'ha (come in ARGO)
    subprocess.run("curl -sL https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz | "
                   "tar -xJ -C /tmp && cp /tmp/ffmpeg-*-static/ff* /usr/local/bin/", shell=True, check=True)

from remotezip import RemoteZip
from ultralytics import YOLO

INIZIO_KERNEL = time.time()
# il limite di Kaggle è 12 h: ci si ferma prima e si tiene quello che è già salvato
ORE_MASSIME = 10.5
INGRESSO = Path("/kaggle/input")
USCITA = Path("/kaggle/working")
TEMPORANEA = Path("/tmp/charades")
ARCHIVIO_VIDEO = "https://ai2-public-datasets.s3-us-west-2.amazonaws.com/charades/Charades_v1_480.zip"
# lancia.sh scrive qui il nome della cartella del kernel: oggetti_charades_1 o oggetti_charades_2
CARTELLA_DEL_KERNEL = "NOME_KERNEL"
PARTE = int(CARTELLA_DEL_KERNEL.split("_")[-1])
NUMERO_PARTI = 2
FPS_CASA = 5
QUOTA_VALIDAZIONE = 0.15
# come casa/casa/casa/percezione.py
RILEVATORE = "yolo26n.pt"
LATO_IMMAGINE = 640
CONFIDENZA_MINIMA_OGGETTI = 0.25
CIBI_COCO = ("banana", "apple", "sandwich", "orange", "broccoli", "carrot", "hot dog", "pizza", "donut", "cake")
CLASSI_OGGETTI = ("bottle", "wine glass", "cup", "bowl", "dining table") + CIBI_COCO


def tempo_scaduto() -> bool:
    return time.time() - INIZIO_KERNEL > ORE_MASSIME * 3600


def divisioni(cartella: Path) -> dict:
    """id del video → train / val / test, come in gesti_stgcn e tara_gesti: val = il 15% dei soggetti di train."""
    scelti = json.loads((cartella / "video_scelti.json").read_text())
    soggetti = {}
    for nome in ["Charades_v1_train.csv", "Charades_v1_test.csv"]:
        with open(cartella / nome) as file:
            for riga in csv.DictReader(file):
                soggetti[riga["id"]] = riga["subject"]
    soggetti_train = set()
    for identificativo in scelti:
        if scelti[identificativo]["divisione"] == "train":
            soggetti_train.add(soggetti[identificativo])
    soggetti_train = sorted(soggetti_train)
    soggetti_val = set(random.Random(0).sample(soggetti_train, int(round(len(soggetti_train) * QUOTA_VALIDAZIONE))))
    risultato = {}
    for identificativo in scelti:
        divisione = scelti[identificativo]["divisione"]
        if divisione == "train" and soggetti[identificativo] in soggetti_val:
            divisione = "val"
        risultato[identificativo] = divisione
    return risultato


def dimensioni_video(percorso: Path) -> tuple:
    """(larghezza, altezza) in pixel, come info_video di gesti_scheletri (lo stesso ffmpeg degli scheletri)."""
    comando = ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
               "-of", "json", str(percorso)]
    risultato = subprocess.run(comando, capture_output=True, text=True)
    flusso = json.loads(risultato.stdout)["streams"][0]
    return int(flusso["width"]), int(flusso["height"])


def rileva_oggetti(rilevatore, percorso: Path) -> dict:
    """Gli oggetti di CLASSI_OGGETTI in ogni fotogramma a FPS_CASA, letti con ffmpeg come in gesti_scheletri."""
    larghezza, altezza = dimensioni_video(percorso)
    byte_per_frame = larghezza * altezza * 3
    comando = ["ffmpeg", "-v", "error", "-i", str(percorso), "-vf", f"fps={FPS_CASA}",
               "-f", "rawvideo", "-pix_fmt", "bgr24", "-"]
    processo = subprocess.Popen(comando, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    righe = {"fotogramma": [], "classe": [], "box": [], "conf": []}
    numero_frame = 0
    while True:
        dati = processo.stdout.read(byte_per_frame)
        if len(dati) < byte_per_frame:
            break
        frame = np.frombuffer(dati, dtype=np.uint8).reshape(altezza, larghezza, 3)
        risultato = rilevatore.predict(frame, conf=CONFIDENZA_MINIMA_OGGETTI, imgsz=LATO_IMMAGINE, device="cpu",
                                       verbose=False)[0]
        box = risultato.boxes.xyxy.cpu().numpy()
        classi = risultato.boxes.cls.int().cpu().numpy()
        confidenze = risultato.boxes.conf.cpu().numpy()
        for indice in range(len(box)):
            nome = risultato.names[int(classi[indice])]
            if nome in CLASSI_OGGETTI:
                righe["fotogramma"].append(numero_frame)
                righe["classe"].append(nome)
                righe["box"].append(box[indice])
                righe["conf"].append(float(confidenze[indice]))
        numero_frame += 1
    processo.stdout.close()
    processo.wait()
    righe["numero_frame"] = numero_frame
    righe["larghezza"] = larghezza
    righe["altezza"] = altezza
    return righe


def salva(righe: dict, destinazione: Path) -> None:
    box = np.zeros((0, 4), dtype=np.float32)
    if len(righe["box"]) > 0:
        box = np.stack(righe["box"]).astype(np.float32)
    np.savez_compressed(destinazione, fotogramma=np.array(righe["fotogramma"], dtype=np.int32),
                        classe=np.array(righe["classe"], dtype=str), box=box,
                        conf=np.array(righe["conf"], dtype=np.float32), numero_frame=righe["numero_frame"],
                        fps=FPS_CASA, larghezza=righe["larghezza"], altezza=righe["altezza"])


cartella_dati = None
for percorso in sorted(INGRESSO.rglob("video_scelti.json")):
    cartella_dati = percorso.parent
divisione_per_video = divisioni(cartella_dati)
da_fare = []
for identificativo in sorted(divisione_per_video):
    if divisione_per_video[identificativo] != "train":
        da_fare.append(identificativo)
mia_parte = []
for posizione in range(len(da_fare)):
    if posizione % NUMERO_PARTI == PARTE - 1:
        mia_parte.append(da_fare[posizione])
print(f"parte {PARTE} di {NUMERO_PARTI}: {len(mia_parte)} video su {len(da_fare)} (val + test)", flush=True)

TEMPORANEA.mkdir(parents=True, exist_ok=True)
cartella_uscita = USCITA / "oggetti"
cartella_uscita.mkdir(exist_ok=True)
rilevatore = YOLO(RILEVATORE)
fatti = 0
with RemoteZip(ARCHIVIO_VIDEO) as archivio:
    nomi_nell_archivio = {}
    for nome in archivio.namelist():
        if nome.endswith(".mp4"):
            nomi_nell_archivio[Path(nome).stem] = nome
    for identificativo in mia_parte:
        if tempo_scaduto():
            print(f"tempo scaduto: mi fermo dopo {fatti} video su {len(mia_parte)}", flush=True)
            break
        try:
            percorso_video = Path(archivio.extract(nomi_nell_archivio[identificativo], TEMPORANEA))
        except Exception as errore:   # un video che non arriva non deve fermare il kernel
            print("video non scaricato:", identificativo, errore, flush=True)
            continue
        righe = rileva_oggetti(rilevatore, percorso_video)
        salva(righe, cartella_uscita / f"{identificativo}.npz")
        percorso_video.unlink()
        fatti += 1
        if fatti % 25 == 0:
            ore = (time.time() - INIZIO_KERNEL) / 3600
            print(f"{fatti}/{len(mia_parte)} video in {ore:.2f} h", flush=True)
ore = (time.time() - INIZIO_KERNEL) / 3600
print(f"finito: {fatti}/{len(mia_parte)} video in {ore:.2f} h", flush=True)
