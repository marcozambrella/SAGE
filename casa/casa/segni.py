"""Primi segni di un evento (Marco, 25/11). Normalmente si analizzano 5 fotogrammi al secondo; appena si vede uno di
questi segni il programma torna indietro di un secondo e li analizza tutti e 10 fino alla fine dell'evento
(principale.py), così i gesti veloci (una pillola alla bocca, un sorso) hanno più fotogrammi:
- mano nella zona portapillole (farmaco);
- contenitore in mano (bevuta);
- persona nella zona porta (uscita).
Cadute, pasto e alzata notturna no: chi è caduto resta a terra e si vede lo stesso (Marco, 25/11), pasto e alzata
durano minuti.
"""

from contratti.configurazione import TelecameraLocale

from casa.bevuta import TIPI_DA_CLASSE, in_mano
from casa.percezione import Osservazione, Persona
from casa.scheletro import polsi
from casa.uscita import FATTORE_ZONA_PORTA
from casa.zone import dentro_zona, zona_allargata, zona_della_persona, zone_del_tipo

class RilevatoreSegni:
    """Cerca solo i segni degli analizzatori accesi su questa telecamera."""

    def __init__(self, telecamera: TelecameraLocale):
        nomi = telecamera.analizzatori
        self.portapillole = []
        if "farmaco" in nomi:
            self.portapillole = zone_del_tipo(telecamera, "portapillole")
        self.porte = []
        if "uscita" in nomi:
            for zona in zone_del_tipo(telecamera, "porta"):
                self.porte.append(zona_allargata(zona, FATTORE_ZONA_PORTA))  # come l'analizzatore dell'uscita
        self.contenitori = "bevuta" in nomi

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
