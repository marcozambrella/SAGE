"""Analizzatore farmaco (D15), rete ibrida (Marco, 24/11). Tre parti separate, ognuna sostituibile dal suo modello:
1. presa: la mano prende il farmaco dal portapillole. PROVVISORIO: un polso dentro la zona "portapillole"; il
   portapillole è aperto se la zona cambia aspetto (aspetto_zona.py). Poi: il rilevatore farmaci_det (scatola,
   blister, portapillole aperto/chiuso).
2. gesto: la mano porta la pillola alla bocca entro 2 minuti. PROVVISORIO: polso vicino al naso senza un contenitore
   alla bocca (quella è una bevuta). Poi: il classificatore allenato sugli scheletri.
3. riconoscimento: quale farmaco, confrontando i ritagli intorno alla mano con le foto di scatola/blister
   (riconoscimento_farmaci.py, CLIP congelato). Con farmaci_det il ritaglio sarà il box della scatola.
Se la presa è in orario, in ritardo o saltata lo decide il backend. Lo stato è per persona (id del tracker).
"""

from dataclasses import dataclass
import datetime
import uuid

import numpy as np

from contratti.configurazione import TelecameraLocale
from contratti.eventi import EventoFarmaco, Fonte, ValoriFarmaco

from casa.aspetto_zona import RiferimentoZona
from casa.bevuta import TIPI_DA_CLASSE, alla_bocca
from casa.percezione import Osservazione, Persona, foto_prova
from casa.riconoscimento_farmaci import RiconoscitoreFarmaci
from casa.scheletro import mano_alla_bocca, misura, polsi
from casa.zone import dentro_zona, zone_del_tipo

SECONDI_DALLA_PRESA_ALLA_BOCCA = 120.0
RITAGLI_MASSIMI = 8              # ritagli della mano per il riconoscimento (i primi, con la mano sul farmaco)
LATO_RITAGLIO_SPALLE = 1.0       # lato del ritaglio intorno alla mano, in larghezze di spalle (una scatola ci sta)
LATO_MANO_SPALLE = 0.5           # quadrato intorno al polso che non conta per dire se il portapillole è aperto
LATO_MINIMO_RITAGLIO = 16


@dataclass
class Presa:
    inizio: datetime.datetime
    ultima_mano_nella_zona: datetime.datetime
    portapillole_aperto: bool
    ritagli: list
    immagine: np.ndarray
    confidenza: float


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


def sta_bevendo(persona: Persona, oggetti: list) -> bool:
    for oggetto in oggetti:
        if oggetto.classe in TIPI_DA_CLASSE and alla_bocca(persona, oggetto):
            return True
    return False


class AnalizzatoreFarmaco:
    # gli oggetti servono solo a escludere le bevute: si usano se la telecamera ha già il rilevatore per la bevuta
    usa_oggetti = False

    def __init__(self, telecamera: TelecameraLocale, riconoscitore: RiconoscitoreFarmaci | None):
        self.telecamera_id = telecamera.id
        self.stanza = telecamera.stanza
        self.riconoscitore = riconoscitore
        self.portapillole = zone_del_tipo(telecamera, "portapillole")
        self.riferimenti = {}  # id zona → RiferimentoZona ("portapillole chiuso")
        for zona in self.portapillole:
            self.riferimenti[zona.id] = RiferimentoZona(zona)
        self.prese = {}        # id traccia → Presa in corso

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
                    presa = Presa(ora, ora, False, [], immagine, 0.0)
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
            if polso_nella_zona is None and mano_alla_bocca(persona) and not sta_bevendo(persona, osservazione.oggetti):
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
        if self.riconoscitore is not None:
            riconoscimento = self.riconoscitore.riconosci(presa.ritagli)
            if riconoscimento is not None:
                farmaco_id = riconoscimento.farmaco_id
                somiglianza = riconoscimento.somiglianza
        fonte = Fonte(telecamera_id=self.telecamera_id, analizzatore="farmaco", confidenza=presa.confidenza)
        return EventoFarmaco(
            id=str(uuid.uuid4()),
            tipo="farmaco",
            inizio=presa.inizio,
            fine=ora_bocca,
            stanza=self.stanza,
            confidenza=presa.confidenza,
            fonti=[fonte],
            foto_prova=foto_prova(presa.immagine),
            valori=ValoriFarmaco(farmaco_id=farmaco_id, somiglianza=somiglianza,
                                 portapillole_aperto=presa.portapillole_aperto, mano_alla_bocca=True),
        )
