"""Analizzatore pasto, regole PROVVISORIE finché non arrivano la segmentazione del cibo (percentuale del piatto) e il
modello visione+linguaggio (che cibo c'è, una foto a pasto, D14):
- pasto: qualcuno sta alla zona "tavolo" per almeno 2 minuti e lì si vede un piatto o del cibo (ciotola o cibi del
  rilevatore pre-allenato). Si guarda la zona, non l'id della persona: in un pasto lungo il tracker può cambiarlo;
- cibi: i cibi che il rilevatore pre-allenato riconosce nella zona (poi: il modello visione+linguaggio sulla foto
  del piatto, che è la foto di prova);
- percentuale mangiata: quanta parte del piatto è coperta di cibo (pixel colorati: il cibo di solito lo è, il
  piatto no), prima (tavolo senza nessuno, o l'inizio del pasto) e dopo (appena la persona si alza).
"""

from dataclasses import dataclass
import datetime
import statistics
import uuid

import cv2
import numpy as np

from contratti.configurazione import TelecameraLocale
from contratti.eventi import EventoPasto, Fonte, ValoriPasto

from casa.aspetto_zona import AreaZona
from casa.percezione import CIBI_COCO, Osservazione, foto_prova
from casa.zone import dentro_zona, zone_del_tipo

CLASSI_PIATTO = ("bowl",) + CIBI_COCO
SATURAZIONE_CIBO = 60              # pixel con almeno tanta saturazione (0-255) contano come cibo
LUMINOSITA_MINIMA_CIBO = 40        # le ombre scure non sono cibo
SECONDI_MINIMI_PASTO = 120.0
SECONDI_FINE_PASTO = 60.0          # nessuno a tavola da tanto: pasto finito
FRAZIONE_PERSONA_A_TAVOLA = 0.1    # parte del box della persona sopra la zona tavolo per dire che è a tavola
MISURE_PER_PIATTO = 5
COPERTURA_MINIMA = 0.02            # meno cibo di così all'inizio: la percentuale non si misura
PIXEL_MINIMI_VISIBILI = 100        # meno pixel del piatto visibili di così (persone davanti): non si misura
# la percentuale del piatto non è abbastanza precisa per un numero: tre categorie (Marco, 25/11, API.md)
SOGLIA_META = 35.0
SOGLIA_TUTTO = 75.0


def quanto_mangiato(percentuale: float) -> str:
    """Categoria del contratto: sotto il 35% meno_di_meta, dal 35 al 75% meta, oltre il 75% tutto."""
    if percentuale < SOGLIA_META:
        return "meno_di_meta"
    if percentuale <= SOGLIA_TUTTO:
        return "meta"
    return "tutto"


@dataclass
class Pasto:
    inizio: datetime.datetime
    ultima_a_tavola: datetime.datetime
    confidenza: float
    prima: list            # coperture del piatto prima del pasto (tavolo senza nessuno)
    durante: list
    dopo: list
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


def copertura_cibo(area: AreaZona, immagine: np.ndarray, box_persone: list, box_piatti: list) -> float | None:
    """Parte della zona (o dei piatti, se il rilevatore li vede) coperta di cibo, senza i pixel coperti dalle persone.
    None se le persone coprono quasi tutto."""
    visibili = area.visibili(box_persone)
    if len(box_piatti) > 0:
        visibili = visibili & area.dentro_i_box(box_piatti)
    quanti_visibili = int(visibili.sum())
    if quanti_visibili < PIXEL_MINIMI_VISIBILI:
        return None
    hsv = cv2.cvtColor(area.ritaglio(immagine), cv2.COLOR_BGR2HSV)
    cibo = (hsv[:, :, 1] >= SATURAZIONE_CIBO) & (hsv[:, :, 2] >= LUMINOSITA_MINIMA_CIBO)
    return int((cibo & visibili).sum()) / quanti_visibili


class AnalizzatorePasto:
    usa_oggetti = True

    def __init__(self, telecamera: TelecameraLocale):
        self.telecamera_id = telecamera.id
        self.stanza = telecamera.stanza
        self.tavoli = zone_del_tipo(telecamera, "tavolo")
        self.aree = {}              # id zona → AreaZona (al primo fotogramma)
        self.coperture_libere = {}  # id zona → ultime coperture con nessuno a tavola
        self.pasti = {}             # id zona → Pasto in corso

    def elabora(self, osservazione: Osservazione) -> list[EventoPasto]:
        eventi = []
        for zona in self.tavoli:
            evento = self.elabora_tavolo(zona, osservazione)
            if evento is not None:
                eventi.append(evento)
        return eventi

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
        copertura = copertura_cibo(area, immagine, box_persone, box_piatti)

        pasto = self.pasti.get(zona.id)
        if a_tavola is not None:
            if pasto is None:
                prima = list(self.coperture_libere.get(zona.id, []))
                pasto = Pasto(ora, ora, 0.0, prima, [], [], [], False, immagine)
                self.pasti[zona.id] = pasto
            pasto.ultima_a_tavola = ora
            pasto.confidenza = max(pasto.confidenza, a_tavola.confidenza)
            pasto.dopo = []  # si è rimessa a tavola: il "dopo" ricomincia quando si alza
            if copertura is not None:
                pasto.durante.append(copertura)
            for oggetto in oggetti_sul_tavolo:
                pasto.piatto_visto = True
                if oggetto.classe in CIBI_COCO and oggetto.classe not in pasto.cibi:
                    pasto.cibi.append(oggetto.classe)
            return None

        if copertura is not None:
            libere = self.coperture_libere.get(zona.id, [])
            libere.append(copertura)
            self.coperture_libere[zona.id] = libere[-MISURE_PER_PIATTO:]
            if pasto is not None and len(pasto.dopo) < MISURE_PER_PIATTO:
                pasto.dopo.append(copertura)
        if pasto is None:
            return None
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

    def evento_se_pasto(self, pasto: Pasto) -> EventoPasto | None:
        durata = (pasto.ultima_a_tavola - pasto.inizio).total_seconds()
        if durata < SECONDI_MINIMI_PASTO or not pasto.piatto_visto:
            return None  # seduta senza piatto o troppo poco: non è un pasto
        prima = pasto.prima
        if len(prima) == 0:
            prima = pasto.durante[:MISURE_PER_PIATTO]
        dopo = pasto.dopo
        if len(dopo) == 0:
            dopo = pasto.durante[-MISURE_PER_PIATTO:]
        confidenza = pasto.confidenza
        categoria = None
        if len(prima) > 0 and len(dopo) > 0 and statistics.median(prima) >= COPERTURA_MINIMA:
            cibo_prima = statistics.median(prima)
            cibo_dopo = statistics.median(dopo)
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
