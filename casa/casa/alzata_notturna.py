"""Alzata notturna: una persona esce dal letto negli orari di notte e resta fuori almeno 30 secondi (Marco, 24/11);
fine = torna a letto.

Nella camera da letto (zona "letto"): si contano le persone tracciate con i piedi nella zona letto. L'alzata comincia
quando a letto ce ne sono meno del solito e qualcuno è visto fuori dal letto: così funziona anche con due persone nel
letto e quando il tracker cambia id a chi passa da sdraiato a in piedi, e una persona che la posa non vede più sotto
le coperte (nessuno visto fuori) non diventa un'alzata.

Nelle altre stanze (telecamera con l'analizzatore ma senza zona letto): una presenza di notte diventa un'alzata con
quella stanza. Il backend coordina gli eventi che si sovrappongono e unisce le stanze attraversate (API.md).
"""

import datetime
import uuid

import numpy as np

from contratti.configurazione import FasciaOraria, TelecameraLocale
from contratti.eventi import EventoAlzataNotturna, Fonte, ValoriAlzataNotturna

from casa.configurazione import dentro_fascia
from casa.percezione import Osservazione, foto_prova
from casa.zone import zona_della_persona, zone_del_tipo

SECONDI_FUORI_DAL_LETTO = 30.0   # Marco, 24/11
SECONDI_RITORNO = 5.0            # di nuovo a letto per tanto: è tornato davvero
SECONDI_STABILE = 5.0            # "quanti sono di solito a letto": il numero visto per almeno tanto
SECONDI_FINE_PRESENZA = 60.0     # stanze senza letto: nessuno visto per tanto, la presenza è finita
SECONDI_MINIMI_PRESENZA = 3.0    # stanze senza letto: una persona vista per meno è un errore della posa


def evento_alzata(telecamera_id: str, stanza: str, inizio: datetime.datetime, fine: datetime.datetime | None,
                  confidenza: float, immagine: np.ndarray) -> EventoAlzataNotturna:
    fonte = Fonte(telecamera_id=telecamera_id, analizzatore="alzata_notturna", confidenza=confidenza)
    return EventoAlzataNotturna(
        id=str(uuid.uuid4()),
        tipo="alzata_notturna",
        inizio=inizio,
        fine=fine,
        stanza=stanza,
        confidenza=confidenza,
        fonti=[fonte],
        foto_prova=foto_prova(immagine),
        valori=ValoriAlzataNotturna(stanze=[stanza]),
    )


class AnalizzatoreAlzataNotturna:
    """Camera da letto (con zona letto)."""

    usa_oggetti = False

    def __init__(self, telecamera: TelecameraLocale, orari_notte: FasciaOraria):
        self.telecamera_id = telecamera.id
        self.stanza = telecamera.stanza
        self.letti = zone_del_tipo(telecamera, "letto")
        self.orari_notte = orari_notte
        # quante persone ci sono di solito a letto (None finché il numero non è stabile)
        self.a_letto_di_solito = None
        self.conteggio_visto = None
        self.conteggio_da = None
        # alzata in corso
        self.inizio = None
        self.foto = None
        self.confidenza = 0.0
        self.ritorno_da = None           # primo fotogramma di nuovo a letto (ritorno non ancora confermato)
        self.ultima_ora = None

    def elabora(self, osservazione: Osservazione) -> list[EventoAlzataNotturna]:
        ora = osservazione.ora
        self.ultima_ora = ora
        altezza = osservazione.immagine.shape[0]
        larghezza = osservazione.immagine.shape[1]
        a_letto = 0
        fuori_dal_letto = []
        for persona in osservazione.persone:
            if zona_della_persona(persona, self.letti, larghezza, altezza) is None:
                fuori_dal_letto.append(persona)
            else:
                a_letto = a_letto + 1

        if self.inizio is None:
            self.aggiorna_di_solito(a_letto, ora)
            mancano = self.a_letto_di_solito is not None and a_letto < self.a_letto_di_solito
            if mancano and len(fuori_dal_letto) > 0:
                # qualcuno si è alzato: l'alzata comincia adesso (diventa vera dopo 30 s fuori)
                self.inizio = ora
                self.foto = osservazione.immagine
                self.confidenza = 0.0
            else:
                return []

        for persona in fuori_dal_letto:
            self.confidenza = max(self.confidenza, persona.confidenza)
        if a_letto < self.a_letto_di_solito:
            self.ritorno_da = None
            return []
        if self.ritorno_da is None:
            self.ritorno_da = ora
        if (ora - self.ritorno_da).total_seconds() < SECONDI_RITORNO:
            return []
        # tornato a letto: è un'alzata se è rimasto fuori almeno 30 s ed era notte
        eventi = []
        if self.alzata_vera(self.ritorno_da):
            eventi.append(evento_alzata(self.telecamera_id, self.stanza, self.inizio, self.ritorno_da,
                                        self.confidenza, self.foto))
        self.inizio = None
        self.foto = None
        self.ritorno_da = None
        return eventi

    def aggiorna_di_solito(self, a_letto: int, ora: datetime.datetime) -> None:
        """Il numero di persone a letto diventa "quello di solito" se resta uguale per SECONDI_STABILE."""
        if a_letto != self.conteggio_visto:
            self.conteggio_visto = a_letto
            self.conteggio_da = ora
        if (ora - self.conteggio_da).total_seconds() >= SECONDI_STABILE:
            self.a_letto_di_solito = a_letto

    def alzata_vera(self, fino_a: datetime.datetime) -> bool:
        fuori_abbastanza = (fino_a - self.inizio).total_seconds() >= SECONDI_FUORI_DAL_LETTO
        return fuori_abbastanza and dentro_fascia(self.inizio, self.orari_notte)

    def fine(self) -> list[EventoAlzataNotturna]:
        """A fine sorgente un'alzata ancora in corso (già fuori da 30 s) esce con fine None."""
        eventi = []
        if self.inizio is not None and self.alzata_vera(self.ultima_ora):
            eventi.append(evento_alzata(self.telecamera_id, self.stanza, self.inizio, None, self.confidenza,
                                        self.foto))
        self.inizio = None
        return eventi


class AnalizzatorePresenzaNotturna:
    """Stanza senza letto: chi è visto qui di notte è alzato. L'evento porta questa stanza tra quelle attraversate."""

    usa_oggetti = False

    def __init__(self, telecamera: TelecameraLocale, orari_notte: FasciaOraria):
        self.telecamera_id = telecamera.id
        self.stanza = telecamera.stanza
        self.orari_notte = orari_notte
        self.inizio = None
        self.ultima_vista = None
        self.foto = None
        self.confidenza = 0.0

    def elabora(self, osservazione: Osservazione) -> list[EventoAlzataNotturna]:
        ora = osservazione.ora
        if len(osservazione.persone) > 0:
            if self.inizio is None:
                self.inizio = ora
                self.foto = osservazione.immagine
                self.confidenza = 0.0
            self.ultima_vista = ora
            for persona in osservazione.persone:
                self.confidenza = max(self.confidenza, persona.confidenza)
            return []
        if self.inizio is None:
            return []
        if (ora - self.ultima_vista).total_seconds() < SECONDI_FINE_PRESENZA:
            return []
        return self.chiudi()

    def chiudi(self) -> list[EventoAlzataNotturna]:
        eventi = []
        durata = (self.ultima_vista - self.inizio).total_seconds()
        if durata >= SECONDI_MINIMI_PRESENZA and dentro_fascia(self.inizio, self.orari_notte):
            eventi.append(evento_alzata(self.telecamera_id, self.stanza, self.inizio, self.ultima_vista,
                                        self.confidenza, self.foto))
        self.inizio = None
        self.foto = None
        return eventi

    def fine(self) -> list[EventoAlzataNotturna]:
        if self.inizio is None:
            return []
        return self.chiudi()
