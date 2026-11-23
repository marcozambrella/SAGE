"""Analizzatore uscita (D16): la persona passa dalla zona porta verso fuori.

Manda sempre l'evento: se l'uscita è in un orario vietato, e se l'allarme è in pausa, lo decide il backend.

Regola PROVVISORIA per "verso fuori" (da far scegliere a Marco): una traccia vista l'ultima volta con i piedi nella
zona porta e poi sparita per SECONDI_SPARIZIONE è uscita. Non serve nessun cambio ai contratti.
"""

from dataclasses import dataclass
import datetime
import uuid

import numpy as np

from contratti.configurazione import TelecameraLocale
from contratti.eventi import EventoUscita, Fonte, ValoriUscita

from casa.percezione import Osservazione, foto_prova
from casa.zone import zona_della_persona, zone_del_tipo

# Più del tempo in cui il tracker tiene in vita una traccia persa (30 fotogrammi: 6 s a 5 fotogrammi al secondo),
# così una persona coperta un attimo dalla porta e ritrovata con lo stesso id non diventa un'uscita. Provvisorio.
SECONDI_SPARIZIONE = 8.0


@dataclass
class UltimaVista:
    ora: datetime.datetime
    confidenza: float
    zona_id: str | None              # zona porta in cui erano i piedi, None se fuori dalle porte
    immagine: np.ndarray | None      # fotogramma se era nella zona porta: diventa la foto di prova


class AnalizzatoreUscita:
    usa_oggetti = False

    def __init__(self, telecamera: TelecameraLocale):
        self.telecamera_id = telecamera.id
        self.stanza = telecamera.stanza
        self.porte = zone_del_tipo(telecamera, "porta")
        self.ultime_viste = {}  # id traccia → UltimaVista

    def elabora(self, osservazione: Osservazione) -> list[EventoUscita]:
        altezza = osservazione.immagine.shape[0]
        larghezza = osservazione.immagine.shape[1]
        for persona in osservazione.persone:
            zona = zona_della_persona(persona, self.porte, larghezza, altezza)
            if zona is None:
                vista = UltimaVista(osservazione.ora, persona.confidenza, None, None)
            else:
                vista = UltimaVista(osservazione.ora, persona.confidenza, zona.id, osservazione.immagine)
            self.ultime_viste[persona.id_traccia] = vista

        sparite = []
        for id_traccia in self.ultime_viste:
            vista = self.ultime_viste[id_traccia]
            secondi_senza_vederla = (osservazione.ora - vista.ora).total_seconds()
            if secondi_senza_vederla >= SECONDI_SPARIZIONE:
                sparite.append(id_traccia)

        eventi = []
        for id_traccia in sparite:
            vista = self.ultime_viste.pop(id_traccia)
            if vista.zona_id is not None:
                eventi.append(self.evento(vista))
        return eventi

    def fine(self) -> list[EventoUscita]:
        """A fine sorgente le tracce ancora visibili non contano come uscite: non si sa se sono uscite."""
        return []

    def evento(self, vista: UltimaVista) -> EventoUscita:
        fonte = Fonte(telecamera_id=self.telecamera_id, analizzatore="uscita", confidenza=vista.confidenza)
        return EventoUscita(
            id=str(uuid.uuid4()),
            tipo="uscita",
            inizio=vista.ora,
            stanza=self.stanza,
            confidenza=vista.confidenza,
            fonti=[fonte],
            foto_prova=foto_prova(vista.immagine),
            valori=ValoriUscita(zona_id=vista.zona_id),
        )
