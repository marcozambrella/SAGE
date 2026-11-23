"""Analizzatore alzata notturna: inizio = la persona esce dalla zona letto negli orari di notte, fine = ci torna.

Non usa gli id delle tracce (di notte, sotto le coperte, il tracker li cambia spesso): guarda solo se nel letto c'è
qualcuno. Un cambio (letto vuoto, letto di nuovo occupato) vale solo se dura almeno SECONDI_CONFERMA, così un
fotogramma in cui la posa non vede la persona sotto le coperte non diventa un'alzata.
Le stanze attraversate dalle altre telecamere le aggiunge l'unione.
"""

import datetime
import uuid

from contratti.configurazione import FasciaOraria, TelecameraLocale
from contratti.eventi import EventoAlzataNotturna, Fonte, ValoriAlzataNotturna

from casa.configurazione import dentro_fascia
from casa.percezione import Osservazione, foto_prova
from casa.zone import zona_della_persona, zone_del_tipo

# Provvisorio (da far scegliere a Marco con i video veri).
SECONDI_CONFERMA = 10.0


class AnalizzatoreAlzataNotturna:
    usa_oggetti = False

    def __init__(self, telecamera: TelecameraLocale, orari_notte: FasciaOraria):
        self.telecamera_id = telecamera.id
        self.stanza = telecamera.stanza
        self.letti = zone_del_tipo(telecamera, "letto")
        self.orari_notte = orari_notte
        # None finché non si è sicuri di come è il letto (all'inizio del video)
        self.letto_occupato = None
        # primo fotogramma del cambio non ancora confermato, con la sua immagine
        self.cambio_da = None
        self.immagine_cambio = None
        # alzata in corso
        self.inizio_alzata = None
        self.foto_alzata = None
        self.confidenza_a_letto = 0.0  # confidenza della persona vista a letto l'ultima volta

    def elabora(self, osservazione: Osservazione) -> list[EventoAlzataNotturna]:
        altezza = osservazione.immagine.shape[0]
        larghezza = osservazione.immagine.shape[1]
        occupato = False
        for persona in osservazione.persone:
            if zona_della_persona(persona, self.letti, larghezza, altezza) is not None:
                occupato = True
                self.confidenza_a_letto = persona.confidenza

        if occupato == self.letto_occupato:
            self.cambio_da = None
            self.immagine_cambio = None
            return []
        if self.cambio_da is None:
            self.cambio_da = osservazione.ora
            self.immagine_cambio = osservazione.immagine
        if (osservazione.ora - self.cambio_da).total_seconds() < SECONDI_CONFERMA:
            return []

        # cambio confermato: è avvenuto al primo fotogramma del cambio
        eventi = []
        if occupato:
            if self.inizio_alzata is not None and self.alzata_di_notte():
                eventi.append(self.evento(self.cambio_da))
            self.inizio_alzata = None
            self.foto_alzata = None
        elif self.letto_occupato:
            # si alza solo chi era a letto: un letto vuoto all'inizio del video non è un'alzata
            self.inizio_alzata = self.cambio_da
            self.foto_alzata = self.immagine_cambio
        self.letto_occupato = occupato
        self.cambio_da = None
        self.immagine_cambio = None
        return eventi

    def fine(self) -> list[EventoAlzataNotturna]:
        """A fine sorgente un'alzata ancora in corso esce con fine None."""
        eventi = []
        if self.inizio_alzata is not None and self.alzata_di_notte():
            eventi.append(self.evento(None))
        self.inizio_alzata = None
        self.foto_alzata = None
        return eventi

    def alzata_di_notte(self) -> bool:
        """Conta solo se si è alzata negli orari di notte: di giorno alzarsi dal letto è normale."""
        return dentro_fascia(self.inizio_alzata, self.orari_notte)

    def evento(self, fine: datetime.datetime | None) -> EventoAlzataNotturna:
        fonte = Fonte(telecamera_id=self.telecamera_id, analizzatore="alzata_notturna",
                      confidenza=self.confidenza_a_letto)
        return EventoAlzataNotturna(
            id=str(uuid.uuid4()),
            tipo="alzata_notturna",
            inizio=self.inizio_alzata,
            fine=fine,
            stanza=self.stanza,
            confidenza=self.confidenza_a_letto,
            fonti=[fonte],
            foto_prova=foto_prova(self.foto_alzata),
            valori=ValoriAlzataNotturna(stanze=[self.stanza]),
        )
