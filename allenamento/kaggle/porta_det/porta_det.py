"""Porta (uscita di casa), GPU: rilevatore YOLO26 n e s di porta aperta e porta chiusa.

L'uscita si capisce quando si vede la persona aprire il portone di casa (Marco, 24/11): il rilevatore dice se la
porta è aperta o chiusa, il programma di casa guarda quando passa da chiusa ad aperta con la persona vicino.
Dati: i dataset Roboflow scaricati dal coordinatore e caricati come dataset privato `sage-roboflow-porta` (una
sottocartella con il suo data.yaml per dataset, formato YOLO); le classi si riconoscono dal nome (vedi classe_porta).
Esclusi (DATASET_ESCLUSI, guardati il 24/11): `shao-ex3mj` ha ante di armadi e quadri elettrici, `vikashs-workspace`
portelloni di camion; insegnerebbero che un armadio aperto è una porta aperta. Nessuno è ripreso dall'alto né in
infrarosso, quindi per una parte delle immagini di allenamento si aggiunge una copia "come la nostra telecamera":
grigio (infrarosso), bassa risoluzione, rumore e a volte una prospettiva dall'alto (vedi copia_come_telecamera).
Non allegati: `thepbordin/indoor-object-detection` segna come "door" l'anta sia chiusa sia aperta e come
"openedDoor" il vano della porta aperta (controllato su 4 immagini il 24/11), quindi non dice se una porta è chiusa;
`mariamelghandoor/openclosedooryolo11` ha la sola classe "door".
Uscita: pesi, metriche, tempi e ONNX in /kaggle/working/porta/ (vedi il blocco comune).
"""
import csv
import json
import os
import random
import subprocess
import sys
import time
from pathlib import Path

import cv2
import numpy as np

subprocess.run([sys.executable, "-m", "pip", "install", "-q", "ultralytics>=8.4", "onnx", "onnxslim"], check=True)

INGRESSO = Path("/kaggle/input")
USCITA = Path("/kaggle/working")
# i dati preparati stanno fuori da /kaggle/working: tutto quello che c'è là diventa uscita del kernel (max 20 GB)
DATI = Path("/tmp/dati")


# ===== blocco comune YOLO: uguale in liquido_seg, cibo_seg, farmaci_det e porta_det =====
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


CLASSI = ["porta_aperta", "porta_chiusa"]
DATASET_ESCLUSI = ["shao-ex3mj", "vikashs-workspace"]
QUOTA_COPIE_DEGRADATE = 0.3
# 5 h di allenamento: con preparazione e riassunto la sessione resta sotto le 6 h (limite Kaggle 12 h)
ORE_ALLENAMENTO = 5.0


def classe_porta(nome: str):
    """Nome della classe di un dataset → indice in CLASSI, None se non dice se la porta è aperta o chiusa
    (es. "door", "slide-door", maniglie, scale)."""
    minuscolo = nome.lower()
    # socchiusa ("semi_door") conta come aperta: il portone che si apre passa da lì (coordinatore, 24/11)
    if "semi" in minuscolo or "open" in minuscolo:
        return 0
    # "clos" prende close, closed, closedoor, door-closed
    if "clos" in minuscolo:
        return 1
    return None


def prospettiva_dall_alto(immagine: np.ndarray, righe: list, generatore: random.Random) -> tuple:
    """Telecamera alta che guarda in giù: le verticali convergono verso il basso. Il lato basso dell'immagine si
    stringe del 10-25% per parte; ogni box diventa il rettangolo che contiene i suoi quattro angoli spostati."""
    altezza, larghezza = immagine.shape[:2]
    rientro = generatore.uniform(0.10, 0.25) * larghezza
    angoli_prima = np.float32([[0, 0], [larghezza, 0], [larghezza, altezza], [0, altezza]])
    angoli_dopo = np.float32([[0, 0], [larghezza, 0], [larghezza - rientro, altezza], [rientro, altezza]])
    matrice = cv2.getPerspectiveTransform(angoli_prima, angoli_dopo)
    girata = cv2.warpPerspective(immagine, matrice, (larghezza, altezza))
    nuove_righe = []
    for riga in righe:
        valori = riga.split()
        centro_x = float(valori[1]) * larghezza
        centro_y = float(valori[2]) * altezza
        mezza_larghezza = float(valori[3]) * larghezza / 2
        mezza_altezza = float(valori[4]) * altezza / 2
        angoli = np.float32([[[centro_x - mezza_larghezza, centro_y - mezza_altezza],
                              [centro_x + mezza_larghezza, centro_y - mezza_altezza],
                              [centro_x + mezza_larghezza, centro_y + mezza_altezza],
                              [centro_x - mezza_larghezza, centro_y + mezza_altezza]]])
        spostati = cv2.perspectiveTransform(angoli, matrice)[0]
        x1 = max(0.0, float(spostati[:, 0].min()))
        x2 = min(float(larghezza), float(spostati[:, 0].max()))
        y1 = max(0.0, float(spostati[:, 1].min()))
        y2 = min(float(altezza), float(spostati[:, 1].max()))
        box = [(x1 + x2) / 2 / larghezza, (y1 + y2) / 2 / altezza, (x2 - x1) / larghezza, (y2 - y1) / altezza]
        nuove_righe.append(riga_da_box(int(valori[0]), box, False))
    return girata, nuove_righe


def copia_come_telecamera(percorso_immagine: Path, righe: list, generatore: random.Random) -> tuple:
    """Immagine come la telecamera di casa di notte: grigio, bassa risoluzione, rumore e, una volta su due, la
    prospettiva dall'alto. Ritorna (immagine, righe delle etichette), (None, None) se l'immagine non si legge."""
    immagine = cv2.imread(str(percorso_immagine))
    if immagine is None:
        return None, None
    if generatore.random() < 0.5:
        immagine, righe = prospettiva_dall_alto(immagine, righe, generatore)
    altezza, larghezza = immagine.shape[:2]
    grigia = cv2.cvtColor(immagine, cv2.COLOR_BGR2GRAY)
    fattore = generatore.uniform(0.25, 0.5)
    piccola = cv2.resize(grigia, (max(8, int(larghezza * fattore)), max(8, int(altezza * fattore))),
                         interpolation=cv2.INTER_AREA)
    grigia = cv2.resize(piccola, (larghezza, altezza), interpolation=cv2.INTER_LINEAR)
    rumore = np.random.default_rng(generatore.randint(0, 10 ** 6)).normal(0, generatore.uniform(3, 10), grigia.shape)
    grigia = np.clip(grigia.astype(np.float32) + rumore, 0, 255).astype(np.uint8)
    return cv2.cvtColor(grigia, cv2.COLOR_GRAY2BGR), righe


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
        degradata, righe_degradata = copia_come_telecamera(percorso_immagine, righe, generatore)
        if degradata is None:
            continue
        nome = percorso_immagine.stem + "-telecamera"
        cv2.imwrite(str(cartella_immagini / (nome + ".jpg")), degradata, [cv2.IMWRITE_JPEG_QUALITY, 85])
        (cartella_etichette / (nome + ".txt")).write_text("\n".join(righe_degradata) + "\n")
        fatte += 1
    conteggio["train copie-telecamera"] = fatte


inizio_preparazione = time.perf_counter()
conteggio = {}
for radice in radici_dataset():
    for cartella in sorted(radice.iterdir()):
        escluso = False
        for nome in DATASET_ESCLUSI:
            if cartella.name.startswith(nome):
                escluso = True
        if cartella.is_dir() and not escluso:
            importa_yolo(cartella, cartella.name.replace("_", "-"), classe_porta, False, conteggio)
aggiungi_copie_degradate(conteggio)
print("esempi per divisione e dataset:", conteggio, flush=True)
print(f"preparazione: {time.perf_counter() - inizio_preparazione:.0f} s", flush=True)
percorso_yaml = scrivi_yaml(CLASSI)
# le porte stanno dritte: niente capovolgimento in verticale, poca rotazione; scale per le porte lontane
addestra_n_e_s(percorso_yaml, "", "porta", ORE_ALLENAMENTO, ["degrees=5", "scale=0.6", "perspective=0.0005"])
riassumi(percorso_yaml, "porta", CLASSI, False)
