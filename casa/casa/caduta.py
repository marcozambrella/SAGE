"""Analizzatore caduta, regole PROVVISORIE dalla geometria dello scheletro finché non arriva il classificatore
allenato sugli scheletri. Per ogni persona tracciata (id del tracker):
- "a terra": busto inclinato di almeno 60° dalla verticale e box non più alto che largo (chi si china a raccogliere
  qualcosa ha il busto inclinato ma il box alto), fuori dalla zona letto;
- caduta: era in piedi meno di 3 s prima di finire a terra (chi si sdraia piano non è caduto) e resta a terra
  almeno 2 s.
L'evento parte subito (urgente, Telegram) con secondi_a_terra None. Quando la persona si rialza si manda un secondo
evento grezzo con la fine e i secondi a terra: il backend lo coordina con il primo (API.md, "la stessa telecamera in
pezzi vicini") e non rimanda l'allarme.
"""

from dataclasses import dataclass
import datetime
import uuid

import numpy as np

from contratti.configurazione import TelecameraLocale
from contratti.eventi import EventoCaduta, Fonte, ValoriCaduta

from casa.percezione import Osservazione, Persona, foto_prova
from casa.scheletro import angolo_del_busto
from casa.zone import zona_della_persona, zone_del_tipo

ANGOLO_A_TERRA = 60.0
ANGOLO_IN_PIEDI = 30.0
RAPPORTO_A_TERRA = 1.0             # larghezza / altezza del box
RAPPORTO_A_TERRA_SENZA_BUSTO = 1.5  # se la posa non vede spalle e anche conta solo il box
SECONDI_CADUTA_RAPIDA = 3.0
SECONDI_A_TERRA = 2.0
SECONDI_RIALZATO = 3.0             # non più a terra da tanto: si è rialzato
SECONDI_TRACCIA_DIMENTICATA = 60.0


def rapporto_del_box(persona: Persona) -> float:
    larghezza = float(persona.box[2] - persona.box[0])
    altezza = float(persona.box[3] - persona.box[1])
    if altezza <= 0:
        return 0.0
    return larghezza / altezza


def a_terra(persona: Persona) -> bool:
    angolo = angolo_del_busto(persona)
    if angolo is None:
        return rapporto_del_box(persona) >= RAPPORTO_A_TERRA_SENZA_BUSTO
    return angolo >= ANGOLO_A_TERRA and rapporto_del_box(persona) >= RAPPORTO_A_TERRA


def in_piedi(persona: Persona) -> bool:
    angolo = angolo_del_busto(persona)
    if angolo is None:
        return rapporto_del_box(persona) <= 1 / RAPPORTO_A_TERRA_SENZA_BUSTO
    return angolo <= ANGOLO_IN_PIEDI and rapporto_del_box(persona) < RAPPORTO_A_TERRA


@dataclass
class StatoPersona:
    vista: datetime.datetime                    # ultima volta vista
    in_piedi: datetime.datetime | None          # ultima volta vista in piedi
    a_terra_da: datetime.datetime | None        # primo fotogramma a terra dopo essere stata in piedi
    non_a_terra_da: datetime.datetime | None    # da quando non è più a terra (per capire se si è rialzata)
    segnalata: bool                             # l'evento urgente è già partito
    confidenza: float
    immagine: np.ndarray | None


class AnalizzatoreCaduta:
    usa_oggetti = False

    def __init__(self, telecamera: TelecameraLocale):
        self.telecamera_id = telecamera.id
        self.stanza = telecamera.stanza
        self.letti = zone_del_tipo(telecamera, "letto")
        self.persone = {}  # id traccia → StatoPersona

    def elabora(self, osservazione: Osservazione) -> list[EventoCaduta]:
        ora = osservazione.ora
        altezza = osservazione.immagine.shape[0]
        larghezza = osservazione.immagine.shape[1]
        eventi = []
        for persona in osservazione.persone:
            stato = self.persone.get(persona.id_traccia)
            if stato is None:
                stato = StatoPersona(ora, None, None, None, False, 0.0, None)
                self.persone[persona.id_traccia] = stato
            stato.vista = ora
            nel_letto = zona_della_persona(persona, self.letti, larghezza, altezza) is not None
            if a_terra(persona) and not nel_letto:
                stato.non_a_terra_da = None
                if stato.a_terra_da is None:
                    caduta_rapida = stato.in_piedi is not None
                    if caduta_rapida:
                        caduta_rapida = (ora - stato.in_piedi).total_seconds() <= SECONDI_CADUTA_RAPIDA
                    if not caduta_rapida:
                        continue
                    stato.a_terra_da = ora
                    stato.confidenza = 0.0
                stato.confidenza = max(stato.confidenza, persona.confidenza)
                secondi_a_terra = (ora - stato.a_terra_da).total_seconds()
                if not stato.segnalata and secondi_a_terra >= SECONDI_A_TERRA:
                    stato.segnalata = True
                    stato.immagine = osservazione.immagine
                    eventi.append(self.evento(stato, None))
                continue
            if in_piedi(persona):
                stato.in_piedi = ora
            if stato.a_terra_da is None:
                continue
            if stato.non_a_terra_da is None:
                stato.non_a_terra_da = ora
            if (ora - stato.non_a_terra_da).total_seconds() < SECONDI_RIALZATO:
                continue
            # rialzata: se l'allarme era partito si manda la fine con i secondi a terra
            if stato.segnalata:
                eventi.append(self.evento(stato, stato.non_a_terra_da))
            stato.a_terra_da = None
            stato.non_a_terra_da = None
            stato.segnalata = False
            stato.immagine = None

        dimenticate = []
        for id_traccia in self.persone:
            if (ora - self.persone[id_traccia].vista).total_seconds() >= SECONDI_TRACCIA_DIMENTICATA:
                dimenticate.append(id_traccia)
        for id_traccia in dimenticate:
            self.persone.pop(id_traccia)
        return eventi

    def fine(self) -> list[EventoCaduta]:
        return []

    def evento(self, stato: StatoPersona, fine: datetime.datetime | None) -> EventoCaduta:
        secondi_a_terra = None
        if fine is not None:
            secondi_a_terra = (fine - stato.a_terra_da).total_seconds()
        fonte = Fonte(telecamera_id=self.telecamera_id, analizzatore="caduta", confidenza=stato.confidenza)
        return EventoCaduta(
            id=str(uuid.uuid4()),
            tipo="caduta",
            inizio=stato.a_terra_da,
            fine=fine,
            stanza=self.stanza,
            confidenza=stato.confidenza,
            fonti=[fonte],
            foto_prova=foto_prova(stato.immagine),
            valori=ValoriCaduta(secondi_a_terra=secondi_a_terra),
        )
