"""Analizzatore uscita (D16): la persona APRE IL PORTONE di casa ed esce (Marco, 24/11). Per ogni persona tracciata
(id del tracker):
- è nella zona porta allargata (con i piedi: allargata per non perdere chi è coperto a metà dalla porta) e la porta
  è aperta, mentre la persona è lì o subito dopo che è sparita;
- poi la persona sparisce per SECONDI_SPARIZIONE.
Porta aperta: il modello allenato porta_aperta/porta_chiusa (25/11) sul ritaglio della zona, solo quando qualcuno è
alla porta e al massimo ogni mezzo secondo. Riserva se mancano i pesi: la zona cambia aspetto rispetto al
riferimento "porta chiusa" (aspetto_zona.py).
Chi apre la porta e poi torna nella stanza (es. a prendere la posta) non è uscito.
Manda sempre l'evento: se l'uscita è in un orario vietato e se l'allarme è in pausa lo decide il backend.
"""

from dataclasses import dataclass
import datetime
import uuid

import numpy as np

from contratti.configurazione import TelecameraLocale
from contratti.eventi import EventoUscita, Fonte, ValoriUscita

from casa.aspetto_zona import AreaZona, RiferimentoZona
from casa.percezione import Osservazione, foto_prova
from casa.zone import zona_allargata, zona_della_persona, zone_del_tipo

# Più del tempo in cui il tracker tiene in vita una traccia persa (30 fotogrammi: 6 s a 5 fotogrammi al secondo),
# così una persona coperta un attimo dalla porta e ritrovata con lo stesso id non diventa un'uscita.
SECONDI_SPARIZIONE = 8.0
FATTORE_ZONA_PORTA = 1.5           # zona porta allargata di un quarto per lato
CONFIDENZA_PORTA = 0.5             # proposta dell'agente di allenamento: da tarare sulle riprese (nessuna dall'alto)
LATO_MODELLO_PORTA = 640           # come nell'allenamento
SECONDI_TRA_CONTROLLI_PORTA = 0.5  # il modello costa ~85 ms: basta guardare la porta ogni mezzo secondo


class ModelloPorta:
    """Rilevatore allenato della porta (classi porta_aperta, anche socchiusa, e porta_chiusa)."""

    def __init__(self, percorso: str):
        from ultralytics import YOLO  # lento da importare: solo quando serve davvero

        self.modello = YOLO(percorso)

    def __deepcopy__(self, memo: dict) -> "ModelloPorta":
        # il modello non è stato: le copie per tornare indietro di un secondo (principale.py) lo condividono
        return self

    def aperta(self, ritaglio: np.ndarray) -> bool | None:
        """True se nel ritaglio c'è una porta aperta, False se c'è solo chiusa, None se il modello non vede porte."""
        risultato = self.modello.predict(ritaglio, conf=CONFIDENZA_PORTA, imgsz=LATO_MODELLO_PORTA, device="cpu",
                                         verbose=False)[0]
        nomi = []
        for classe in risultato.boxes.cls.int().cpu().numpy():
            nomi.append(risultato.names[int(classe)])
        if "porta_aperta" in nomi:
            return True  # anche una porta socchiusa conta: meglio un allarme in più che un'uscita persa
        if "porta_chiusa" in nomi:
            return False
        return None


@dataclass
class ControlloPorta:
    ora: datetime.datetime
    aperta: bool | None


@dataclass
class Traccia:
    ora: datetime.datetime            # ultima volta vista
    confidenza: float
    zona_id: str | None               # zona porta in cui aveva i piedi l'ultima volta, None se fuori dalle porte
    porta_aperta: bool                # la porta si è aperta mentre era lì (o subito dopo che è sparita)
    immagine: np.ndarray | None       # foto di prova: davanti alla porta, se possibile con la porta aperta


class AnalizzatoreUscita:
    usa_oggetti = False

    def __init__(self, telecamera: TelecameraLocale, modello_porta: ModelloPorta | None = None):
        self.telecamera_id = telecamera.id
        self.stanza = telecamera.stanza
        self.modello_porta = modello_porta
        self.porte = []        # zone porta allargate
        self.riferimenti = {}  # id zona → RiferimentoZona ("porta chiusa"), per la regola di riserva
        for zona in zone_del_tipo(telecamera, "porta"):
            self.porte.append(zona_allargata(zona, FATTORE_ZONA_PORTA))
            self.riferimenti[zona.id] = RiferimentoZona(zona)
        self.controlli = {}    # id zona → ultimo ControlloPorta del modello
        self.tracce = {}       # id traccia → Traccia

    def porte_aperte(self, osservazione: Osservazione, zone_da_guardare: list) -> list:
        """Id delle zone porta, tra quelle da guardare, che adesso sembrano aperte."""
        box_persone = []
        for persona in osservazione.persone:
            box_persone.append(persona.box)
        aperte = []
        for zona in self.porte:
            if zona.id not in zone_da_guardare:
                continue
            if self.modello_porta is None:
                if self.riferimenti[zona.id].cambiata(osservazione.immagine, box_persone):
                    aperte.append(zona.id)
                continue
            controllo = self.controlli.get(zona.id)
            if controllo is None or (osservazione.ora - controllo.ora).total_seconds() >= SECONDI_TRA_CONTROLLI_PORTA:
                ritaglio = AreaZona(zona, osservazione.immagine).ritaglio(osservazione.immagine)
                controllo = ControlloPorta(osservazione.ora, self.modello_porta.aperta(ritaglio))
                self.controlli[zona.id] = controllo
            if controllo.aperta:
                aperte.append(zona.id)
        return aperte

    def elabora(self, osservazione: Osservazione) -> list[EventoUscita]:
        ora = osservazione.ora
        altezza = osservazione.immagine.shape[0]
        larghezza = osservazione.immagine.shape[1]
        # la porta si guarda solo dove qualcuno è davanti o è appena sparito: il modello costa
        zone_da_guardare = []
        visti = []
        for persona in osservazione.persone:
            visti.append(persona.id_traccia)
            zona = zona_della_persona(persona, self.porte, larghezza, altezza)
            if zona is not None:
                zone_da_guardare.append(zona.id)
        for id_traccia in self.tracce:
            if id_traccia not in visti and self.tracce[id_traccia].zona_id is not None:
                zone_da_guardare.append(self.tracce[id_traccia].zona_id)
        aperte = self.porte_aperte(osservazione, zone_da_guardare)

        for persona in osservazione.persone:
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

        # riferimento "porta chiusa" della regola di riserva: solo quando non c'è nessuno e nessuno è appena sparito
        # dalla porta
        if self.modello_porta is None and len(osservazione.persone) == 0 and not in_attesa_davanti_alla_porta:
            for riferimento in self.riferimenti.values():
                riferimento.aggiorna(osservazione.immagine)
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
