"""Gesti con la regola, senza allenamento (Marco, 25/11): "mano alla bocca" = un polso vicino al naso per almeno una
durata minima; bere, mangiare o farmaco lo dice l'oggetto del rilevatore.

Tara su Charades (scheletri di `gesti_scheletri`) la soglia della distanza polso-naso, divisa per la misura della
persona (larghezza delle spalle o altezza del box), e la durata minima, a 5 fotogrammi al secondo come a casa.
Stessa divisione e stesse metriche per gesto del kernel `gesti_stgcn` (v2), per confrontarle:
- gesto preso: un tratto della regola tocca il gesto vero (dall'inizio fino a 2 s dopo la fine);
- gesto inventato: un tratto della regola lontano da ogni gesto vero, contato all'ora di video.
La scelta (misura, soglia, durata) è quella con la F1 migliore tra gesti presi e tratti giusti sulla validazione,
tra le soglie che vogliono dire davvero "alla bocca" (LIMITI_ALLA_BOCCA). Senza limiti vince la regola più larga
(polso entro il 60% dell'altezza della persona per 4 s): le azioni di Charades coprono tutto il tempo con la tazza o il
piatto davanti, quindi premiano "mani davanti al busto a lungo", non il gesto (prova del 25/11).

Uso: python3 allenamento/tara_gesti.py runs/dataset_gesti_n
"""
import csv
import json
import random
import sys
from pathlib import Path

import numpy as np

FPS_CASA = 5
AZIONI_GESTO = ["c129", "c106", "c065", "c156"]
CONFIDENZA_MINIMA = 0.3
SECONDI_TOLLERANZA = 2.0
QUOTA_VALIDAZIONE = 0.15
SOGLIE = {"spalle": [0.4, 0.6, 0.8, 1.0, 1.2, 1.4, 1.6, 2.0, 2.5, 3.0],
          "box": [0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.5, 0.6]}
DURATE = [0.2, 0.6, 1.0, 1.4, 2.0, 3.0, 4.0]
# polso entro una larghezza di spalle dal naso, o entro un quarto dell'altezza della persona (circa una testa e mezza)
LIMITI_ALLA_BOCCA = {"spalle": 1.0, "box": 0.25}


def divisioni(cartella: Path) -> dict:
    """id del video → train / val / test, come in gesti_stgcn: val = il 15% dei soggetti di train (seme 0)."""
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


def distanze_a_5_fps(percorso: Path) -> dict:
    """Per ogni istante a FPS_CASA: distanza minima polso-naso divisa per la larghezza delle spalle e per l'altezza del
    box (infinito se i punti non si vedono). La persona è la più sicura del fotogramma, come nei kernel."""
    dati = np.load(percorso)
    numero_frame = int(dati["numero_frame"])
    fps = float(dati["fps"])
    fotogrammi = dati["frame"]
    confidenze = dati["conf"]
    punti_righe = dati["punti"]
    box = dati["box"]
    punti = np.zeros((numero_frame, 17, 3), dtype=np.float32)
    altezze = np.zeros(numero_frame, dtype=np.float32)
    migliore = np.full(numero_frame, -1.0, dtype=np.float32)
    for riga in range(len(fotogrammi)):
        fotogramma = int(fotogrammi[riga])
        if fotogramma >= numero_frame or confidenze[riga] <= migliore[fotogramma]:
            continue
        migliore[fotogramma] = confidenze[riga]
        punti[fotogramma] = punti_righe[riga]
        altezze[fotogramma] = box[riga][3] - box[riga][1]
    durata = numero_frame / fps
    istanti = np.arange(0, durata, 1 / FPS_CASA)
    indici = np.minimum(np.round(istanti * fps).astype(int), numero_frame - 1)
    punti = punti[indici]
    altezze = altezze[indici]
    naso = punti[:, 0]
    spalle = np.linalg.norm(punti[:, 5, :2] - punti[:, 6, :2], axis=1)
    spalle_visibili = (punti[:, 5, 2] > CONFIDENZA_MINIMA) & (punti[:, 6, 2] > CONFIDENZA_MINIMA) & (spalle > 1)
    distanza = np.full(len(indici), np.inf)
    for polso in [9, 10]:
        visibili = (punti[:, polso, 2] > CONFIDENZA_MINIMA) & (naso[:, 2] > CONFIDENZA_MINIMA)
        valore = np.linalg.norm(punti[:, polso, :2] - naso[:, :2], axis=1)
        distanza = np.where(visibili, np.minimum(distanza, valore), distanza)
    per_spalle = np.where(spalle_visibili, distanza / np.maximum(spalle, 1), np.inf)
    per_box = np.where(altezze > 1, distanza / np.maximum(altezze, 1), np.inf)
    return {"istanti": istanti, "spalle": per_spalle, "box": per_box, "durata": durata}


def tratti_della_regola(distanze: np.ndarray, istanti: np.ndarray, soglia: float, durata_minima: float) -> list:
    """Tratti (inizio, fine) in secondi in cui la distanza resta sotto la soglia per almeno durata_minima."""
    tratti = []
    posizione = 0
    while posizione < len(distanze):
        if distanze[posizione] >= soglia:
            posizione += 1
            continue
        fine = posizione
        while fine < len(distanze) and distanze[fine] < soglia:
            fine += 1
        if (fine - posizione) / FPS_CASA >= durata_minima:
            tratti.append((istanti[posizione], istanti[fine - 1]))
        posizione = fine
    return tratti


def misura(video: list, chiave: str, soglia: float, durata_minima: float) -> dict:
    gesti = 0
    presi = 0
    tratti_totali = 0
    inventati = 0
    ore = 0.0
    for voce in video:
        ore += voce["distanze"]["durata"] / 3600
        tratti = tratti_della_regola(voce["distanze"][chiave], voce["distanze"]["istanti"], soglia, durata_minima)
        for inizio, fine in voce["gesti"]:
            gesti += 1
            for inizio_tratto, fine_tratto in tratti:
                if inizio_tratto <= fine + SECONDI_TOLLERANZA and fine_tratto >= inizio:
                    presi += 1
                    break
        for inizio_tratto, fine_tratto in tratti:
            tratti_totali += 1
            vicino = False
            for inizio, fine in voce["gesti"]:
                if inizio_tratto <= fine + SECONDI_TOLLERANZA and fine_tratto >= inizio:
                    vicino = True
            if not vicino:
                inventati += 1
    richiamo = presi / max(gesti, 1)
    precisione = (tratti_totali - inventati) / max(tratti_totali, 1)
    f1 = 2 * precisione * richiamo / max(precisione + richiamo, 1e-12)
    return {"misura": chiave, "soglia": soglia, "durata_minima_s": durata_minima, "gesti": gesti, "presi": presi,
            "richiamo": round(richiamo, 4), "precisione_tratti": round(precisione, 4), "f1": round(f1, 4),
            "inventati": inventati, "inventati_ora": round(inventati / max(ore, 1e-9), 1), "ore": round(ore, 2)}


cartella = Path(sys.argv[1])
divisione_per_video = divisioni(cartella)
scelti = json.loads((cartella / "video_scelti.json").read_text())
video = {"val": [], "test": []}
for percorso in sorted((cartella / "scheletri").rglob("*.npz")):
    identificativo = percorso.name.split(".")[0]
    divisione = divisione_per_video[identificativo]
    if divisione == "train":
        continue
    gesti = []
    for azione in scelti[identificativo]["azioni"].split(";"):
        parti = azione.split()
        if len(parti) == 3 and parti[0] in AZIONI_GESTO:
            gesti.append((float(parti[1]), float(parti[2])))
    video[divisione].append({"distanze": distanze_a_5_fps(percorso), "gesti": gesti})
print(f"video: val {len(video['val'])}, test {len(video['test'])}", flush=True)
migliore = None
migliore_senza_limiti = None
for chiave in SOGLIE:
    for soglia in SOGLIE[chiave]:
        for durata_minima in DURATE:
            prova = misura(video["val"], chiave, soglia, durata_minima)
            if migliore_senza_limiti is None or prova["f1"] > migliore_senza_limiti["f1"]:
                migliore_senza_limiti = prova
            if soglia > LIMITI_ALLA_BOCCA[chiave]:
                continue
            if migliore is None or prova["f1"] > migliore["f1"]:
                migliore = prova
test = misura(video["test"], migliore["misura"], migliore["soglia"], migliore["durata_minima_s"])
print("scelta sulla validazione:", migliore)
print("test:", test)
print("senza limiti (solo per confronto):", migliore_senza_limiti)
# anche la migliore per ogni misura e per ogni durata, per vedere quanto cambia
for chiave in SOGLIE:
    for durata_minima in DURATE:
        migliore_durata = None
        for soglia in SOGLIE[chiave]:
            prova = misura(video["val"], chiave, soglia, durata_minima)
            if migliore_durata is None or prova["f1"] > migliore_durata["f1"]:
                migliore_durata = prova
        test_durata = misura(video["test"], chiave, migliore_durata["soglia"], durata_minima)
        print(f"{chiave} durata {durata_minima} s: soglia {migliore_durata['soglia']}, val F1 {migliore_durata['f1']}, "
              f"test presi {test_durata['presi']}/{test_durata['gesti']}, inventati/ora {test_durata['inventati_ora']}, "
              f"F1 {test_durata['f1']}")
