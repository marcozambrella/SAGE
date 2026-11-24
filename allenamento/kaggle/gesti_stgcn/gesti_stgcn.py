"""Gesti (D15, rete ibrida di Marco): classificatore ST-GCN dei gesti dagli scheletri, prende_farmaco / beve / mangia /
altro. Il rilevatore dei farmaci trova scatola o portapillole, questo modello il gesto; il programma di casa li unisce.

Ingresso: gli scheletri di `gesti_scheletri` (Charades, 12 fotogrammi al secondo, un npz per video) in un dataset
privato: questo kernel allega `sage-gesti-scheletri-n` (posa n), `gesti_stgcn_s` (stesso codice)
`sage-gesti-scheletri-s` (posa s); nel dataset anche video_scelti.json (divisione, azioni) e i csv di Charades
(soggetti).
Classi dalle azioni di Charades: c129 (prende una medicina) → prende_farmaco, c106 (beve da tazza, bicchiere o
bottiglia) → beve, c065 e c156 (mangia) → mangia, il resto → altro. Se due si sovrappongono vince il farmaco, poi
bere, poi mangiare. c128 (tiene in mano una medicina) non è un gesto preciso: quei tratti non si usano.
Una finestra prende la classe di un gesto se il gesto copre almeno metà della finestra; le finestre coperte solo in
parte da un gesto (o da c128) sono ambigue e non si usano per allenare né per le metriche per finestra.
Divisione per soggetto (lezione di ARGO): test = divisione ufficiale di Charades (soggetti diversi da quelli di
train), validazione = il 15% dei soggetti di train.
Varianti (coordinatore, 24/11): 4, 6 e 12 fotogrammi al secondo, finestre di SECONDI_FINESTRA secondi. Per stare nei
tempi della CPU (stima ~7 h per le tre varianti, 12 epoche) allenamento e validazione usano al massimo
MASSIMO_PER_CLASSE e MASSIMO_PER_CLASSE_VAL finestre per classe; il kernel si ferma comunque a ORE_MASSIME.
Metriche sul test: per finestra (macro-F1, richiamo e precisione per classe) e per gesto: gesti presi (una finestra
della classe giusta dentro il gesto o entro 2 s dalla fine) e gesti inventati all'ora (tratti di finestre di una
classe lontani da ogni gesto di quella classe), su tutte le finestre dei video di test.
Uscita in /kaggle/working: un .pt e un .onnx per variante, risultati.json, confronto.md.
"""
import csv
import json
import math
import os
import random
import subprocess
import sys
import time
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
    # ogni dati["..."] rilegge l'array dal file npz: si leggono una volta sola (prima era lentissimo su Charades)
    numero_frame = int(dati["numero_frame"])
    fps = float(dati["fps"])
    fotogrammi = dati["frame"]
    confidenze = dati["conf"]
    punti_righe = dati["punti"]
    box = dati["box"]
    punti = np.zeros((numero_frame, NUMERO_PUNTI, 3), dtype=np.float32)
    altezze = np.zeros(numero_frame, dtype=np.float32)
    migliore = np.full(numero_frame, -1.0, dtype=np.float32)
    for riga in range(len(fotogrammi)):
        fotogramma = int(fotogrammi[riga])
        if fotogramma >= numero_frame or confidenze[riga] <= migliore[fotogramma]:
            continue
        migliore[fotogramma] = confidenze[riga]
        punti[fotogramma] = punti_righe[riga]
        altezze[fotogramma] = box[riga][3] - box[riga][1]
    return {"punti": punti, "altezze": altezze, "presente": migliore >= 0, "fps": fps, "numero_frame": numero_frame}


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


CLASSI = ["altro", "prende_farmaco", "beve", "mangia"]
# codice di Charades → classe; -1 = ambigua (tiene in mano una medicina)
AZIONI = {"c129": 1, "c106": 2, "c065": 3, "c156": 3, "c128": -1}
# ordine di scrittura: l'ultima scritta vince dove le azioni si sovrappongono (farmaco, poi bere, poi mangiare)
ORDINE_SCRITTURA = [-1, 3, 2, 1]
FPS_VARIANTI = [4, 6, 12]
SECONDI_FINESTRA = 4
MASSIMO_PER_CLASSE = 6000
# anche la validazione (si guarda a ogni epoca) è limitata: con tutte le finestre "altro" a 12 fps costava ~6 min
# a epoca sulla CPU di Kaggle (stima dalla prova locale del 24/11)
MASSIMO_PER_CLASSE_VAL = 3000
QUOTA_VALIDAZIONE = 0.15
SECONDI_TOLLERANZA = 2.0


def trova_file(nome: str) -> Path:
    for cartella, _, nomi in os.walk(INGRESSO, followlinks=True):
        if nome in nomi:
            return Path(cartella) / nome
    raise FileNotFoundError(nome)


def leggi_soggetti() -> dict:
    """id del video → soggetto, dai csv di Charades."""
    soggetti = {}
    for nome in ["Charades_v1_train.csv", "Charades_v1_test.csv"]:
        with open(trova_file(nome)) as file:
            for riga in csv.DictReader(file):
                soggetti[riga["id"]] = riga["subject"]
    return soggetti


def intervalli_azioni(testo_azioni: str) -> list:
    """"c106 14.20 22.50;c107 0.00 32.00" → [(classe, inizio, fine)] solo per le azioni in AZIONI."""
    intervalli = []
    for azione in testo_azioni.split(";"):
        parti = azione.split()
        if len(parti) == 3 and parti[0] in AZIONI:
            intervalli.append((AZIONI[parti[0]], float(parti[1]), float(parti[2])))
    return intervalli


def etichette_fotogrammi(intervalli: list, numero_frame: int, fps: float) -> np.ndarray:
    etichette = np.zeros(numero_frame, dtype=np.int64)
    for classe in ORDINE_SCRITTURA:
        for classe_azione, inizio, fine in intervalli:
            if classe_azione == classe:
                etichette[int(inizio * fps):min(int(math.ceil(fine * fps)) + 1, numero_frame)] = classe
    return etichette


def etichetta_gesto(etichette: np.ndarray) -> int:
    """Classe della finestra: un gesto se copre almeno metà dei fotogrammi, altro se non c'è niente, -1 (ambigua)
    se c'è solo un pezzo di gesto o c128."""
    if len(etichette) == 0:
        return -1
    for classe in [1, 2, 3]:
        if np.mean(etichette == classe) >= 0.5:
            return classe
    if np.any(etichette != 0):
        return -1
    return 0


def prepara_video(cartella_scheletri: Path) -> list:
    scelti = json.loads(trova_file("video_scelti.json").read_text())
    soggetti = leggi_soggetti()
    soggetti_train = set()
    for identificativo in scelti:
        if scelti[identificativo]["divisione"] == "train":
            soggetti_train.add(soggetti[identificativo])
    soggetti_train = sorted(soggetti_train)
    numero_val = int(round(len(soggetti_train) * QUOTA_VALIDAZIONE))
    soggetti_val = set(random.Random(0).sample(soggetti_train, numero_val))
    video = []
    for percorso in sorted(cartella_scheletri.rglob("*.npz")):
        identificativo = percorso.name.split(".")[0]
        if identificativo not in scelti:
            continue
        divisione = scelti[identificativo]["divisione"]
        if divisione == "train" and soggetti[identificativo] in soggetti_val:
            divisione = "val"
        scheletro = carica_scheletro(percorso)
        intervalli = intervalli_azioni(scelti[identificativo]["azioni"])
        etichette = etichette_fotogrammi(intervalli, scheletro["numero_frame"], scheletro["fps"])
        video.append({"id": identificativo, "divisione": divisione, "scheletro": scheletro, "etichette": etichette,
                      "intervalli": intervalli, "durata": scheletro["numero_frame"] / scheletro["fps"]})
    return video


def costruisci_finestre(video: list, fps_finestra: float) -> dict:
    """train e val: solo finestre non ambigue, al massimo MASSIMO_PER_CLASSE (train) e MASSIMO_PER_CLASSE_VAL (val)
    per classe, scelte a caso; test: tutte, anche le ambigue (classe -1), per le metriche per gesto sul flusso
    intero."""
    dati = {}
    for nome in ["train", "val", "test"]:
        dati[nome] = {"finestre": [], "classi": [], "video": [], "fini": []}
    for voce in video:
        finestre, classi, fini = finestre_di_un_video(voce["scheletro"], voce["etichette"], fps_finestra,
                                                      SECONDI_FINESTRA, etichetta_gesto)
        parte = dati[voce["divisione"]]
        for indice in range(len(finestre)):
            if classi[indice] < 0 and voce["divisione"] != "test":
                continue
            parte["finestre"].append(finestre[indice])
            parte["classi"].append(classi[indice])
            parte["fini"].append(fini[indice])
            parte["video"].append(voce["id"])
    generatore = random.Random(0)
    massimi = {"train": MASSIMO_PER_CLASSE, "val": MASSIMO_PER_CLASSE_VAL}
    for nome in massimi:
        tenute = []
        for classe in range(len(CLASSI)):
            indici = []
            for indice in range(len(dati[nome]["classi"])):
                if dati[nome]["classi"][indice] == classe:
                    indici.append(indice)
            if len(indici) > massimi[nome]:
                indici = generatore.sample(indici, massimi[nome])
            tenute.extend(indici)
        tenute.sort()
        for chiave in ["finestre", "classi", "fini", "video"]:
            valori = []
            for indice in tenute:
                valori.append(dati[nome][chiave][indice])
            dati[nome][chiave] = valori
    lunghezza = int(round(SECONDI_FINESTRA * fps_finestra))
    for nome in dati:
        parte = dati[nome]
        if parte["finestre"]:
            parte["finestre"] = np.stack(parte["finestre"]).astype(np.float32)
        else:
            parte["finestre"] = np.zeros((0, lunghezza, NUMERO_PUNTI, 3), dtype=np.float32)
        parte["classi"] = np.array(parte["classi"], dtype=np.int64)
        parte["fini"] = np.array(parte["fini"])
    return dati


def metriche_gesti(predette: np.ndarray, parte: dict, video_per_id: dict) -> dict:
    """Per ogni classe di gesto: gesti presi (una finestra predetta di quella classe che finisce dentro il gesto o
    entro SECONDI_TOLLERANZA dopo) e gesti inventati (tratti di finestre predette di quella classe lontani da ogni
    gesto vero della stessa classe), all'ora di video."""
    finestre_per_video = {}
    for indice in range(len(parte["video"])):
        identificativo = parte["video"][indice]
        if identificativo not in finestre_per_video:
            finestre_per_video[identificativo] = []
        finestre_per_video[identificativo].append((parte["fini"][indice], int(predette[indice])))
    ore = 0.0
    for identificativo in finestre_per_video:
        ore += video_per_id[identificativo]["durata"] / 3600
    risultato = {"ore_video": round(ore, 2)}
    for classe in [1, 2, 3]:
        gesti = 0
        presi = 0
        inventati = 0
        for identificativo in finestre_per_video:
            finestre = sorted(finestre_per_video[identificativo])
            veri = []
            for classe_azione, inizio, fine in video_per_id[identificativo]["intervalli"]:
                if classe_azione == classe:
                    veri.append((inizio, fine))
            for inizio, fine in veri:
                gesti += 1
                for tempo, predetta in finestre:
                    if predetta == classe and inizio <= tempo <= fine + SECONDI_TOLLERANZA:
                        presi += 1
                        break
            tratti = []
            for tempo, predetta in finestre:
                if predetta != classe:
                    continue
                if tratti and tempo - tratti[-1][1] <= PASSO_SECONDI + 1e-6:
                    tratti[-1][1] = tempo
                else:
                    tratti.append([tempo, tempo])
            for inizio_tratto, fine_tratto in tratti:
                vicino = False
                for inizio, fine in veri:
                    if inizio_tratto - SECONDI_FINESTRA <= fine + SECONDI_TOLLERANZA and fine_tratto >= inizio:
                        vicino = True
                if not vicino:
                    inventati += 1
        risultato[CLASSI[classe]] = {"gesti": gesti, "presi": presi, "richiamo": round(presi / max(gesti, 1), 4),
                                     "inventati": inventati, "inventati_ora": round(inventati / max(ore, 1e-9), 1)}
    return risultato


torch.set_num_threads(4)
risultati = {}
righe_confronto = ["| posa | fps | macro-F1 test | richiamo farmaco / beve / mangia (finestre) | gesti presi farmaco / "
                   "beve / mangia | inventati all'ora farmaco / beve / mangia | ms CPU |", "|---|---|---|---|---|---|---|"]
cartelle = cartelle_scheletri()
for modello_posa in cartelle:
    inizio = time.perf_counter()
    video = prepara_video(cartelle[modello_posa])
    video_per_id = {}
    conteggio = {}
    for voce in video:
        video_per_id[voce["id"]] = voce
        if voce["divisione"] not in conteggio:
            conteggio[voce["divisione"]] = 0
        conteggio[voce["divisione"]] += 1
    print(f"[{modello_posa}] video: {conteggio} ({time.perf_counter() - inizio:.0f} s)", flush=True)
    for fps_finestra in FPS_VARIANTI:
        nome = f"gesti_stgcn_{modello_posa}_{fps_finestra}fps_{SECONDI_FINESTRA}s"
        if tempo_scaduto():
            print(f"[{nome}] saltata: tempo del kernel scaduto", flush=True)
            continue
        inizio = time.perf_counter()
        dati = costruisci_finestre(video, fps_finestra)
        numeri = {}
        for parte in dati:
            numeri[parte] = np.bincount(dati[parte]["classi"][dati[parte]["classi"] >= 0],
                                        minlength=len(CLASSI)).tolist()
        print(f"[{nome}] finestre per classe {CLASSI}: {numeri} ({time.perf_counter() - inizio:.0f} s)", flush=True)
        coppie = {}
        for parte in ["train", "val"]:
            coppie[parte] = (dati[parte]["finestre"], dati[parte]["classi"])
        modello, storia = addestra(coppie, CLASSI, epoche=12, pazienza=4)
        uscita = {"finestre_per_classe": numeri, "storia": storia}
        predette_val = probabilita(modello, dati["val"]["finestre"]).argmax(axis=1)
        predette_test = probabilita(modello, dati["test"]["finestre"]).argmax(axis=1)
        uscita["classi_val"] = metriche_classi(dati["val"]["classi"], predette_val, CLASSI)
        chiare = dati["test"]["classi"] >= 0
        uscita["classi_test"] = metriche_classi(dati["test"]["classi"][chiare], predette_test[chiare], CLASSI)
        uscita["gesti_test"] = metriche_gesti(predette_test, dati["test"], video_per_id)
        lunghezza = int(round(SECONDI_FINESTRA * fps_finestra))
        uscita["ms_cpu_per_finestra"] = millisecondi_cpu(modello, lunghezza)
        uscita["secondi_variante"] = round(time.perf_counter() - inizio, 1)
        esporta(modello, CLASSI, lunghezza, nome, {"fps": fps_finestra, "secondi": SECONDI_FINESTRA,
                                                   "posa": modello_posa})
        risultati[nome] = uscita
        classi_test = uscita["classi_test"]
        gesti = uscita["gesti_test"]
        richiami = []
        presi = []
        inventati = []
        for classe in CLASSI[1:]:
            richiami.append(str(classi_test[classe]["richiamo"]))
            presi.append(f"{gesti[classe]['presi']}/{gesti[classe]['gesti']}")
            inventati.append(str(gesti[classe]["inventati_ora"]))
        righe_confronto.append(f"| {modello_posa} | {fps_finestra} | {classi_test['macro_f1']} | {' / '.join(richiami)} | "
                               f"{' / '.join(presi)} | {' / '.join(inventati)} | {uscita['ms_cpu_per_finestra']} |")
        print(f"[{nome}] test: {classi_test['macro_f1']} macro-F1, gesti {gesti}", flush=True)
        # scritti dopo ogni variante: se la sessione finisce prima, quello che è fatto resta
        (USCITA / "risultati.json").write_text(json.dumps(risultati, indent=1, ensure_ascii=False))
        (USCITA / "confronto.md").write_text("\n".join(righe_confronto) + "\n")
print("\n".join(righe_confronto), flush=True)
