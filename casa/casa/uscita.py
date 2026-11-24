"""Analizzatore uscita (D16): la persona APRE IL PORTONE di casa ed esce (Marco, 24/11).

Regola PROVVISORIA finché non arriva il modello porta aperta/chiusa: per ogni persona tracciata (id del tracker),
- è nella zona porta (con i piedi) e la porta cambia aspetto rispetto al riferimento "porta chiusa"
  (aspetto_zona.py), mentre la persona è lì o subito dopo che è sparita;
- poi la persona sparisce per SECONDI_SPARIZIONE.
Chi apre la porta e poi torna nella stanza (es. a prendere la posta) non è uscito.
Manda sempre l'evento: se l'uscita è in un orario vietato e se l'allarme è in pausa lo decide il backend.
"""

from dataclasses import dataclass
import datetime
import uuid

import numpy as np

from contratti.configurazione import TelecameraLocale
from contratti.eventi import EventoUscita, Fonte, ValoriUscita

from casa.aspetto_zona import RiferimentoZona
from casa.percezione import Osservazione, foto_prova
from casa.zone import zona_della_persona, zone_del_tipo

# Più del tempo in cui il tracker tiene in vita una traccia persa (30 fotogrammi: 6 s a 5 fotogrammi al secondo),
# così una persona coperta un attimo dalla porta e ritrovata con lo stesso id non diventa un'uscita.
SECONDI_SPARIZIONE = 8.0


@dataclass
class Traccia:
    ora: datetime.datetime            # ultima volta vista
    confidenza: float
    zona_id: str | None               # zona porta in cui aveva i piedi l'ultima volta, None se fuori dalle porte
    porta_aperta: bool                # la porta si è aperta mentre era lì (o subito dopo che è sparita)
    immagine: np.ndarray | None       # foto di prova: davanti alla porta, se possibile con la porta aperta


class AnalizzatoreUscita:
    usa_oggetti = False

    def __init__(self, telecamera: TelecameraLocale):
        self.telecamera_id = telecamera.id
        self.stanza = telecamera.stanza
        self.porte = zone_del_tipo(telecamera, "porta")
        self.riferimenti = {}  # id zona → RiferimentoZona ("porta chiusa")
        for zona in self.porte:
            self.riferimenti[zona.id] = RiferimentoZona(zona)
        self.tracce = {}       # id traccia → Traccia

    def porte_aperte(self, osservazione: Osservazione) -> list:
        """Id delle zone porta che adesso sembrano aperte."""
        box_persone = []
        for persona in osservazione.persone:
            box_persone.append(persona.box)
        aperte = []
        for zona in self.porte:
            if self.riferimenti[zona.id].cambiata(osservazione.immagine, box_persone):
                aperte.append(zona.id)
        return aperte

    def elabora(self, osservazione: Osservazione) -> list[EventoUscita]:
        ora = osservazione.ora
        altezza = osservazione.immagine.shape[0]
        larghezza = osservazione.immagine.shape[1]
        aperte = self.porte_aperte(osservazione)

        visti = []
        for persona in osservazione.persone:
            visti.append(persona.id_traccia)
            zona = zona_della_persona(persona, self.porte, larghezza, altezza)
            traccia = self.tracce.get(persona.id_traccia)
            if traccia is None:
                traccia = Traccia(ora, persona.confidenza, None, False, None)
                self.tracce[persona.id_traccia] = traccia
            traccia.ora = ora
            traccia.confidenza = persona.confidenza
            if zona is None:
                # tornata nella stanza: un'apertura di prima non conta più
                traccia.zona_id = None
                traccia.porta_aperta = False
                traccia.immagine = None
                continue
            traccia.zona_id = zona.id
            if not traccia.porta_aperta:
                traccia.immagine = osservazione.immagine
            if zona.id in aperte:
                traccia.porta_aperta = True

        eventi = []
        sparite = []
        in_attesa_davanti_alla_porta = False
        for id_traccia in self.tracce:
            if id_traccia in visti:
                continue
            traccia = self.tracce[id_traccia]
            if traccia.zona_id is not None:
                in_attesa_davanti_alla_porta = True
                # la porta si vede meglio appena la persona non la copre più
                if traccia.zona_id in aperte:
                    traccia.porta_aperta = True
            if (ora - traccia.ora).total_seconds() >= SECONDI_SPARIZIONE:
                sparite.append(id_traccia)
        for id_traccia in sparite:
            traccia = self.tracce.pop(id_traccia)
            if traccia.zona_id is not None and traccia.porta_aperta:
                eventi.append(self.evento(traccia))

        # riferimento "porta chiusa": solo quando non c'è nessuno e nessuno è appena sparito dalla porta
        if len(osservazione.persone) == 0 and not in_attesa_davanti_alla_porta:
            for zona in self.porte:
                self.riferimenti[zona.id].aggiorna(osservazione.immagine)
        return eventi

    def fine(self) -> list[EventoUscita]:
        """A fine sorgente le tracce ancora aperte non contano come uscite: non si sa se sono uscite."""
        return []

    def evento(self, traccia: Traccia) -> EventoUscita:
        fonte = Fonte(telecamera_id=self.telecamera_id, analizzatore="uscita", confidenza=traccia.confidenza)
        return EventoUscita(
            id=str(uuid.uuid4()),
            tipo="uscita",
            inizio=traccia.ora,
            stanza=self.stanza,
            confidenza=traccia.confidenza,
            fonti=[fonte],
            foto_prova=foto_prova(traccia.immagine),
            valori=ValoriUscita(zona_id=traccia.zona_id),
        )
