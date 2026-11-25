"""Classificatore delle cadute: ST-GCN allenato sugli scheletri della posa n (kernel cadute_stgcn, 25/11).

Modello, normalizzazione e costruzione delle finestre sono IDENTICI all'allenamento
(allenamento/kaggle/cadute_stgcn/cadute_stgcn.py: StGcn, normalizza_finestra, finestre_di_un_video), perché il
classificatore deve ricevere gli scheletri come li ha visti allenandosi:
- finestra di T = secondi × fps istanti a passo 1/fps che finiscono adesso, con fps e secondi dell'allenamento
  (scritti nel file dei pesi), qualunque sia il ritmo dell'analisi (5 o 10 fotogrammi al secondo);
- per ogni istante il fotogramma analizzato più vicino della telecamera; se lì la persona (traccia) non c'era, o
  l'istante è prima del primo fotogramma: tutti zeri;
- punti con confidenza ≤ 0,1: zeri; x, y meno il centro (media dei punti visibili della finestra) diviso per la
  mediana dell'altezza del box della persona; terzo canale la confidenza del punto;
- uscita softmax [normale, caduta, a_terra]: caduta se p(caduta) + p(a_terra) ≥ soglia; una finestra ogni 0,5 s.
"""

from dataclasses import dataclass
import datetime

import numpy as np
import torch
from torch import nn

# ===== copiato dall'allenamento (blocco comune finestre e modello): non cambiare senza riallenare =====
NUMERO_PUNTI = 17
# ossa dello scheletro COCO (0 naso, 5-6 spalle, 7-8 gomiti, 9-10 polsi, 11-12 anche, 13-14 ginocchia, 15-16 caviglie)
OSSA = [(0, 1), (0, 2), (1, 3), (2, 4), (0, 5), (0, 6), (5, 6), (5, 7), (7, 9), (6, 8), (8, 10), (5, 11), (6, 12),
        (11, 12), (11, 13), (13, 15), (12, 14), (14, 16)]
CENTRO_SCHELETRO = 0
CONFIDENZA_MINIMA_PUNTO = 0.1
PASSO_SECONDI = 0.5


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
    """ST-GCN piccolo (6 blocchi, 32-128 canali): gira su CPU a casa."""

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
# ===== fine della parte copiata =====


@dataclass
class Scheletro:
    punti: np.ndarray   # (17, 3): x, y in pixel e confidenza
    altezza: float      # altezza del box della persona


@dataclass
class ScheletriDelFotogramma:
    """Un fotogramma analizzato della telecamera: gli scheletri delle persone tracciate (id traccia → Scheletro)."""

    ora: datetime.datetime
    scheletri: dict


def fotogramma_piu_vicino(fotogrammi: list, istante: datetime.datetime) -> ScheletriDelFotogramma:
    migliore = fotogrammi[0]
    for fotogramma in fotogrammi:
        if abs((fotogramma.ora - istante).total_seconds()) < abs((migliore.ora - istante).total_seconds()):
            migliore = fotogramma
    return migliore


def finestra_della_traccia(fotogrammi: list, id_traccia: int, fine: datetime.datetime, fps: float,
                           lunghezza: int) -> np.ndarray:
    """Finestra normalizzata (lunghezza, 17, 3) di una persona che finisce a `fine`, come finestre_di_un_video
    nell'allenamento: per ogni istante il fotogramma analizzato più vicino. fotogrammi: in ordine di tempo."""
    punti = np.zeros((lunghezza, NUMERO_PUNTI, 3), np.float32)
    altezze = np.zeros(lunghezza, np.float32)
    presente = np.zeros(lunghezza, bool)
    if len(fotogrammi) == 0:
        return punti
    # istanti più vicini a un fotogramma prima del primo che al primo: "prima dell'inizio del video", zeri
    mezzo_intervallo = datetime.timedelta(0)
    if len(fotogrammi) > 1:
        mezzo_intervallo = (fotogrammi[1].ora - fotogrammi[0].ora) / 2
    primo_utile = fotogrammi[0].ora - mezzo_intervallo
    for posizione in range(lunghezza):
        istante = fine - datetime.timedelta(seconds=(lunghezza - 1 - posizione) / fps)
        if istante < primo_utile:
            continue
        scheletro = fotogramma_piu_vicino(fotogrammi, istante).scheletri.get(id_traccia)
        if scheletro is None:
            continue
        punti[posizione] = scheletro.punti
        altezze[posizione] = scheletro.altezza
        presente[posizione] = True
    return normalizza_finestra(punti, altezze, presente)


class ClassificatoreCadute:
    """Un modello allenato (.pt dell'allenamento: pesi, classi, lunghezza, fps, secondi, soglia)."""

    def __init__(self, percorso: str):
        dati = torch.load(percorso, map_location="cpu")
        self.classi = dati["classi"]
        self.lunghezza = int(dati["lunghezza"])
        informazioni = dati["informazioni"]
        self.fps = float(informazioni["fps"])
        self.secondi = float(informazioni["secondi"])
        self.soglia = float(informazioni["soglia_allarme"])
        self.modello = StGcn(len(self.classi))
        self.modello.load_state_dict(dati["stato"])  # strict: se il modello copiato non è identico si ferma qui
        self.modello.eval()

    def __deepcopy__(self, memo: dict) -> "ClassificatoreCadute":
        # il modello non è stato: le copie per tornare indietro di un secondo (principale.py) lo condividono
        return self

    def probabilita_caduta(self, finestra: np.ndarray) -> float:
        """p(caduta) + p(a_terra) di una finestra normalizzata (lunghezza, 17, 3)."""
        with torch.no_grad():
            logit = self.modello(torch.from_numpy(finestra[None]))
            probabilita = torch.softmax(logit, dim=1)[0].numpy()
        return float(probabilita[self.classi.index("caduta")] + probabilita[self.classi.index("a_terra")])
