"""Analizzatore pasto:
- pasto: qualcuno sta alla zona "tavolo" per almeno 2 minuti e lì c'è del cibo: un piatto o un cibo del rilevatore
  pre-allenato (ciotola, pizza, ...) oppure il cibo visto dal modello del piatto. Si guarda la zona, non l'id della
  persona: in un pasto lungo il tracker può cambiarlo;
- cibi: i cibi che il rilevatore pre-allenato riconosce nella zona (poi: il modello visione+linguaggio sulla foto
  del piatto, che è la foto di prova, D14);
- quanto ha mangiato: il modello allenato di segmentazione del cibo (25/11) dà la parte del piatto coperta di cibo.
  Gira solo all'inizio del pasto (appena a tavola si vede cibo) e alla fine (appena la persona si alza); la
  percentuale mangiata diventa una delle tre categorie del contratto. Senza pesi del modello: non misurato.
"""

from dataclasses import dataclass
import datetime
import statistics
import uuid

import numpy as np

from contratti.configurazione import TelecameraLocale
from contratti.eventi import EventoPasto, Fonte, ValoriPasto

from casa.aspetto_zona import AreaZona
from casa.percezione import CIBI_COCO, Osservazione, foto_prova
from casa.zone import dentro_zona, zone_del_tipo

CLASSI_PIATTO = ("bowl",) + CIBI_COCO
SECONDI_MINIMI_PASTO = 120.0
SECONDI_FINE_PASTO = 60.0          # nessuno a tavola da tanto: pasto finito
FRAZIONE_PERSONA_A_TAVOLA = 0.1    # parte del box della persona sopra la zona tavolo per dire che è a tavola
MISURE_PER_PIATTO = 3              # misure del piatto all'inizio e alla fine (mediana)
SECONDI_TRA_MISURE = 2.0           # tra due misure dello stesso momento del pasto
SECONDI_TRA_MISURE_SENZA_CIBO = 10.0  # a tavola ma il cibo non c'è ancora: si riguarda di rado (il modello costa)
COPERTURA_MINIMA = 0.02            # meno cibo di così: non c'è cibo
PIXEL_MINIMI_VISIBILI = 100        # meno pixel del piatto visibili di così (persone davanti): non si misura
CONFIDENZA_CIBO = 0.25
LATO_MODELLO_CIBO = 640
# la percentuale del piatto non è abbastanza precisa per un numero: tre categorie (Marco, 25/11, API.md)
SOGLIA_META = 35.0
SOGLIA_TUTTO = 75.0


class ModelloPiatto:
    """Segmentazione allenata del cibo (classe unica "cibo") sul ritaglio del tavolo o del piatto."""

    def __init__(self, percorso: str):
        from ultralytics import YOLO  # lento da importare: solo quando serve davvero

        self.modello = YOLO(percorso)

    def __deepcopy__(self, memo: dict) -> "ModelloPiatto":
        # il modello non è stato: le copie per tornare indietro di un secondo (principale.py) lo condividono
        return self

    def maschera_cibo(self, ritaglio: np.ndarray) -> np.ndarray:
        """True nei pixel del ritaglio coperti di cibo."""
        # retina_masks: maschere grandi come il ritaglio, non come l'immagine ridotta del modello
        risultato = self.modello.predict(ritaglio, conf=CONFIDENZA_CIBO, imgsz=LATO_MODELLO_CIBO, device="cpu",
                                         retina_masks=True, verbose=False)[0]
        maschera = np.zeros(ritaglio.shape[:2], bool)
        if risultato.masks is None:
            return maschera
        for una_maschera in risultato.masks.data.cpu().numpy():
            maschera = maschera | (una_maschera > 0.5)
        return maschera


def quanto_mangiato(percentuale: float) -> str:
    """Categoria del contratto: sotto il 35% meno_di_meta, dal 35 al 75% meta, oltre il 75% tutto."""
    if percentuale < SOGLIA_META:
        return "meno_di_meta"
    if percentuale <= SOGLIA_TUTTO:
        return "meta"
    return "tutto"


@dataclass
class Scena:
    """Un fotogramma del tavolo con quello che copre o delimita il piatto."""

    immagine: np.ndarray
    box_persone: list
    box_piatti: list


@dataclass
class Pasto:
    zona_id: str
    inizio: datetime.datetime
    ultima_a_tavola: datetime.datetime
    confidenza: float
    prima: list                        # coperture all'inizio, appena a tavola si vede cibo
    dopo: list                         # coperture appena la persona si alza
    ultima_misura: datetime.datetime | None
    ultima_scena: Scena | None         # l'ultimo momento a tavola: la fine, se il piatto sparisce o il video finisce
    cibi: list
    piatto_visto: bool
    immagine: np.ndarray


def area_del_box(box: np.ndarray) -> float:
    return max(float(box[2] - box[0]), 0.0) * max(float(box[3] - box[1]), 0.0)


def area_in_comune(box_a: np.ndarray, box_b: np.ndarray) -> float:
    x1 = max(float(box_a[0]), float(box_b[0]))
    y1 = max(float(box_a[1]), float(box_b[1]))
    x2 = min(float(box_a[2]), float(box_b[2]))
    y2 = min(float(box_a[3]), float(box_b[3]))
    return area_del_box(np.array([x1, y1, x2, y2]))


def copertura_cibo(area: AreaZona, scena: Scena, modello: ModelloPiatto) -> float | None:
    """Parte della zona (o dei piatti, se il rilevatore li vede) coperta di cibo, senza i pixel coperti dalle persone.
    None se le persone coprono quasi tutto."""
    visibili = area.visibili(scena.box_persone)
    if len(scena.box_piatti) > 0:
        visibili = visibili & area.dentro_i_box(scena.box_piatti)
    quanti_visibili = int(visibili.sum())
    if quanti_visibili < PIXEL_MINIMI_VISIBILI:
        return None
    cibo = modello.maschera_cibo(area.ritaglio(scena.immagine))
    return int((cibo & visibili).sum()) / quanti_visibili


def e_ora_di_misurare(pasto: Pasto, ora: datetime.datetime, secondi_tra_misure: float) -> bool:
    if pasto.ultima_misura is None:
        return True
    return (ora - pasto.ultima_misura).total_seconds() >= secondi_tra_misure


class AnalizzatorePasto:
    usa_oggetti = True

    def __init__(self, telecamera: TelecameraLocale, modello_piatto: ModelloPiatto | None = None):
        self.telecamera_id = telecamera.id
        self.stanza = telecamera.stanza
        self.modello_piatto = modello_piatto
        self.tavoli = zone_del_tipo(telecamera, "tavolo")
        self.aree = {}              # id zona → AreaZona (al primo fotogramma)
        self.pasti = {}             # id zona → Pasto in corso

    def elabora(self, osservazione: Osservazione) -> list[EventoPasto]:
        eventi = []
        for zona in self.tavoli:
            evento = self.elabora_tavolo(zona, osservazione)
            if evento is not None:
                eventi.append(evento)
        return eventi

    def misura(self, zona_id: str, scena: Scena) -> float | None:
        if self.modello_piatto is None:
            return None
        return copertura_cibo(self.aree[zona_id], scena, self.modello_piatto)

    def elabora_tavolo(self, zona, osservazione: Osservazione) -> EventoPasto | None:
        ora = osservazione.ora
        immagine = osservazione.immagine
        altezza = immagine.shape[0]
        larghezza = immagine.shape[1]
        if zona.id not in self.aree:
            self.aree[zona.id] = AreaZona(zona, immagine)
        area = self.aree[zona.id]
        riquadro_zona = np.array([area.x1, area.y1, area.x2, area.y2], np.float32)

        box_persone = []
        a_tavola = None  # la persona più sicura a tavola
        for persona in osservazione.persone:
            box_persone.append(persona.box)
            sopra = area_in_comune(persona.box, riquadro_zona)
            if sopra >= FRAZIONE_PERSONA_A_TAVOLA * area_del_box(persona.box):
                if a_tavola is None or persona.confidenza > a_tavola.confidenza:
                    a_tavola = persona
        box_piatti = []
        oggetti_sul_tavolo = []
        for oggetto in osservazione.oggetti:
            centro_x = float(oggetto.box[0] + oggetto.box[2]) / 2
            centro_y = float(oggetto.box[1] + oggetto.box[3]) / 2
            if oggetto.classe in CLASSI_PIATTO and dentro_zona(centro_x, centro_y, zona, larghezza, altezza):
                oggetti_sul_tavolo.append(oggetto)
                if oggetto.classe == "bowl":
                    box_piatti.append(oggetto.box)
        scena = Scena(immagine, box_persone, box_piatti)

        pasto = self.pasti.get(zona.id)
        if a_tavola is not None:
            if pasto is None:
                pasto = Pasto(zona.id, ora, ora, 0.0, [], [], None, None, [], False, immagine)
                self.pasti[zona.id] = pasto
            pasto.ultima_a_tavola = ora
            pasto.ultima_scena = scena
            pasto.confidenza = max(pasto.confidenza, a_tavola.confidenza)
            pasto.dopo = []  # si è rimessa a tavola: il "dopo" ricomincia quando si alza
            for oggetto in oggetti_sul_tavolo:
                pasto.piatto_visto = True
                if oggetto.classe in CIBI_COCO and oggetto.classe not in pasto.cibi:
                    pasto.cibi.append(oggetto.classe)
            # inizio del pasto: si riguarda finché si vede cibo, poi qualche misura ravvicinata
            attesa = SECONDI_TRA_MISURE_SENZA_CIBO
            if len(pasto.prima) > 0:
                attesa = SECONDI_TRA_MISURE
            if len(pasto.prima) < MISURE_PER_PIATTO and e_ora_di_misurare(pasto, ora, attesa):
                copertura = self.misura(zona.id, scena)
                pasto.ultima_misura = ora
                if copertura is not None and copertura >= COPERTURA_MINIMA:
                    pasto.prima.append(copertura)
                    pasto.piatto_visto = True  # il cibo lo vede il modello anche se il rilevatore COCO no
            return None

        if pasto is None:
            return None
        # fine del pasto: qualche misura appena la persona si è alzata
        if len(pasto.dopo) < MISURE_PER_PIATTO and e_ora_di_misurare(pasto, ora, SECONDI_TRA_MISURE):
            copertura = self.misura(zona.id, scena)
            pasto.ultima_misura = ora
            if copertura is not None:
                pasto.dopo.append(copertura)
        if (ora - pasto.ultima_a_tavola).total_seconds() < SECONDI_FINE_PASTO:
            return None
        self.pasti.pop(zona.id)
        return self.evento_se_pasto(pasto)

    def fine(self) -> list[EventoPasto]:
        eventi = []
        for id_zona in self.pasti:
            evento = self.evento_se_pasto(self.pasti[id_zona])
            if evento is not None:
                eventi.append(evento)
        self.pasti = {}
        return eventi

    def cibo_alla_fine(self, pasto: Pasto) -> float | None:
        """Copertura alla fine: dopo che si è alzata; se lì il piatto non si vede più (portato via con sé) o il video
        finisce a tavola, l'ultimo momento a tavola."""
        cibo_dopo = None
        if len(pasto.dopo) > 0:
            cibo_dopo = statistics.median(pasto.dopo)
        if cibo_dopo is not None and cibo_dopo >= COPERTURA_MINIMA:
            return cibo_dopo
        if pasto.ultima_scena is None:
            return cibo_dopo
        cibo_a_tavola = self.misura(pasto.zona_id, pasto.ultima_scena)
        if cibo_a_tavola is None:
            return cibo_dopo
        return cibo_a_tavola

    def evento_se_pasto(self, pasto: Pasto) -> EventoPasto | None:
        durata = (pasto.ultima_a_tavola - pasto.inizio).total_seconds()
        if durata < SECONDI_MINIMI_PASTO or not pasto.piatto_visto:
            return None  # seduta senza piatto o troppo poco: non è un pasto
        confidenza = pasto.confidenza
        categoria = None
        cibo_dopo = None
        if len(pasto.prima) > 0:
            cibo_dopo = self.cibo_alla_fine(pasto)
        if cibo_dopo is not None:
            cibo_prima = statistics.median(pasto.prima)
            percentuale = (cibo_prima - cibo_dopo) / cibo_prima * 100
            categoria = quanto_mangiato(percentuale)
        else:
            confidenza = confidenza / 2  # pasto visto, quanto ha mangiato non si misura
            print("telecamera " + self.telecamera_id + ": pasto visto, quanto ha mangiato non misurato")
        fonte = Fonte(telecamera_id=self.telecamera_id, analizzatore="pasto", confidenza=confidenza)
        return EventoPasto(
            id=str(uuid.uuid4()),
            tipo="pasto",
            inizio=pasto.inizio,
            fine=pasto.ultima_a_tavola,
            stanza=self.stanza,
            confidenza=confidenza,
            fonti=[fonte],
            foto_prova=foto_prova(pasto.immagine),
            valori=ValoriPasto(cibi=pasto.cibi, quanto_mangiato=categoria),
        )
