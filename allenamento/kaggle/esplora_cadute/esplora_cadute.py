"""Esplorazione dei dataset di cadute (kernel solo CPU, gratis): formato, numero di video, etichette, luce, posa.

Per ogni dataset allegato: file per estensione e per cartella, video (fps, fotogrammi, risoluzione, durata),
sequenze di immagini, esempi dei file di etichette e dei README, quanti video sembrano in infrarosso (saturazione
quasi zero), un mosaico di fotogrammi per vedere l'inquadratura e una prova della posa YOLO26 n e s su pochi
fotogrammi (quante persone trova, confidenza, tempo per fotogramma sulla CPU di Kaggle).
Uscita in /kaggle/working: esplorazione.json, esplorazione.md, mosaico_<dataset>.jpg, posa_<dataset>.jpg.
"""
import json
import os
import random
import re
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

import cv2
import numpy as np

subprocess.run([sys.executable, "-m", "pip", "install", "-q", "ultralytics>=8.4"], check=True)
from ultralytics import YOLO  # noqa: E402  (installato qui sopra)

INGRESSO = Path("/kaggle/input")
USCITA = Path("/kaggle/working")
# nome della cartella montata da Kaggle → nome breve del dataset
DATASET = {
    "caucafall": "caucafall",
    "gmdcsa24": "gmdcsa24_ambatipallisahasra",
    "gmdcsa": "gmdcsa24_nguynthnhquang",
    "ur-fall-detection-dataset": "urfall",
    "falldataset-imvia": "le2i",
}
# la seconda copia di GMDCSA24 serve solo a confrontare le etichette: la posa si prova una volta per dataset
DATASET_PROVA_POSA = ["caucafall", "gmdcsa24_ambatipallisahasra", "urfall", "le2i"]
MODELLI_POSA = ["yolo26n-pose.pt", "yolo26s-pose.pt"]
ESTENSIONI_VIDEO = [".avi", ".mp4", ".mov", ".mkv", ".mpg"]
ESTENSIONI_IMMAGINE = [".png", ".jpg", ".jpeg", ".bmp"]
ESTENSIONI_ETICHETTE = [".txt", ".csv", ".json", ".xml", ".xlsx", ".xls", ".mat"]
# una cartella con almeno tante immagini è una sequenza di fotogrammi (UR Fall è distribuito a png)
IMMAGINI_MINIME_SEQUENZA = 20
# sotto questa saturazione media (0-255) il fotogramma è in bianco e nero: infrarosso (o video in grigio)
SATURAZIONE_INFRAROSSO = 12
VIDEO_PER_PROVA = 16
FRAZIONI_PROVA = [0.25, 0.5, 0.75]
LARGHEZZA_TESSERA = 320
ALTEZZA_TESSERA = 240


def trova_dataset() -> dict:
    """Cartelle dei dataset sotto /kaggle/input (Kaggle le monta a profondità diverse a seconda della versione)."""
    trovati = {}
    for cartella, sottocartelle, _ in os.walk(INGRESSO, followlinks=True):
        percorso = Path(cartella)
        if percorso.name in DATASET and DATASET[percorso.name] not in trovati:
            trovati[DATASET[percorso.name]] = percorso
        if len(percorso.relative_to(INGRESSO).parts) >= 3:
            sottocartelle.clear()   # i dataset sono montati vicino alla radice: non serve scendere oltre
    return trovati


def elenca_file(radice: Path) -> list:
    """Tutti i file sotto radice. os.walk segue i collegamenti: il glob "**" di Python 3.13 no (lezione di ARGO)."""
    file = []
    for cartella, _, nomi in os.walk(radice, followlinks=True):
        for nome in nomi:
            file.append(Path(cartella) / nome)
    file.sort()
    return file


def colore_e_luce(frame: np.ndarray) -> tuple:
    """Saturazione e luminosità medie (0-255): saturazione quasi zero = bianco e nero (infrarosso)."""
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    saturazione = float(hsv[:, :, 1].mean())
    luminosita = float(hsv[:, :, 2].mean())
    return saturazione, luminosita


def leggi_video(percorso: Path) -> dict:
    """fps, fotogrammi, risoluzione, durata e colore/luce del fotogramma a metà video."""
    video = cv2.VideoCapture(str(percorso))
    fps = video.get(cv2.CAP_PROP_FPS)
    numero_frame = int(video.get(cv2.CAP_PROP_FRAME_COUNT))
    larghezza = int(video.get(cv2.CAP_PROP_FRAME_WIDTH))
    altezza = int(video.get(cv2.CAP_PROP_FRAME_HEIGHT))
    video.set(cv2.CAP_PROP_POS_FRAMES, numero_frame // 2)
    letto, frame = video.read()
    video.release()
    secondi = 0.0
    if fps > 0:
        secondi = numero_frame / fps
    info = {"percorso": str(percorso), "fps": round(fps, 2), "frame": numero_frame, "larghezza": larghezza,
            "altezza": altezza, "secondi": round(secondi, 1), "saturazione": None, "luminosita": None}
    if letto:
        saturazione, luminosita = colore_e_luce(frame)
        info["saturazione"] = round(saturazione, 1)
        info["luminosita"] = round(luminosita, 1)
    return info


def leggi_sequenza(cartella: Path, immagini: list) -> dict:
    """Una cartella di fotogrammi: quanti sono, risoluzione e colore/luce dell'immagine a metà."""
    centrale = cv2.imread(str(immagini[len(immagini) // 2]))
    info = {"percorso": str(cartella), "frame": len(immagini), "larghezza": 0, "altezza": 0,
            "saturazione": None, "luminosita": None}
    if centrale is not None:
        info["larghezza"] = centrale.shape[1]
        info["altezza"] = centrale.shape[0]
        saturazione, luminosita = colore_e_luce(centrale)
        info["saturazione"] = round(saturazione, 1)
        info["luminosita"] = round(luminosita, 1)
    return info


def fotogrammi_del_video(percorso: Path, frazioni: list) -> list:
    """I fotogrammi a quelle frazioni della durata (es. 0.5 = metà); salta quelli che non si leggono."""
    video = cv2.VideoCapture(str(percorso))
    numero_frame = int(video.get(cv2.CAP_PROP_FRAME_COUNT))
    fotogrammi = []
    for frazione in frazioni:
        video.set(cv2.CAP_PROP_POS_FRAMES, int(numero_frame * frazione))
        letto, frame = video.read()
        if letto:
            fotogrammi.append(frame)
    video.release()
    return fotogrammi


def fotogrammi_della_sequenza(immagini: list, frazioni: list) -> list:
    fotogrammi = []
    for frazione in frazioni:
        frame = cv2.imread(str(immagini[int(len(immagini) * frazione)]))
        if frame is not None:
            fotogrammi.append(frame)
    return fotogrammi


def tipo_di_file(percorso: Path) -> str:
    """Nome con le cifre sostituite da # (es. "video (#).txt"): raggruppa i file di etichette dello stesso tipo."""
    return re.sub(r"\d+", "#", percorso.name)


def prime_righe(percorso: Path, quante: int) -> list:
    righe = []
    with open(percorso, errors="replace") as file:
        for riga in file:
            righe.append(riga.rstrip("\n")[:200])
            if len(righe) >= quante:
                break
    return righe


def riassunto_etichette(file_etichette: list) -> dict:
    """Per ogni tipo di file di etichette: quanti sono, due esempi e (se sono tanti, es. uno per fotogramma)
    quante righe hanno e quali valori ha la prima colonna (per i txt YOLO è la classe)."""
    per_tipo = {}
    for percorso in file_etichette:
        tipo = tipo_di_file(percorso)
        if tipo not in per_tipo:
            per_tipo[tipo] = []
        per_tipo[tipo].append(percorso)
    riassunto = {}
    for tipo in sorted(per_tipo):
        percorsi = per_tipo[tipo]
        voce = {"numero": len(percorsi), "esempi": {}}
        for percorso in percorsi[:2]:
            if percorso.suffix.lower() in [".txt", ".csv", ".json", ".xml"]:
                voce["esempi"][str(percorso)] = prime_righe(percorso, 25)
        if len(percorsi) >= 20 and percorsi[0].suffix.lower() in [".txt", ".csv"]:
            righe_per_file = Counter()
            prima_colonna = Counter()
            for percorso in percorsi[:3000]:
                righe = prime_righe(percorso, 100000)
                righe_per_file[len(righe)] += 1
                for riga in righe:
                    parti = riga.replace(",", " ").split()
                    if parti:
                        prima_colonna[parti[0]] += 1
            voce["righe_per_file"] = dict(righe_per_file.most_common(10))
            voce["prima_colonna"] = dict(prima_colonna.most_common(15))
        riassunto[tipo] = voce
    return riassunto


def mosaico(fotogrammi: list, didascalie: list, colonne: int = 4) -> np.ndarray:
    tessere = []
    for indice in range(len(fotogrammi)):
        tessera = cv2.resize(fotogrammi[indice], (LARGHEZZA_TESSERA, ALTEZZA_TESSERA))
        cv2.putText(tessera, didascalie[indice], (5, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 255), 1)
        tessere.append(tessera)
    while len(tessere) % colonne != 0:
        tessere.append(np.zeros((ALTEZZA_TESSERA, LARGHEZZA_TESSERA, 3), dtype=np.uint8))
    righe = []
    for inizio in range(0, len(tessere), colonne):
        righe.append(np.hstack(tessere[inizio:inizio + colonne]))
    return np.vstack(righe)


def prova_posa(nome_modello: str, fotogrammi: list, infrarossi: list) -> tuple:
    """Posa su ogni fotogramma: quota con almeno una persona, confidenze medie e millisecondi per fotogramma,
    in totale e separati per fotogrammi in infrarosso e a colori. Ritorna anche i fotogrammi disegnati."""
    modello = YOLO(nome_modello)
    modello.predict(fotogrammi[0], imgsz=640, device="cpu", verbose=False)   # riscaldamento, non misurato
    righe = []
    disegnati = []
    millisecondi = []
    for indice in range(len(fotogrammi)):
        inizio = time.perf_counter()
        risultato = modello.predict(fotogrammi[indice], imgsz=640, device="cpu", conf=0.25, verbose=False)[0]
        millisecondi.append((time.perf_counter() - inizio) * 1000)
        persone = len(risultato.boxes)
        confidenza_box = 0.0
        confidenza_punti = 0.0
        if persone > 0:
            migliore = int(risultato.boxes.conf.argmax())
            confidenza_box = float(risultato.boxes.conf[migliore])
            if risultato.keypoints is not None and risultato.keypoints.conf is not None:
                confidenza_punti = float(risultato.keypoints.conf[migliore].mean())
        righe.append({"persone": persone, "conf_box": confidenza_box, "conf_punti": confidenza_punti,
                      "infrarosso": infrarossi[indice]})
        disegnati.append(risultato.plot())
    riassunto = {"ms_per_frame": round(float(np.median(millisecondi)), 1)}
    for gruppo in ["tutti", "infrarosso", "colore"]:
        scelte = []
        for riga in righe:
            if gruppo == "tutti":
                scelte.append(riga)
            elif gruppo == "infrarosso" and riga["infrarosso"]:
                scelte.append(riga)
            elif gruppo == "colore" and not riga["infrarosso"]:
                scelte.append(riga)
        if not scelte:
            continue
        confidenze_box = []
        confidenze_punti = []
        for riga in scelte:
            if riga["persone"] > 0:
                confidenze_box.append(riga["conf_box"])
                confidenze_punti.append(riga["conf_punti"])
        voce = {"fotogrammi": len(scelte), "con_persona": len(confidenze_box)}
        if confidenze_box:
            voce["conf_box_media"] = round(float(np.mean(confidenze_box)), 3)
            voce["conf_punti_media"] = round(float(np.mean(confidenze_punti)), 3)
        riassunto[gruppo] = voce
    return riassunto, disegnati


def statistiche_sorgenti(sorgenti: list) -> dict:
    """Riassunto di video o sequenze: numero, durata, risoluzioni, fps, quota in infrarosso, luminosità."""
    risoluzioni = Counter()
    fps = Counter()
    secondi = []
    frame_totali = 0
    infrarossi = 0
    luminosita = []
    for sorgente in sorgenti:
        risoluzioni[f"{sorgente['larghezza']}x{sorgente['altezza']}"] += 1
        if "fps" in sorgente:
            fps[str(sorgente["fps"])] += 1
            secondi.append(sorgente["secondi"])
        frame_totali += sorgente["frame"]
        if sorgente["saturazione"] is not None:
            luminosita.append(sorgente["luminosita"])
            if sorgente["saturazione"] < SATURAZIONE_INFRAROSSO:
                infrarossi += 1
    statistiche = {"numero": len(sorgenti), "frame_totali": frame_totali, "risoluzioni": dict(risoluzioni),
                   "fps": dict(fps), "in_bianco_e_nero": infrarossi}
    if secondi:
        statistiche["minuti_totali"] = round(sum(secondi) / 60, 1)
        statistiche["secondi_min_mediana_max"] = [min(secondi), float(np.median(secondi)), max(secondi)]
    if luminosita:
        statistiche["luminosita_min_mediana_max"] = [min(luminosita), float(np.median(luminosita)),
                                                     max(luminosita)]
    return statistiche


def esplora(nome: str, radice: Path) -> dict:
    inizio = time.perf_counter()
    file = elenca_file(radice)
    estensioni = Counter()
    per_cartella = Counter()
    byte_totali = 0
    video = []
    immagini_per_cartella = {}
    file_etichette = []
    leggimi = {}
    for percorso in file:
        estensione = percorso.suffix.lower()
        estensioni[estensione] += 1
        byte_totali += percorso.stat().st_size
        relativo = percorso.relative_to(radice)
        per_cartella["/".join(relativo.parts[:-1][:3])] += 1
        if estensione in ESTENSIONI_VIDEO:
            video.append(percorso)
        elif estensione in ESTENSIONI_IMMAGINE:
            if percorso.parent not in immagini_per_cartella:
                immagini_per_cartella[percorso.parent] = []
            immagini_per_cartella[percorso.parent].append(percorso)
        elif estensione in ESTENSIONI_ETICHETTE:
            file_etichette.append(percorso)
        nome_maiuscolo = percorso.name.upper()
        if nome_maiuscolo.startswith("README") or nome_maiuscolo.startswith("LICENSE"):
            leggimi[str(relativo)] = prime_righe(percorso, 40)
    print(f"[{nome}] {len(file)} file, {byte_totali / 1e9:.2f} GB, {len(video)} video", flush=True)

    info_video = []
    for percorso in video:
        info_video.append(leggi_video(percorso))
    sequenze = []
    immagini_sequenze = {}
    for cartella in sorted(immagini_per_cartella):
        immagini = sorted(immagini_per_cartella[cartella])
        if len(immagini) >= IMMAGINI_MINIME_SEQUENZA:
            sequenze.append(leggi_sequenza(cartella, immagini))
            immagini_sequenze[str(cartella)] = immagini
    print(f"[{nome}] video e sequenze letti ({len(sequenze)} sequenze)", flush=True)

    riassunto = {
        "radice": str(radice), "file_totali": len(file), "gb_totali": round(byte_totali / 1e9, 2),
        "estensioni": dict(estensioni.most_common()), "file_per_cartella": dict(per_cartella.most_common(60)),
        "video": statistiche_sorgenti(info_video), "sequenze": statistiche_sorgenti(sequenze),
        "elenco_video": info_video, "elenco_sequenze": sequenze,
        "etichette": riassunto_etichette(file_etichette), "leggimi": leggimi,
    }

    # fotogrammi per mosaico e posa: video se ci sono, altrimenti sequenze (es. UR Fall)
    generatore = random.Random(0)
    fotogrammi = []
    infrarossi = []
    didascalie = []
    if info_video:
        scelti = generatore.sample(info_video, min(VIDEO_PER_PROVA, len(info_video)))
    else:
        scelti = generatore.sample(sequenze, min(VIDEO_PER_PROVA, len(sequenze)))
    for sorgente in scelti:
        if info_video:
            letti = fotogrammi_del_video(Path(sorgente["percorso"]), FRAZIONI_PROVA)
        else:
            letti = fotogrammi_della_sequenza(immagini_sequenze[sorgente["percorso"]], FRAZIONI_PROVA)
        infrarosso = sorgente["saturazione"] is not None and sorgente["saturazione"] < SATURAZIONE_INFRAROSSO
        breve = str(Path(sorgente["percorso"]).relative_to(radice))[-38:]
        for frame in letti:
            fotogrammi.append(frame)
            infrarossi.append(infrarosso)
            didascalie.append(breve)
    centrali = []
    didascalie_centrali = []
    for indice in range(1, len(fotogrammi), len(FRAZIONI_PROVA)):
        centrali.append(fotogrammi[indice])
        didascalie_centrali.append(didascalie[indice])
    if centrali:
        cv2.imwrite(str(USCITA / f"mosaico_{nome}.jpg"), mosaico(centrali, didascalie_centrali))

    if nome in DATASET_PROVA_POSA and fotogrammi:
        riassunto["posa"] = {}
        for nome_modello in MODELLI_POSA:
            risultato, disegnati = prova_posa(nome_modello, fotogrammi, infrarossi)
            riassunto["posa"][nome_modello] = risultato
            print(f"[{nome}] posa {nome_modello}: {risultato}", flush=True)
            if nome_modello == MODELLI_POSA[-1]:
                disegnati_centrali = []
                for indice in range(1, len(disegnati), len(FRAZIONI_PROVA)):
                    disegnati_centrali.append(disegnati[indice])
                cv2.imwrite(str(USCITA / f"posa_{nome}.jpg"), mosaico(disegnati_centrali, didascalie_centrali))
    riassunto["secondi_esplorazione"] = round(time.perf_counter() - inizio, 1)
    return riassunto


def testo_rapporto(riassunti: dict) -> str:
    righe = ["# Esplorazione dei dataset di cadute", ""]
    for nome in riassunti:
        riassunto = riassunti[nome]
        righe.append(f"## {nome}")
        righe.append(f"- radice `{riassunto['radice']}`: {riassunto['file_totali']} file, "
                     f"{riassunto['gb_totali']} GB")
        righe.append(f"- estensioni: {riassunto['estensioni']}")
        righe.append(f"- video: {json.dumps(riassunto['video'])}")
        righe.append(f"- sequenze di immagini: {json.dumps(riassunto['sequenze'])}")
        if "posa" in riassunto:
            for nome_modello in riassunto["posa"]:
                righe.append(f"- posa {nome_modello}: {json.dumps(riassunto['posa'][nome_modello])}")
        righe.append("- file per cartella (primi livelli):")
        for cartella in riassunto["file_per_cartella"]:
            righe.append(f"  - `{cartella}`: {riassunto['file_per_cartella'][cartella]}")
        righe.append("- etichette:")
        for tipo in riassunto["etichette"]:
            voce = riassunto["etichette"][tipo]
            righe.append(f"  - `{tipo}`: {voce['numero']} file")
            if "righe_per_file" in voce:
                righe.append(f"    righe per file {voce['righe_per_file']}; prima colonna {voce['prima_colonna']}")
            for percorso in voce["esempi"]:
                righe.append(f"    esempio `{percorso}`:")
                righe.append("    ```")
                for riga in voce["esempi"][percorso]:
                    righe.append("    " + riga)
                righe.append("    ```")
        for nome_file in riassunto["leggimi"]:
            righe.append(f"- `{nome_file}`:")
            righe.append("  ```")
            for riga in riassunto["leggimi"][nome_file]:
                righe.append("  " + riga)
            righe.append("  ```")
        righe.append("")
    return "\n".join(righe) + "\n"


trovati = trova_dataset()
for nome in sorted(trovati):
    print("dataset trovato:", nome, trovati[nome], flush=True)
riassunti = {}
for nome in sorted(trovati):
    riassunti[nome] = esplora(nome, trovati[nome])
    # scritti dopo ogni dataset: se il kernel si ferma a metà, quello che è fatto resta nell'uscita
    (USCITA / "esplorazione.json").write_text(json.dumps(riassunti, indent=1, ensure_ascii=False))
    (USCITA / "esplorazione.md").write_text(testo_rapporto(riassunti))
print("fatto", flush=True)
