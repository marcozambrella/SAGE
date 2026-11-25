"""Valutazione del sistema delle cadute di casa sugli scheletri dei dataset pubblici, posa n contro posa s, prima e dopo
regole in più contro i falsi allarmi (Marco, 25/11: "riprova il confronto tra posa piccola e media implementando
regole per diminuire i falsi allarmi nelle cadute").

Il codice di casa non si riscrive: si importano AnalizzatoreCaduta e ClassificatoreCadute dal worktree casa
(casa/casa/casa/caduta.py: la geometria decide, il classificatore a 5 fps con soglia 0,94 conferma, senza conferma
allarme dopo 30 s a terra). Gli scheletri sono quelli di cadute_scheletri, presi a 5 fotogrammi al secondo; le
etichette e le divisioni (validazione e test) quelle dell'allenamento (kernel etichette_cadute). Niente zona letto:
i dataset pubblici non hanno il letto segnato.

Per provare tante soglie e regole senza rifare tutto, ogni video passa una volta sola in AnalizzatoreRegistrato:
l'analizzatore di casa che registra le probabilità del classificatore e i momenti "a terra da almeno 2 s" (dove casa
chiede la conferma) invece di mandare l'allarme. Poi decidi_allarmi applica le stesse condizioni di caduta.py con
qualunque soglia, numero di finestre di fila e regola in più. Controllo: con le soglie di casa e senza regole gli
allarmi sono identici a quelli dell'analizzatore vero (verifica).

Metriche per video: una caduta è presa se un allarme arriva da 1 s prima dell'inizio a 5 s dopo la fine del tratto
caduta + a terra; un allarme lontano da ogni caduta è falso (all'ora di video); F1 tra allarmi giusti e cadute prese;
ritardo = secondi tra l'inizio della caduta e l'allarme.
Regole e soglie si scelgono solo sulla validazione (n e s insieme, così casa ha le stesse regole con tutte e due le
pose); i numeri finali sono sul test.

Uso (con il python del worktree casa, che ha torch e pydantic):
  ../casa/.venv/bin/python allenamento/valuta_cadute_casa.py ../casa runs/kaggle/etichette_cadute/etichette_cadute.json
Con --solo-casa valuta solo il codice di casa com'è (dopo che casa ha messo le regole in caduta.py).
"""
import datetime
import json
import statistics
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

CARTELLA_CASA = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(CARTELLA_CASA / "casa"))
sys.path.insert(0, str(CARTELLA_CASA / "contratti"))
from contratti.configurazione import TelecameraLocale  # noqa: E402

from casa.caduta import SECONDI_A_TERRA_SENZA_CONFERMA, SECONDI_CADUTA_RAPIDA, AnalizzatoreCaduta  # noqa: E402
from casa.classificatore_cadute import ClassificatoreCadute  # noqa: E402
from casa.percezione import Osservazione, Persona  # noqa: E402
from casa.scheletro import angolo_del_busto  # noqa: E402

PERCORSO_ETICHETTE = Path(sys.argv[2])
SOLO_CASA = "--solo-casa" in sys.argv
CARTELLE_SCHELETRI = {"n": Path("runs/dataset_scheletri_n/scheletri/yolo26n-pose"),
                      "s": Path("runs/dataset_scheletri_s/scheletri/yolo26s-pose")}
# come PESI_CADUTE in casa/casa/casa/principale.py
PESI = {"n": "pesi/cadute_n_5fps_2s.pt", "s": "pesi/cadute_s_5fps_2s.pt"}
SOGLIA_CASA = 0.94
FINESTRE_CASA = 1
FPS_CASA = 5
INIZIO_VIDEO = datetime.datetime(2026, 12, 1, 10, 0, tzinfo=ZoneInfo("Europe/Rome"))
SECONDI_PRIMA = 1.0
SECONDI_DOPO = 5.0
# molte clip pubbliche finiscono meno di 2 s dopo che la persona è a terra: casa non può ancora decidere (vuole 2 s a
# terra). Si contano a parte le cadute con almeno questi secondi di video dopo l'inizio
SECONDI_VALUTABILE = 4.0
TELECAMERA = TelecameraLocale.model_validate({"id": "valutazione", "nome": "Valutazione", "stanza": "living room",
                                              "sorgente": "x.mp4", "analizzatori": ["caduta"]})
VISIBILITA_MINIMA = 0.3   # come scheletro.py di casa

# Regole provate (una alla volta e poi insieme), tutte nelle altezze della persona in piedi (il box più alto negli
# ultimi 5 s prima di finire a terra), così non dipendono da quanto è lontana dalla telecamera:
# - discesa: velocità massima con cui scendono il centro delle anche o il naso, in altezze al secondo, da 3 s prima
#   a 1 s dopo l'inizio dello stare a terra (chi si sdraia piano scende lento);
# - ferma: dopo la discesa resta quasi ferma: negli ultimi N secondi (sempre a terra) il centro dei punti si muove
#   meno di M altezze al secondo (chi fa esercizi a terra si muove); N=4 ritarda l'allarme a 4 s a terra;
# - angolo: busto più orizzontale dei 60° di casa;
# - basso: centro del box sotto questa frazione dell'altezza del fotogramma;
# - punti: confidenza media dei 17 punti almeno questa (scheletri poco sicuri scartati);
# - grandezza: lato più lungo del box almeno questa frazione dell'altezza del fotogramma (persona troppo piccola).
# Le regole valgono solo per la conferma veloce: l'allarme dopo 30 s a terra resta com'è (rete di sicurezza).
VALORI_REGOLE = {
    "discesa": [0.3, 0.5, 0.7, 1.0],
    "ferma": [(2, 0.3), (2, 0.2), (2, 0.1), (4, 0.3), (4, 0.2), (4, 0.1)],
    "angolo": [70, 75, 80],
    "basso": [0.3, 0.4, 0.5],
    "punti": [0.3, 0.4, 0.5],
    "grandezza": [0.1, 0.15, 0.2],
}
SOGLIE_CLASSIFICATORE = [0.9, 0.94, 0.97, 0.99]
FINESTRE_DI_FILA = [1, 2, 3, 4]


class AnalizzatoreRegistrato(AnalizzatoreCaduta):
    """L'analizzatore di casa che non manda allarmi: registra le probabilità del classificatore, gli scheletri e i
    fotogrammi in cui casa chiederebbe la conferma (a terra da almeno SECONDI_A_TERRA, caduta rapida)."""

    def __init__(self, telecamera: TelecameraLocale, classificatore: ClassificatoreCadute):
        super().__init__(telecamera, classificatore)
        self.probabilita = []   # (numero dello stato, secondi, probabilità)
        self.candidati = []     # (id traccia, numero dello stato, secondi, a terra da, secondi a terra)
        self.storia = {}        # id traccia → [(secondi, Persona)]
        self.numero_stati = 0

    def numero_dello_stato(self, stato) -> int:
        # lo stato di una persona rinasce se la traccia sparisce per 60 s: le probabilità recenti ripartono da zero
        if not hasattr(stato, "numero_registro"):
            self.numero_stati += 1
            stato.numero_registro = self.numero_stati
        return stato.numero_registro

    def elabora(self, osservazione: Osservazione) -> list:
        secondi = (osservazione.ora - INIZIO_VIDEO).total_seconds()
        for persona in osservazione.persone:
            if persona.id_traccia not in self.storia:
                self.storia[persona.id_traccia] = []
            self.storia[persona.id_traccia].append((secondi, persona))
        return super().elabora(osservazione)

    def valuta(self, stato, id_traccia: int, ora: datetime.datetime) -> None:
        prima = stato.valutata
        super().valuta(stato, id_traccia, ora)
        if stato.valutata is not prima:
            secondi = (ora - INIZIO_VIDEO).total_seconds()
            self.probabilita.append((self.numero_dello_stato(stato), secondi, stato.probabilita_recenti[-1]))

    def confermata(self, stato, secondi_a_terra: float) -> bool:
        id_traccia = None
        for identificativo in self.persone:
            if self.persone[identificativo] is stato:
                id_traccia = identificativo
        secondi = (stato.vista - INIZIO_VIDEO).total_seconds()
        a_terra_da = (stato.a_terra_da - INIZIO_VIDEO).total_seconds()
        self.candidati.append((id_traccia, self.numero_dello_stato(stato), secondi, a_terra_da, secondi_a_terra))
        return False


def osservazioni_del_video(percorso: Path) -> list:
    """Le Osservazioni a FPS_CASA di un npz di cadute_scheletri: per ogni istante il fotogramma più vicino, con tutte le
    persone tracciate (immagine nera: a casa serve solo per la foto di prova)."""
    dati = np.load(percorso)
    numero_frame = int(dati["numero_frame"])
    fps = float(dati["fps"])
    fotogrammi = dati["frame"]
    tracce = dati["traccia"]
    box = dati["box"]
    confidenze = dati["conf"]
    punti = dati["punti"]
    immagine = np.zeros((int(dati["altezza"]), int(dati["larghezza"]), 3), dtype=np.uint8)
    righe_per_fotogramma = {}
    for riga in range(len(fotogrammi)):
        fotogramma = int(fotogrammi[riga])
        if fotogramma not in righe_per_fotogramma:
            righe_per_fotogramma[fotogramma] = []
        righe_per_fotogramma[fotogramma].append(riga)
    osservazioni = []
    istanti = np.arange(0, numero_frame / fps, 1 / FPS_CASA)
    for istante in istanti:
        fotogramma = min(int(round(istante * fps)), numero_frame - 1)
        persone = []
        for riga in righe_per_fotogramma.get(fotogramma, []):
            persone.append(Persona(int(tracce[riga]), box[riga].astype(np.float32), float(confidenze[riga]),
                                   punti[riga].astype(np.float32)))
        ora = INIZIO_VIDEO + datetime.timedelta(seconds=float(istante))
        osservazioni.append(Osservazione(TELECAMERA.id, TELECAMERA.stanza, ora, immagine, persone, []))
    return osservazioni


def punto_visto(persona: Persona, indici: list):
    visti = []
    for indice in indici:
        if persona.keypoint[indice, 2] >= VISIBILITA_MINIMA:
            visti.append(persona.keypoint[indice, 0:2])
    if len(visti) == 0:
        return None
    return np.mean(np.stack(visti), axis=0)


def velocita_discesa(storia: list, a_terra_da: float, altezza: float) -> float:
    """Massima velocità di discesa (altezze al secondo) del centro delle anche o del naso, su passi di circa 1 s, da
    3 s prima a 1 s dopo l'inizio dello stare a terra."""
    massima = 0.0
    for indici in [[11, 12], [0]]:
        posizioni = []
        for secondi, persona in storia:
            if a_terra_da - 3 <= secondi <= a_terra_da + 1:
                punto = punto_visto(persona, indici)
                if punto is not None:
                    posizioni.append((secondi, float(punto[1])))
        for primo in range(len(posizioni)):
            for secondo in range(primo + 1, len(posizioni)):
                intervallo = posizioni[secondo][0] - posizioni[primo][0]
                if 0.6 <= intervallo <= 1.4:
                    velocita = (posizioni[secondo][1] - posizioni[primo][1]) / intervallo / altezza
                    massima = max(massima, velocita)
    return massima


def velocita_a_terra(storia: list, inizio: float, fine: float, altezza: float) -> float:
    """Velocità media (altezze al secondo) del centro dei punti visibili tra inizio e fine; infinita se la persona
    si vede troppo poco per dirlo."""
    centri = []
    for secondi, persona in storia:
        if inizio <= secondi <= fine:
            centro = punto_visto(persona, list(range(17)))
            if centro is not None:
                centri.append((secondi, centro))
    if len(centri) < 2 or centri[-1][0] - centri[0][0] < 0.6 * (fine - inizio):
        return float("inf")
    strada = 0.0
    for indice in range(1, len(centri)):
        strada += float(np.linalg.norm(centri[indice][1] - centri[indice - 1][1]))
    return strada / (centri[-1][0] - centri[0][0]) / altezza


def misure_del_candidato(storia: list, secondi: float, a_terra_da: float, secondi_a_terra: float,
                         altezza_immagine: int) -> dict:
    """Le grandezze delle regole nel fotogramma in cui casa chiederebbe la conferma."""
    persona = None
    altezza = 0.0
    for momento, vista in storia:
        if momento == secondi:
            persona = vista
        if a_terra_da - 5 <= momento <= a_terra_da:
            altezza = max(altezza, float(vista.box[3] - vista.box[1]))
    larghezza_box = float(persona.box[2] - persona.box[0])
    altezza_box = float(persona.box[3] - persona.box[1])
    if altezza <= 1:
        altezza = max(larghezza_box, altezza_box, 1.0)
    ferma = {}
    for durata in [2, 4]:
        ferma[durata] = float("inf")
        if secondi_a_terra >= durata:
            ferma[durata] = velocita_a_terra(storia, secondi - durata, secondi, altezza)
    return {"discesa": velocita_discesa(storia, a_terra_da, altezza), "ferma": ferma,
            "angolo": angolo_del_busto(persona),
            "basso": float(persona.box[1] + persona.box[3]) / 2 / altezza_immagine,
            "punti": float(np.mean(persona.keypoint[:, 2])),
            "grandezza": max(larghezza_box, altezza_box) / altezza_immagine}


def rispetta_le_regole(misure: dict, regole: dict) -> bool:
    for nome in regole:
        valore = regole[nome]
        if nome == "discesa" and misure["discesa"] < valore:
            return False
        if nome == "ferma" and misure["ferma"][valore[0]] > valore[1]:
            return False
        # angolo che la posa non vede: la regola non può dire niente, non blocca
        if nome == "angolo" and misure["angolo"] is not None and misure["angolo"] < valore:
            return False
        if nome == "basso" and misure["basso"] < valore:
            return False
        if nome == "punti" and misure["punti"] < valore:
            return False
        if nome == "grandezza" and misure["grandezza"] < valore:
            return False
    return True


def registra_video(percorso: Path, classificatore: ClassificatoreCadute) -> dict:
    analizzatore = AnalizzatoreRegistrato(TELECAMERA, classificatore)
    osservazioni = osservazioni_del_video(percorso)
    for osservazione in osservazioni:
        analizzatore.elabora(osservazione)
    altezza_immagine = osservazioni[0].immagine.shape[0]
    candidati = []
    for id_traccia, numero_stato, secondi, a_terra_da, secondi_a_terra in analizzatore.candidati:
        misure = misure_del_candidato(analizzatore.storia[id_traccia], secondi, a_terra_da, secondi_a_terra,
                                      altezza_immagine)
        candidati.append({"stato": numero_stato, "secondi": secondi, "a_terra_da": a_terra_da,
                          "secondi_a_terra": secondi_a_terra, "misure": misure})
    return {"probabilita": analizzatore.probabilita, "candidati": candidati}


def decidi_allarmi(registro: dict, soglia: float, finestre_di_fila: int, regole: dict) -> list:
    """Secondi degli allarmi con le condizioni di caduta.py: il primo fotogramma di ogni volta a terra in cui c'è la
    conferma del classificatore (k finestre di fila sopra la soglia, da SECONDI_CADUTA_RAPIDA prima di finire a terra
    in poi) e le regole, oppure 30 s a terra."""
    conferme = {}   # numero dello stato → secondi in cui le ultime k probabilità superano la soglia
    recenti = {}
    for numero_stato, secondi, probabilita in registro["probabilita"]:
        if numero_stato not in recenti:
            recenti[numero_stato] = []
            conferme[numero_stato] = []
        recenti[numero_stato].append(probabilita)
        ultime = recenti[numero_stato][-finestre_di_fila:]
        if len(ultime) == finestre_di_fila and min(ultime) >= soglia:
            conferme[numero_stato].append(secondi)
    allarmi = []
    segnalate = set()
    for candidato in registro["candidati"]:
        volta = (candidato["stato"], candidato["a_terra_da"])
        if volta in segnalate:
            continue
        pronta = candidato["secondi_a_terra"] >= SECONDI_A_TERRA_SENZA_CONFERMA
        if not pronta:
            for secondi in conferme.get(candidato["stato"], []):
                if candidato["a_terra_da"] - SECONDI_CADUTA_RAPIDA <= secondi <= candidato["secondi"]:
                    pronta = True
            if pronta:
                pronta = rispetta_le_regole(candidato["misure"], regole)
        if pronta:
            segnalate.add(volta)
            allarmi.append(candidato["secondi"])
    return allarmi


def metriche(allarmi_per_video: dict, etichette: dict) -> dict:
    """allarmi_per_video: id del video → secondi degli allarmi."""
    cadute = 0
    prese = 0
    valutabili = 0
    prese_valutabili = 0
    allarmi_totali = 0
    falsi = 0
    ore = 0.0
    ritardi = []
    for identificativo in allarmi_per_video:
        voce = etichette[identificativo]
        durata = voce["numero_frame"] / voce["fps"]
        ore += durata / 3600
        allarmi = allarmi_per_video[identificativo]
        for inizio, fine in voce["eventi"]:
            cadute += 1
            valutabile = durata - inizio >= SECONDI_VALUTABILE
            if valutabile:
                valutabili += 1
            for allarme in allarmi:
                if inizio - SECONDI_PRIMA <= allarme <= fine + SECONDI_DOPO:
                    prese += 1
                    if valutabile:
                        prese_valutabili += 1
                    ritardi.append(allarme - inizio)
                    break
        for allarme in allarmi:
            allarmi_totali += 1
            vicino = False
            for inizio, fine in voce["eventi"]:
                if inizio - SECONDI_PRIMA <= allarme <= fine + SECONDI_DOPO:
                    vicino = True
            if not vicino:
                falsi += 1
    richiamo = prese / max(cadute, 1)
    precisione = (allarmi_totali - falsi) / max(allarmi_totali, 1)
    f1 = 2 * precisione * richiamo / max(precisione + richiamo, 1e-12)
    ritardo_mediano = None
    ritardo_massimo = None
    if len(ritardi) > 0:
        ritardo_mediano = round(statistics.median(ritardi), 1)
        ritardo_massimo = round(max(ritardi), 1)
    return {"cadute": cadute, "prese": prese, "valutabili": valutabili, "prese_valutabili": prese_valutabili,
            "falsi": falsi, "ore": round(ore, 3),
            "falsi_ora": round(falsi / max(ore, 1e-9), 1), "f1": round(f1, 3), "ritardo_mediano_s": ritardo_mediano,
            "ritardo_massimo_s": ritardo_massimo}


def metriche_del_registro(registri: dict, video: list, soglia: float, finestre_di_fila: int, regole: dict) -> dict:
    allarmi_per_video = {}
    for identificativo in video:
        allarmi_per_video[identificativo] = decidi_allarmi(registri[identificativo], soglia, finestre_di_fila, regole)
    return metriche(allarmi_per_video, etichette)


def somma(prima: dict, seconda: dict) -> dict:
    """Le metriche di n e s insieme, per scegliere regole uguali per le due pose."""
    return {"prese_n": prima["prese"], "prese_s": seconda["prese"], "falsi": prima["falsi"] + seconda["falsi"],
            "f1": round((prima["f1"] + seconda["f1"]) / 2, 3)}


def riga(nome: str, risultato: dict) -> str:
    return (f"| {nome} | {risultato['prese']}/{risultato['cadute']} | "
            f"{risultato['prese_valutabili']}/{risultato['valutabili']} | {risultato['falsi_ora']} | "
            f"{risultato['f1']} | {risultato['ritardo_mediano_s']} (max {risultato['ritardo_massimo_s']}) |")


def allarmi_di_casa(percorso: Path, classificatore: ClassificatoreCadute) -> list:
    """Secondi degli allarmi dell'analizzatore di casa vero (il primo evento di ogni caduta, quello urgente)."""
    analizzatore = AnalizzatoreCaduta(TELECAMERA, classificatore)
    allarmi = []
    for osservazione in osservazioni_del_video(percorso):
        for evento in analizzatore.elabora(osservazione):
            if evento.fine is None:
                allarmi.append((osservazione.ora - INIZIO_VIDEO).total_seconds())
    return allarmi


etichette = json.loads(PERCORSO_ETICHETTE.read_text())
video_per_divisione = {"val": [], "test": []}
for identificativo in sorted(etichette):
    divisione = etichette[identificativo]["divisione"]
    if divisione in video_per_divisione:
        video_per_divisione[divisione].append(identificativo)
print(f"video: val {len(video_per_divisione['val'])}, test {len(video_per_divisione['test'])}", flush=True)

if SOLO_CASA:
    # il codice di casa com'è, senza registro: gli allarmi veri dell'analizzatore
    for posa in CARTELLE_SCHELETRI:
        classificatore = ClassificatoreCadute(str(CARTELLA_CASA / PESI[posa]), SOGLIA_CASA, FINESTRE_CASA)
        for divisione in ["val", "test"]:
            allarmi_per_video = {}
            for identificativo in video_per_divisione[divisione]:
                percorso = CARTELLE_SCHELETRI[posa] / (identificativo + ".npz")
                allarmi_per_video[identificativo] = allarmi_di_casa(percorso, classificatore)
            risultato = metriche(allarmi_per_video, etichette)
            print(f"casa com'è, posa {posa}, {divisione}:", risultato, flush=True)
    sys.exit(0)

registri = {}   # posa → id del video → registro
for posa in CARTELLE_SCHELETRI:
    classificatore = ClassificatoreCadute(str(CARTELLA_CASA / PESI[posa]), SOGLIA_CASA, FINESTRE_CASA)
    registri[posa] = {}
    for divisione in ["val", "test"]:
        for identificativo in video_per_divisione[divisione]:
            registri[posa][identificativo] = registra_video(CARTELLE_SCHELETRI[posa] / (identificativo + ".npz"),
                                                            classificatore)
    print(f"registrata la posa {posa}", flush=True)

# controllo: con le soglie di casa e senza regole il registro dà gli stessi allarmi dell'analizzatore vero
classificatore = ClassificatoreCadute(str(CARTELLA_CASA / PESI["n"]), SOGLIA_CASA, FINESTRE_CASA)
diversi = 0
for identificativo in video_per_divisione["val"]:
    veri = allarmi_di_casa(CARTELLE_SCHELETRI["n"] / (identificativo + ".npz"), classificatore)
    dal_registro = decidi_allarmi(registri["n"][identificativo], SOGLIA_CASA, FINESTRE_CASA, {})
    if veri != dal_registro:
        diversi += 1
        print("diverso:", identificativo, veri, dal_registro, flush=True)
print(f"controllo sulla validazione (posa n): {diversi} video con allarmi diversi da casa", flush=True)


def valuta_su_val(soglia: float, finestre_di_fila: int, regole: dict) -> dict:
    risultato_n = metriche_del_registro(registri["n"], video_per_divisione["val"], soglia, finestre_di_fila, regole)
    risultato_s = metriche_del_registro(registri["s"], video_per_divisione["val"], soglia, finestre_di_fila, regole)
    return somma(risultato_n, risultato_s)


# scelta sulla validazione, un passo alla volta: si aggiunge la regola (o si cambia soglia o finestre di fila) che
# toglie più falsi allarmi senza perdere cadute rispetto a casa com'è (né con la n né con la s); ci si ferma quando
# nessuna toglie altro
base = valuta_su_val(SOGLIA_CASA, FINESTRE_CASA, {})
print("casa com'è, validazione n + s:", base, flush=True)
scelta = {"soglia": SOGLIA_CASA, "finestre": FINESTRE_CASA, "regole": {}}
attuale = base
while True:
    prove = []
    for soglia in SOGLIE_CLASSIFICATORE:
        for finestre_di_fila in FINESTRE_DI_FILA:
            prove.append({"soglia": soglia, "finestre": finestre_di_fila, "regole": dict(scelta["regole"])})
    for nome in VALORI_REGOLE:
        for valore in VALORI_REGOLE[nome]:
            regole = dict(scelta["regole"])
            regole[nome] = valore
            prove.append({"soglia": scelta["soglia"], "finestre": scelta["finestre"], "regole": regole})
    migliore = None
    migliore_risultato = None
    for prova in prove:
        risultato = valuta_su_val(prova["soglia"], prova["finestre"], prova["regole"])
        print("  prova", prova, risultato, flush=True)
        if risultato["prese_n"] < base["prese_n"] or risultato["prese_s"] < base["prese_s"]:
            continue
        if risultato["falsi"] >= attuale["falsi"]:
            continue
        if migliore is None or risultato["falsi"] < migliore_risultato["falsi"]:
            migliore = prova
            migliore_risultato = risultato
    if migliore is None:
        break
    scelta = migliore
    attuale = migliore_risultato
    print("scelta:", scelta, attuale, flush=True)

print("regole scelte sulla validazione:", scelta, flush=True)
righe = ["| posa | regole | divisione | cadute prese | prese con >= 4 s di video dopo | falsi allarmi/ora | F1 | "
         "secondi tra caduta e allarme (mediana) |", "|---|---|---|---|---|---|---|---|"]
for posa in CARTELLE_SCHELETRI:
    for divisione in ["val", "test"]:
        for nome, soglia, finestre_di_fila, regole in [("casa com'è", SOGLIA_CASA, FINESTRE_CASA, {}),
                                                       ("con le regole", scelta["soglia"], scelta["finestre"],
                                                        scelta["regole"])]:
            risultato = metriche_del_registro(registri[posa], video_per_divisione[divisione], soglia,
                                              finestre_di_fila, regole)
            print(f"posa {posa}, {divisione}, {nome}:", risultato, flush=True)
            righe.append(riga(f"{posa} | {nome} | {divisione}", risultato))
print("\n".join(righe), flush=True)
