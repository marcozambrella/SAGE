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
Con --solo-casa valuta solo il codice di casa com'è, con soglia e finestre di principale.py (dopo che casa ha messo
le regole in caduta.py). Il modo normale (scelta di regole e isteresi) va fatto girare con casa a67435c: da ad1a952
l'isteresi è già dentro caduta.py e qui si aggiungerebbe una seconda volta (con ad1a952 --solo-casa dà gli stessi
numeri di "isteresi + regole scelte", 25/11).
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

import casa.caduta  # noqa: E402
from casa.caduta import (RAPPORTO_A_TERRA_SENZA_BUSTO, SECONDI_A_TERRA, SECONDI_A_TERRA_SENZA_CONFERMA,  # noqa: E402
                         SECONDI_CADUTA_RAPIDA, AnalizzatoreCaduta, rapporto_del_box)
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
# Isteresi di "a terra" (coordinatore, 25/11): si esce solo dopo N secondi di fila chiaramente in piedi. A pari
# risultati vince la prima provata: 1 s con le soglie di in_piedi di casa (30°, box più alto che largo), perché un
# fotogramma solo "in piedi" può essere un errore della posa
ISTERESI_PREFERITA = (1, 30, 1.0)
SECONDI_USCITA = [0, 1, 2, 3]
ANGOLI_USCITA = [30, 20]
RAPPORTI_USCITA = [1.0, 0.8]
# Solo per Marco (non da mettere a casa): un classificatore molto sicuro che fa partire l'allarme senza la geometria.
# Conferme della stessa persona a meno di SECONDI_STESSO_ALLARME dalla precedente sono lo stesso allarme
SOLO_CLASSIFICATORE = [(0.98, 3), (0.99, 3), (0.99, 4)]
SECONDI_STESSO_ALLARME = 10.0
# --allarme-classificatore (Marco, 25/11 sera: sì all'allarme dal solo classificatore molto sicuro): soglie e finestre
# di fila provate sulla validazione, dalla più severa alla più larga (a pari risultato vince la più severa)
SOGLIE_SICURE = [0.995, 0.99, 0.98, 0.97]
FINESTRE_SICURE = [6, 5, 4, 3, 2]
ALLARME_CLASSIFICATORE = "--allarme-classificatore" in sys.argv
A_TERRA_DI_CASA = casa.caduta.a_terra


class Isteresi:
    """"A terra" con isteresi (coordinatore, 25/11): si entra con la regola di oggi (a_terra di caduta.py), si esce
    solo dopo `secondi_uscita` secondi di fila chiaramente in piedi (busto sotto `angolo_uscita` gradi e box più alto
    che largo, larghezza / altezza sotto `rapporto_uscita`; se la posa non vede il busto conta solo il box, come
    in_piedi di casa). Se la persona sparisce per un po' lo stato resta. Nella prova sostituisce caduta.a_terra (una
    nuova per ogni video); a casa andrà dentro caduta.py."""

    def __init__(self, secondi_uscita: float, angolo_uscita: float, rapporto_uscita: float):
        self.secondi_uscita = secondi_uscita
        self.angolo_uscita = angolo_uscita
        self.rapporto_uscita = rapporto_uscita
        self.a_terra_per_traccia = {}
        self.in_piedi_da = {}
        self.secondi = 0.0   # il momento del fotogramma, lo scrive AnalizzatoreRegistrato

    def chiaramente_in_piedi(self, persona: Persona) -> bool:
        angolo = angolo_del_busto(persona)
        rapporto = rapporto_del_box(persona)
        if angolo is None:
            return rapporto <= 1 / RAPPORTO_A_TERRA_SENZA_BUSTO
        return angolo <= self.angolo_uscita and rapporto < self.rapporto_uscita

    def a_terra(self, persona: Persona) -> bool:
        traccia = persona.id_traccia
        if not self.a_terra_per_traccia.get(traccia, False):
            if A_TERRA_DI_CASA(persona):
                self.a_terra_per_traccia[traccia] = True
                self.in_piedi_da[traccia] = None
                return True
            return False
        if not self.chiaramente_in_piedi(persona):
            self.in_piedi_da[traccia] = None
            return True
        if self.in_piedi_da[traccia] is None:
            self.in_piedi_da[traccia] = self.secondi
        if self.secondi - self.in_piedi_da[traccia] >= self.secondi_uscita:
            self.a_terra_per_traccia[traccia] = False
            return False
        return True


class AnalizzatoreRegistrato(AnalizzatoreCaduta):
    """L'analizzatore di casa che non manda allarmi: registra le probabilità del classificatore, gli scheletri e i
    fotogrammi in cui casa chiederebbe la conferma (a terra da almeno SECONDI_A_TERRA, caduta rapida)."""

    def __init__(self, telecamera: TelecameraLocale, classificatore: ClassificatoreCadute, isteresi):
        super().__init__(telecamera, classificatore)
        self.isteresi = isteresi
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
        if self.isteresi is not None:
            self.isteresi.secondi = secondi
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

    def confermata(self, stato, persona: Persona, secondi_a_terra: float) -> bool:
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


def registra_video(percorso: Path, classificatore: ClassificatoreCadute, isteresi_scelta) -> dict:
    """isteresi_scelta: None (casa di oggi) o (secondi, angolo, rapporto) di uscita."""
    isteresi = None
    casa.caduta.a_terra = A_TERRA_DI_CASA
    if isteresi_scelta is not None:
        isteresi = Isteresi(isteresi_scelta[0], isteresi_scelta[1], isteresi_scelta[2])
        casa.caduta.a_terra = isteresi.a_terra
    analizzatore = AnalizzatoreRegistrato(TELECAMERA, classificatore, isteresi)
    osservazioni = osservazioni_del_video(percorso)
    for osservazione in osservazioni:
        analizzatore.elabora(osservazione)
    casa.caduta.a_terra = A_TERRA_DI_CASA
    altezza_immagine = osservazioni[0].immagine.shape[0]
    # i momenti in cui le regole di oggi vedono qualcuno a terra o in piedi, per dividere le cadute perse per causa
    a_terra_visti = []
    in_piedi_visti = []
    for osservazione in osservazioni:
        for persona in osservazione.persone:
            secondi = (osservazione.ora - INIZIO_VIDEO).total_seconds()
            if A_TERRA_DI_CASA(persona):
                a_terra_visti.append((secondi, persona.id_traccia))
            if casa.caduta.in_piedi(persona):
                in_piedi_visti.append((secondi, persona.id_traccia))
    candidati = []
    for id_traccia, numero_stato, secondi, a_terra_da, secondi_a_terra in analizzatore.candidati:
        misure = misure_del_candidato(analizzatore.storia[id_traccia], secondi, a_terra_da, secondi_a_terra,
                                      altezza_immagine)
        candidati.append({"stato": numero_stato, "secondi": secondi, "a_terra_da": a_terra_da,
                          "secondi_a_terra": secondi_a_terra, "misure": misure})
    return {"probabilita": analizzatore.probabilita, "candidati": candidati, "a_terra_visti": a_terra_visti,
            "in_piedi_visti": in_piedi_visti}


def decidi_allarmi(registro: dict, soglia: float, finestre_di_fila: int, regole: dict) -> list:
    """Secondi degli allarmi con le condizioni di caduta.py (vedi allarmi_con_stato)."""
    allarmi = []
    for secondi, numero_stato in allarmi_con_stato(registro, soglia, finestre_di_fila, regole):
        allarmi.append(secondi)
    return allarmi


def allarmi_con_stato(registro: dict, soglia: float, finestre_di_fila: int, regole: dict) -> list:
    """(secondi, numero dello stato) degli allarmi con le condizioni di caduta.py: il primo fotogramma di ogni volta a
    terra in cui c'è la conferma del classificatore (k finestre di fila sopra la soglia, da SECONDI_CADUTA_RAPIDA prima
    di finire a terra in poi) e le regole, oppure 30 s a terra."""
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
            allarmi.append((candidato["secondi"], candidato["stato"]))
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


def causa_della_persa(registro: dict, inizio: float, fine: float, durata: float, scelta: dict) -> str:
    """Perché una caduta non ha avuto l'allarme, nell'ordine in cui casa decide."""
    if durata - inizio < SECONDI_VALUTABILE:
        return "clip finita prima che casa possa decidere"
    # prima volta a terra di ogni traccia nella caduta
    prima_a_terra = {}
    for secondi, traccia in registro["a_terra_visti"]:
        if inizio - SECONDI_PRIMA <= secondi <= fine + SECONDI_DOPO and traccia not in prima_a_terra:
            prima_a_terra[traccia] = secondi
    if len(prima_a_terra) == 0:
        return "mai a terra per la geometria"
    if durata - min(prima_a_terra.values()) < SECONDI_A_TERRA:
        return "clip finita prima che casa possa decidere"
    candidati = []
    for candidato in registro["candidati"]:
        if inizio - SECONDI_PRIMA <= candidato["secondi"] <= fine + SECONDI_DOPO:
            candidati.append(candidato)
    if len(candidati) == 0:
        in_piedi_qualcuno = False
        in_piedi_stessa_traccia = False
        for secondi, traccia in registro["in_piedi_visti"]:
            for traccia_a_terra in prima_a_terra:
                momento = prima_a_terra[traccia_a_terra]
                if momento - SECONDI_CADUTA_RAPIDA <= secondi <= momento:
                    in_piedi_qualcuno = True
                    if traccia == traccia_a_terra:
                        in_piedi_stessa_traccia = True
        if not in_piedi_qualcuno:
            return "non in piedi nei 3 s prima di finire a terra"
        if not in_piedi_stessa_traccia:
            return "il tracker cambia id nella caduta (in piedi era un'altra traccia)"
        return "a terra che va e viene"
    for allarme in decidi_allarmi(registro, scelta["soglia"], scelta["finestre"], {}):
        if inizio - SECONDI_PRIMA <= allarme <= fine + SECONDI_DOPO:
            return "tolta dalle regole"
    return "il classificatore non conferma"


def cause_delle_perse(registri: dict, video: list, scelta: dict) -> dict:
    cause = {}
    for identificativo in video:
        voce = etichette[identificativo]
        durata = voce["numero_frame"] / voce["fps"]
        registro = registri[identificativo]
        allarmi = decidi_allarmi(registro, scelta["soglia"], scelta["finestre"], scelta["regole"])
        for inizio, fine in voce["eventi"]:
            presa = False
            for allarme in allarmi:
                if inizio - SECONDI_PRIMA <= allarme <= fine + SECONDI_DOPO:
                    presa = True
            if presa:
                continue
            causa = causa_della_persa(registro, inizio, fine, durata, scelta)
            if causa not in cause:
                cause[causa] = 0
            cause[causa] += 1
    return cause


def conferme_sicure(registro: dict, soglia: float, finestre_di_fila: int) -> list:
    """(secondi, numero dello stato) delle conferme sicure nuove: le ultime k finestre della persona tutte sopra la
    soglia, senza conferme sicure della stessa persona nei SECONDI_STESSO_ALLARME prima (una serie di conferme di fila
    è un allarme solo)."""
    recenti = {}
    ultima_conferma = {}
    conferme = []
    for numero_stato, secondi, probabilita in registro["probabilita"]:
        if numero_stato not in recenti:
            recenti[numero_stato] = []
        recenti[numero_stato].append(probabilita)
        ultime = recenti[numero_stato][-finestre_di_fila:]
        if len(ultime) < finestre_di_fila or min(ultime) < soglia:
            continue
        nuova = True
        if numero_stato in ultima_conferma:
            nuova = secondi - ultima_conferma[numero_stato] > SECONDI_STESSO_ALLARME
        if nuova:
            conferme.append((secondi, numero_stato))
        ultima_conferma[numero_stato] = secondi
    return conferme


def allarmi_con_classificatore_sicuro(registro: dict, scelta: dict, soglia_sicura: float, finestre_sicure: int) -> list:
    """Allarmi di casa più quelli del solo classificatore molto sicuro (Marco, 25/11 sera: sì). Una persona non dà
    due allarmi a meno di SECONDI_STESSO_ALLARME l'uno dall'altro: il secondo non si manda (se è quello della
    geometria, a casa la caduta conta già segnalata)."""
    eventi = allarmi_con_stato(registro, scelta["soglia"], scelta["finestre"], scelta["regole"])
    eventi = eventi + conferme_sicure(registro, soglia_sicura, finestre_sicure)
    eventi.sort()
    ultimo_allarme = {}
    allarmi = []
    for secondi, numero_stato in eventi:
        if numero_stato in ultimo_allarme and secondi - ultimo_allarme[numero_stato] <= SECONDI_STESSO_ALLARME:
            continue
        ultimo_allarme[numero_stato] = secondi
        allarmi.append(secondi)
    return allarmi


def scegli_regole(registri_val: dict, stampa: bool) -> tuple:
    """Sulla validazione, un passo alla volta: si aggiunge la regola (o si cambia soglia o finestre di fila) che toglie
    più falsi allarmi senza perdere cadute rispetto a casa senza regole (né con la n né con la s); ci si ferma quando
    nessuna toglie altro. registri_val: posa → id del video → registro."""
    base = valuta_su_val(registri_val, SOGLIA_CASA, FINESTRE_CASA, {})
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
            risultato = valuta_su_val(registri_val, prova["soglia"], prova["finestre"], prova["regole"])
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
        if stampa:
            print("    passo:", scelta, attuale, flush=True)
    return base, scelta, attuale


def valuta_su_val(registri_val: dict, soglia: float, finestre_di_fila: int, regole: dict) -> dict:
    risultato_n = metriche_del_registro(registri_val["n"], video_per_divisione["val"], soglia, finestre_di_fila,
                                        regole)
    risultato_s = metriche_del_registro(registri_val["s"], video_per_divisione["val"], soglia, finestre_di_fila,
                                        regole)
    return somma(risultato_n, risultato_s)


def registra(divisioni: list, isteresi_scelta) -> dict:
    """posa → id del video → registro, per i video delle divisioni date."""
    registri = {}
    for posa in CARTELLE_SCHELETRI:
        classificatore = ClassificatoreCadute(str(CARTELLA_CASA / PESI[posa]), SOGLIA_CASA, FINESTRE_CASA)
        registri[posa] = {}
        for divisione in divisioni:
            for identificativo in video_per_divisione[divisione]:
                percorso = CARTELLE_SCHELETRI[posa] / (identificativo + ".npz")
                registri[posa][identificativo] = registra_video(percorso, classificatore, isteresi_scelta)
    return registri


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

if ALLARME_CLASSIFICATORE:
    # sul codice di casa com'è (755c443: regole, isteresi ed eredità dentro caduta.py): il registro senza isteresi in
    # più riproduce casa; si sceglie sulla validazione la conferma sicura che prende più cadute senza più falsi allarmi
    from casa.principale import PESI_CADUTE
    pesi_della_posa = {"n": PESI_CADUTE["pesi/yolo26n-pose.pt"], "s": PESI_CADUTE["pesi/yolo26s-pose.pt"]}
    regole_di_casa = {"angolo": casa.caduta.ANGOLO_A_TERRA_CONFERMATA}
    registri = registra(["val", "test"], None)
    for posa in ["s", "n"]:
        pesi = pesi_della_posa[posa]
        scelta_casa = {"soglia": pesi.soglia, "finestre": pesi.finestre_di_fila, "regole": regole_di_casa}
        classificatore = ClassificatoreCadute(str(CARTELLA_CASA / pesi.percorso), pesi.soglia, pesi.finestre_di_fila)
        diversi = 0
        for divisione in ["val", "test"]:
            for identificativo in video_per_divisione[divisione]:
                veri = allarmi_di_casa(CARTELLE_SCHELETRI[posa] / (identificativo + ".npz"), classificatore)
                dal_registro = decidi_allarmi(registri[posa][identificativo], scelta_casa["soglia"],
                                              scelta_casa["finestre"], scelta_casa["regole"])
                if veri != dal_registro:
                    diversi += 1
        print(f"posa {posa}: {diversi} video con allarmi diversi dal codice di casa", flush=True)
        base = {}
        for divisione in ["val", "test"]:
            base[divisione] = metriche_del_registro(registri[posa], video_per_divisione[divisione],
                                                    scelta_casa["soglia"], scelta_casa["finestre"],
                                                    scelta_casa["regole"])
            print(f"posa {posa}, {divisione}, casa com'è:", base[divisione], flush=True)
        migliore = None
        for soglia_sicura in SOGLIE_SICURE:
            for finestre_sicure in FINESTRE_SICURE:
                allarmi_per_video = {}
                for identificativo in video_per_divisione["val"]:
                    allarmi_per_video[identificativo] = allarmi_con_classificatore_sicuro(
                        registri[posa][identificativo], scelta_casa, soglia_sicura, finestre_sicure)
                risultato = metriche(allarmi_per_video, etichette)
                print(f"  val, {finestre_sicure} finestre >= {soglia_sicura}:", risultato, flush=True)
                if risultato["falsi"] > base["val"]["falsi"] or risultato["prese"] <= base["val"]["prese"]:
                    continue
                if migliore is not None:
                    if risultato["prese"] < migliore["risultato"]["prese"]:
                        continue
                    if risultato["prese"] == migliore["risultato"]["prese"]:
                        if risultato["falsi"] >= migliore["risultato"]["falsi"]:
                            continue
                migliore = {"soglia": soglia_sicura, "finestre": finestre_sicure, "risultato": risultato}
        if migliore is None:
            print(f"posa {posa}: nessuna conferma sicura prende più cadute senza più falsi allarmi", flush=True)
            continue
        allarmi_per_video = {}
        for identificativo in video_per_divisione["test"]:
            allarmi_per_video[identificativo] = allarmi_con_classificatore_sicuro(
                registri[posa][identificativo], scelta_casa, migliore["soglia"], migliore["finestre"])
        print(f"posa {posa}: scelta sulla validazione {migliore['finestre']} finestre >= {migliore['soglia']}:",
              migliore["risultato"], flush=True)
        print(f"posa {posa}, test, con il solo classificatore sicuro:", metriche(allarmi_per_video, etichette),
              flush=True)
    sys.exit(0)

if SOLO_CASA:
    # il codice di casa com'è, senza registro: gli allarmi veri dell'analizzatore, con soglia e finestre di principale.py
    from casa.principale import PESI_CADUTE
    pesi_della_posa = {"n": PESI_CADUTE["pesi/yolo26n-pose.pt"], "s": PESI_CADUTE["pesi/yolo26s-pose.pt"]}
    for posa in CARTELLE_SCHELETRI:
        pesi = pesi_della_posa[posa]
        classificatore = ClassificatoreCadute(str(CARTELLA_CASA / pesi.percorso), pesi.soglia, pesi.finestre_di_fila)
        for divisione in ["val", "test"]:
            allarmi_per_video = {}
            for identificativo in video_per_divisione[divisione]:
                percorso = CARTELLE_SCHELETRI[posa] / (identificativo + ".npz")
                allarmi_per_video[identificativo] = allarmi_di_casa(percorso, classificatore)
            risultato = metriche(allarmi_per_video, etichette)
            print(f"casa com'è (soglia {pesi.soglia}, {pesi.finestre_di_fila} finestre), posa {posa}, {divisione}:",
                  risultato, flush=True)
    sys.exit(0)

# controllo: senza isteresi e con le regole che casa ha già (a67435c: 3 finestre di fila, busto 70°) il registro dà
# gli stessi allarmi dell'analizzatore vero di casa
solo_regole = {"soglia": SOGLIA_CASA, "finestre": 3, "regole": {"angolo": 70}}
casa_com_era = {"soglia": SOGLIA_CASA, "finestre": FINESTRE_CASA, "regole": {}}
registri_oggi = registra(["val", "test"], None)
classificatore = ClassificatoreCadute(str(CARTELLA_CASA / PESI["n"]), solo_regole["soglia"], solo_regole["finestre"])
diversi = 0
for identificativo in video_per_divisione["val"]:
    veri = allarmi_di_casa(CARTELLE_SCHELETRI["n"] / (identificativo + ".npz"), classificatore)
    dal_registro = decidi_allarmi(registri_oggi["n"][identificativo], solo_regole["soglia"], solo_regole["finestre"],
                                  solo_regole["regole"])
    if veri != dal_registro:
        diversi += 1
        print("diverso:", identificativo, veri, dal_registro, flush=True)
print(f"controllo sulla validazione (posa n): {diversi} video con allarmi diversi da casa", flush=True)

# scelta sulla validazione: per ogni isteresi (e senza) le regole con scegli_regole; vince quella che prende più
# cadute (n + s), a pari cadute quella con meno falsi allarmi, a pari ancora la più semplice (la prima dell'elenco)
prove_isteresi = [None, ISTERESI_PREFERITA]
for secondi_uscita in SECONDI_USCITA:
    for angolo_uscita in ANGOLI_USCITA:
        for rapporto_uscita in RAPPORTI_USCITA:
            if (secondi_uscita, angolo_uscita, rapporto_uscita) != ISTERESI_PREFERITA:
                prove_isteresi.append((secondi_uscita, angolo_uscita, rapporto_uscita))
migliore = None
for isteresi_scelta in prove_isteresi:
    print("isteresi (secondi, angolo, rapporto di uscita):", isteresi_scelta, flush=True)
    registri_val = registri_oggi
    if isteresi_scelta is not None:
        registri_val = registra(["val"], isteresi_scelta)
    base, scelta, risultato = scegli_regole(registri_val, True)
    print("    senza regole:", base, "| con le regole:", scelta, risultato, flush=True)
    prese = risultato["prese_n"] + risultato["prese_s"]
    if migliore is not None:
        prese_migliore = migliore["risultato"]["prese_n"] + migliore["risultato"]["prese_s"]
        if prese < prese_migliore:
            continue
        if prese == prese_migliore and risultato["falsi"] >= migliore["risultato"]["falsi"]:
            continue
    migliore = {"isteresi": isteresi_scelta, "scelta": scelta, "risultato": risultato}
print("scelta sulla validazione:", migliore, flush=True)

# numeri finali sul test: casa com'era, solo le regole del primo giro (3 finestre di fila, busto >= 70°), isteresi e
# regole scelte
registri_scelti = registra(["val", "test"], migliore["isteresi"])
varianti = [("casa com'era", registri_oggi, casa_com_era), ("3 finestre + busto 70°", registri_oggi, solo_regole),
            ("isteresi + regole scelte", registri_scelti, migliore["scelta"])]
righe = ["| posa | variante | divisione | cadute prese | prese con >= 4 s di video dopo | falsi allarmi/ora | F1 | "
         "secondi tra caduta e allarme (mediana) |", "|---|---|---|---|---|---|---|---|"]
for posa in CARTELLE_SCHELETRI:
    for divisione in ["val", "test"]:
        for nome, registri, scelta in varianti:
            risultato = metriche_del_registro(registri[posa], video_per_divisione[divisione], scelta["soglia"],
                                              scelta["finestre"], scelta["regole"])
            cause = cause_delle_perse(registri[posa], video_per_divisione[divisione], scelta)
            print(f"posa {posa}, {divisione}, {nome}:", risultato, "perse:", cause, flush=True)
            righe.append(riga(f"{posa} | {nome} | {divisione}", risultato))
print("\n".join(righe), flush=True)

# solo per Marco: il classificatore molto sicuro fa partire l'allarme anche senza la geometria
for posa in CARTELLE_SCHELETRI:
    for divisione in ["val", "test"]:
        for soglia, finestre_di_fila in SOLO_CLASSIFICATORE:
            allarmi_per_video = {}
            for identificativo in video_per_divisione[divisione]:
                registro = registri_scelti[posa][identificativo]
                allarmi_per_video[identificativo] = allarmi_con_classificatore_sicuro(registro, migliore["scelta"],
                                                                                      soglia, finestre_di_fila)
            risultato = metriche(allarmi_per_video, etichette)
            print(f"posa {posa}, {divisione}, isteresi + regole + solo classificatore {finestre_di_fila} finestre >= "
                  f"{soglia}:", risultato, flush=True)
