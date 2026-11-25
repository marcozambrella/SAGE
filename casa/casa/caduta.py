"""Analizzatore caduta, rete ibrida (Marco, 25/11): la geometria dello scheletro decide, il classificatore allenato
sugli scheletri (classificatore_cadute.py) conferma, per avere meno falsi allarmi. Per ogni persona tracciata (id del
tracker):
- "a terra": busto inclinato di almeno 60° dalla verticale e box non più alto che largo (chi si china a raccogliere
  qualcosa ha il busto inclinato ma il box alto), fuori dalla zona letto;
- caduta: era in piedi meno di 3 s prima di finire a terra (chi si sdraia piano non è caduto) e resta a terra
  almeno 2 s;
- conferma: il classificatore (un passo solo, scheletri a 5 al secondo, una finestra ogni 0,5 s per persona) ha
  visto una caduta, per k finestre di fila, da poco prima di finire a terra in poi; e, per far partire l'allarme, il
  busto è quasi orizzontale (70°, se la posa lo vede). Le due cose contro i falsi allarmi le ha scelte l'agente di
  allenamento sui dati pubblici (25/11). Le cadute non fanno passare a 10 fotogrammi al secondo: una volta caduta la
  persona resta a terra e si vede lo stesso (Marco, 25/11).
- senza conferma l'allarme parte lo stesso se resta a terra 30 s; il classificatore da solo non fa partire niente
  (Marco, 25/11). Senza pesi del classificatore basta la geometria.
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

from casa.classificatore_cadute import (PASSO_SECONDI, ClassificatoreCadute, Scheletro, ScheletriDelFotogramma,
                                       finestra_della_traccia)
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
SECONDI_A_TERRA_SENZA_CONFERMA = 30.0
# con la conferma del classificatore l'allarme parte solo con il busto ad almeno 70° ("a terra" resta 60°): sul test
# pubblico i falsi allarmi scendono da 16 a 8 all'ora con la posa n e da 20 a 8 con la s, perdendo una caduta su 39
# con la s (agente di allenamento, 25/11, insieme alle 3 finestre di fila in principale.py)
ANGOLO_A_TERRA_CONFERMATA = 70.0


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
    valutata: datetime.datetime | None          # ultima finestra data al classificatore
    probabilita_recenti: list                   # probabilità delle ultime finestre_di_fila finestre
    confermata: datetime.datetime | None        # ultima volta che il classificatore ha visto una caduta


class AnalizzatoreCaduta:
    usa_oggetti = False

    def __init__(self, telecamera: TelecameraLocale, classificatore: ClassificatoreCadute | None = None):
        self.telecamera_id = telecamera.id
        self.stanza = telecamera.stanza
        self.letti = zone_del_tipo(telecamera, "letto")
        self.classificatore = classificatore
        self.fotogrammi = []  # ScheletriDelFotogramma degli ultimi secondi, per le finestre del classificatore
        self.persone = {}     # id traccia → StatoPersona

    def ricorda_fotogramma(self, osservazione: Osservazione) -> None:
        scheletri = {}
        for persona in osservazione.persone:
            altezza_box = float(persona.box[3] - persona.box[1])
            scheletri[persona.id_traccia] = Scheletro(persona.keypoint, altezza_box)
        self.fotogrammi.append(ScheletriDelFotogramma(osservazione.ora, scheletri))
        # la finestra più un secondo
        secondi_da_tenere = self.classificatore.secondi + 1
        tenuti = []
        for fotogramma in self.fotogrammi:
            if (osservazione.ora - fotogramma.ora).total_seconds() <= secondi_da_tenere:
                tenuti.append(fotogramma)
        self.fotogrammi = tenuti

    def valuta(self, stato: StatoPersona, id_traccia: int, ora: datetime.datetime) -> None:
        """Una finestra per ogni mezzo secondo dell'orologio (PASSO_SECONDI) per persona, come nell'allenamento: a 5
        fotogrammi al secondo "ogni 0,5 s dall'ultima" diventerebbe ogni 0,6 s."""
        if stato.valutata is not None:
            mezzo_secondo_adesso = int(ora.timestamp() / PASSO_SECONDI)
            if mezzo_secondo_adesso == int(stato.valutata.timestamp() / PASSO_SECONDI):
                return
        stato.valutata = ora
        finestra = finestra_della_traccia(self.fotogrammi, id_traccia, ora, self.classificatore.fps,
                                          self.classificatore.lunghezza)
        stato.probabilita_recenti.append(self.classificatore.probabilita_caduta(finestra))
        stato.probabilita_recenti = stato.probabilita_recenti[-self.classificatore.finestre_di_fila:]
        if len(stato.probabilita_recenti) < self.classificatore.finestre_di_fila:
            return
        if min(stato.probabilita_recenti) >= self.classificatore.soglia:
            stato.confermata = ora

    def confermata(self, stato: StatoPersona, persona: Persona, secondi_a_terra: float) -> bool:
        if self.classificatore is None or secondi_a_terra >= SECONDI_A_TERRA_SENZA_CONFERMA:
            return True
        if stato.confermata is None:
            return False
        # la caduta si vede nelle finestre da poco prima di finire a terra
        if stato.confermata < stato.a_terra_da - datetime.timedelta(seconds=SECONDI_CADUTA_RAPIDA):
            return False
        # se la posa non vede spalle o anche il busto non blocca
        angolo = angolo_del_busto(persona)
        return angolo is None or angolo >= ANGOLO_A_TERRA_CONFERMATA

    def elabora(self, osservazione: Osservazione) -> list[EventoCaduta]:
        ora = osservazione.ora
        altezza = osservazione.immagine.shape[0]
        larghezza = osservazione.immagine.shape[1]
        if self.classificatore is not None:
            self.ricorda_fotogramma(osservazione)
        eventi = []
        for persona in osservazione.persone:
            stato = self.persone.get(persona.id_traccia)
            if stato is None:
                stato = StatoPersona(ora, None, None, None, False, 0.0, None, None, [], None)
                self.persone[persona.id_traccia] = stato
            stato.vista = ora
            if self.classificatore is not None:
                self.valuta(stato, persona.id_traccia, ora)
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
                pronta = secondi_a_terra >= SECONDI_A_TERRA and self.confermata(stato, persona, secondi_a_terra)
                if not stato.segnalata and pronta:
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
