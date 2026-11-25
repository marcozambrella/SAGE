"""Etichette delle cadute per la valutazione del sistema di casa (valuta_cadute_casa.py), CPU, pochi minuti.

La valutazione importa il codice di casa e gira sul PC; le etichette però sono nei dataset originali su Kaggle
(CAUCAFall 8,3 GB, Le2i, GMDCSA): questo kernel le legge come cadute_stgcn e scrive solo un json piccolo.
Funzioni copiate da cadute_stgcn.py senza cambiarle (stesse etichette e stesse divisioni dell'allenamento).
Uscita: etichette_cadute.json, per ogni video (id come in cadute_stgcn: "<dataset>/<percorso del video>"):
dataset, divisione, fps, numero_frame, eventi (inizio e fine in secondi di ogni tratto caduta + a terra) e tratti
(primo fotogramma, fotogramma dopo l'ultimo, classe 1 caduta o 2 a terra).
"""
import csv
import json
import math
import os
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

INGRESSO = Path("/kaggle/input")
USCITA = Path("/kaggle/working")
SECONDI_CADUTA = 1.5


# ===== copiato da cadute_stgcn.py =====
def radici_dataset() -> list:
    """Le cartelle dei dataset allegati: /kaggle/input/<nome> o /kaggle/input/datasets/<utente>/<nome>."""
    radici = []
    for cartella in sorted(INGRESSO.iterdir()):
        if cartella.name == "datasets":
            for utente in sorted(cartella.iterdir()):
                for dataset in sorted(utente.iterdir()):
                    radici.append(dataset)
        elif cartella.is_dir():
            radici.append(cartella)
    return radici



def cartelle_scheletri() -> dict:
    """Modello di posa → cartella scheletri/<modello>/ negli ingressi. Se lo stesso modello compare in due ingressi
    si tiene il primo: gli stessi video non devono contare due volte."""
    trovate = {}
    for cartella, sottocartelle, _ in os.walk(INGRESSO, followlinks=True):
        percorso = Path(cartella)
        if percorso.name == "scheletri":
            for modello in sorted(sottocartelle):
                if modello not in trovate:
                    trovate[modello] = percorso / modello
            sottocartelle.clear()
    return trovate


def dividi_caduta(cade: np.ndarray, fps: float) -> np.ndarray:
    """Fotogrammi "fall" (caduta + a terra) → i primi SECONDI_CADUTA secondi di ogni tratto caduta (1), il resto
    a_terra (2), gli altri normale (0)."""
    etichette = np.zeros(len(cade), dtype=np.int64)
    primi = int(round(SECONDI_CADUTA * fps))
    posizione = 0
    while posizione < len(cade):
        if not cade[posizione]:
            posizione += 1
            continue
        fine = posizione
        while fine < len(cade) and cade[fine]:
            fine += 1
        etichette[posizione:fine] = 2
        etichette[posizione:min(posizione + primi, fine)] = 1
        posizione = fine
    return etichette


def prima_parola_del_file(percorso: Path) -> str:
    with open(percorso) as file:
        testo = file.read().split()
    if testo:
        return testo[0]
    return ""


def etichette_caucafall(cartella_video: Path, numero_frame: int, fps: float) -> np.ndarray:
    """Un txt per fotogramma nella cartella del video (classes.txt dice: 0 nofall, 1 fall). Letti con più thread:
    su Kaggle aprire tanti file piccoli è lento (esplorazione del 24/11)."""
    file_txt = []
    for percorso in sorted(cartella_video.iterdir()):
        if percorso.suffix == ".txt" and percorso.name != "classes.txt":
            file_txt.append(percorso)
    with ThreadPoolExecutor(32) as esecutore:
        classi = list(esecutore.map(prima_parola_del_file, file_txt))
    cade = np.zeros(numero_frame, dtype=bool)
    for indice in range(min(len(classi), numero_frame)):
        cade[indice] = classi[indice] == "1"
    return dividi_caduta(cade, fps)


def etichette_gmdcsa(percorso_csv: Path, nome_video: str, numero_frame: int, fps: float) -> np.ndarray:
    """Riga del video nel csv: gli intervalli "Falling (..)[a to b]" in secondi sono caduta + a terra."""
    cade = np.zeros(numero_frame, dtype=bool)
    for riga in percorso_csv.read_text(errors="replace").splitlines():
        if not riga.startswith(nome_video):
            continue
        for inizio, fine in re.findall(r"Falling[^\[]*\[\s*([\d.]+)\s*to\s*([\d.]+)\s*\]", riga):
            primo = int(float(inizio) * fps)
            ultimo = int(math.ceil(float(fine) * fps))
            cade[primo:min(ultimo + 1, numero_frame)] = True
    return dividi_caduta(cade, fps)


def etichette_le2i(percorso_txt: Path, numero_frame: int) -> np.ndarray:
    """Prime due righe: fotogramma di inizio e di fine della caduta (da 1; 0 e 0 = nessuna caduta). Dopo la fine
    la persona resta a terra fino alla fine del video. I video senza caduta possono non avere le due righe e
    cominciare subito con i box ("1,1,249,152,318,240")."""
    righe = percorso_txt.read_text().split()
    etichette = np.zeros(numero_frame, dtype=np.int64)
    if len(righe) < 2 or "," in righe[0] or "," in righe[1]:
        return etichette
    inizio = int(righe[0])
    fine = int(righe[1])
    if inizio > 0 and fine >= inizio:
        etichette[inizio - 1:min(fine, numero_frame)] = 1
        etichette[min(fine, numero_frame):] = 2
    return etichette


def etichette_urfall(tabella: dict, sequenza: str, numero_frame: int) -> np.ndarray:
    """csv ufficiali: -1 non a terra, 0 sta cadendo, 1 a terra. Nelle attività normali ("adl") anche sdraiarsi
    sul letto è 1: lì è tutto normale."""
    etichette = np.zeros(numero_frame, dtype=np.int64)
    if sequenza.startswith("adl"):
        return etichette
    for fotogramma, valore in tabella.get(sequenza, []):
        if 0 < fotogramma <= numero_frame:
            if valore == 0:
                etichette[fotogramma - 1] = 1
            elif valore == 1:
                etichette[fotogramma - 1] = 2
    return etichette


def leggi_tabella_urfall() -> dict:
    tabella = {}
    for radice in radici_dataset():
        for percorso in sorted(radice.rglob("urfall-cam0-*.csv")):
            with open(percorso) as file:
                for riga in csv.reader(file):
                    if len(riga) < 3:
                        continue
                    if riga[0] not in tabella:
                        tabella[riga[0]] = []
                    tabella[riga[0]].append((int(riga[1]), int(riga[2])))
    return tabella


def divisione(dataset: str, relativo: str) -> str:
    if dataset == "caucafall":
        soggetto = int(re.search(r"Subject\.(\d+)", relativo).group(1))
        if soggetto in [8, 10]:
            return "test"
        if soggetto == 9:
            return "val"
        return "train"
    if dataset == "gmdcsa24":
        soggetto = int(re.search(r"Subject (\d+)", relativo).group(1))
        if soggetto == 4:
            return "test"
        if soggetto == 3:
            return "val"
        return "train"
    if dataset == "le2i":
        scena = relativo.split("/")[0]
        if scena == "Home_02":
            return "test"
        if scena == "Coffee_room_02":
            return "val"
        return "train"
    numero = int(re.search(r"-(\d+)-", relativo).group(1))
    if relativo.split("/")[-1].startswith("fall"):
        if numero >= 25:
            return "test"
        if numero >= 21:
            return "val"
        return "train"
    if numero >= 35:
        return "test"
    if numero >= 30:
        return "val"
    return "train"


def trova_radice(nome: str):
    for radice in radici_dataset():
        if radice.name == nome:
            return radice
    return None


# =====


def tratti_delle_etichette(etichette: np.ndarray) -> list:
    """[primo, dopo l'ultimo, classe] per ogni tratto di fotogrammi con la stessa classe diversa da 0."""
    tratti = []
    posizione = 0
    while posizione < len(etichette):
        classe = int(etichette[posizione])
        if classe == 0:
            posizione += 1
            continue
        fine = posizione
        while fine < len(etichette) and etichette[fine] == classe:
            fine += 1
        tratti.append([posizione, fine, classe])
        posizione = fine
    return tratti


# come prepara_video di cadute_stgcn, senza caricare gli scheletri: servono solo numero_frame e fps
radice_cauca = trova_radice("caucafall")
radice_gmdcsa = trova_radice("gmdcsa")
radice_le2i = trova_radice("falldataset-imvia")
tabella_urfall = leggi_tabella_urfall()
cartelle = cartelle_scheletri()
cartella_scheletri = cartelle["yolo26n-pose"]
risultato = {}
for percorso in sorted(cartella_scheletri.rglob("*.npz")):
    relativo_npz = percorso.relative_to(cartella_scheletri)
    dataset = relativo_npz.parts[0]
    relativo = str(Path(*relativo_npz.parts[1:]))[:-len(".npz")]
    dati = np.load(percorso)
    numero_frame = int(dati["numero_frame"])
    fps = float(dati["fps"])
    etichette = None
    if dataset == "caucafall" and radice_cauca is not None:
        etichette = etichette_caucafall((radice_cauca / relativo).parent, numero_frame, fps)
    elif dataset == "gmdcsa24" and radice_gmdcsa is not None:
        percorso_video = Path(relativo)
        percorso_csv = radice_gmdcsa / percorso_video.parent.parent / (percorso_video.parent.name + ".csv")
        if percorso_csv.exists():
            etichette = etichette_gmdcsa(percorso_csv, percorso_video.name, numero_frame, fps)
    elif dataset == "le2i" and radice_le2i is not None:
        for nome_cartella in ["/Annotation_files/", "/Annotations_files/"]:
            percorso_txt = radice_le2i / relativo.replace("/Videos/", nome_cartella)
            percorso_txt = percorso_txt.with_suffix(".txt")
            if percorso_txt.exists():
                etichette = etichette_le2i(percorso_txt, numero_frame)
    elif dataset == "urfall" and tabella_urfall:
        sequenza = "-".join(relativo.split("/")[-1].split("-")[:2])
        etichette = etichette_urfall(tabella_urfall, sequenza, numero_frame)
    if etichette is None:
        continue
    eventi = []
    posizione = 0
    while posizione < numero_frame:
        if etichette[posizione] == 0:
            posizione += 1
            continue
        fine = posizione
        while fine < numero_frame and etichette[fine] != 0:
            fine += 1
        eventi.append([posizione / fps, fine / fps])
        posizione = fine
    risultato[dataset + "/" + relativo] = {"dataset": dataset, "divisione": divisione(dataset, relativo), "fps": fps,
                                           "numero_frame": numero_frame, "eventi": eventi,
                                           "tratti": tratti_delle_etichette(etichette)}
(USCITA / "etichette_cadute.json").write_text(json.dumps(risultato, indent=1))
conteggi = {}
for identificativo in risultato:
    chiave = risultato[identificativo]["dataset"] + " " + risultato[identificativo]["divisione"]
    if chiave not in conteggi:
        conteggi[chiave] = 0
    conteggi[chiave] += 1
print(json.dumps(conteggi, indent=1, sort_keys=True), flush=True)
