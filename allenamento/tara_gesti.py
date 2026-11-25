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

Con le cartelle del kernel oggetti_charades tara anche FRAZIONE_ALTEZZA_OGGETTO_TESTA di casa (la condizione
sull'oggetto della bevuta): scelta sulla validazione, numeri finali solo sul test.

Uso: python3 allenamento/tara_gesti.py runs/dataset_gesti_n [runs/kaggle/oggetti_charades_1 runs/kaggle/...]
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
# Condizione sull'oggetto (coordinatore, 25/11): FRAZIONE_ALTEZZA_OGGETTO_TESTA di casa, distanza tra il naso e il box
# del contenitore in altezze del box della persona (prima 0,04 = 0,3 larghezze di spalle × 0,14). Si tara sulle
# bevute di Charades con la regola del polso di casa: polso entro 0,25 altezze dal naso per 1 s.
AZIONE_BEVUTA = "c106"
CONTENITORI = ["bottle", "wine glass", "cup"]   # le classi COCO di TIPI_DA_CLASSE in bevuta.py
SOGLIE_OGGETTO = [0.0, 0.02, 0.04, 0.06, 0.08, 0.1, 0.15, 0.2, 0.3, 0.5]
# casa tiene gli oggetti sopra 0,25 (CONFIDENZA_MINIMA_OGGETTI): le tazze alla bocca sono piccole e coperte dalla mano,
# quindi si prova anche a scendere (il kernel oggetti_charades salva da 0,05)
CONFIDENZE_OGGETTO = [0.25, 0.15, 0.1, 0.05]
# Seconda forma della condizione (prova del 25/11): con la tazza alla bocca il rilevatore quasi non la vede, quindi
# basta il contenitore vicino alla testa almeno una volta da FINESTRA secondi prima dell'inizio del tratto del polso
# fino a FINESTRA secondi dopo la fine (non in ogni fotogramma)
FINESTRE_OGGETTO = [0, 2, 5]
POLSO_CASA = 0.25
SECONDI_CASA = 1.0


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
    return {"istanti": istanti, "spalle": per_spalle, "box": per_box, "durata": durata, "naso": naso,
            "altezze": altezze}


def distanze_oggetto(percorso: Path, distanze: dict, confidenza_minima: float) -> np.ndarray:
    """Per ogni istante a FPS_CASA: distanza tra il naso e il box del contenitore più vicino, divisa per l'altezza del
    box della persona, come oggetto_alla_testa di casa (infinito se il naso non si vede o non c'è un contenitore).
    Gli oggetti vengono dal kernel oggetti_charades, a 5 fotogrammi al secondo come gli istanti."""
    dati = np.load(percorso)
    fotogrammi = dati["fotogramma"]
    classi = dati["classe"]
    box = dati["box"]
    confidenze = dati["conf"]
    naso = distanze["naso"]
    altezze = distanze["altezze"]
    risultato = np.full(len(naso), np.inf)
    for riga in range(len(fotogrammi)):
        istante = int(fotogrammi[riga])
        if istante >= len(naso) or str(classi[riga]) not in CONTENITORI:
            continue
        if confidenze[riga] < confidenza_minima:
            continue
        if naso[istante, 2] <= CONFIDENZA_MINIMA or altezze[istante] <= 1:
            continue
        # distanza dal punto al rettangolo (0 se il naso è dentro), come distanza_dal_box di casa
        dx = max(float(box[riga, 0] - naso[istante, 0]), 0.0, float(naso[istante, 0] - box[riga, 2]))
        dy = max(float(box[riga, 1] - naso[istante, 1]), 0.0, float(naso[istante, 1] - box[riga, 3]))
        valore = (dx ** 2 + dy ** 2) ** 0.5 / float(altezze[istante])
        risultato[istante] = min(risultato[istante], valore)
    return risultato


def con_oggetto(video: list, confidenza_minima: float, soglia_oggetto: float) -> list:
    """I video con la distanza polso-naso tenuta solo negli istanti con un contenitore vicino alla testa: la regola
    della bevuta di casa (alla_bocca in bevuta.py). I gesti veri sono solo le bevute."""
    risultato = []
    for voce in video:
        distanze = dict(voce["distanze"])
        vicino = voce["oggetto"][confidenza_minima] <= soglia_oggetto
        distanze["box"] = np.where(vicino, voce["distanze"]["box"], np.inf)
        risultato.append({"distanze": distanze, "gesti": voce["bevute"], "oggetto": voce["oggetto"]})
    return risultato


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


def tratti_con_oggetto(voce: dict, tratti: list, filtro: dict) -> list:
    """I tratti con un contenitore (confidenza >= filtro["confidenza"]) entro filtro["soglia"] altezze dal naso
    almeno una volta, da filtro["finestra"] secondi prima dell'inizio a filtro["finestra"] secondi dopo la fine."""
    istanti = voce["distanze"]["istanti"]
    oggetto = voce["oggetto"][filtro["confidenza"]]
    tenuti = []
    for inizio_tratto, fine_tratto in tratti:
        dentro = (istanti >= inizio_tratto - filtro["finestra"]) & (istanti <= fine_tratto + filtro["finestra"])
        if np.any(oggetto[dentro] <= filtro["soglia"]):
            tenuti.append((inizio_tratto, fine_tratto))
    return tenuti


def misura(video: list, chiave: str, soglia: float, durata_minima: float, filtro_oggetto: dict = None) -> dict:
    gesti = 0
    presi = 0
    tratti_totali = 0
    inventati = 0
    ore = 0.0
    for voce in video:
        ore += voce["distanze"]["durata"] / 3600
        tratti = tratti_della_regola(voce["distanze"][chiave], voce["distanze"]["istanti"], soglia, durata_minima)
        if filtro_oggetto is not None:
            tratti = tratti_con_oggetto(voce, tratti, filtro_oggetto)
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
percorsi_oggetti = {}
for cartella_oggetti in sys.argv[2:]:
    for percorso in Path(cartella_oggetti).rglob("*.npz"):
        percorsi_oggetti[percorso.stem] = percorso
video = {"val": [], "test": []}
video_oggetti = {"val": [], "test": []}
for percorso in sorted((cartella / "scheletri").rglob("*.npz")):
    identificativo = percorso.name.split(".")[0]
    divisione = divisione_per_video[identificativo]
    if divisione == "train":
        continue
    gesti = []
    bevute = []
    for azione in scelti[identificativo]["azioni"].split(";"):
        parti = azione.split()
        if len(parti) == 3 and parti[0] in AZIONI_GESTO:
            gesti.append((float(parti[1]), float(parti[2])))
        if len(parti) == 3 and parti[0] == AZIONE_BEVUTA:
            bevute.append((float(parti[1]), float(parti[2])))
    voce = {"distanze": distanze_a_5_fps(percorso), "gesti": gesti}
    video[divisione].append(voce)
    if identificativo in percorsi_oggetti:
        voce["oggetto"] = {}
        for confidenza_minima in CONFIDENZE_OGGETTO:
            voce["oggetto"][confidenza_minima] = distanze_oggetto(percorsi_oggetti[identificativo], voce["distanze"],
                                                                  confidenza_minima)
        voce["bevute"] = bevute
        video_oggetti[divisione].append(voce)
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

if len(sys.argv) > 2:
    print(f"condizione sull'oggetto: video val {len(video_oggetti['val'])}, test {len(video_oggetti['test'])}; "
          f"polso entro {POLSO_CASA} per {SECONDI_CASA} s; gesti veri = bevute ({AZIONE_BEVUTA})")
    for divisione in ["val", "test"]:
        solo_bevute = []
        for voce in video_oggetti[divisione]:
            solo_bevute.append({"distanze": voce["distanze"], "gesti": voce["bevute"]})
        print(f"solo il polso, {divisione}:", misura(solo_bevute, "box", POLSO_CASA, SECONDI_CASA))
    # confidenza e soglia si scelgono solo sulla validazione; il test si guarda solo per le scelte fatte
    scelta_per_confidenza = {}
    for confidenza_minima in CONFIDENZE_OGGETTO:
        for soglia_oggetto in SOGLIE_OGGETTO:
            prova = misura(con_oggetto(video_oggetti["val"], confidenza_minima, soglia_oggetto), "box", POLSO_CASA,
                           SECONDI_CASA)
            prova["confidenza_oggetto"] = confidenza_minima
            prova["soglia_oggetto"] = soglia_oggetto
            print(f"confidenza {confidenza_minima}, oggetto entro {soglia_oggetto}: val presi {prova['presi']}/"
                  f"{prova['gesti']}, precisione {prova['precisione_tratti']}, inventati/ora {prova['inventati_ora']}, "
                  f"F1 {prova['f1']}")
            if confidenza_minima not in scelta_per_confidenza:
                scelta_per_confidenza[confidenza_minima] = prova
            if prova["f1"] > scelta_per_confidenza[confidenza_minima]["f1"]:
                scelta_per_confidenza[confidenza_minima] = prova
    migliore_oggetto = None
    for confidenza_minima in CONFIDENZE_OGGETTO:
        scelta = scelta_per_confidenza[confidenza_minima]
        if migliore_oggetto is None or scelta["f1"] > migliore_oggetto["f1"]:
            migliore_oggetto = scelta
    # la scelta con la confidenza di casa (0,25) e la migliore in assoluto
    for scelta in [scelta_per_confidenza[CONFIDENZE_OGGETTO[0]], migliore_oggetto]:
        test = misura(con_oggetto(video_oggetti["test"], scelta["confidenza_oggetto"], scelta["soglia_oggetto"]), "box",
                      POLSO_CASA, SECONDI_CASA)
        print(f"FRAZIONE_ALTEZZA_OGGETTO_TESTA {scelta['soglia_oggetto']} con confidenza {scelta['confidenza_oggetto']}"
              f" (scelta sulla validazione): val {scelta}")
        print("    test:", test)
    # seconda forma: contenitore vicino alla testa almeno una volta intorno al tratto del polso
    migliore_finestra = None
    for confidenza_minima in CONFIDENZE_OGGETTO:
        for finestra in FINESTRE_OGGETTO:
            for soglia_oggetto in SOGLIE_OGGETTO:
                filtro = {"confidenza": confidenza_minima, "finestra": finestra, "soglia": soglia_oggetto}
                prova = misura(con_oggetto(video_oggetti["val"], confidenza_minima, np.inf), "box", POLSO_CASA,
                               SECONDI_CASA, filtro)
                prova["filtro_oggetto"] = filtro
                if migliore_finestra is None or prova["f1"] > migliore_finestra["f1"]:
                    migliore_finestra = prova
    filtro = migliore_finestra["filtro_oggetto"]
    test = misura(con_oggetto(video_oggetti["test"], filtro["confidenza"], np.inf), "box", POLSO_CASA, SECONDI_CASA,
                  filtro)
    print("contenitore almeno una volta intorno al tratto (scelta sulla validazione): val", migliore_finestra)
    print("    test:", test)
