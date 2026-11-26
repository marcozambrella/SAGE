"""Inattività (Marco, 25/11): di giorno, fuori da orari_notte, nessuna persona vista da nessuna telecamera per
regole.ore_inattivita ore (di base 3). È urgente (Telegram): l'allarme parte subito, con inizio = l'ultima volta che
si è vista una persona; quando la persona ricompare parte un secondo evento grezzo con la fine.

Le ore si contano solo di giorno: chi è stato visto l'ultima volta la sera conta dalla fine della notte (se alle 10
nessuno si è ancora visto, con la notte fino alle 7, parte l'allarme). Un solo analizzatore per tutta la casa: il
ciclo principale gli passa le osservazioni di tutte le telecamere (c'è se almeno una telecamera ha "inattivita").
"""

import datetime
import uuid

import numpy as np

from contratti.configurazione import FasciaOraria, RegoleAllarmi
from contratti.eventi import EventoInattivita, Fonte, ValoriInattivita

from casa.configurazione import dentro_fascia, ora_del_testo
from casa.percezione import Osservazione, foto_prova

# l'assenza di persone davanti alle telecamere è un fatto, non una stima di un modello
CONFIDENZA_INATTIVITA = 1.0


def fine_della_notte(ora: datetime.datetime, notte: FasciaOraria) -> datetime.datetime:
    """L'ultima fine della notte (orari_notte.alle) prima di quest'ora, nel fuso della casa."""
    alle = ora_del_testo(notte.alle)
    fine = ora.replace(hour=alle.hour, minute=alle.minute, second=0, microsecond=0)
    if fine > ora:
        fine = fine - datetime.timedelta(days=1)
    return fine


class AnalizzatoreInattivita:
    def __init__(self, regole: RegoleAllarmi):
        self.secondi_inattivita = regole.ore_inattivita * 3600
        self.notte = regole.orari_notte
        self.ultima_vista = None         # l'ultima volta che si è vista una persona (o l'avvio, se mai vista)
        self.ultima_telecamera_id = None
        self.ultima_stanza = None
        self.immagini = {}               # id telecamera → ultimo fotogramma (foto di prova: la stanza vuota)
        self.allarme_mandato = False     # aspetta che la persona ricompaia

    def elabora(self, osservazione: Osservazione) -> list[EventoInattivita]:
        ora = osservazione.ora
        self.immagini[osservazione.telecamera_id] = osservazione.immagine
        if len(osservazione.persone) > 0:
            eventi = []
            if self.allarme_mandato:
                # è ricomparsa: la fine, con la stessa telecamera e lo stesso inizio dell'allarme
                eventi.append(self.evento(ora, osservazione.immagine))
                self.allarme_mandato = False
            # tornando indietro di un secondo (principale.py) le ore possono ripassare: conta la più recente
            if self.ultima_vista is None or ora >= self.ultima_vista:
                self.ultima_vista = ora
                self.ultima_telecamera_id = osservazione.telecamera_id
                self.ultima_stanza = osservazione.stanza
            return eventi
        if self.ultima_vista is None:
            # nessuno visto da quando il programma è partito: si conta da adesso
            self.ultima_vista = ora
            self.ultima_telecamera_id = osservazione.telecamera_id
            self.ultima_stanza = osservazione.stanza
            return []
        if self.allarme_mandato or dentro_fascia(ora, self.notte):
            return []
        da_quando = max(self.ultima_vista, fine_della_notte(ora, self.notte))
        if (ora - da_quando).total_seconds() < self.secondi_inattivita:
            return []
        self.allarme_mandato = True
        return [self.evento(None, self.immagini[self.ultima_telecamera_id])]

    def fine(self) -> list[EventoInattivita]:
        return []

    def evento(self, fine: datetime.datetime | None, immagine: np.ndarray) -> EventoInattivita:
        fonte = Fonte(telecamera_id=self.ultima_telecamera_id, analizzatore="inattivita",
                      confidenza=CONFIDENZA_INATTIVITA)
        return EventoInattivita(
            id=str(uuid.uuid4()),
            tipo="inattivita",
            inizio=self.ultima_vista,
            fine=fine,
            stanza=self.ultima_stanza,
            confidenza=CONFIDENZA_INATTIVITA,
            fonti=[fonte],
            foto_prova=foto_prova(immagine),
            valori=ValoriInattivita(ultima_telecamera_id=self.ultima_telecamera_id),
        )
