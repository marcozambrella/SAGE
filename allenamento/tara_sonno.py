"""Ore di sonno con regole sulla posa s (Marco, 25/11 sera: "prendi dei video dai dataset e prova a vedere con dei test
se con delle regole e yolo pose arrivi almeno al 99% di accuracy, altrimenti allena un modello").

Per ogni finestra di FINESTRA_SECONDI secondi (a 5 fotogrammi al secondo, una ogni secondo) la persona è in uno di tre
stati: dorme (sdraiata e quasi ferma), sveglia a letto (seduta, o sdraiata ma in movimento), fuori dal letto.
Etichette dai dataset pubblici che hanno già gli scheletri della posa s:
- Charades (azioni con i secondi): c134 sdraiato sul letto → dorme, ma sveglia se nello stesso momento fa altro
  (telefono, libro, mangiare...; coperta e cuscino no); c135 seduto nel letto e c133 si sveglia → sveglia. Fuori dal
  letto non si sa: il resto del video non si usa;
- GMDCSA (csv con le classi e i secondi): Sleeping → dorme, Sitting → sveglia, Standing e Walking → fuori;
- UR Fall, attività normali: a terra o sdraiato (1 nei csv ufficiali) → dorme.
Limiti: nessun dataset distingue chi è sdraiato e dorme da chi è sdraiato e sveglio ma fermo, né ha il letto
segnato (a casa "fuori dal letto" lo dice la zona letto) né video lunghi di sonno vero: i minuti di errore su inizio e
fine del sonno non si possono misurare. Divisioni come gesti_stgcn (Charades) e cadute_stgcn (GMDCSA, UR Fall).
Le soglie si scelgono solo sulla validazione (accuratezza per finestra), i numeri finali sono sul test.

Uso: python3 allenamento/tara_sonno.py
"""
import csv
import json
import random
import re
from pathlib import Path

import numpy as np

CARTELLA_GESTI = Path("runs/dataset_gesti_s")
CARTELLA_CADUTE = Path("runs/dataset_scheletri_s/scheletri/yolo26s-pose")
CARTELLA_GMDCSA = Path("runs/etichette_gmdcsa")
CSV_URFALL = Path("runs/dataset_scheletri_s/etichette_urfall/urfall-cam0-adls.csv")
FPS_CASA = 5
FINESTRA_SECONDI = 2.0
QUOTA_MINIMA = 0.8          # una finestra ha un'etichetta se almeno l'80% dei fotogrammi ha la stessa
VISIBILITA_MINIMA = 0.3     # come scheletro.py di casa
QUOTA_VALIDAZIONE = 0.15
DORME = 0
SVEGLIA = 1
FUORI = 2
NOMI_STATI = ["dorme", "sveglia a letto", "fuori dal letto"]
# Postura (la parte delle regole che i dati pubblici permettono di misurare bene): c134 di Charades è sdraiato anche se
# nel frattempo fa altro
SDRAIATA = 0
SEDUTA = 1
IN_PIEDI = 2
NOMI_POSTURE = ["sdraiata", "seduta", "in piedi"]
AZIONI_LETTO = ["c133", "c134", "c135"]
# azioni che si fanno da sdraiati e fermi: non svegliano
AZIONI_COMPATIBILI_CON_SONNO = ["c070", "c072", "c076", "c078"]
SOGLIE_ANGOLO = [40, 45, 50, 55, 60, 65, 70]
SOGLIE_MOVIMENTO = [0.02, 0.03, 0.05, 0.08, 0.12, 0.2, float("inf")]
SOGLIE_COSCIA = [0.3, 0.4, 0.5, 0.6, 0.7, 0.8]


def divisioni_charades() -> dict:
    """id del video → train / val / test, come in gesti_stgcn: val = il 15% dei soggetti di train (seme 0)."""
    scelti = json.loads((CARTELLA_GESTI / "video_scelti.json").read_text())
    soggetti = {}
    for nome in ["Charades_v1_train.csv", "Charades_v1_test.csv"]:
        with open(CARTELLA_GESTI / nome) as file:
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


def divisione_cadute(dataset: str, relativo: str) -> str:
    """Come divisione() di cadute_stgcn per GMDCSA e UR Fall."""
    if dataset == "gmdcsa24":
        soggetto = int(re.search(r"Subject (\d+)", relativo).group(1))
        if soggetto == 4:
            return "test"
        if soggetto == 3:
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


def persona_per_istante(percorso: Path) -> dict:
    """Per ogni istante a FPS_CASA la persona più sicura: punti (N, 17, 3), box (N, 4), presente (N,)."""
    dati = np.load(percorso)
    numero_frame = int(dati["numero_frame"])
    fps = float(dati["fps"])
    fotogrammi = dati["frame"]
    confidenze = dati["conf"]
    punti_righe = dati["punti"]
    box_righe = dati["box"]
    punti = np.zeros((numero_frame, 17, 3), dtype=np.float32)
    box = np.zeros((numero_frame, 4), dtype=np.float32)
    migliore = np.full(numero_frame, -1.0, dtype=np.float32)
    for riga in range(len(fotogrammi)):
        fotogramma = int(fotogrammi[riga])
        if fotogramma >= numero_frame or confidenze[riga] <= migliore[fotogramma]:
            continue
        migliore[fotogramma] = confidenze[riga]
        punti[fotogramma] = punti_righe[riga]
        box[fotogramma] = box_righe[riga]
    istanti = np.arange(0, numero_frame / fps, 1 / FPS_CASA)
    indici = np.minimum(np.round(istanti * fps).astype(int), numero_frame - 1)
    return {"istanti": istanti, "punti": punti[indici], "box": box[indici], "presente": migliore[indici] >= 0}


def etichette_charades(azioni: str, istanti: np.ndarray) -> tuple:
    intervalli = {}
    for pezzo in azioni.split(";"):
        parti = pezzo.split()
        if len(parti) != 3:
            continue
        if parti[0] not in intervalli:
            intervalli[parti[0]] = []
        intervalli[parti[0]].append((float(parti[1]), float(parti[2])))
    etichette = np.full(len(istanti), -1, dtype=np.int64)
    posture = np.full(len(istanti), -1, dtype=np.int64)
    for posizione in range(len(istanti)):
        istante = istanti[posizione]
        attive = set()
        for classe in intervalli:
            for inizio, fine in intervalli[classe]:
                if inizio <= istante <= fine:
                    attive.add(classe)
        if "c134" in attive and "c135" in attive:
            continue
        if "c134" in attive:
            posture[posizione] = SDRAIATA
        if "c135" in attive:
            posture[posizione] = SEDUTA
        if "c135" in attive or "c133" in attive:
            etichette[posizione] = SVEGLIA
        elif "c134" in attive:
            etichette[posizione] = DORME
            for classe in attive:
                if classe not in AZIONI_LETTO and classe not in AZIONI_COMPATIBILI_CON_SONNO:
                    etichette[posizione] = SVEGLIA
    return etichette, posture


def etichette_gmdcsa(riga: str, istanti: np.ndarray) -> tuple:
    intervalli = re.findall(r"([A-Za-z]+)\s*(?:\([A-Za-z]*\)?)?\s*\[\s*([\d.]+)\s*(?:to\s*)?([\d.]+)\s*\]", riga)
    etichette = np.full(len(istanti), -1, dtype=np.int64)
    posture = np.full(len(istanti), -1, dtype=np.int64)
    for posizione in range(len(istanti)):
        attive = set()
        for nome, inizio, fine in intervalli:
            if float(inizio) <= istanti[posizione] <= float(fine):
                attive.add(nome)
        in_piedi = "Standing" in attive or "Walking" in attive
        if len(attive.intersection({"Fall", "Falling"})) > 0:
            continue
        if in_piedi and len(attive.intersection({"Sitting", "Sleeping"})) == 0:
            etichette[posizione] = FUORI
            posture[posizione] = IN_PIEDI
        elif "Sleeping" in attive and "Sitting" not in attive and not in_piedi:
            etichette[posizione] = DORME
            posture[posizione] = SDRAIATA
        elif "Sitting" in attive and "Sleeping" not in attive and not in_piedi:
            etichette[posizione] = SVEGLIA
            posture[posizione] = SEDUTA
    return etichette, posture


def carica_video() -> dict:
    """divisione → lista di {id, persona, etichette}."""
    video = {"train": [], "val": [], "test": []}
    scelti = json.loads((CARTELLA_GESTI / "video_scelti.json").read_text())
    divisioni = divisioni_charades()
    for percorso in sorted((CARTELLA_GESTI / "scheletri").rglob("*.npz")):
        identificativo = percorso.name.split(".")[0]
        azioni = scelti[identificativo]["azioni"]
        sul_letto = False
        for classe in AZIONI_LETTO:
            if classe in azioni:
                sul_letto = True
        if not sul_letto:
            continue
        persona = persona_per_istante(percorso)
        etichette, posture = etichette_charades(azioni, persona["istanti"])
        video[divisioni[identificativo]].append({"id": "charades/" + identificativo, "persona": persona,
                                                 "etichette": etichette, "posture": posture})
    righe_gmdcsa = {}
    for percorso_csv in sorted(CARTELLA_GMDCSA.rglob("*.csv")):
        soggetto = percorso_csv.parent.name
        for riga in percorso_csv.read_text(errors="replace").splitlines()[1:]:
            righe_gmdcsa[soggetto + "/" + percorso_csv.stem + "/" + riga.split(",")[0]] = riga
    for percorso in sorted((CARTELLA_CADUTE / "gmdcsa24").rglob("*.npz")):
        chiave = percorso.parent.parent.name + "/" + percorso.parent.name + "/" + percorso.name[:-len(".npz")]
        if chiave not in righe_gmdcsa:
            continue
        persona = persona_per_istante(percorso)
        relativo = str(percorso.relative_to(CARTELLA_CADUTE / "gmdcsa24"))
        etichette, posture = etichette_gmdcsa(righe_gmdcsa[chiave], persona["istanti"])
        video[divisione_cadute("gmdcsa24", relativo)].append({"id": "gmdcsa24/" + chiave, "persona": persona,
                                                              "etichette": etichette, "posture": posture})
    sdraiati = {}
    with open(CSV_URFALL) as file:
        for riga in csv.reader(file):
            if len(riga) >= 3 and riga[2] == "1":
                if riga[0] not in sdraiati:
                    sdraiati[riga[0]] = set()
                sdraiati[riga[0]].add(int(riga[1]))
    for percorso in sorted((CARTELLA_CADUTE / "urfall").rglob("adl-*.npz")):
        sequenza = "-".join(percorso.name.split("-")[:2])
        dati = np.load(percorso)
        fps = float(dati["fps"])
        persona = persona_per_istante(percorso)
        etichette = np.full(len(persona["istanti"]), -1, dtype=np.int64)
        for posizione in range(len(persona["istanti"])):
            # i csv ufficiali contano i fotogrammi da 1
            if int(round(persona["istanti"][posizione] * fps)) + 1 in sdraiati.get(sequenza, set()):
                etichette[posizione] = DORME
        relativo = str(percorso.relative_to(CARTELLA_CADUTE / "urfall"))
        # sdraiato è anche la postura
        video[divisione_cadute("urfall", relativo)].append({"id": "urfall/" + sequenza, "persona": persona,
                                                            "etichette": etichette, "posture": etichette.copy()})
    return video


def angolo_del_busto(punti: np.ndarray):
    """Gradi del busto dalla verticale, come scheletro.py di casa (None se spalle o anche non si vedono)."""
    spalle = []
    anche = []
    for indice in [5, 6]:
        if punti[indice, 2] >= VISIBILITA_MINIMA:
            spalle.append(punti[indice, :2])
    for indice in [11, 12]:
        if punti[indice, 2] >= VISIBILITA_MINIMA:
            anche.append(punti[indice, :2])
    if len(spalle) == 0 or len(anche) == 0:
        return None
    centro_spalle = np.mean(np.stack(spalle), axis=0)
    centro_anche = np.mean(np.stack(anche), axis=0)
    dx = float(centro_spalle[0] - centro_anche[0])
    dy = float(centro_anche[1] - centro_spalle[1])
    if dx == 0 and dy == 0:
        return None
    return float(np.degrees(np.arctan2(abs(dx), dy)))


def coscia_verticale(punti: np.ndarray):
    """Quanto scende la coscia (anca → ginocchio, in verticale) rispetto alla lunghezza del busto: circa 1 in piedi,
    vicino a 0 da seduti (coscia orizzontale). None se i punti non si vedono."""
    rapporti = []
    for anca, ginocchio, spalla in [(11, 13, 5), (12, 14, 6)]:
        visibili = True
        for indice in [anca, ginocchio, spalla]:
            if punti[indice, 2] < VISIBILITA_MINIMA:
                visibili = False
        if not visibili:
            continue
        busto = float(np.linalg.norm(punti[anca, :2] - punti[spalla, :2]))
        if busto < 1:
            continue
        rapporti.append(abs(float(punti[ginocchio, 1] - punti[anca, 1])) / busto)
    if len(rapporti) == 0:
        return None
    return float(np.mean(rapporti))


def misure_finestra(persona: dict, fine: int, lunghezza: int):
    """Angolo e coscia (mediane), rapporto del box e movimento (altezze del box al secondo) della finestra che
    finisce all'istante `fine`. None se la persona c'è in meno di metà dei fotogrammi."""
    inizio = fine - lunghezza + 1
    angoli = []
    cosce = []
    rapporti = []
    movimenti = []
    presenti = 0
    for posizione in range(inizio, fine + 1):
        if not persona["presente"][posizione]:
            continue
        presenti += 1
        punti = persona["punti"][posizione]
        box = persona["box"][posizione]
        altezza = max(float(box[3] - box[1]), 1.0)
        rapporti.append(float(box[2] - box[0]) / altezza)
        angolo = angolo_del_busto(punti)
        if angolo is not None:
            angoli.append(angolo)
        coscia = coscia_verticale(punti)
        if coscia is not None:
            cosce.append(coscia)
        precedente = posizione - 1
        if precedente >= inizio and persona["presente"][precedente]:
            prima = persona["punti"][precedente]
            visibili = (punti[:, 2] >= VISIBILITA_MINIMA) & (prima[:, 2] >= VISIBILITA_MINIMA)
            if visibili.any():
                spostamento = np.linalg.norm(punti[visibili, :2] - prima[visibili, :2], axis=1).mean()
                movimenti.append(float(spostamento) / altezza * FPS_CASA)
    if presenti < lunghezza / 2:
        return None
    misure = {"angolo": None, "coscia": None, "rapporto": float(np.median(rapporti)), "movimento": float("inf")}
    if len(angoli) > 0:
        misure["angolo"] = float(np.median(angoli))
    if len(cosce) > 0:
        misure["coscia"] = float(np.median(cosce))
    if len(movimenti) > 0:
        misure["movimento"] = float(np.mean(movimenti))
    return misure


def finestre(video: list, chiave: str) -> list:
    """(misure, stato o postura vera) di ogni finestra con un'etichetta chiara, una al secondo; chiave "etichette"
    (i tre stati) o "posture"."""
    lunghezza = int(round(FINESTRA_SECONDI * FPS_CASA))
    risultato = []
    for voce in video:
        etichette = voce[chiave]
        for fine in range(lunghezza - 1, len(etichette), FPS_CASA):
            pezzo = etichette[fine - lunghezza + 1:fine + 1]
            stato = None
            for candidato in [DORME, SVEGLIA, FUORI]:
                if np.mean(pezzo == candidato) >= QUOTA_MINIMA:
                    stato = candidato
            if stato is None:
                continue
            misure = misure_finestra(voce["persona"], fine, lunghezza)
            if misure is None:
                continue
            risultato.append((misure, stato))
    return risultato


def stato_della_regola(misure: dict, soglia_angolo: float, soglia_movimento: float, soglia_coscia: float) -> int:
    """Sdraiata (busto oltre la soglia; senza busto, box largo) → dorme se si muove poco, altrimenti sveglia;
    seduta (coscia poco verticale) → sveglia; altrimenti in piedi → fuori dal letto."""
    sdraiata = misure["rapporto"] >= 1.5
    if misure["angolo"] is not None:
        sdraiata = misure["angolo"] >= soglia_angolo
    if sdraiata:
        if misure["movimento"] <= soglia_movimento:
            return DORME
        return SVEGLIA
    if misure["coscia"] is not None and misure["coscia"] <= soglia_coscia:
        return SVEGLIA
    return FUORI


def postura_della_regola(misure: dict, soglia_angolo: float, soglia_coscia: float) -> int:
    sdraiata = misure["rapporto"] >= 1.5
    if misure["angolo"] is not None:
        sdraiata = misure["angolo"] >= soglia_angolo
    if sdraiata:
        return SDRAIATA
    if misure["coscia"] is not None and misure["coscia"] <= soglia_coscia:
        return SEDUTA
    return IN_PIEDI


def valuta_postura(elenco: list, soglia_angolo: float, soglia_coscia: float) -> dict:
    confusione = np.zeros((3, 3), dtype=np.int64)
    for misure, postura in elenco:
        confusione[postura, postura_della_regola(misure, soglia_angolo, soglia_coscia)] += 1
    accuratezza = float(np.trace(confusione)) / max(int(confusione.sum()), 1)
    return {"accuratezza": round(accuratezza, 4), "finestre": int(confusione.sum()), "confusione": confusione.tolist()}


def valuta(elenco: list, soglia_angolo: float, soglia_movimento: float, soglia_coscia: float) -> dict:
    confusione = np.zeros((3, 3), dtype=np.int64)
    for misure, stato in elenco:
        confusione[stato, stato_della_regola(misure, soglia_angolo, soglia_movimento, soglia_coscia)] += 1
    accuratezza = float(np.trace(confusione)) / max(int(confusione.sum()), 1)
    return {"accuratezza": round(accuratezza, 4), "finestre": int(confusione.sum()), "confusione": confusione.tolist()}


video = carica_video()
for chiave, nomi in [("posture", NOMI_POSTURE), ("etichette", NOMI_STATI)]:
    elenchi = {}
    for divisione in video:
        elenchi[divisione] = finestre(video[divisione], chiave)
        conteggi = [0, 0, 0]
        for misure, stato in elenchi[divisione]:
            conteggi[stato] += 1
        print(f"{chiave}, {divisione}: {len(video[divisione])} video, finestre {dict(zip(nomi, conteggi))}", flush=True)
    migliore = None
    for soglia_angolo in SOGLIE_ANGOLO:
        for soglia_coscia in SOGLIE_COSCIA:
            movimenti = SOGLIE_MOVIMENTO
            if chiave == "posture":
                movimenti = [None]
            for soglia_movimento in movimenti:
                if chiave == "posture":
                    prova = valuta_postura(elenchi["val"], soglia_angolo, soglia_coscia)
                else:
                    prova = valuta(elenchi["val"], soglia_angolo, soglia_movimento, soglia_coscia)
                if migliore is None or prova["accuratezza"] > migliore["accuratezza"]:
                    migliore = prova
                    migliore["soglie"] = (soglia_angolo, soglia_coscia, soglia_movimento)
    print(f"{chiave}: regole scelte sulla validazione (angolo, coscia, movimento):", migliore, flush=True)
    soglia_angolo, soglia_coscia, soglia_movimento = migliore["soglie"]
    if chiave == "posture":
        print(f"{chiave}, test:", valuta_postura(elenchi["test"], soglia_angolo, soglia_coscia), flush=True)
    else:
        print(f"{chiave}, test:", valuta(elenchi["test"], soglia_angolo, soglia_movimento, soglia_coscia), flush=True)
    print("righe = vero, colonne = regola, nell'ordine", nomi, flush=True)
