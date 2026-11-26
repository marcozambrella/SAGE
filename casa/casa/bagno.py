"""Visite al bagno (Marco, 25/11): nessuna telecamera dentro il bagno, la zona "bagno" è la porta del bagno vista da
fuori. Regole PROVVISORIE:
- entra: una persona tracciata con i piedi vicino alla porta del bagno (zona allargata, come per il portone) sparisce
  e non si vede più per SECONDI_SPARIZIONE; inizio = l'ultima volta vista alla porta;
- riesce: una traccia nuova compare vicino alla stessa porta (nei primi 2 s in cui si vede); fine = quando compare.
  Chi compare altrove nella stanza può essere un'altra persona e non chiude la visita;
- conta se dura almeno 30 s (meno è il tracker che perde la persona davanti alla porta) e al massimo 2 ore (di più
  è uscita da un'altra parte senza farsi vedere: niente evento). Una visita ancora aperta a fine sorgente non manda
  niente: non si sa se è ancora in bagno.
Di base è spento: gira solo sulle telecamere con l'analizzatore "bagno" (se mostrarlo lo decide la web app con
visite_bagno_attive).
"""

from dataclasses import dataclass
import datetime
import uuid

import numpy as np

from contratti.configurazione import TelecameraLocale
from contratti.eventi import EventoVisitaBagno, Fonte, ValoriVisitaBagno

from casa.percezione import Osservazione, foto_prova
from casa.uscita import FATTORE_ZONA_PORTA, SECONDI_SPARIZIONE
from casa.zone import zona_allargata, zona_della_persona, zone_del_tipo

SECONDI_PER_COMPARIRE = 2.0      # una traccia nuova "esce dal bagno" se è alla porta nei suoi primi 2 s
SECONDI_MINIMI_VISITA = 30.0
SECONDI_MASSIMI_VISITA = 2 * 3600.0


@dataclass
class TracciaVicinoAlBagno:
    prima_vista: datetime.datetime
    ora: datetime.datetime            # ultima volta vista
    zona_id: str | None               # porta del bagno dove ha i piedi, None se è lontana
    confidenza: float
    immagine: np.ndarray | None       # ultimo fotogramma alla porta


@dataclass
class Visita:
    zona_id: str
    inizio: datetime.datetime
    confidenza: float
    foto: np.ndarray


class AnalizzatoreBagno:
    usa_oggetti = False

    def __init__(self, telecamera: TelecameraLocale):
        self.telecamera_id = telecamera.id
        self.stanza = telecamera.stanza
        self.porte = []    # zone bagno allargate
        for zona in zone_del_tipo(telecamera, "bagno"):
            self.porte.append(zona_allargata(zona, FATTORE_ZONA_PORTA))
        self.tracce = {}   # id traccia → TracciaVicinoAlBagno
        self.visite = {}   # id zona → Visita in corso

    def elabora(self, osservazione: Osservazione) -> list[EventoVisitaBagno]:
        ora = osservazione.ora
        altezza = osservazione.immagine.shape[0]
        larghezza = osservazione.immagine.shape[1]
        eventi = []
        visti = []
        for persona in osservazione.persone:
            visti.append(persona.id_traccia)
            traccia = self.tracce.get(persona.id_traccia)
            if traccia is None:
                traccia = TracciaVicinoAlBagno(ora, ora, None, 0.0, None)
                self.tracce[persona.id_traccia] = traccia
            traccia.ora = ora
            traccia.confidenza = max(traccia.confidenza, persona.confidenza)
            zona = zona_della_persona(persona, self.porte, larghezza, altezza)
            if zona is None:
                traccia.zona_id = None
                traccia.immagine = None
                continue
            traccia.zona_id = zona.id
            traccia.immagine = osservazione.immagine
            visita = self.visite.get(zona.id)
            appena_comparsa = (ora - traccia.prima_vista).total_seconds() <= SECONDI_PER_COMPARIRE
            if visita is not None and appena_comparsa:
                # esce dal bagno
                self.visite.pop(zona.id)
                if (ora - visita.inizio).total_seconds() >= SECONDI_MINIMI_VISITA:
                    eventi.append(self.evento(visita, ora))

        sparite = []
        for id_traccia in self.tracce:
            if id_traccia in visti:
                continue
            if (ora - self.tracce[id_traccia].ora).total_seconds() >= SECONDI_SPARIZIONE:
                sparite.append(id_traccia)
        for id_traccia in sparite:
            traccia = self.tracce.pop(id_traccia)
            # sparita davanti alla porta del bagno: è entrata (una visita alla volta per porta)
            if traccia.zona_id is not None and traccia.zona_id not in self.visite:
                self.visite[traccia.zona_id] = Visita(traccia.zona_id, traccia.ora, traccia.confidenza,
                                                      traccia.immagine)

        troppo_lunghe = []
        for zona_id in self.visite:
            if (ora - self.visite[zona_id].inizio).total_seconds() > SECONDI_MASSIMI_VISITA:
                troppo_lunghe.append(zona_id)
        for zona_id in troppo_lunghe:
            self.visite.pop(zona_id)
        return eventi

    def fine(self) -> list[EventoVisitaBagno]:
        # una visita ancora aperta non si sa come è finita: niente evento
        self.visite = {}
        return []

    def evento(self, visita: Visita, fine: datetime.datetime) -> EventoVisitaBagno:
        fonte = Fonte(telecamera_id=self.telecamera_id, analizzatore="bagno", confidenza=visita.confidenza)
        return EventoVisitaBagno(
            id=str(uuid.uuid4()),
            tipo="visita_bagno",
            inizio=visita.inizio,
            fine=fine,
            stanza=self.stanza,
            confidenza=visita.confidenza,
            fonti=[fonte],
            foto_prova=foto_prova(visita.foto),
            valori=ValoriVisitaBagno(zona_id=visita.zona_id),
        )
