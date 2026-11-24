"""Cadute, passo 1 (GPU): scheletri di tutti i video dei dataset di cadute con YOLO26-pose n e s + tracking BoT-SORT.

Un file .npz per video e per modello in /kaggle/working/scheletri/<modello>/<dataset>/<percorso relativo>.npz con,
per ogni persona trovata in ogni fotogramma: numero del fotogramma, id della traccia, box, confidenza del box e
17 punti COCO (x, y, confidenza) in pixel. Le etichette non si leggono qui: le legge il passo delle finestre dai file
originali dei dataset (allegati anche là).
- Tutti i fotogrammi alla frequenza originale (CAUCAFall 20, GMDCSA 15-30, Le2i 25, UR Fall 30 fps): la frequenza
  delle finestre si sceglie dopo, è una decisione aperta di Marco.
- Due grandezze di posa (n e s) perché la scelta della grandezza è aperta (Marco, 24/11): n sulla GPU 0, s sulla
  GPU 1, due processi per GPU (come ARGO).
- I video si leggono con ffmpeg e non con OpenCV: gli avi di Le2i (video grezzo + audio mp3) fanno cadere OpenCV
  con un errore nativo (esplorazione del 24/11).
"""
import json
import multiprocessing
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import cv2
import numpy as np

subprocess.run([sys.executable, "-m", "pip", "install", "-q", "ultralytics>=8.4", "lap"], check=True)
if shutil.which("ffprobe") is None:   # build statica di ffmpeg se l'immagine di Kaggle non l'ha (come in ARGO)
    subprocess.run("curl -sL https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz | "
                   "tar -xJ -C /tmp && cp /tmp/ffmpeg-*-static/ff* /usr/local/bin/", shell=True, check=True)

INGRESSO = Path("/kaggle/input")
USCITA = Path("/kaggle/working")
# nome della cartella montata da Kaggle → nome breve del dataset
DATASET = {
    "caucafall": "caucafall",
    "gmdcsa": "gmdcsa24",
    "ur-fall-detection-dataset": "urfall",
    "falldataset-imvia": "le2i",
}
# modello di posa → GPU che lo usa
MODELLI = {"yolo26n-pose.pt": 0, "yolo26s-pose.pt": 1}
PROCESSI_PER_GPU = 2
ESTENSIONI_VIDEO = [".avi", ".mp4", ".mov", ".mkv"]
ESTENSIONI_IMMAGINE = [".png", ".jpg", ".jpeg"]
IMMAGINI_MINIME_SEQUENZA = 20
# UR Fall è distribuito a fotogrammi png: la pagina ufficiale dice 30 fps
FPS_SEQUENZE = 30.0
# 0,1 come il default di Ultralytics per .track (ARGO D3): il tracker usa anche le persone poco sicure
CONFIDENZA_MINIMA = 0.1


def trova_dataset() -> dict:
    trovati = {}
    for cartella, sottocartelle, _ in os.walk(INGRESSO, followlinks=True):
        percorso = Path(cartella)
        if percorso.name in DATASET and DATASET[percorso.name] not in trovati:
            trovati[DATASET[percorso.name]] = percorso
        if len(percorso.relative_to(INGRESSO).parts) >= 3:
            sottocartelle.clear()
    return trovati


def info_video(percorso: Path) -> dict:
    comando = ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
               "stream=width,height,avg_frame_rate:format=duration", "-of", "json", str(percorso)]
    risultato = subprocess.run(comando, capture_output=True, text=True)
    if risultato.returncode != 0:
        return {}
    dati = json.loads(risultato.stdout)
    if not dati.get("streams"):
        return {}
    flusso = dati["streams"][0]
    numeratore, denominatore = flusso.get("avg_frame_rate", "0/0").split("/")
    fps = 0.0
    if float(denominatore) > 0:
        fps = float(numeratore) / float(denominatore)
    return {"larghezza": int(flusso["width"]), "altezza": int(flusso["height"]), "fps": fps}


def elenca_sorgenti(dataset: dict) -> list:
    """Video e sequenze di immagini di tutti i dataset. Una cartella con un video non è anche una sequenza
    (CAUCAFall ha nella stessa cartella l'avi e i suoi png)."""
    sorgenti = []
    for nome in sorted(dataset):
        radice = dataset[nome]
        for cartella, _, nomi in os.walk(radice, followlinks=True):
            nomi_ordinati = sorted(nomi)
            video = []
            immagini = []
            for nome_file in nomi_ordinati:
                estensione = Path(nome_file).suffix.lower()
                if estensione in ESTENSIONI_VIDEO:
                    video.append(Path(cartella) / nome_file)
                elif estensione in ESTENSIONI_IMMAGINE:
                    immagini.append(Path(cartella) / nome_file)
            for percorso in video:
                informazioni = info_video(percorso)
                if not informazioni:
                    print("video illeggibile:", percorso, flush=True)
                    continue
                relativo = str(percorso.relative_to(radice))
                sorgenti.append({"dataset": nome, "relativo": relativo, "percorso": str(percorso), "tipo": "video",
                                 "fps": informazioni["fps"], "larghezza": informazioni["larghezza"],
                                 "altezza": informazioni["altezza"]})
            if not video and len(immagini) >= IMMAGINI_MINIME_SEQUENZA:
                relativo = str(Path(cartella).relative_to(radice))
                sorgenti.append({"dataset": nome, "relativo": relativo, "percorso": cartella, "tipo": "sequenza",
                                 "fps": FPS_SEQUENZE, "immagini": [str(immagine) for immagine in immagini]})
    return sorgenti


def nuovo_tracker(modello) -> None:
    """Tracker vuoto per un video nuovo. Si chiama sempre .track con persist=True: con persist=False al primo
    fotogramma Ultralytics ricrea il tracker a ogni chiamata e le tracce non durano."""
    predittore = modello.predictor
    if predittore is not None and hasattr(predittore, "trackers"):
        for tracker in predittore.trackers:
            tracker.reset()


def analizza(modello, frame: np.ndarray, indice: int, dispositivo: int, percorso_tracker: str, righe: dict) -> None:
    risultato = modello.track(frame, persist=True, tracker=percorso_tracker, conf=CONFIDENZA_MINIMA, imgsz=640,
                              device=dispositivo, verbose=False)[0]
    numero = len(risultato.boxes)
    if numero == 0:
        return
    box = risultato.boxes.xyxy.cpu().numpy()
    confidenze = risultato.boxes.conf.cpu().numpy()
    tracce = np.full(numero, -1)
    if risultato.boxes.id is not None:
        tracce = risultato.boxes.id.cpu().numpy().astype(int)
    punti = risultato.keypoints.data.cpu().numpy()
    for persona in range(numero):
        righe["frame"].append(indice)
        righe["traccia"].append(tracce[persona])
        righe["box"].append(box[persona])
        righe["conf"].append(confidenze[persona])
        righe["punti"].append(punti[persona])


def estrai_sorgente(modello, sorgente: dict, dispositivo: int, percorso_tracker: str) -> tuple:
    """Righe (una per persona per fotogramma) e numero di fotogrammi letti."""
    nuovo_tracker(modello)
    righe = {"frame": [], "traccia": [], "box": [], "conf": [], "punti": []}
    numero_frame = 0
    if sorgente["tipo"] == "video":
        larghezza = sorgente["larghezza"]
        altezza = sorgente["altezza"]
        byte_per_frame = larghezza * altezza * 3
        comando = ["ffmpeg", "-v", "error", "-i", sorgente["percorso"], "-f", "rawvideo", "-pix_fmt", "bgr24", "-"]
        processo = subprocess.Popen(comando, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        while True:
            dati = processo.stdout.read(byte_per_frame)
            if len(dati) < byte_per_frame:
                break
            frame = np.frombuffer(dati, dtype=np.uint8).reshape(altezza, larghezza, 3)
            analizza(modello, frame, numero_frame, dispositivo, percorso_tracker, righe)
            numero_frame += 1
        processo.stdout.close()
        processo.wait()
    else:
        for percorso_immagine in sorgente["immagini"]:
            frame = cv2.imread(percorso_immagine)
            if frame is None:
                continue
            if numero_frame == 0:
                sorgente["larghezza"] = frame.shape[1]
                sorgente["altezza"] = frame.shape[0]
            analizza(modello, frame, numero_frame, dispositivo, percorso_tracker, righe)
            numero_frame += 1
    return righe, numero_frame


def salva(righe: dict, numero_frame: int, sorgente: dict, nome_modello: str) -> None:
    cartella_modello = USCITA / "scheletri" / Path(nome_modello).stem
    percorso = cartella_modello / sorgente["dataset"] / (sorgente["relativo"] + ".npz")
    percorso.parent.mkdir(parents=True, exist_ok=True)
    numero = len(righe["frame"])
    box = np.zeros((0, 4), dtype=np.float32)
    punti = np.zeros((0, 17, 3), dtype=np.float32)
    if numero > 0:
        box = np.array(righe["box"], dtype=np.float32)
        punti = np.array(righe["punti"], dtype=np.float32)
    np.savez_compressed(percorso, frame=np.array(righe["frame"], dtype=np.int32),
                        traccia=np.array(righe["traccia"], dtype=np.int32), box=box,
                        conf=np.array(righe["conf"], dtype=np.float32), punti=punti,
                        numero_frame=numero_frame, fps=sorgente["fps"], larghezza=sorgente.get("larghezza", 0),
                        altezza=sorgente.get("altezza", 0))


def lavora(nome_modello: str, dispositivo: int, sorgenti: list, percorso_tracker: str, etichetta: str) -> None:
    """Un processo: carica il modello sulla sua GPU ed estrae le sue sorgenti."""
    from ultralytics import YOLO

    modello = YOLO(nome_modello)
    inizio = time.perf_counter()
    frame_totali = 0
    for numero, sorgente in enumerate(sorgenti):
        righe, numero_frame = estrai_sorgente(modello, sorgente, dispositivo, percorso_tracker)
        salva(righe, numero_frame, sorgente, nome_modello)
        frame_totali += numero_frame
        if numero % 20 == 0:
            secondi = time.perf_counter() - inizio
            print(f"[{etichetta}] {numero + 1}/{len(sorgenti)} sorgenti, {frame_totali} fotogrammi, "
                  f"{frame_totali / max(secondi, 1):.1f} fotogrammi/s", flush=True)
    secondi = time.perf_counter() - inizio
    tempi = {"modello": nome_modello, "sorgenti": len(sorgenti), "fotogrammi": frame_totali,
             "secondi": round(secondi, 1)}
    (USCITA / f"tempi_{etichetta}.json").write_text(json.dumps(tempi))
    print(f"[{etichetta}] finito: {tempi}", flush=True)


def tracker_telecamera_ferma() -> str:
    """botsort.yaml di Ultralytics senza compensazione del movimento (costa ~11 ms a fotogramma, ARGO):
    le telecamere dei dataset e di casa sono ferme."""
    from ultralytics.utils.checks import check_yaml

    testo = Path(check_yaml("botsort.yaml")).read_text()
    testo = testo.replace("gmc_method: sparseOptFlow", "gmc_method: none")
    percorso = USCITA / "botsort_fermo.yaml"
    percorso.write_text(testo)
    return str(percorso)


dataset = trova_dataset()
for nome in sorted(dataset):
    print("dataset trovato:", nome, dataset[nome], flush=True)
sorgenti = elenca_sorgenti(dataset)
conteggio = {}
for sorgente in sorgenti:
    chiave = sorgente["dataset"] + " " + sorgente["tipo"]
    if chiave not in conteggio:
        conteggio[chiave] = 0
    conteggio[chiave] += 1
print("sorgenti:", conteggio, flush=True)
elenco = []
for sorgente in sorgenti:
    voce = {}
    for chiave in sorgente:
        if chiave != "immagini":
            voce[chiave] = sorgente[chiave]
    elenco.append(voce)
(USCITA / "elenco_sorgenti.json").write_text(json.dumps(elenco, indent=1))
percorso_tracker = tracker_telecamera_ferma()

# fork: il processo principale non ha toccato la GPU, ogni figlio inizializza la sua
contesto = multiprocessing.get_context("fork")
processi = []
for nome_modello in MODELLI:
    for parte in range(PROCESSI_PER_GPU):
        etichetta = f"{Path(nome_modello).stem}_parte{parte}"
        mie_sorgenti = sorgenti[parte::PROCESSI_PER_GPU]
        processo = contesto.Process(target=lavora, args=(nome_modello, MODELLI[nome_modello], mie_sorgenti,
                                                         percorso_tracker, etichetta))
        processo.start()
        processi.append(processo)
for processo in processi:
    processo.join()
    print("processo finito con codice", processo.exitcode, flush=True)
fatti = len(list((USCITA / "scheletri").rglob("*.npz")))
print("file npz:", fatti, "attesi:", len(sorgenti) * len(MODELLI), flush=True)
