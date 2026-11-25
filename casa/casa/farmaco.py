"""Analizzatore farmaco (D15), rete ibrida (Marco, 24/11). Tre parti separate, ognuna sostituibile dal suo modello:
1. presa: la mano prende il farmaco dal portapillole. PROVVISORIO: un polso dentro la zona "portapillole"; il
   portapillole è aperto se la zona cambia aspetto (aspetto_zona.py). Il rilevatore allenato farmaci_det (25/11:
   pillola, blister, scatola_farmaco, portapillole, scomparto) gira solo quando un polso è vicino alla zona.
2. gesto: la mano porta la pillola alla bocca entro 2 minuti. È la regola dei gesti (scheletro.py, Marco 25/11): un
   polso vicino al naso per almeno 1 s, e una pillola, un blister o una scatola di farmaci_det vicino alla testa,
   vista almeno una volta da 2 s prima a 2 s dopo, anche con confidenza bassa (alla bocca la mano la copre). Per
   questo, durante la presa, il rilevatore guarda anche il riquadro intorno al naso. Senza i pesi di farmaci_det basta
   il polso, e un contenitore alla bocca è una bevuta. Con i pesi la confidenza dell'evento è la minore tra quella
   della persona e la più alta di un farmaco visto vicino alla persona (sul portapillole o intorno alla testa) da 2 s
   prima del gesto a quando l'evento parte (coordinatore, 25/11).
3. riconoscimento: quale farmaco, confrontando i ritagli con le foto di scatola/blister (riconoscimento_farmaci.py,
   CLIP congelato). I ritagli sono i box di scatola e blister di farmaci_det; senza, i ritagli intorno alla mano.
Se la presa è in orario, in ritardo o saltata lo decide il backend. Lo stato è per persona (id del tracker).
"""

from dataclasses import dataclass
import datetime
import uuid

import numpy as np

from contratti.configurazione import TelecameraLocale
from contratti.eventi import EventoFarmaco, Fonte, ValoriFarmaco

from casa.aspetto_zona import AreaZona, RiferimentoZona
from casa.bevuta import TIPI_DA_CLASSE, alla_bocca
from casa.percezione import Oggetto, Osservazione, Persona, foto_prova
from casa.riconoscimento_farmaci import RiconoscitoreFarmaci
from casa.scheletro import (NASO, Gesto, alza_la_massima, gesto_dopo, mano_alla_bocca, massime_delle_viste, misura,
                            oggetto_alla_testa, polsi, punto, viste_recenti)
from casa.zone import dentro_zona, zona_allargata, zone_del_tipo

SECONDI_DALLA_PRESA_ALLA_BOCCA = 120.0
RITAGLI_MASSIMI = 8              # ritagli della mano per il riconoscimento (i primi, con la mano sul farmaco)
LATO_RITAGLIO_SPALLE = 1.0       # lato del ritaglio intorno alla mano, in larghezze di spalle (una scatola ci sta)
LATO_MANO_SPALLE = 0.5           # quadrato intorno al polso che non conta per dire se il portapillole è aperto
LATO_MINIMO_RITAGLIO = 16
FATTORE_ZONA_PORTAPILLOLE = 1.5  # "vicino al portapillole": la zona allargata di un quarto per lato
CONFIDENZA_FARMACI = 0.5         # agente di allenamento (v3, 25/11); i ritagli sbagliati vanno a CLIP
LATO_MODELLO_FARMACI = 640       # come nell'allenamento
SECONDI_TRA_RILEVAMENTI = 0.2    # il rilevatore costa ~60-80 ms: al massimo 5 volte al secondo anche durante gli eventi
CLASSI_DA_RICONOSCERE = ("scatola_farmaco", "blister")  # le foto caricate nell'app sono di scatole e blister
CLASSI_DEL_GESTO = ("pillola", "blister", "scatola_farmaco")  # l'oggetto vicino alla testa (Marco, 25/11)
CONFIDENZA_FARMACI_TESTA = 0.05  # come i contenitori della bevuta: alla bocca la mano copre il farmaco
LATO_RIQUADRO_TESTA = 0.6        # lato del riquadro intorno al naso, in altezze del box: lo 0,2 della regola + oggetto
MARGINE_RITAGLIO_FARMACO = 0.1   # un po' di bordo intorno al box della scatola


class ModelloFarmaci:
    """Rilevatore allenato farmaci_det sul riquadro della zona portapillole allargata."""

    def __init__(self, percorso: str):
        from ultralytics import YOLO  # lento da importare: solo quando serve davvero

        self.modello = YOLO(percorso)

    def __deepcopy__(self, memo: dict) -> "ModelloFarmaci":
        # il modello non è stato: le copie per tornare indietro di un secondo (principale.py) lo condividono
        return self

    def oggetti_delle_classi(self, ritaglio: np.ndarray, x1: int, y1: int, classi_cercate: tuple,
                             confidenza: float) -> list[Oggetto]:
        """Oggetti delle classi cercate nel ritaglio che parte da x1, y1 (box in pixel dell'immagine intera)."""
        risultato = self.modello.predict(ritaglio, conf=confidenza, imgsz=LATO_MODELLO_FARMACI, device="cpu",
                                         verbose=False)[0]
        box_ritaglio = risultato.boxes.xyxy.cpu().numpy()
        classi = risultato.boxes.cls.int().cpu().numpy()
        confidenze = risultato.boxes.conf.cpu().numpy()
        spostamento = np.array([x1, y1, x1, y1], np.float32)
        oggetti = []
        for indice in range(len(box_ritaglio)):
            nome = risultato.names[int(classi[indice])]
            if nome in classi_cercate:
                oggetti.append(Oggetto(nome, box_ritaglio[indice] + spostamento, float(confidenze[indice])))
        return oggetti

    def scatole_e_blister(self, immagine: np.ndarray, area: AreaZona) -> list[Oggetto]:
        """Scatole e blister nel riquadro dell'area."""
        return self.oggetti_delle_classi(area.ritaglio(immagine), area.x1, area.y1, CLASSI_DA_RICONOSCERE,
                                         CONFIDENZA_FARMACI)

    def farmaci_nel_riquadro(self, immagine: np.ndarray, riquadro: np.ndarray) -> list[Oggetto]:
        """Pillole, blister e scatole nel riquadro (x1, y1, x2, y2 in pixel, tagliato ai bordi)."""
        x1 = max(int(riquadro[0]), 0)
        y1 = max(int(riquadro[1]), 0)
        x2 = min(int(riquadro[2]), immagine.shape[1])
        y2 = min(int(riquadro[3]), immagine.shape[0])
        if x2 - x1 < LATO_MINIMO_RITAGLIO or y2 - y1 < LATO_MINIMO_RITAGLIO:
            return []
        return self.oggetti_delle_classi(immagine[y1:y2, x1:x2], x1, y1, CLASSI_DEL_GESTO, CONFIDENZA_FARMACI_TESTA)


@dataclass
class Presa:
    inizio: datetime.datetime
    ultima_mano_nella_zona: datetime.datetime
    portapillole_aperto: bool
    ritagli: list            # intorno alla mano
    immagine: np.ndarray
    confidenza: float
    ritagli_farmaci: list    # box di scatole e blister del rilevatore farmaci_det
    gesto: Gesto | None                             # polso vicino al naso
    ultima_vista_farmaco: datetime.datetime | None  # ultima volta che farmaci_det ha visto un farmaco alla testa
    viste_vicine: list       # VistaOggetto dei farmaci visti vicino alla persona negli ultimi 2 s
    massime_al_gesto: dict   # classe → confidenza più alta da 2 s prima del gesto in poi


def quadrato(centro: np.ndarray, lato: float) -> np.ndarray:
    meta = lato / 2
    return np.array([centro[0] - meta, centro[1] - meta, centro[0] + meta, centro[1] + meta], np.float32)


def ritaglio_intorno(immagine: np.ndarray, centro: np.ndarray, lato: float) -> np.ndarray | None:
    box = quadrato(centro, lato)
    x1 = max(int(box[0]), 0)
    y1 = max(int(box[1]), 0)
    x2 = min(int(box[2]), immagine.shape[1])
    y2 = min(int(box[3]), immagine.shape[0])
    if x2 - x1 < LATO_MINIMO_RITAGLIO or y2 - y1 < LATO_MINIMO_RITAGLIO:
        return None
    return immagine[y1:y2, x1:x2].copy()


def ritaglio_del_box(immagine: np.ndarray, box: np.ndarray) -> np.ndarray | None:
    margine_x = MARGINE_RITAGLIO_FARMACO * float(box[2] - box[0])
    margine_y = MARGINE_RITAGLIO_FARMACO * float(box[3] - box[1])
    x1 = max(int(box[0] - margine_x), 0)
    y1 = max(int(box[1] - margine_y), 0)
    x2 = min(int(box[2] + margine_x), immagine.shape[1])
    y2 = min(int(box[3] + margine_y), immagine.shape[0])
    if x2 - x1 < LATO_MINIMO_RITAGLIO or y2 - y1 < LATO_MINIMO_RITAGLIO:
        return None
    return immagine[y1:y2, x1:x2].copy()


def sta_bevendo(persona: Persona, oggetti: list) -> bool:
    for oggetto in oggetti:
        if oggetto.classe in TIPI_DA_CLASSE and alla_bocca(persona, oggetto):
            return True
    return False


class AnalizzatoreFarmaco:
    # gli oggetti servono solo a escludere le bevute: si usano se la telecamera ha già il rilevatore per la bevuta
    usa_oggetti = False

    def __init__(self, telecamera: TelecameraLocale, riconoscitore: RiconoscitoreFarmaci | None,
                 modello_farmaci: ModelloFarmaci | None = None):
        self.telecamera_id = telecamera.id
        self.stanza = telecamera.stanza
        self.riconoscitore = riconoscitore
        self.modello_farmaci = modello_farmaci
        self.portapillole = zone_del_tipo(telecamera, "portapillole")
        self.riferimenti = {}  # id zona → RiferimentoZona ("portapillole chiuso")
        self.vicino_al_portapillole = []  # zone allargate
        for zona in self.portapillole:
            self.riferimenti[zona.id] = RiferimentoZona(zona)
            self.vicino_al_portapillole.append(zona_allargata(zona, FATTORE_ZONA_PORTAPILLOLE))
        self.ultimo_rilevamento = None
        self.prese = {}        # id traccia → Presa in corso

    def e_ora_di_rilevare(self, ora: datetime.datetime) -> bool:
        if self.ultimo_rilevamento is None:
            return True
        return (ora - self.ultimo_rilevamento).total_seconds() >= SECONDI_TRA_RILEVAMENTI

    def rileva_farmaci(self, presa: Presa, persona: Persona, immagine: np.ndarray,
                       ora: datetime.datetime) -> list[Oggetto]:
        """Il rilevatore farmaci_det sulle zone portapillole (allargate) a cui un polso della persona è vicino."""
        trovati = []
        if len(presa.ritagli_farmaci) >= RITAGLI_MASSIMI:
            return trovati
        if not self.e_ora_di_rilevare(ora):
            return trovati
        altezza = immagine.shape[0]
        larghezza = immagine.shape[1]
        for zona in self.vicino_al_portapillole:
            vicino = False
            for polso in polsi(persona):
                if dentro_zona(float(polso[0]), float(polso[1]), zona, larghezza, altezza):
                    vicino = True
            if not vicino:
                continue
            self.ultimo_rilevamento = ora
            for oggetto in self.modello_farmaci.scatole_e_blister(immagine, AreaZona(zona, immagine)):
                trovati.append(oggetto)
                ritaglio = ritaglio_del_box(immagine, oggetto.box)
                if ritaglio is not None and len(presa.ritagli_farmaci) < RITAGLI_MASSIMI:
                    presa.ritagli_farmaci.append(ritaglio)
        return trovati

    def farmaci_intorno_alla_testa(self, persona: Persona, immagine: np.ndarray,
                                   ora: datetime.datetime) -> list[Oggetto]:
        """farmaci_det sul riquadro intorno al naso: pillole, blister e scatole lì intorno."""
        naso = punto(persona, NASO)
        if naso is None or not self.e_ora_di_rilevare(ora):
            return []
        self.ultimo_rilevamento = ora
        lato = LATO_RIQUADRO_TESTA * float(persona.box[3] - persona.box[1])
        return self.modello_farmaci.farmaci_nel_riquadro(immagine, quadrato(naso, lato))

    def portapillole_aperto(self, immagine: np.ndarray, persone: list) -> bool:
        """Una zona portapillole ha cambiato aspetto (senza contare i pixel intorno ai polsi)?"""
        mani = []
        for persona in persone:
            for polso in polsi(persona):
                mani.append(quadrato(polso, LATO_MANO_SPALLE * misura(persona)))
        for zona in self.portapillole:
            if self.riferimenti[zona.id].cambiata(immagine, mani):
                return True
        return False

    def elabora(self, osservazione: Osservazione) -> list[EventoFarmaco]:
        ora = osservazione.ora
        immagine = osservazione.immagine
        altezza = immagine.shape[0]
        larghezza = immagine.shape[1]
        aperto = self.portapillole_aperto(immagine, osservazione.persone)
        mani_al_portapillole = False
        eventi = []
        for persona in osservazione.persone:
            polso_nella_zona = None
            for polso in polsi(persona):
                for zona in self.portapillole:
                    if dentro_zona(float(polso[0]), float(polso[1]), zona, larghezza, altezza):
                        polso_nella_zona = polso
            presa = self.prese.get(persona.id_traccia)
            if polso_nella_zona is not None:
                mani_al_portapillole = True
                if presa is None:
                    presa = Presa(ora, ora, False, [], immagine, 0.0, [], None, None, [], {})
                    self.prese[persona.id_traccia] = presa
                presa.ultima_mano_nella_zona = ora
                presa.confidenza = max(presa.confidenza, persona.confidenza)
                if len(presa.ritagli) < RITAGLI_MASSIMI:
                    ritaglio = ritaglio_intorno(immagine, polso_nella_zona, LATO_RITAGLIO_SPALLE * misura(persona))
                    if ritaglio is not None:
                        presa.ritagli.append(ritaglio)
            if presa is None:
                continue
            if aperto:
                presa.portapillole_aperto = True
            vicini = []  # farmaci visti adesso vicino alla persona (portapillole o testa): per la confidenza
            if self.modello_farmaci is not None:
                for oggetto in self.rileva_farmaci(presa, persona, immagine, ora):
                    vicini.append(oggetto)
                # la testa si guarda per tutta la presa: il farmaco conta anche visto fino a 2 s prima del gesto
                # (il rilevatore sul portapillole ha la precedenza: un rilevamento ogni 0,2 s in tutto)
                for oggetto in self.farmaci_intorno_alla_testa(persona, immagine, ora):
                    vicini.append(oggetto)
                    if oggetto_alla_testa(persona, oggetto.box):
                        presa.ultima_vista_farmaco = ora
            presa.viste_vicine = viste_recenti(presa.viste_vicine, vicini, ora)
            polso_al_naso = polso_nella_zona is None and mano_alla_bocca(persona)
            # senza i pesi di farmaci_det conta il solo polso, e un contenitore alla bocca è una bevuta; con i pesi
            # decide il farmaco visto (la pillola presa con l'acqua è un farmaco e una bevuta)
            if self.modello_farmaci is None and sta_bevendo(persona, osservazione.oggetti):
                polso_al_naso = False
            presa.gesto = gesto_dopo(presa.gesto, polso_al_naso, ora)
            if presa.gesto is None:
                continue
            if presa.gesto.inizio == ora:
                presa.massime_al_gesto = massime_delle_viste(presa.viste_vicine)
            else:
                for oggetto in vicini:
                    alza_la_massima(presa.massime_al_gesto, oggetto)
            if not presa.gesto.abbastanza_lungo():
                continue
            if self.modello_farmaci is None or presa.gesto.oggetto_visto_intorno(presa.ultima_vista_farmaco):
                eventi.append(self.evento(presa, ora))
                self.prese.pop(persona.id_traccia)

        dimenticate = []
        for id_traccia in self.prese:
            if (ora - self.prese[id_traccia].ultima_mano_nella_zona).total_seconds() > SECONDI_DALLA_PRESA_ALLA_BOCCA:
                dimenticate.append(id_traccia)
        for id_traccia in dimenticate:
            self.prese.pop(id_traccia)

        # riferimento "portapillole chiuso": quando nessuna mano ci sta sopra e nessuno sta prendendo un farmaco
        if not mani_al_portapillole and len(self.prese) == 0:
            for zona in self.portapillole:
                self.riferimenti[zona.id].aggiorna(immagine)
        return eventi

    def fine(self) -> list[EventoFarmaco]:
        # senza la mano alla bocca non è una presa: le prese a metà a fine video non contano
        self.prese = {}
        return []

    def evento(self, presa: Presa, ora_bocca: datetime.datetime) -> EventoFarmaco:
        farmaco_id = None
        somiglianza = None
        ritagli = presa.ritagli_farmaci
        if len(ritagli) == 0:
            ritagli = presa.ritagli
        if self.riconoscitore is not None:
            riconoscimento = self.riconoscitore.riconosci(ritagli)
            if riconoscimento is not None:
                farmaco_id = riconoscimento.farmaco_id
                somiglianza = riconoscimento.somiglianza
        confidenza = presa.confidenza
        if self.modello_farmaci is not None and len(presa.massime_al_gesto) > 0:
            confidenza = min(confidenza, max(presa.massime_al_gesto.values()))
        fonte = Fonte(telecamera_id=self.telecamera_id, analizzatore="farmaco", confidenza=confidenza)
        return EventoFarmaco(
            id=str(uuid.uuid4()),
            tipo="farmaco",
            inizio=presa.inizio,
            fine=ora_bocca,
            stanza=self.stanza,
            confidenza=confidenza,
            fonti=[fonte],
            foto_prova=foto_prova(presa.immagine),
            valori=ValoriFarmaco(farmaco_id=farmaco_id, somiglianza=somiglianza,
                                 portapillole_aperto=presa.portapillole_aperto, mano_alla_bocca=True),
        )
