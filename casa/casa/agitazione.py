"""Agitazione (Marco, 25/11): una persona cammina avanti e indietro a lungo senza meta (pacing), spesso nel tardo
pomeriggio e la sera. Regole PROVVISORIE, da provare sui dataset pubblici:
- un campione al secondo della posizione dei piedi (centro del lato basso del box); il campione è "in movimento" se
  la persona si è spostata di almeno 0,2 altezze del box al secondo (camminare piano è circa 0,5);
- inversione: un movimento che va all'indietro rispetto al movimento prima (girata di più di 120°);
- episodio: movimenti di fila senza fermarsi per 20 s e senza restare 20 s in una zona tavolo o letto (a sedere, a
  letto); è agitazione se dura almeno 3 minuti con almeno 6 inversioni (una ogni 30 s);
- l'evento parte alla fine dell'episodio, con inizio, fine e numero di inversioni.
Lo stato è per traccia; se il tracker cambia id (box che si toccano, traccia vecchia vista da poco) l'episodio passa
alla traccia nuova. Non è un primo segno: resta a 5 fotogrammi al secondo.
"""

from dataclasses import dataclass
import datetime
import uuid

import numpy as np

from contratti.configurazione import TelecameraLocale
from contratti.eventi import EventoAgitazione, Fonte, ValoriAgitazione

from casa.caduta import box_si_toccano
from casa.percezione import Osservazione, Persona, foto_prova
from casa.zone import punto_a_terra, zona_della_persona, zone_del_tipo

SECONDI_CAMPIONE = 1.0
VELOCITA_CAMMINO = 0.2          # altezze del box al secondo
COSENO_INVERSIONE = -0.5        # girata di più di 120°
SECONDI_FERMO = 20.0            # fermo per tanto: l'episodio è finito (si è seduto o si è fermato)
SECONDI_IN_ZONA = 20.0          # a tavola o a letto per tanto: l'episodio è finito
SECONDI_MINIMI_EPISODIO = 180.0  # "in movimento per almeno 3 minuti"
INVERSIONI_MINIME = 6
SECONDI_TRACCIA_PERSA = 10.0    # traccia non vista da tanto: l'episodio è finito
SECONDI_EREDITA = 3.0           # traccia sparita da meno di così: una traccia nuova che la tocca è la stessa persona


@dataclass
class Camminata:
    """Lo stato di una traccia."""

    vista: datetime.datetime                 # ultima volta vista
    box: np.ndarray                          # ultimo box (per l'eredità quando il tracker cambia id)
    ultimo_campione: datetime.datetime
    posizione: np.ndarray                    # piedi all'ultimo campione, in pixel
    direzione: np.ndarray | None             # direzione (unitaria) dell'ultimo movimento
    inizio: datetime.datetime | None         # episodio in corso: primo movimento
    ultimo_movimento: datetime.datetime | None
    in_zona_da: datetime.datetime | None     # piedi in una zona tavolo o letto da
    inversioni: int
    confidenza: float
    foto: np.ndarray | None


def piedi(persona: Persona) -> np.ndarray:
    x, y = punto_a_terra(persona)
    return np.array([x, y], np.float32)


class AnalizzatoreAgitazione:
    usa_oggetti = False

    def __init__(self, telecamera: TelecameraLocale):
        self.telecamera_id = telecamera.id
        self.stanza = telecamera.stanza
        self.zone_per_fermarsi = zone_del_tipo(telecamera, "tavolo") + zone_del_tipo(telecamera, "letto")
        self.camminate = {}  # id traccia → Camminata

    def eredita(self, osservazione: Osservazione) -> None:
        """Traccia nuova che tocca il box di una traccia sparita da meno di 3 s: il tracker ha cambiato id."""
        ora = osservazione.ora
        visti = []
        for persona in osservazione.persone:
            visti.append(persona.id_traccia)
        for persona in osservazione.persone:
            if persona.id_traccia in self.camminate:
                continue
            vecchia = None
            for id_traccia in self.camminate:
                camminata = self.camminate[id_traccia]
                if id_traccia in visti or (ora - camminata.vista).total_seconds() > SECONDI_EREDITA:
                    continue
                if box_si_toccano(camminata.box, persona.box):
                    vecchia = id_traccia
            if vecchia is not None:
                self.camminate[persona.id_traccia] = self.camminate.pop(vecchia)

    def elabora(self, osservazione: Osservazione) -> list[EventoAgitazione]:
        ora = osservazione.ora
        altezza = osservazione.immagine.shape[0]
        larghezza = osservazione.immagine.shape[1]
        self.eredita(osservazione)
        eventi = []
        for persona in osservazione.persone:
            camminata = self.camminate.get(persona.id_traccia)
            if camminata is None:
                camminata = Camminata(ora, persona.box, ora, piedi(persona), None, None, None, None, 0, 0.0, None)
                self.camminate[persona.id_traccia] = camminata
            camminata.vista = ora
            camminata.box = persona.box
            self.campiona(camminata, persona, osservazione)
            if zona_della_persona(persona, self.zone_per_fermarsi, larghezza, altezza) is None:
                camminata.in_zona_da = None
            elif camminata.in_zona_da is None:
                camminata.in_zona_da = ora
            if camminata.inizio is None:
                continue
            fermo = (ora - camminata.ultimo_movimento).total_seconds() >= SECONDI_FERMO
            in_zona = camminata.in_zona_da is not None
            if in_zona:
                in_zona = (ora - camminata.in_zona_da).total_seconds() >= SECONDI_IN_ZONA
            if fermo or in_zona:
                for evento in self.chiudi(camminata):
                    eventi.append(evento)

        perse = []
        for id_traccia in self.camminate:
            if (ora - self.camminate[id_traccia].vista).total_seconds() >= SECONDI_TRACCIA_PERSA:
                perse.append(id_traccia)
        for id_traccia in perse:
            for evento in self.chiudi(self.camminate.pop(id_traccia)):
                eventi.append(evento)
        return eventi

    def campiona(self, camminata: Camminata, persona: Persona, osservazione: Osservazione) -> None:
        """Un campione al secondo: se si è mosso abbastanza è un movimento, forse un'inversione."""
        ora = osservazione.ora
        secondi = (ora - camminata.ultimo_campione).total_seconds()
        if secondi < SECONDI_CAMPIONE:
            return
        posizione = piedi(persona)
        spostamento = posizione - camminata.posizione
        lunghezza = float(np.linalg.norm(spostamento))
        altezza_box = float(persona.box[3] - persona.box[1])
        precedente = camminata.ultimo_campione
        camminata.ultimo_campione = ora
        camminata.posizione = posizione
        if altezza_box <= 0 or lunghezza / altezza_box / secondi < VELOCITA_CAMMINO:
            return
        direzione = spostamento / lunghezza
        if camminata.inizio is None:
            camminata.inizio = precedente
            camminata.inversioni = 0
            camminata.confidenza = 0.0
            camminata.foto = osservazione.immagine
        elif camminata.direzione is not None and float(np.dot(direzione, camminata.direzione)) < COSENO_INVERSIONE:
            camminata.inversioni = camminata.inversioni + 1
        camminata.direzione = direzione
        camminata.ultimo_movimento = ora
        camminata.confidenza = max(camminata.confidenza, persona.confidenza)

    def chiudi(self, camminata: Camminata) -> list[EventoAgitazione]:
        """Fine dell'episodio: è agitazione se è durato abbastanza con abbastanza inversioni."""
        eventi = []
        durata = (camminata.ultimo_movimento - camminata.inizio).total_seconds()
        if durata >= SECONDI_MINIMI_EPISODIO and camminata.inversioni >= INVERSIONI_MINIME:
            eventi.append(self.evento(camminata))
        camminata.inizio = None
        camminata.ultimo_movimento = None
        camminata.direzione = None
        camminata.inversioni = 0
        camminata.foto = None
        return eventi

    def fine(self) -> list[EventoAgitazione]:
        """A fine sorgente un episodio in corso si chiude all'ultimo movimento."""
        eventi = []
        for camminata in self.camminate.values():
            if camminata.inizio is not None:
                for evento in self.chiudi(camminata):
                    eventi.append(evento)
        self.camminate = {}
        return eventi

    def evento(self, camminata: Camminata) -> EventoAgitazione:
        fonte = Fonte(telecamera_id=self.telecamera_id, analizzatore="agitazione", confidenza=camminata.confidenza)
        return EventoAgitazione(
            id=str(uuid.uuid4()),
            tipo="agitazione",
            inizio=camminata.inizio,
            fine=camminata.ultimo_movimento,
            stanza=self.stanza,
            confidenza=camminata.confidenza,
            fonti=[fonte],
            foto_prova=foto_prova(camminata.foto),
            valori=ValoriAgitazione(inversioni=camminata.inversioni),
        )
