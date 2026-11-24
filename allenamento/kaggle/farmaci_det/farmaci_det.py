"""Farmaci (D15), GPU: rilevatore YOLO26 n e s di pillole, blister, scatole, portapillole e scomparti.

La telecamera di casa guarda dall'alto con una vista ristretta (Marco, 24/11): gli oggetti sono piccoli, spesso in
infrarosso e con la mano sopra. Molti dataset di pillole invece sono foto ravvicinate e frontali, quindi:
- le foto ravvicinate di pillole (`alexanderyyy/pills-detection-dataset`, 12 mila immagini quasi tutte da vicino)
  sono limitate a MASSIMO_PILLOLE_VICINE immagini, per non coprire i dataset visti dall'alto;
- per una parte delle immagini di allenamento si aggiunge una copia "come la nostra telecamera": scala di grigi
  (infrarosso), bassa risoluzione, rumore e a volte una mano (ellisse color pelle) sopra una parte di un oggetto;
- nell'allenamento: oggetti rimpiccioliti (scale), qualsiasi rotazione e capovolgimento (vista dall'alto).
Dati: tutti i dataset allegati in formato YOLO (Kaggle e Roboflow caricati come dataset privati) o VOC xml
(`perfect9015/pillsdetectiondataset`); le classi si riconoscono dal nome (vedi classe_farmaci).
Uscita: pesi, metriche, tempi e ONNX in /kaggle/working/farmaci/ (vedi il blocco comune).
"""
import csv
import json
import os
import random
import subprocess
import sys
import time
import xml.etree.ElementTree as albero_xml
from pathlib import Path

import cv2
import numpy as np

subprocess.run([sys.executable, "-m", "pip", "install", "-q", "ultralytics>=8.4", "onnx", "onnxslim"], check=True)

INGRESSO = Path("/kaggle/input")
USCITA = Path("/kaggle/working")
# i dati preparati stanno fuori da /kaggle/working: tutto quello che c'è là diventa uscita del kernel (max 20 GB)
DATI = Path("/tmp/dati")


# ===== blocco comune YOLO: uguale in liquido_seg, cibo_seg e farmaci_det =====
# Kaggle carica un solo file per kernel, quindi questo blocco è copiato in ognuno (come l'avvio comune di ARGO).
# Le grandezze n e s si allenano insieme, n sulla GPU 0 e s sulla GPU 1: la scelta della grandezza la fa Marco con
# i numeri (precisione sulla validazione e millisecondi su CPU, 24/11).
GRANDEZZE = ["n", "s"]
LATO_IMMAGINE = 640


def elenca_file(radice: Path) -> list:
    """Tutti i file sotto radice. os.walk segue i collegamenti: il glob "**" di Python 3.13 no (lezione di ARGO)."""
    file = []
    for cartella, _, nomi in os.walk(radice, followlinks=True):
        for nome in nomi:
            file.append(Path(cartella) / nome)
    file.sort()
    return file


def radici_dataset() -> list:
    """Le cartelle dei dataset allegati: /kaggle/input/<nome> o, nelle versioni nuove di Kaggle,
    /kaggle/input/datasets/<utente>/<nome> (esplorazione del 23/11)."""
    radici = []
    for cartella in sorted(INGRESSO.iterdir()):
        if cartella.name == "datasets":
            for utente in sorted(cartella.iterdir()):
                for dataset in sorted(utente.iterdir()):
                    radici.append(dataset)
        elif cartella.is_dir():
            radici.append(cartella)
    return radici


def poligoni_da_maschera(maschera: np.ndarray, area_minima: int = 50) -> list:
    """Contorni esterni di una maschera (valori > 0) come liste [x1, y1, x2, y2, ...] normalizzate 0-1."""
    altezza, larghezza = maschera.shape[:2]
    binaria = (maschera > 0).astype(np.uint8)
    contorni, _ = cv2.findContours(binaria, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    poligoni = []
    for contorno in contorni:
        if cv2.contourArea(contorno) < area_minima:
            continue
        # meno punti: errore massimo 0,2% del perimetro, invisibile a 640 px
        semplice = cv2.approxPolyDP(contorno, 0.002 * cv2.arcLength(contorno, True), True)
        if len(semplice) < 3:
            continue
        punti = []
        for punto in semplice.reshape(-1, 2):
            punti.append(round(float(punto[0]) / larghezza, 6))
            punti.append(round(float(punto[1]) / altezza, 6))
        poligoni.append(punti)
    return poligoni


def riga_da_box(classe: int, valori: list, segmentazione: bool) -> str:
    """Riga YOLO da un box (cx, cy, w, h normalizzati): per la segmentazione diventa un rettangolo."""
    if not segmentazione:
        return f"{classe} {valori[0]:.6f} {valori[1]:.6f} {valori[2]:.6f} {valori[3]:.6f}"
    x1 = valori[0] - valori[2] / 2
    y1 = valori[1] - valori[3] / 2
    x2 = valori[0] + valori[2] / 2
    y2 = valori[1] + valori[3] / 2
    return f"{classe} {x1:.6f} {y1:.6f} {x2:.6f} {y1:.6f} {x2:.6f} {y2:.6f} {x1:.6f} {y2:.6f}"


def riga_da_poligono(classe: int, poligono: list) -> str:
    testo = []
    for valore in poligono:
        testo.append(f"{min(max(valore, 0.0), 1.0):.6f}")
    return f"{classe} " + " ".join(testo)


def aggiungi_esempio(divisione: str, nome: str, percorso_immagine: Path, righe: list, conteggio: dict) -> None:
    """Un'immagine nel dataset preparato: collegamento all'originale (niente copie) + file di etichette."""
    cartella_immagini = DATI / "images" / divisione
    cartella_etichette = DATI / "labels" / divisione
    cartella_immagini.mkdir(parents=True, exist_ok=True)
    cartella_etichette.mkdir(parents=True, exist_ok=True)
    destinazione = cartella_immagini / (nome + percorso_immagine.suffix.lower())
    if not destinazione.exists():
        os.symlink(os.path.abspath(percorso_immagine), destinazione)
    (cartella_etichette / (nome + ".txt")).write_text("\n".join(righe) + "\n")
    chiave = divisione + " " + nome.split("_")[0]
    if chiave not in conteggio:
        conteggio[chiave] = 0
    conteggio[chiave] += 1


def leggi_yaml_semplice(percorso: Path) -> dict:
    """I campi di un data.yaml che servono (names e percorsi), senza dipendere dal formato esatto."""
    import yaml

    return yaml.safe_load(percorso.read_text())


def nomi_classi_yaml(dati_yaml: dict) -> list:
    nomi = dati_yaml.get("names", [])
    if isinstance(nomi, dict):
        elenco = []
        for chiave in sorted(nomi, key=int):
            elenco.append(nomi[chiave])
        return elenco
    return list(nomi)


def importa_yolo(radice: Path, prefisso: str, mappa_classi, segmentazione: bool, conteggio: dict,
                 massimo_immagini: int = 0, scarta_box: bool = False) -> None:
    """Ogni data.yaml sotto radice: immagini e etichette YOLO (box o poligoni) con le classi rinominate da
    mappa_classi(nome) → indice o None (classe scartata). Le cartelle train → train, valid/val/test → validazione.
    scarta_box: per la segmentazione salta le etichette a box invece di farne rettangoli.
    I nomi hanno anche il numero del data.yaml: i dataset Roboflow caricati insieme hanno più data.yaml nella stessa
    radice e con il solo indice le immagini prendevano le etichette di un'altra (bug trovato il 24/11)."""
    numero_yaml = 0
    for percorso_yaml in elenca_file(radice):
        if percorso_yaml.name not in ["data.yaml", "data.yml"]:
            continue
        numero_yaml = numero_yaml + 1
        nomi = nomi_classi_yaml(leggi_yaml_semplice(percorso_yaml))
        nuove_classi = []
        for nome in nomi:
            nuove_classi.append(mappa_classi(str(nome)))
        print(f"[{prefisso}] {percorso_yaml}: classi {nomi} → {nuove_classi}", flush=True)
        immagini = []
        for percorso in elenca_file(percorso_yaml.parent):
            if percorso.suffix.lower() in [".jpg", ".jpeg", ".png", ".bmp", ".webp"] and "images" in percorso.parts:
                immagini.append(percorso)
        if massimo_immagini and len(immagini) > massimo_immagini:
            immagini = random.Random(0).sample(immagini, massimo_immagini)
        for indice, percorso_immagine in enumerate(immagini):
            parti = list(percorso_immagine.parts)
            posizione = len(parti) - 1 - parti[::-1].index("images")
            parti[posizione] = "labels"
            percorso_etichetta = Path(*parti).with_suffix(".txt")
            divisione = "train"
            for parte in percorso_immagine.parts:
                if parte.lower() in ["valid", "val", "test", "validation"]:
                    divisione = "val"
            righe = []
            etichette_lette = 0
            if percorso_etichetta.exists():
                for riga in percorso_etichetta.read_text().splitlines():
                    valori = riga.split()
                    if len(valori) < 5:
                        continue
                    etichette_lette = etichette_lette + 1
                    classe_originale = int(float(valori[0]))
                    if classe_originale >= len(nuove_classi) or nuove_classi[classe_originale] is None:
                        continue
                    numeri = []
                    for valore in valori[1:]:
                        numeri.append(float(valore))
                    if len(numeri) == 4:
                        if segmentazione and scarta_box:
                            continue
                        righe.append(riga_da_box(nuove_classi[classe_originale], numeri, segmentazione))
                    elif segmentazione:
                        righe.append(riga_da_poligono(nuove_classi[classe_originale], numeri))
                    else:
                        # poligono → box che lo contiene, per i rilevatori
                        xs = numeri[0::2]
                        ys = numeri[1::2]
                        box = [(min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, max(xs) - min(xs), max(ys) - min(ys)]
                        righe.append(riga_da_box(nuove_classi[classe_originale], box, False))
            # un'immagine con oggetti segnati ma nessuno tenuto (classe scartata o box nella segmentazione) si salta:
            # non è un esempio negativo, es. le foto di cibo con solo box sarebbero diventate "niente cibo" (24/11)
            if etichette_lette > 0 and not righe:
                continue
            # anche le immagini senza oggetti delle nostre classi servono (esempi negativi)
            aggiungi_esempio(divisione, f"{prefisso}-{numero_yaml}_{indice:06d}", percorso_immagine, righe, conteggio)


def scrivi_yaml(nomi_classi: list) -> Path:
    righe = [f"path: {DATI}", "train: images/train", "val: images/val", "names:"]
    for indice, nome in enumerate(nomi_classi):
        righe.append(f"  {indice}: {nome}")
    percorso = DATI / "data.yaml"
    percorso.write_text("\n".join(righe) + "\n")
    return percorso


def addestra_n_e_s(percorso_yaml: Path, suffisso_modello: str, nome: str, ore: float, opzioni: list) -> None:
    """yolo train delle due grandezze in parallelo (una per GPU). `time` limita le ore (la sessione Kaggle dura al
    massimo 12 h): Ultralytics adatta il calendario del tasso di apprendimento al tempo."""
    processi = []
    for gpu in range(len(GRANDEZZE)):
        grandezza = GRANDEZZE[gpu]
        comando = ["yolo", "train", f"model=yolo26{grandezza}{suffisso_modello}.pt", f"data={percorso_yaml}",
                   "epochs=300", f"time={ore}", f"imgsz={LATO_IMMAGINE}", f"device={gpu}", "batch=16", "workers=2",
                   f"project={USCITA / nome}", f"name=yolo26{grandezza}", "exist_ok=True", "patience=50"]
        comando = comando + opzioni
        print("lancio:", " ".join(comando), flush=True)
        processi.append(subprocess.Popen(comando))
    for processo in processi:
        processo.wait()
        print("allenamento finito con codice", processo.returncode, flush=True)


def ultima_e_migliore_riga(percorso_csv: Path, colonna: str) -> tuple:
    righe = []
    with open(percorso_csv) as file:
        for riga in csv.DictReader(file):
            pulita = {}
            for chiave in riga:
                pulita[chiave.strip()] = riga[chiave].strip()
            righe.append(pulita)
    migliore = righe[0]
    for riga in righe:
        if float(riga[colonna]) > float(migliore[colonna]):
            migliore = riga
    return righe[-1], migliore


def riassumi(percorso_yaml: Path, nome: str, nomi_classi: list, segmentazione: bool) -> None:
    """Per ogni grandezza: metriche per classe sulla validazione, millisecondi per immagine su CPU (proxy: CPU di
    Kaggle, 4 core; il PC di Marco si misura a parte), ONNX, tutto in risultati.json."""
    from ultralytics import YOLO

    colonna = "metrics/mAP50-95(B)"
    if segmentazione:
        colonna = "metrics/mAP50-95(M)"
    immagini_val = sorted((DATI / "images" / "val").iterdir())[:30]
    risultati = {"classi": nomi_classi}
    for grandezza in GRANDEZZE:
        cartella = USCITA / nome / f"yolo26{grandezza}"
        pesi = cartella / "weights" / "best.pt"
        if not pesi.exists():
            risultati[grandezza] = {"errore": "best.pt mancante"}
            continue
        ultima, migliore = ultima_e_migliore_riga(cartella / "results.csv", colonna)
        modello = YOLO(str(pesi))
        metriche = modello.val(data=str(percorso_yaml), imgsz=LATO_IMMAGINE, device=0, plots=False, verbose=False)
        per_classe = {}
        mappe = metriche.box.maps
        if segmentazione:
            mappe = metriche.seg.maps
        for indice in range(len(nomi_classi)):
            per_classe[nomi_classi[indice]] = round(float(mappe[indice]), 4)
        modello_cpu = YOLO(str(pesi))
        for percorso in immagini_val[:3]:
            modello_cpu.predict(str(percorso), imgsz=LATO_IMMAGINE, device="cpu", verbose=False)
        millisecondi = []
        for percorso in immagini_val:
            inizio = time.perf_counter()
            modello_cpu.predict(str(percorso), imgsz=LATO_IMMAGINE, device="cpu", verbose=False)
            millisecondi.append((time.perf_counter() - inizio) * 1000)
        percorso_onnx = modello_cpu.export(format="onnx", imgsz=LATO_IMMAGINE)
        risultati[grandezza] = {
            "epoche": int(float(ultima["epoch"])), "migliore_epoca": int(float(migliore["epoch"])),
            "ore_allenamento": round(float(ultima.get("time", 0) or 0) / 3600, 2),
            "migliore_riga_results_csv": migliore, "mAP50_95_per_classe_val": per_classe,
            "ms_cpu_kaggle_mediana": round(float(np.median(millisecondi)), 1),
            "pesi": str(pesi), "onnx": str(percorso_onnx),
        }
        print(f"[{grandezza}] {risultati[grandezza]}", flush=True)
    (USCITA / nome / "risultati.json").write_text(json.dumps(risultati, indent=1, ensure_ascii=False))
# =====


CLASSI = ["pillola", "blister", "scatola_farmaco", "portapillole", "scomparto"]
MASSIMO_PILLOLE_VICINE = 3000
QUOTA_COPIE_DEGRADATE = 0.3


def classe_farmaci(nome: str):
    """Nome della classe di un dataset → indice in CLASSI, None se non serve (es. mouth, nomi ambigui)."""
    minuscolo = nome.lower().replace("_", " ").replace("-", " ")
    if "compartment" in minuscolo or "scomparto" in minuscolo or "slot" in minuscolo:
        return 4
    for parola in ["pillbox", "pill box", "organizer", "organiser", "portapillole", "pill case", "dispenser"]:
        if parola in minuscolo:
            return 3
    if "blister" in minuscolo:
        return 1
    for parola in ["medicine box", "medicine package", "drug box", "box", "package", "carton", "scatola"]:
        if parola in minuscolo:
            return 2
    for parola in ["pill", "tablet", "capsule", "pastiglia", "compress"]:
        if parola in minuscolo:
            return 0
    return None


def importa_voc(radice: Path, prefisso: str, conteggio: dict) -> None:
    """Annotazioni VOC (un xml per immagine, cartelle annotations/ e images/), tutte in allenamento tranne il 15%."""
    immagini_per_nome = {}
    xml = []
    for percorso in elenca_file(radice):
        if percorso.suffix.lower() in [".jpg", ".jpeg", ".png"]:
            immagini_per_nome[percorso.stem] = percorso
        elif percorso.suffix.lower() == ".xml":
            xml.append(percorso)
    generatore = random.Random(0)
    for indice, percorso_xml in enumerate(xml):
        if percorso_xml.stem not in immagini_per_nome:
            continue
        radice_xml = albero_xml.parse(percorso_xml).getroot()
        larghezza = float(radice_xml.find("size/width").text)
        altezza = float(radice_xml.find("size/height").text)
        if larghezza <= 0 or altezza <= 0:
            continue
        righe = []
        for oggetto in radice_xml.findall("object"):
            classe = classe_farmaci(oggetto.find("name").text)
            if classe is None:
                continue
            riquadro = oggetto.find("bndbox")
            x1 = float(riquadro.find("xmin").text)
            y1 = float(riquadro.find("ymin").text)
            x2 = float(riquadro.find("xmax").text)
            y2 = float(riquadro.find("ymax").text)
            box = [(x1 + x2) / 2 / larghezza, (y1 + y2) / 2 / altezza, (x2 - x1) / larghezza, (y2 - y1) / altezza]
            righe.append(riga_da_box(classe, box, False))
        divisione = "train"
        if generatore.random() < 0.15:
            divisione = "val"
        aggiungi_esempio(divisione, f"{prefisso}_{indice:06d}", immagini_per_nome[percorso_xml.stem], righe, conteggio)


def copia_come_telecamera(percorso_immagine: Path, righe: list, generatore: random.Random) -> np.ndarray:
    """Immagine degradata come una telecamera in alto di notte: grigio, bassa risoluzione, rumore, a volte una
    "mano" (ellisse color pelle) sopra una parte di un oggetto. Le etichette restano le stesse."""
    immagine = cv2.imread(str(percorso_immagine))
    if immagine is None:
        return None
    altezza, larghezza = immagine.shape[:2]
    grigia = cv2.cvtColor(immagine, cv2.COLOR_BGR2GRAY)
    fattore = generatore.uniform(0.25, 0.5)
    piccola = cv2.resize(grigia, (max(8, int(larghezza * fattore)), max(8, int(altezza * fattore))),
                         interpolation=cv2.INTER_AREA)
    grigia = cv2.resize(piccola, (larghezza, altezza), interpolation=cv2.INTER_LINEAR)
    rumore = np.random.default_rng(generatore.randint(0, 10 ** 6)).normal(0, generatore.uniform(3, 10), grigia.shape)
    grigia = np.clip(grigia.astype(np.float32) + rumore, 0, 255).astype(np.uint8)
    degradata = cv2.cvtColor(grigia, cv2.COLOR_GRAY2BGR)
    if righe and generatore.random() < 0.5:
        valori = righe[generatore.randrange(len(righe))].split()
        centro_x = float(valori[1]) * larghezza
        centro_y = float(valori[2]) * altezza
        mezza_larghezza = float(valori[3]) * larghezza / 2
        mezza_altezza = float(valori[4]) * altezza / 2
        # la mano copre circa metà dell'oggetto, spostata verso un lato
        centro = (int(centro_x + generatore.uniform(-1, 1) * mezza_larghezza),
                  int(centro_y + generatore.uniform(-1, 1) * mezza_altezza))
        assi = (max(2, int(mezza_larghezza * generatore.uniform(0.6, 1.0))),
                max(2, int(mezza_altezza * generatore.uniform(0.6, 1.0))))
        tono = generatore.randint(120, 200)
        cv2.ellipse(degradata, centro, assi, generatore.uniform(0, 180), 0, 360, (tono, tono, tono), -1)
    return degradata


def aggiungi_copie_degradate(conteggio: dict) -> None:
    cartella_immagini = DATI / "images" / "train"
    cartella_etichette = DATI / "labels" / "train"
    generatore = random.Random(1)
    originali = sorted(cartella_immagini.iterdir())
    fatte = 0
    for percorso_immagine in originali:
        if generatore.random() >= QUOTA_COPIE_DEGRADATE:
            continue
        righe = []
        percorso_etichetta = cartella_etichette / (percorso_immagine.stem + ".txt")
        for riga in percorso_etichetta.read_text().splitlines():
            if riga.strip():
                righe.append(riga)
        degradata = copia_come_telecamera(percorso_immagine, righe, generatore)
        if degradata is None:
            continue
        nome = percorso_immagine.stem + "-telecamera"
        cv2.imwrite(str(cartella_immagini / (nome + ".jpg")), degradata, [cv2.IMWRITE_JPEG_QUALITY, 85])
        (cartella_etichette / (nome + ".txt")).write_text("\n".join(righe) + "\n")
        fatte += 1
    conteggio["train copie-telecamera"] = fatte


inizio_preparazione = time.perf_counter()
conteggio = {}
for radice in radici_dataset():
    prefisso = radice.name.replace("_", "-")
    massimo = 0
    if "pills-detection-dataset" in radice.name:
        massimo = MASSIMO_PILLOLE_VICINE
    importa_yolo(radice, prefisso + "-yolo", classe_farmaci, False, conteggio, massimo_immagini=massimo)
    importa_voc(radice, prefisso + "-voc", conteggio)
aggiungi_copie_degradate(conteggio)
print("esempi per divisione e dataset:", conteggio, flush=True)
print(f"preparazione: {time.perf_counter() - inizio_preparazione:.0f} s", flush=True)
percorso_yaml = scrivi_yaml(CLASSI)
# vista dall'alto: qualsiasi rotazione e capovolgimento; scale ampio per avere oggetti piccoli come da lontano
addestra_n_e_s(percorso_yaml, "", "farmaci", 6.0, ["degrees=180", "flipud=0.5", "scale=0.9", "perspective=0.0003"])
riassumi(percorso_yaml, "farmaci", CLASSI, False)
