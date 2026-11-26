"""Sonno (Marco, 25/11): i pezzi di sonno nella zona letto, inizio = si addormenta, fine = si sveglia. Regole
PROVVISORIE, finché l'agente di allenamento non manda soglie o modello provati sui dataset pubblici:
- dorme: una persona con i piedi o il busto nella zona letto, sdraiata (busto ad almeno 60° dalla verticale, o non
  visto: sotto le coperte) e quasi ferma (i suoi punti si muovono meno di 0,15 altezze del box al secondo) per
  5 minuti; l'inizio è quando è diventata ferma;
- si sveglia: è seduta (busto entro 30°) o si muove tanto per almeno 1 minuto (le pause tranquille di meno di 15 s
  non lo interrompono, e girarsi nel sonno per pochi secondi non sveglia); oppure qualcuno è visto fuori dal letto per
  5 s mentre nel letto non si vede nessuno. La fine è quando ha cominciato a sedersi, muoversi o stare fuori;
- nel letto la sparizione non sveglia (sotto le coperte la posa la perde): conta come "dorme ancora" finché non si
  vede qualcuno fuori dal letto, come per l'alzata notturna. Chi è fuori dal letto mentre un altro dorme visibile
  (il compagno) non sveglia nessuno.
Un evento per ogni pezzo di sonno, quando finisce (a fine sorgente con fine None); le alzate notturne sono i buchi
tra un pezzo e l'altro. Lo stato è per zona letto, non per traccia: chi dorme cambia spesso id. Il sonno non è un
primo segno: resta a 5 fotogrammi al secondo.
"""

from dataclasses import dataclass
import datetime
import uuid

import numpy as np

from contratti.configurazione import TelecameraLocale, Zona
from contratti.eventi import EventoSonno, Fonte, ValoriSonno

from casa.percezione import Osservazione, Persona, foto_prova
from casa.scheletro import (ANCA_DX, ANCA_SX, SPALLA_DX, SPALLA_SX, VISIBILITA_MINIMA, angolo_del_busto,
                            media_dei_punti)
from casa.zone import dentro_zona, zona_della_persona, zone_del_tipo

ANGOLO_SDRAIATO = 60.0             # come "a terra" nelle cadute
ANGOLO_SEDUTO = 30.0               # come "in piedi" nelle cadute: busto quasi verticale
VELOCITA_MOSSO = 0.15              # altezze del box al secondo (mediana dei punti): il tremolio della posa sta sotto
SECONDI_PER_ADDORMENTARSI = 300.0  # "quasi fermo per qualche minuto"
SECONDI_SVEGLIO = 60.0             # seduto o in movimento per tanto: si è svegliato
SECONDI_CALMA = 15.0               # tranquillo per tanto dopo un movimento: era solo girarsi nel sonno
SECONDI_FUORI_PER_SVEGLIA = 5.0    # visto fuori dal letto per tanto (un fotogramma può essere un errore della posa)
SECONDI_PUNTI_DIMENTICATI = 10.0   # punti di una traccia non vista da tanto: non servono più per il movimento


@dataclass
class PuntiVisti:
    ora: datetime.datetime
    keypoint: np.ndarray


@dataclass
class SonnoNelLetto:
    """Lo stato di una zona letto."""

    fermo_da: datetime.datetime | None        # qualcuno sdraiato e quasi fermo da (prima di dormire)
    inizio: datetime.datetime | None          # si è addormentato: pezzo di sonno in corso
    sveglio_da: datetime.datetime | None      # mentre dorme: seduto o in movimento da
    ultimo_sveglio: datetime.datetime | None  # ultimo fotogramma seduto o in movimento
    fuori_da: datetime.datetime | None        # mentre dorme: qualcuno fuori dal letto e nessuno nel letto, da
    confidenza: float
    foto: np.ndarray | None


def stato_vuoto() -> SonnoNelLetto:
    return SonnoNelLetto(None, None, None, None, None, 0.0, None)


class AnalizzatoreSonno:
    usa_oggetti = False

    def __init__(self, telecamera: TelecameraLocale):
        self.telecamera_id = telecamera.id
        self.stanza = telecamera.stanza
        self.letti = zone_del_tipo(telecamera, "letto")
        self.stati = {}         # id zona letto → SonnoNelLetto
        for zona in self.letti:
            self.stati[zona.id] = stato_vuoto()
        self.punti_prima = {}   # id traccia → PuntiVisti del fotogramma prima

    def zona_del_letto(self, persona: Persona, larghezza: int, altezza: int) -> Zona | None:
        """La zona letto con i piedi o il centro del busto della persona."""
        zona = zona_della_persona(persona, self.letti, larghezza, altezza)
        if zona is not None:
            return zona
        busto = media_dei_punti(persona, [SPALLA_SX, SPALLA_DX, ANCA_SX, ANCA_DX])
        if busto is None:
            return None
        for zona in self.letti:
            if dentro_zona(float(busto[0]), float(busto[1]), zona, larghezza, altezza):
                return zona
        return None

    def velocita(self, persona: Persona, ora: datetime.datetime) -> float | None:
        """Quanto si muovono i punti dal fotogramma prima: mediana sui punti visti tutte e due le volte, in altezze del
        box al secondo (così non conta se si analizzano 5 o 10 fotogrammi al secondo). None se non si sa."""
        prima = self.punti_prima.get(persona.id_traccia)
        if prima is None:
            return None
        secondi = (ora - prima.ora).total_seconds()
        altezza = float(persona.box[3] - persona.box[1])
        if secondi <= 0 or altezza <= 0:
            return None
        visti = (persona.keypoint[:, 2] >= VISIBILITA_MINIMA) & (prima.keypoint[:, 2] >= VISIBILITA_MINIMA)
        if not visti.any():
            return None
        spostamenti = np.linalg.norm(persona.keypoint[visti, 0:2] - prima.keypoint[visti, 0:2], axis=1)
        return float(np.median(spostamenti)) / altezza / secondi

    def elabora(self, osservazione: Osservazione) -> list[EventoSonno]:
        ora = osservazione.ora
        altezza = osservazione.immagine.shape[0]
        larghezza = osservazione.immagine.shape[1]
        nel_letto = {}    # id zona → persone nella zona
        quieta = {}       # id zona → qualcuno lì è sdraiato e quasi fermo
        sveglia = {}      # id zona → qualcuno lì è seduto o si muove
        for zona in self.letti:
            nel_letto[zona.id] = []
            quieta[zona.id] = False
            sveglia[zona.id] = False
        qualcuno_fuori = False
        for persona in osservazione.persone:
            zona = self.zona_del_letto(persona, larghezza, altezza)
            if zona is None:
                qualcuno_fuori = True
                continue
            nel_letto[zona.id].append(persona)
            angolo = angolo_del_busto(persona)
            velocita = self.velocita(persona, ora)
            mosso = velocita is not None and velocita > VELOCITA_MOSSO
            sdraiato = angolo is None or angolo >= ANGOLO_SDRAIATO
            seduto = angolo is not None and angolo <= ANGOLO_SEDUTO
            if sdraiato and not mosso:
                quieta[zona.id] = True
            if seduto or mosso:
                sveglia[zona.id] = True
        self.ricorda_punti(osservazione)

        eventi = []
        for zona in self.letti:
            stato = self.stati[zona.id]
            # con qualcuno tranquillo nel letto, chi si muove accanto (il compagno) non sveglia
            sveglia_zona = sveglia[zona.id] and not quieta[zona.id]
            for evento in self.aggiorna(zona.id, stato, nel_letto[zona.id], quieta[zona.id], sveglia_zona,
                                        qualcuno_fuori, osservazione):
                eventi.append(evento)
        return eventi

    def ricorda_punti(self, osservazione: Osservazione) -> None:
        for persona in osservazione.persone:
            self.punti_prima[persona.id_traccia] = PuntiVisti(osservazione.ora, persona.keypoint)
        vecchi = []
        for id_traccia in self.punti_prima:
            if (osservazione.ora - self.punti_prima[id_traccia].ora).total_seconds() > SECONDI_PUNTI_DIMENTICATI:
                vecchi.append(id_traccia)
        for id_traccia in vecchi:
            self.punti_prima.pop(id_traccia)

    def aggiorna(self, zona_id: str, stato: SonnoNelLetto, persone_nel_letto: list, quieta: bool, sveglia: bool,
                 qualcuno_fuori: bool, osservazione: Osservazione) -> list[EventoSonno]:
        ora = osservazione.ora
        visti_nel_letto = len(persone_nel_letto) > 0
        if stato.inizio is None:
            if quieta:
                if stato.fermo_da is None:
                    stato.fermo_da = ora
                    stato.foto = osservazione.immagine
                    stato.confidenza = 0.0
                for persona in persone_nel_letto:
                    stato.confidenza = max(stato.confidenza, persona.confidenza)
                if (ora - stato.fermo_da).total_seconds() >= SECONDI_PER_ADDORMENTARSI:
                    stato.inizio = stato.fermo_da
            elif visti_nel_letto or qualcuno_fuori:
                # nel letto ma non tranquillo, o in giro per la stanza: non si sta addormentando
                stato.fermo_da = None
            # nessuno visto: sotto le coperte, resta com'è
            return []

        for persona in persone_nel_letto:
            stato.confidenza = max(stato.confidenza, persona.confidenza)
        if visti_nel_letto:
            stato.fuori_da = None
        elif qualcuno_fuori:
            if stato.fuori_da is None:
                stato.fuori_da = ora
            if (ora - stato.fuori_da).total_seconds() >= SECONDI_FUORI_PER_SVEGLIA:
                # si è alzato: dall'inizio del movimento nel letto, se c'era, se no da quando è fuori
                sveglio = stato.fuori_da
                if stato.sveglio_da is not None and stato.sveglio_da < sveglio:
                    sveglio = stato.sveglio_da
                return self.svegliato(zona_id, stato, sveglio)
            return []
        if sveglia:
            if stato.sveglio_da is None:
                stato.sveglio_da = ora
            stato.ultimo_sveglio = ora
            if (ora - stato.sveglio_da).total_seconds() >= SECONDI_SVEGLIO:
                return self.svegliato(zona_id, stato, stato.sveglio_da)
        elif quieta and stato.ultimo_sveglio is not None:
            if (ora - stato.ultimo_sveglio).total_seconds() >= SECONDI_CALMA:
                stato.sveglio_da = None
                stato.ultimo_sveglio = None
        return []

    def dorme(self) -> bool:
        """C'è un pezzo di sonno aperto (anche se sotto le coperte non si vede)?"""
        for stato in self.stati.values():
            if stato.inizio is not None:
                return True
        return False

    def svegliato(self, zona_id: str, stato: SonnoNelLetto, fine: datetime.datetime) -> list[EventoSonno]:
        evento = self.evento(zona_id, stato, fine)
        self.stati[zona_id] = stato_vuoto()
        return [evento]

    def fine(self) -> list[EventoSonno]:
        """A fine sorgente un pezzo di sonno ancora in corso esce con fine None."""
        eventi = []
        for zona in self.letti:
            stato = self.stati[zona.id]
            if stato.inizio is not None:
                eventi.append(self.evento(zona.id, stato, None))
            self.stati[zona.id] = stato_vuoto()
        return eventi

    def evento(self, zona_id: str, stato: SonnoNelLetto, fine: datetime.datetime | None) -> EventoSonno:
        fonte = Fonte(telecamera_id=self.telecamera_id, analizzatore="sonno", confidenza=stato.confidenza)
        return EventoSonno(
            id=str(uuid.uuid4()),
            tipo="sonno",
            inizio=stato.inizio,
            fine=fine,
            stanza=self.stanza,
            confidenza=stato.confidenza,
            fonti=[fonte],
            foto_prova=foto_prova(stato.foto),
            valori=ValoriSonno(zona_id=zona_id),
        )
