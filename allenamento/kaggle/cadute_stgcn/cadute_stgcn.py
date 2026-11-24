"""Cadute, passo 2: classificatore ST-GCN (come ARGO) su finestre di scheletri, in più varianti.

Ingresso:
- scheletri di `cadute_scheletri` (un npz per video) in un dataset privato: questo kernel allega
  `sage-cadute-scheletri-n` (posa n, estratta su CPU), `cadute_stgcn_s` (stesso codice) `sage-cadute-scheletri-s`
  (posa s, kernel GPU): due sessioni CPU in parallelo. Si usa ogni cartella scheletri/<modello posa>/ trovata.
- etichette dai dataset originali allegati: CAUCAFall (un txt YOLO per fotogramma, classe 1 = fall), GMDCSA-24
  v2.1 (csv con "Falling (SW)[3.4 to 6]"), Le2i (txt con fotogramma di inizio e fine caduta), UR Fall (csv
  ufficiali per fotogramma: -1 non a terra, 0 cade, 1 a terra, copiati nel dataset degli scheletri).
Classi: normale (0), caduta (1), a_terra (2). CAUCAFall e GMDCSA chiamano "fall" sia la caduta sia lo stare a terra
dopo: i primi SECONDI_CADUTA secondi diventano caduta, il resto a_terra (scelta mia, scritta in PIANO.md).
Divisione per soggetto e scena (lezione di ARGO), mai per finestra:
- CAUCAFall: test soggetti 8 (infrarosso) e 10, validazione 9, il resto allenamento (anche il 6 in infrarosso);
- GMDCSA: test soggetto 4, validazione 3; Le2i: test Home_02, validazione Coffee_room_02 (Office e Lecture_room non
  hanno etichette); UR Fall: i soggetti non sono scritti, quindi per numero di sequenza.
Varianti (Marco, 24/11: "fai diverse prove"): fotogrammi al secondo 5, 10 e 25 (quasi la frequenza piena dei video)
× finestre di 2 e 3 secondi, una finestra ogni 0,5 s, per ogni grandezza di posa trovata. Prima le varianti più
leggere: se il tempo finisce (ORE_MASSIME, la sessione Kaggle chiude a 12 h) mancano solo le ultime.
Metriche sul test (come PIANO.md, sez. 1): classi per finestra; allarme = p(caduta) + p(a_terra) ≥ soglia scelta
sulla validazione; F1 su pezzi di 5 secondi, cadute prese (allarme entro 3 s dalla fine) e falsi allarmi all'ora.
Uscita in /kaggle/working: un .pt e un .onnx per variante, risultati.json, confronto.md.
"""
import csv
import json
import math
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

subprocess.run([sys.executable, "-m", "pip", "install", "-q", "onnx"], check=True)
import torch  # noqa: E402
from torch import nn  # noqa: E402

INGRESSO = Path("/kaggle/input")
USCITA = Path("/kaggle/working")
INIZIO_KERNEL = time.time()
# la sessione Kaggle chiude a 12 h: oltre questo tempo si salva quello che c'è e si chiude
ORE_MASSIME = 10.5


# ===== blocco comune finestre: uguale in cadute_stgcn e gesti_stgcn =====
# Kaggle carica un solo file per kernel, quindi questo blocco è copiato in ognuno (come l'avvio comune di ARGO).
NUMERO_PUNTI = 17
# ossa dello scheletro COCO (0 naso, 5-6 spalle, 7-8 gomiti, 9-10 polsi, 11-12 anche, 13-14 ginocchia, 15-16 caviglie)
OSSA = [(0, 1), (0, 2), (1, 3), (2, 4), (0, 5), (0, 6), (5, 6), (5, 7), (7, 9), (6, 8), (8, 10), (5, 11), (6, 12),
        (11, 12), (11, 13), (13, 15), (12, 14), (14, 16)]
CENTRO_SCHELETRO = 0
# sinistra ↔ destra, per l'aumentazione a specchio
COPPIE_SPECCHIO = [(1, 2), (3, 4), (5, 6), (7, 8), (9, 10), (11, 12), (13, 14), (15, 16)]
CONFIDENZA_MINIMA_PUNTO = 0.1
PASSO_SECONDI = 0.5


def tempo_scaduto() -> bool:
    return time.time() - INIZIO_KERNEL > ORE_MASSIME * 3600


def carica_scheletro(percorso: Path) -> dict:
    """Per ogni fotogramma la persona più sicura (i dataset hanno una persona sola): punti (N, 17, 3), altezza del
    box (N,), presente (N,), fps."""
    dati = np.load(percorso)
    numero_frame = int(dati["numero_frame"])
    punti = np.zeros((numero_frame, NUMERO_PUNTI, 3), dtype=np.float32)
    altezze = np.zeros(numero_frame, dtype=np.float32)
    migliore = np.full(numero_frame, -1.0, dtype=np.float32)
    for riga in range(len(dati["frame"])):
        fotogramma = int(dati["frame"][riga])
        if fotogramma >= numero_frame or dati["conf"][riga] <= migliore[fotogramma]:
            continue
        migliore[fotogramma] = dati["conf"][riga]
        punti[fotogramma] = dati["punti"][riga]
        altezze[fotogramma] = dati["box"][riga][3] - dati["box"][riga][1]
    return {"punti": punti, "altezze": altezze, "presente": migliore >= 0, "fps": float(dati["fps"]),
            "numero_frame": numero_frame}


def normalizza_finestra(punti: np.ndarray, altezze: np.ndarray, presente: np.ndarray) -> np.ndarray:
    """Punti (T, 17, 3) centrati sulla media dei punti visibili della finestra e divisi per l'altezza mediana del
    box: la finestra non dipende da dove sta la persona né da quanto è lontana. Punti invisibili = 0."""
    visibili = (punti[:, :, 2] > CONFIDENZA_MINIMA_PUNTO) & presente[:, None]
    uscita = np.zeros_like(punti)
    if not visibili.any():
        return uscita
    centro = punti[:, :, :2][visibili].mean(axis=0)
    scala = float(np.median(altezze[presente]))
    if scala <= 1:
        scala = 1.0
    uscita[:, :, :2] = (punti[:, :, :2] - centro) / scala
    uscita[:, :, 2] = punti[:, :, 2]
    uscita[~visibili] = 0
    return uscita


def finestre_di_un_video(scheletro: dict, etichette: np.ndarray, fps_finestra: float, secondi: float,
                         etichetta_finestra) -> tuple:
    """Finestre di `secondi` a `fps_finestra` (fotogramma più vicino del video), una ogni PASSO_SECONDI, dalla fine
    del primo secondo in poi (le prime possono cominciare prima del video: quei fotogrammi sono vuoti).
    etichetta_finestra(etichette dei fotogrammi della finestra) → classe. Ritorna (finestre, classi, secondi di fine)."""
    fps_video = scheletro["fps"]
    numero_frame = scheletro["numero_frame"]
    durata = numero_frame / fps_video
    lunghezza = int(round(secondi * fps_finestra))
    finestre = []
    classi = []
    fini = []
    fine = 1.0
    while fine <= durata + 1e-6:
        indici = []
        for posizione in range(lunghezza):
            tempo = fine - (lunghezza - 1 - posizione) / fps_finestra
            indici.append(int(round(tempo * fps_video)) - 1)
        indici = np.array(indici)
        dentro = (indici >= 0) & (indici < numero_frame)
        indici_validi = np.clip(indici, 0, numero_frame - 1)
        punti = scheletro["punti"][indici_validi].copy()
        presente = scheletro["presente"][indici_validi] & dentro
        punti[~presente] = 0
        finestre.append(normalizza_finestra(punti, scheletro["altezze"][indici_validi], presente))
        classi.append(etichetta_finestra(etichette[indici_validi[dentro]]))
        fini.append(fine)
        fine += PASSO_SECONDI
    return finestre, classi, fini


def adiacenza_partizioni() -> np.ndarray:
    """(3, 17, 17): il nodo stesso, i vicini più vicini al centro e quelli più lontani, normalizzati per grado
    (partizione spaziale di ST-GCN, come in ARGO)."""
    vicini = np.eye(NUMERO_PUNTI, dtype=bool)
    for primo, secondo in OSSA:
        vicini[primo, secondo] = True
        vicini[secondo, primo] = True
    # distanza in salti dal centro dello scheletro
    distanza = np.full(NUMERO_PUNTI, -1)
    distanza[CENTRO_SCHELETRO] = 0
    for salto in range(1, NUMERO_PUNTI):
        for nodo in range(NUMERO_PUNTI):
            if distanza[nodo] == salto - 1:
                for altro in range(NUMERO_PUNTI):
                    if vicini[nodo, altro] and distanza[altro] < 0:
                        distanza[altro] = salto
    grado = vicini.sum(axis=0)
    partizioni = np.zeros((3, NUMERO_PUNTI, NUMERO_PUNTI), dtype=np.float32)
    for nodo in range(NUMERO_PUNTI):
        for vicino in range(NUMERO_PUNTI):
            if not vicini[nodo, vicino]:
                continue
            peso = 1.0 / grado[vicino]
            if distanza[vicino] == distanza[nodo]:
                partizioni[0, vicino, nodo] = peso
            elif distanza[vicino] > distanza[nodo]:
                partizioni[1, vicino, nodo] = peso
            else:
                partizioni[2, vicino, nodo] = peso
    return partizioni


class BloccoStGcn(nn.Module):
    """Convoluzione sul grafo (una per partizione) + convoluzione nel tempo, con residuo (come ARGO)."""

    def __init__(self, canali_ingresso: int, canali_uscita: int, passo: int, dropout: float, residuo: bool):
        super().__init__()
        self.convoluzione_grafo = nn.Conv2d(canali_ingresso, canali_uscita * 3, kernel_size=1)
        self.convoluzione_tempo = nn.Sequential(
            nn.BatchNorm2d(canali_uscita), nn.ReLU(inplace=True),
            nn.Conv2d(canali_uscita, canali_uscita, (9, 1), (passo, 1), (4, 0)),
            nn.BatchNorm2d(canali_uscita), nn.Dropout(dropout))
        self.tipo_residuo = "nessuno"
        if residuo and canali_ingresso == canali_uscita and passo == 1:
            self.tipo_residuo = "identita"
        elif residuo:
            self.tipo_residuo = "convoluzione"
            self.residuo = nn.Sequential(nn.Conv2d(canali_ingresso, canali_uscita, 1, (passo, 1)),
                                         nn.BatchNorm2d(canali_uscita))
        self.attivazione = nn.ReLU(inplace=True)

    def forward(self, x: torch.Tensor, adiacenza: torch.Tensor) -> torch.Tensor:
        """x (N, C, T, V), adiacenza (3, V, V)."""
        residuo = 0
        if self.tipo_residuo == "identita":
            residuo = x
        elif self.tipo_residuo == "convoluzione":
            residuo = self.residuo(x)
        y = self.convoluzione_grafo(x)
        lotto, _, frame, nodi = y.shape
        y = y.view(lotto, 3, -1, frame, nodi)
        y = torch.einsum("nkctv,kvw->nctw", y, adiacenza)
        return self.attivazione(self.convoluzione_tempo(y) + residuo)


class StGcn(nn.Module):
    """ST-GCN più piccolo di quello di ARGO (6 blocchi, 32-128 canali): deve girare su CPU a casa e allenarsi su
    CPU Kaggle (sul PC di Marco, 4 thread: 0,5 ms per fotogramma di finestra contro 1,5 ms con 64-256 canali)."""

    def __init__(self, numero_classi: int, dropout: float = 0.3):
        super().__init__()
        self.register_buffer("adiacenza", torch.from_numpy(adiacenza_partizioni()))
        self.normalizzazione_dati = nn.BatchNorm1d(3 * NUMERO_PUNTI)
        configurazione = [(3, 32, 1, False), (32, 32, 1, True), (32, 64, 2, True), (64, 64, 1, True),
                          (64, 128, 2, True), (128, 128, 1, True)]
        blocchi = []
        importanze = []
        for numero in range(len(configurazione)):
            ingresso, uscita, passo, residuo = configurazione[numero]
            dropout_blocco = dropout
            if numero == 0:
                dropout_blocco = 0.0
            blocchi.append(BloccoStGcn(ingresso, uscita, passo, dropout_blocco, residuo))
            importanze.append(nn.Parameter(torch.ones_like(self.adiacenza)))
        self.blocchi = nn.ModuleList(blocchi)
        self.importanza_archi = nn.ParameterList(importanze)
        self.classificatore = nn.Linear(128, numero_classi)

    def forward(self, finestre: torch.Tensor) -> torch.Tensor:
        """finestre (B, T, 17, 3) → logit (B, classi)."""
        lotto, frame, nodi, canali = finestre.shape
        x = finestre.permute(0, 2, 3, 1).reshape(lotto, nodi * canali, frame)
        x = self.normalizzazione_dati(x)
        x = x.view(lotto, nodi, canali, frame).permute(0, 2, 3, 1)   # (B, C, T, V)
        for numero in range(len(self.blocchi)):
            x = self.blocchi[numero](x, self.adiacenza * self.importanza_archi[numero])
        return self.classificatore(x.mean(dim=(2, 3)))


def aumenta(finestre: torch.Tensor) -> torch.Tensor:
    """A specchio (sinistra ↔ destra) metà delle finestre, scala ±10% e un po' di rumore sui punti visibili."""
    finestre = finestre.clone()
    specchio = torch.rand(finestre.shape[0]) < 0.5
    if specchio.any():
        girate = finestre[specchio]
        girate[:, :, :, 0] = -girate[:, :, :, 0]
        for sinistro, destro in COPPIE_SPECCHIO:
            copia = girate[:, :, sinistro].clone()
            girate[:, :, sinistro] = girate[:, :, destro]
            girate[:, :, destro] = copia
        finestre[specchio] = girate
    visibili = (finestre[:, :, :, 2] > 0).float()
    scala = 0.9 + 0.2 * torch.rand(finestre.shape[0], 1, 1, 1)
    rumore = 0.01 * torch.randn_like(finestre[:, :, :, :2])
    finestre[:, :, :, :2] = (finestre[:, :, :, :2] * scala + rumore) * visibili[:, :, :, None]
    return finestre


def matrice_confusione(vere: np.ndarray, predette: np.ndarray, numero_classi: int) -> np.ndarray:
    matrice = np.zeros((numero_classi, numero_classi), dtype=np.int64)
    np.add.at(matrice, (vere, predette), 1)
    return matrice   # righe = classe vera, colonne = predetta


def metriche_classi(vere: np.ndarray, predette: np.ndarray, classi: list) -> dict:
    matrice = matrice_confusione(vere, predette, len(classi))
    veri_positivi = np.diag(matrice).astype(float)
    richiamo = veri_positivi / np.maximum(matrice.sum(axis=1), 1)
    precisione = veri_positivi / np.maximum(matrice.sum(axis=0), 1)
    f1 = 2 * precisione * richiamo / np.maximum(precisione + richiamo, 1e-12)
    presenti = matrice.sum(axis=1) > 0
    macro_f1 = 0.0
    if presenti.any():
        macro_f1 = float(f1[presenti].mean())
    risultato = {"macro_f1": round(macro_f1, 4), "accuratezza": round(float(veri_positivi.sum() / max(matrice.sum(), 1)), 4),
                 "matrice_confusione": matrice.tolist()}
    for indice in range(len(classi)):
        risultato[classi[indice]] = {"richiamo": round(float(richiamo[indice]), 4),
                                     "precisione": round(float(precisione[indice]), 4)}
    return risultato


def probabilita(modello: nn.Module, finestre: np.ndarray) -> np.ndarray:
    modello.eval()
    uscite = []
    with torch.no_grad():
        for inizio in range(0, len(finestre), 256):
            lotto = torch.from_numpy(finestre[inizio:inizio + 256])
            uscite.append(torch.softmax(modello(lotto), dim=1).numpy())
    if not uscite:
        return np.zeros((0, 1), dtype=np.float32)
    return np.concatenate(uscite)


def addestra(dati: dict, classi: list, epoche: int = 20, pazienza: int = 5, seme: int = 0) -> tuple:
    """dati["train"/"val"] = (finestre, classi). Perdita pesata per classe (le cadute sono poche), AdamW con
    riscaldamento e coseno; si tiene l'epoca con la macro-F1 di validazione migliore (come ARGO). Si ferma
    anche quando il tempo del kernel è scaduto."""
    torch.manual_seed(seme)
    generatore = np.random.default_rng(seme)
    finestre_train, classi_train = dati["train"]
    conteggio = np.bincount(classi_train, minlength=len(classi))
    pesi = conteggio.sum() / np.maximum(conteggio, 1) / len(classi)
    pesi = np.where(conteggio > 0, pesi, 0.0)
    perdita = nn.CrossEntropyLoss(weight=torch.tensor(pesi, dtype=torch.float32))
    modello = StGcn(len(classi))
    ottimizzatore = torch.optim.AdamW(modello.parameters(), lr=1e-3, weight_decay=0.01)
    dimensione_lotto = 64
    passi_totali = epoche * math.ceil(len(classi_train) / dimensione_lotto)
    passi_riscaldamento = max(1, passi_totali // 20)
    passo = 0
    migliore_f1 = -1.0
    migliore_stato = None
    migliore_epoca = 0
    senza_miglioramento = 0
    storia = []
    for epoca in range(1, epoche + 1):
        modello.train()
        inizio = time.perf_counter()
        ordine = generatore.permutation(len(classi_train))
        perdita_totale = 0.0
        for partenza in range(0, len(ordine), dimensione_lotto):
            indici = ordine[partenza:partenza + dimensione_lotto]
            if len(indici) < 2:
                continue   # BatchNorm vuole almeno 2 esempi
            # tasso: sale nel primo 5% dei passi, poi scende a coseno
            fattore = min((passo + 1) / passi_riscaldamento, 0.5 * (1 + math.cos(math.pi * min(passo / passi_totali, 1.0))))
            for gruppo in ottimizzatore.param_groups:
                gruppo["lr"] = 1e-3 * fattore
            lotto = aumenta(torch.from_numpy(finestre_train[indici]))
            valore = perdita(modello(lotto), torch.from_numpy(classi_train[indici]))
            ottimizzatore.zero_grad()
            valore.backward()
            nn.utils.clip_grad_norm_(modello.parameters(), 1.0)
            ottimizzatore.step()
            passo += 1
            perdita_totale += float(valore) * len(indici)
        finestre_val, classi_val = dati["val"]
        predette = probabilita(modello, finestre_val).argmax(axis=1)
        f1_val = metriche_classi(classi_val, predette, classi)["macro_f1"]
        storia.append({"epoca": epoca, "perdita": round(perdita_totale / len(ordine), 4), "macro_f1_val": f1_val,
                       "secondi": round(time.perf_counter() - inizio, 1)})
        print(f"  epoca {epoca}: {storia[-1]}", flush=True)
        if f1_val > migliore_f1:
            migliore_f1 = f1_val
            migliore_epoca = epoca
            migliore_stato = {}
            stato = modello.state_dict()
            for chiave in stato:
                migliore_stato[chiave] = stato[chiave].clone()
            senza_miglioramento = 0
        else:
            senza_miglioramento += 1
            if senza_miglioramento >= pazienza:
                break
        if tempo_scaduto():
            print("  tempo scaduto: si tiene l'epoca migliore fin qui", flush=True)
            break
    modello.load_state_dict(migliore_stato)
    modello.eval()
    return modello, {"migliore_epoca": migliore_epoca, "storia": storia}


def millisecondi_cpu(modello: nn.Module, lunghezza: int) -> float:
    """Millisecondi per una finestra (lotto da 1) su CPU, come a casa."""
    finestra = torch.randn(1, lunghezza, NUMERO_PUNTI, 3)
    with torch.no_grad():
        for _ in range(3):
            modello(finestra)
        inizio = time.perf_counter()
        for _ in range(30):
            modello(finestra)
    return round((time.perf_counter() - inizio) / 30 * 1000, 2)


def esporta(modello: nn.Module, classi: list, lunghezza: int, nome: str, informazioni: dict) -> None:
    torch.save({"stato": modello.state_dict(), "classi": classi, "lunghezza": lunghezza, "informazioni": informazioni},
               USCITA / f"{nome}.pt")
    # dynamo=False: con l'esportatore nuovo (predefinito in torch 2.11, quello di Kaggle) il lotto restava fisso a 1
    # e i pesi in un file a parte (provato in locale il 24/11)
    torch.onnx.export(modello, torch.randn(1, lunghezza, NUMERO_PUNTI, 3), str(USCITA / f"{nome}.onnx"),
                      input_names=["finestre"], output_names=["logit"], dynamic_axes={"finestre": {0: "lotto"}},
                      opset_version=17, dynamo=False)


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
# =====


CLASSI = ["normale", "caduta", "a_terra"]
SECONDI_CADUTA = 1.5
FPS_VARIANTI = [5, 10, 25]
SECONDI_VARIANTI = [2, 3]
SECONDI_PEZZO = 5.0
SECONDI_TOLLERANZA = 3.0


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


def etichetta_finestra(etichette: np.ndarray) -> int:
    """Classe di una finestra dalla sua seconda metà (quello che succede adesso): caduta se almeno il 30% dei
    fotogrammi è caduta, altrimenti a_terra se lo è almeno il 30%, altrimenti normale."""
    if len(etichette) == 0:
        return 0
    meta = etichette[len(etichette) // 2:]
    if np.mean(meta == 1) >= 0.3:
        return 1
    if np.mean(meta == 2) >= 0.3:
        return 2
    return 0


def trova_radice(nome: str):
    for radice in radici_dataset():
        if radice.name == nome:
            return radice
    return None


def prepara_video(cartella_scheletri: Path) -> list:
    """Per ogni npz con etichette: scheletro, etichette per fotogramma, divisione, eventi di caduta in secondi."""
    radice_cauca = trova_radice("caucafall")
    radice_gmdcsa = trova_radice("gmdcsa")
    radice_le2i = trova_radice("falldataset-imvia")
    tabella_urfall = leggi_tabella_urfall()
    video = []
    for percorso in sorted(cartella_scheletri.rglob("*.npz")):
        relativo_npz = percorso.relative_to(cartella_scheletri)
        dataset = relativo_npz.parts[0]
        relativo = str(Path(*relativo_npz.parts[1:]))[:-len(".npz")]
        scheletro = carica_scheletro(percorso)
        numero_frame = scheletro["numero_frame"]
        etichette = None
        if dataset == "caucafall" and radice_cauca is not None:
            etichette = etichette_caucafall((radice_cauca / relativo).parent, numero_frame, scheletro["fps"])
        elif dataset == "gmdcsa24" and radice_gmdcsa is not None:
            percorso_video = Path(relativo)
            percorso_csv = radice_gmdcsa / percorso_video.parent.parent / (percorso_video.parent.name + ".csv")
            if percorso_csv.exists():
                etichette = etichette_gmdcsa(percorso_csv, percorso_video.name, numero_frame, scheletro["fps"])
        elif dataset == "le2i" and radice_le2i is not None:
            # Coffee_room_02 chiama la cartella "Annotations_files"; Office e Lecture_room non hanno etichette
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
            eventi.append((posizione / scheletro["fps"], fine / scheletro["fps"]))
            posizione = fine
        video.append({"id": dataset + "/" + relativo, "dataset": dataset, "divisione": divisione(dataset, relativo),
                      "scheletro": scheletro, "etichette": etichette, "eventi": eventi,
                      "durata": numero_frame / scheletro["fps"]})
    return video


def costruisci_finestre(video: list, fps_finestra: float, secondi: float) -> dict:
    dati = {}
    for nome in ["train", "val", "test"]:
        dati[nome] = {"finestre": [], "classi": [], "video": [], "fini": []}
    for voce in video:
        finestre, classi, fini = finestre_di_un_video(voce["scheletro"], voce["etichette"], fps_finestra, secondi,
                                                      etichetta_finestra)
        parte = dati[voce["divisione"]]
        parte["finestre"].extend(finestre)
        parte["classi"].extend(classi)
        parte["fini"].extend(fini)
        for _ in range(len(finestre)):
            parte["video"].append(voce["id"])
    for nome in dati:
        parte = dati[nome]
        lunghezza = int(round(secondi * fps_finestra))
        if parte["finestre"]:
            parte["finestre"] = np.stack(parte["finestre"]).astype(np.float32)
        else:
            parte["finestre"] = np.zeros((0, lunghezza, NUMERO_PUNTI, 3), dtype=np.float32)
        parte["classi"] = np.array(parte["classi"], dtype=np.int64)
        parte["fini"] = np.array(parte["fini"])
    return dati


def metriche_allarme(probabilita_caduta: np.ndarray, parte: dict, video_per_id: dict, soglia: float) -> dict:
    """Allarme = p(caduta) + p(a_terra) ≥ soglia. Pezzi di SECONDI_PEZZO secondi (positivo se c'è una caduta vera,
    predetto se un allarme finisce nel pezzo), cadute prese (un allarme entro SECONDI_TOLLERANZA dalla fine) e
    falsi allarmi (tratti di allarme lontani da ogni caduta vera) all'ora."""
    allarmi_per_video = {}
    for indice in range(len(parte["video"])):
        identificativo = parte["video"][indice]
        if identificativo not in allarmi_per_video:
            allarmi_per_video[identificativo] = []
        allarmi_per_video[identificativo].append((parte["fini"][indice], probabilita_caduta[indice] >= soglia))
    veri_positivi = 0
    falsi_positivi = 0
    falsi_negativi = 0
    cadute = 0
    prese = 0
    falsi_allarmi = 0
    ore = 0.0
    for identificativo in allarmi_per_video:
        voce = video_per_id[identificativo]
        finestre = sorted(allarmi_per_video[identificativo])
        ore += voce["durata"] / 3600
        numero_pezzi = int(math.ceil(voce["durata"] / SECONDI_PEZZO))
        for pezzo in range(numero_pezzi):
            inizio = pezzo * SECONDI_PEZZO
            fine = inizio + SECONDI_PEZZO
            vero = False
            for evento in voce["eventi"]:
                if evento[0] < fine and evento[1] > inizio:
                    vero = True
            predetto = False
            for tempo, allarme in finestre:
                if allarme and inizio <= tempo < fine:
                    predetto = True
            if vero and predetto:
                veri_positivi += 1
            elif predetto:
                falsi_positivi += 1
            elif vero:
                falsi_negativi += 1
        for evento in voce["eventi"]:
            cadute += 1
            for tempo, allarme in finestre:
                if allarme and evento[0] <= tempo <= evento[1] + SECONDI_TOLLERANZA:
                    prese += 1
                    break
        # tratti consecutivi di allarme
        tratti = []
        for tempo, allarme in finestre:
            if not allarme:
                continue
            if tratti and tempo - tratti[-1][1] <= PASSO_SECONDI + 1e-6:
                tratti[-1][1] = tempo
            else:
                tratti.append([tempo, tempo])
        for inizio_tratto, fine_tratto in tratti:
            vicino = False
            for evento in voce["eventi"]:
                if inizio_tratto <= evento[1] + SECONDI_TOLLERANZA and fine_tratto >= evento[0]:
                    vicino = True
            if not vicino:
                falsi_allarmi += 1
    precisione = veri_positivi / max(veri_positivi + falsi_positivi, 1)
    richiamo = veri_positivi / max(veri_positivi + falsi_negativi, 1)
    f1 = 2 * precisione * richiamo / max(precisione + richiamo, 1e-12)
    return {"soglia": round(float(soglia), 3), "f1_pezzi": round(f1, 4), "precisione_pezzi": round(precisione, 4),
            "richiamo_pezzi": round(richiamo, 4), "cadute": cadute, "cadute_prese": prese,
            "richiamo_cadute": round(prese / max(cadute, 1), 4), "falsi_allarmi": falsi_allarmi,
            "ore_video": round(ore, 3), "falsi_allarmi_ora": round(falsi_allarmi / max(ore, 1e-9), 2)}


torch.set_num_threads(4)
risultati = {}
righe_confronto = ["| posa | fps | secondi | macro-F1 test | F1 pezzi test | cadute prese | falsi allarmi/ora | ms CPU |",
                   "|---|---|---|---|---|---|---|---|"]
cartelle = cartelle_scheletri()
for modello_posa in cartelle:
    inizio = time.perf_counter()
    video = prepara_video(cartelle[modello_posa])
    video_per_id = {}
    conteggio = {}
    for voce in video:
        video_per_id[voce["id"]] = voce
        chiave = voce["dataset"] + " " + voce["divisione"]
        if chiave not in conteggio:
            conteggio[chiave] = 0
        conteggio[chiave] += 1
    print(f"[{modello_posa}] video con etichette: {conteggio} ({time.perf_counter() - inizio:.0f} s)", flush=True)
    for fps_finestra in FPS_VARIANTI:
        for secondi in SECONDI_VARIANTI:
            nome = f"cadute_stgcn_{modello_posa}_{fps_finestra}fps_{secondi}s"
            if tempo_scaduto():
                print(f"[{nome}] saltata: tempo del kernel scaduto", flush=True)
                continue
            inizio = time.perf_counter()
            dati = costruisci_finestre(video, fps_finestra, secondi)
            numeri = {}
            for parte in dati:
                numeri[parte] = np.bincount(dati[parte]["classi"], minlength=len(CLASSI)).tolist()
            print(f"[{nome}] finestre per classe: {numeri}", flush=True)
            coppie = {}
            for parte in ["train", "val"]:
                coppie[parte] = (dati[parte]["finestre"], dati[parte]["classi"])
            modello, storia = addestra(coppie, CLASSI)
            uscita = {"finestre_per_classe": numeri, "storia": storia}
            probabilita_val = probabilita(modello, dati["val"]["finestre"])
            probabilita_test = probabilita(modello, dati["test"]["finestre"])
            uscita["classi_val"] = metriche_classi(dati["val"]["classi"], probabilita_val.argmax(axis=1), CLASSI)
            uscita["classi_test"] = metriche_classi(dati["test"]["classi"], probabilita_test.argmax(axis=1), CLASSI)
            # soglia dell'allarme scelta sulla validazione (F1 dei pezzi), poi la stessa sul test
            caduta_val = probabilita_val[:, 1] + probabilita_val[:, 2]
            caduta_test = probabilita_test[:, 1] + probabilita_test[:, 2]
            migliore = None
            for soglia in np.arange(0.1, 0.96, 0.05):
                prova = metriche_allarme(caduta_val, dati["val"], video_per_id, soglia)
                if migliore is None or prova["f1_pezzi"] > migliore["f1_pezzi"]:
                    migliore = prova
            uscita["allarme_val"] = migliore
            uscita["allarme_test"] = metriche_allarme(caduta_test, dati["test"], video_per_id, migliore["soglia"])
            lunghezza = int(round(secondi * fps_finestra))
            uscita["ms_cpu_per_finestra"] = millisecondi_cpu(modello, lunghezza)
            uscita["secondi_variante"] = round(time.perf_counter() - inizio, 1)
            esporta(modello, CLASSI, lunghezza, nome, {"fps": fps_finestra, "secondi": secondi,
                                                       "soglia_allarme": migliore["soglia"], "posa": modello_posa})
            risultati[nome] = uscita
            test = uscita["allarme_test"]
            righe_confronto.append(
                f"| {modello_posa} | {fps_finestra} | {secondi} | {uscita['classi_test']['macro_f1']} | "
                f"{test['f1_pezzi']} | {test['cadute_prese']}/{test['cadute']} | {test['falsi_allarmi_ora']} | "
                f"{uscita['ms_cpu_per_finestra']} |")
            print(f"[{nome}] test: {uscita['classi_test']['macro_f1']} macro-F1, allarme {test}", flush=True)
            # scritti dopo ogni variante: se la sessione finisce prima, quello che è fatto resta
            (USCITA / "risultati.json").write_text(json.dumps(risultati, indent=1, ensure_ascii=False))
            (USCITA / "confronto.md").write_text("\n".join(righe_confronto) + "\n")
print("\n".join(righe_confronto), flush=True)
