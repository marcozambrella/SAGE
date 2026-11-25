"""Primi segni di un evento (Marco, 25/11). Normalmente si analizzano 5 fotogrammi al secondo; appena si vede uno di
questi segni il programma torna indietro di un secondo e li analizza tutti e 10 fino alla fine dell'evento
(principale.py), così i gesti veloci (una caduta, una pillola alla bocca) hanno più fotogrammi:
- mano nella zona portapillole (farmaco);
- contenitore in mano (bevuta);
- persona nella zona porta (uscita);
- busto che si inclina in fretta (caduta).
Pasto e alzata notturna no: durano minuti, 5 al secondo bastano.
"""

from dataclasses import dataclass
import datetime

from contratti.configurazione import TelecameraLocale

from casa.bevuta import TIPI_DA_CLASSE, in_mano
from casa.percezione import Osservazione, Persona
from casa.scheletro import angolo_del_busto, polsi
from casa.zone import dentro_zona, zona_della_persona, zone_del_tipo

GRADI_IN_FRETTA = 30.0   # il busto si inclina di almeno tanto...
SECONDI_IN_FRETTA = 1.0  # ...in meno di così


@dataclass
class Busto:
    ora: datetime.datetime
    gradi: float


class RilevatoreSegni:
    """Cerca solo i segni degli analizzatori accesi su questa telecamera."""

    def __init__(self, telecamera: TelecameraLocale):
        nomi = telecamera.analizzatori
        self.portapillole = []
        if "farmaco" in nomi:
            self.portapillole = zone_del_tipo(telecamera, "portapillole")
        self.porte = []
        if "uscita" in nomi:
            self.porte = zone_del_tipo(telecamera, "porta")
        self.contenitori = "bevuta" in nomi
        self.cadute = "caduta" in nomi
        self.busti = {}  # id traccia → Busto dell'ultimo secondo

    def c_e_un_segno(self, osservazione: Osservazione) -> bool:
        altezza = osservazione.immagine.shape[0]
        larghezza = osservazione.immagine.shape[1]
        segno = False
        for persona in osservazione.persone:
            if self.mano_nel_portapillole(persona, larghezza, altezza):
                segno = True
            if zona_della_persona(persona, self.porte, larghezza, altezza) is not None:
                segno = True
            if self.contenitori and self.contenitore_in_mano(persona, osservazione.oggetti):
                segno = True
        # il busto si guarda sempre, anche se c'è già un segno: serve la storia dell'ultimo secondo
        if self.cadute and self.busto_in_fretta(osservazione):
            segno = True
        return segno

    def mano_nel_portapillole(self, persona: Persona, larghezza: int, altezza: int) -> bool:
        for polso in polsi(persona):
            for zona in self.portapillole:
                if dentro_zona(float(polso[0]), float(polso[1]), zona, larghezza, altezza):
                    return True
        return False

    def contenitore_in_mano(self, persona: Persona, oggetti: list) -> bool:
        for oggetto in oggetti:
            if oggetto.classe in TIPI_DA_CLASSE and in_mano(persona, oggetto):
                return True
        return False

    def busto_in_fretta(self, osservazione: Osservazione) -> bool:
        """Qualcuno ha il busto più inclinato di GRADI_IN_FRETTA rispetto a meno di un secondo fa."""
        ora = osservazione.ora
        recenti = {}
        for id_traccia in self.busti:
            tenuti = []
            for busto in self.busti[id_traccia]:
                if (ora - busto.ora).total_seconds() <= SECONDI_IN_FRETTA:
                    tenuti.append(busto)
            if len(tenuti) > 0:
                recenti[id_traccia] = tenuti
        self.busti = recenti
        in_fretta = False
        for persona in osservazione.persone:
            gradi = angolo_del_busto(persona)
            if gradi is None:
                continue
            storia = self.busti.get(persona.id_traccia, [])
            for busto in storia:
                if gradi - busto.gradi >= GRADI_IN_FRETTA:
                    in_fretta = True
            storia.append(Busto(ora, gradi))
            self.busti[persona.id_traccia] = storia
        return in_fretta
