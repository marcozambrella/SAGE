"""Gesti (prendere il farmaco, bere, mangiare), passo 1 (GPU): scheletri dei video di Charades.

Proposta di Marco (24/11): riconoscere la presa del farmaco anche dal movimento (mano al portapillole, mano alla
bocca, spesso una bevuta) con un classificatore sulle finestre di scheletri, come per le cadute. Charades
(9.848 video girati in casa, licenza non commerciale, ammessa da D34) ha le azioni con i secondi:
c129 prendere/assumere una medicina, c128 tenere una medicina, c106 bere da tazza/bicchiere/bottiglia,
c156 mangiare qualcosa, c065 mangiare un panino.
- Si scaricano dall'archivio ufficiale di AI2 le annotazioni (Charades.zip, 3,5 MB) e i video a 480p
  (Charades_v1_480.zip, 16,3 GB); si estraggono solo i video con queste azioni + VIDEO_ALTRO video senza
  (esempi di "altro").
- Scheletri a FPS_ESTRAZIONE fotogrammi al secondo (i gesti durano qualche secondo; 12 fps lasciano scegliere
  dopo 12, 6 o 4 fps per le finestre), posa n e s come le cadute (blocco comune).
Uscita: scheletri/<modello>/charades/<id>.mp4.npz, le annotazioni csv e video_scelti.json.
"""
import csv
import json
import multiprocessing
import random
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

import cv2
import numpy as np

subprocess.run([sys.executable, "-m", "pip", "install", "-q", "ultralytics>=8.4", "lap"], check=True)
if shutil.which("ffprobe") is None:   # build statica di ffmpeg se l'immagine di Kaggle non l'ha (come in ARGO)
    subprocess.run("curl -sL https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz | "
                   "tar -xJ -C /tmp && cp /tmp/ffmpeg-*-static/ff* /usr/local/bin/", shell=True, check=True)

INGRESSO = Path("/kaggle/input")
USCITA = Path("/kaggle/working")
INDIRIZZO_AI2 = "https://ai2-public-datasets.s3-us-west-2.amazonaws.com/charades"
CLASSI_GESTI = ["c129", "c128", "c106", "c156", "c065"]
VIDEO_ALTRO = 1000
FPS_ESTRAZIONE = 12
TEMPORANEA = Path("/tmp/charades")


# ===== blocco comune scheletri: uguale in cadute_scheletri e gesti_scheletri =====
# Kaggle carica un solo file per kernel, quindi questo blocco è copiato in ognuno (come l'avvio comune di ARGO).
# modello di posa → GPU che lo usa; si contano le GPU con nvidia-smi per non inizializzare CUDA prima del fork
MODELLI = {"yolo26n-pose.pt": 0, "yolo26s-pose.pt": 1}
PROCESSI_PER_GPU = 2
elenco_gpu = subprocess.run("nvidia-smi -L", shell=True, capture_output=True, text=True).stdout
if elenco_gpu.count("GPU ") < 2:
    MODELLI = {"yolo26n-pose.pt": "cpu"}
    PROCESSI_PER_GPU = 1
# 0,1 come il default di Ultralytics per .track (ARGO D3): il tracker usa anche le persone poco sicure
CONFIDENZA_MINIMA = 0.1


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
        comando = ["ffmpeg", "-v", "error", "-i", sorgente["percorso"]]
        if "fps_estrazione" in sorgente:
            comando = comando + ["-vf", f"fps={sorgente['fps_estrazione']}"]
        comando = comando + ["-f", "rawvideo", "-pix_fmt", "bgr24", "-"]
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
    fps = sorgente["fps"]
    if "fps_estrazione" in sorgente:
        fps = sorgente["fps_estrazione"]
    np.savez_compressed(percorso, frame=np.array(righe["frame"], dtype=np.int32),
                        traccia=np.array(righe["traccia"], dtype=np.int32), box=box,
                        conf=np.array(righe["conf"], dtype=np.float32), punti=punti,
                        numero_frame=numero_frame, fps=fps, larghezza=sorgente.get("larghezza", 0),
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


def estrai_in_parallelo(sorgenti: list) -> None:
    """Scrive l'elenco delle sorgenti e le divide tra i processi (per ogni modello PROCESSI_PER_GPU processi)."""
    conteggio = {}
    elenco = []
    for sorgente in sorgenti:
        chiave = sorgente["dataset"] + " " + sorgente["tipo"]
        if chiave not in conteggio:
            conteggio[chiave] = 0
        conteggio[chiave] += 1
        voce = {}
        for campo in sorgente:
            if campo != "immagini":
                voce[campo] = sorgente[campo]
        elenco.append(voce)
    print("sorgenti:", conteggio, flush=True)
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
# =====


def scarica(nome_file: str) -> Path:
    destinazione = TEMPORANEA / nome_file
    if not destinazione.exists():
        inizio = time.perf_counter()
        subprocess.run(["curl", "-sS", "-L", "--retry", "5", "-o", str(destinazione), f"{INDIRIZZO_AI2}/{nome_file}"],
                       check=True)
        print(f"scaricato {nome_file} in {time.perf_counter() - inizio:.0f} s", flush=True)
    return destinazione


def azioni_del_video(testo: str) -> list:
    """"c092 11.90 21.20;c147 0.00 12.60" → [("c092", 11.9, 21.2), ...]"""
    azioni = []
    for pezzo in (testo or "").split(";"):
        parti = pezzo.split()
        if len(parti) == 3:
            azioni.append((parti[0], float(parti[1]), float(parti[2])))
    return azioni


TEMPORANEA.mkdir(parents=True, exist_ok=True)
with zipfile.ZipFile(scarica("Charades.zip")) as archivio_annotazioni:
    archivio_annotazioni.extractall(TEMPORANEA)
annotazioni = {}
for percorso_csv in sorted(TEMPORANEA.rglob("Charades_v1_*.csv")):
    if percorso_csv.name not in ["Charades_v1_train.csv", "Charades_v1_test.csv"]:
        continue
    shutil.copy(percorso_csv, USCITA / percorso_csv.name)
    with open(percorso_csv) as file:
        for riga in csv.DictReader(file):
            annotazioni[riga["id"]] = {"divisione": percorso_csv.stem.split("_")[-1], "azioni": riga["actions"],
                                       "lunghezza": riga["length"], "scena": riga["scene"]}
for percorso_classi in TEMPORANEA.rglob("Charades_v1_classes.txt"):
    shutil.copy(percorso_classi, USCITA / percorso_classi.name)
con_gesto = []
senza_gesto = []
for identificativo in sorted(annotazioni):
    classi = []
    for azione in azioni_del_video(annotazioni[identificativo]["azioni"]):
        classi.append(azione[0])
    trovato = False
    for classe in CLASSI_GESTI:
        if classe in classi:
            trovato = True
    if trovato:
        con_gesto.append(identificativo)
    else:
        senza_gesto.append(identificativo)
scelti = con_gesto + random.Random(0).sample(senza_gesto, VIDEO_ALTRO)
print(f"video: {len(annotazioni)}, con gesto {len(con_gesto)}, scelti {len(scelti)}", flush=True)
elenco_scelti = {}
for identificativo in scelti:
    elenco_scelti[identificativo] = annotazioni[identificativo]
(USCITA / "video_scelti.json").write_text(json.dumps(elenco_scelti, indent=1))

archivio_video = scarica("Charades_v1_480.zip")
cartella_video = TEMPORANEA / "video"
cartella_video.mkdir(exist_ok=True)
insieme_scelti = set(scelti)
with zipfile.ZipFile(archivio_video) as archivio:
    for nome in archivio.namelist():
        identificativo = Path(nome).stem
        if nome.endswith(".mp4") and identificativo in insieme_scelti:
            (cartella_video / Path(nome).name).write_bytes(archivio.read(nome))
archivio_video.unlink()   # 16 GB in meno sul disco temporaneo
sorgenti = []
for percorso in sorted(cartella_video.iterdir()):
    informazioni = info_video(percorso)
    if not informazioni:
        print("video illeggibile:", percorso.name, flush=True)
        continue
    sorgenti.append({"dataset": "charades", "relativo": percorso.name, "percorso": str(percorso), "tipo": "video",
                     "fps": informazioni["fps"], "fps_estrazione": FPS_ESTRAZIONE,
                     "larghezza": informazioni["larghezza"], "altezza": informazioni["altezza"]})
estrai_in_parallelo(sorgenti)
