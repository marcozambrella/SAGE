"""Bevuta: ml dalla percentuale di altezza (D9, scelta di Marco), senza correzioni per la forma del contenitore.

    ml = livello_sceso_px / altezza_contenitore_px × capienza_ml

Esempio di Marco: scende 10 px su una bottiglia alta 100 px da 2 L → 10% → 200 ml.
La percentuale si misura in ogni fotogramma come rapporto tra la riga del liquido e l'altezza del contenitore NELLO
STESSO fotogramma; "prima" e "dopo" si confrontano in percentuale, così non conta se il contenitore è più lontano o
più vicino (Marco, 24/11). Se il contenitore è uno della personalizzazione si manda il suo contenitore_id e il
backend ricalcola i ml con la sua capienza.

Analizzatore con regole PROVVISORIE finché non arrivano i modelli allenati (contenitori e livello del liquido):
- sorso: un contenitore del rilevatore pre-allenato (bottiglia, bicchiere, tazza) tenuto in mano vicino alla bocca
  per almeno 1 s; sorsi vicini della stessa persona (id del tracker) sono la stessa bevuta;
- livello: il bordo orizzontale più netto nel ritaglio del contenitore (dove finisce il liquido), mediana di
  qualche misura prima e dopo, solo quando il contenitore non è alla bocca.
"""

from dataclasses import dataclass
import datetime
import statistics
import uuid

import cv2
import numpy as np

from contratti.configurazione import Contenitore, Personalizzazione, TelecameraLocale
from contratti.eventi import EventoBevuta, Fonte, ValoriBevuta

from casa.percezione import Osservazione, Oggetto, Persona, foto_prova
from casa.scheletro import NASO, distanza_dal_box, misura, polsi, punto

# classe del rilevatore pre-allenato (COCO) → tipi di contenitore compatibili, nell'ordine in cui si cercano nella
# personalizzazione ("cup" in COCO comprende anche i bicchieri d'acqua)
TIPI_DA_CLASSE = {"bottle": ["bottiglia"], "wine glass": ["bicchiere"], "cup": ["tazza", "bicchiere"]}
# capienza se il contenitore non è nella personalizzazione (il backend tiene i ml del programma di casa)
CAPIENZA_PREDEFINITA = {"bottiglia": 1500, "bicchiere": 250, "tazza": 300}

FRAZIONE_SPALLE_CONTENITORE = 0.3  # bocca e mano a meno di così (× larghezza spalle) dal contenitore
SECONDI_MINIMI_ALLA_BOCCA = 1.0
SECONDI_FINE_SORSO = 2.0           # contenitore lontano dalla bocca da tanto: sorso finito
SECONDI_ATTESA_DOPO = 30.0         # tempo massimo per misurare il livello dopo il sorso
MISURE_PER_LIVELLO = 5             # mediana di tante misure, prima e dopo
SOGLIA_BORDO = 8.0                 # salto medio di grigio tra due righe per dire che il bordo del liquido si vede
MARGINE_ALTO = 0.15                # il tappo e il bordo del contenitore non sono il liquido
MARGINE_BASSO = 0.05


def valori_bevuta(contenitore: str, contenitore_id: str | None, capienza_ml: float, altezza_contenitore_px: float,
                  percentuale: float) -> ValoriBevuta:
    """Valori del contratto dalla percentuale scesa, con la formula di D9: i pixel scesi sono la percentuale
    dell'altezza del contenitore."""
    livello_sceso_px = percentuale / 100 * altezza_contenitore_px
    ml = percentuale / 100 * capienza_ml
    return ValoriBevuta(
        contenitore=contenitore,
        contenitore_id=contenitore_id,
        capienza_ml=capienza_ml,
        altezza_contenitore_px=altezza_contenitore_px,
        livello_sceso_px=livello_sceso_px,
        percentuale=percentuale,
        ml=ml,
    )


def riga_del_livello(maschera_liquido: np.ndarray) -> int:
    """Prima riga dall'alto che contiene liquido; se non c'è liquido il livello è sul fondo del ritaglio."""
    righe_con_liquido = np.flatnonzero(maschera_liquido.any(axis=1))
    if len(righe_con_liquido) == 0:
        return maschera_liquido.shape[0]
    return int(righe_con_liquido[0])


def frazione_piena(maschera_liquido: np.ndarray) -> float:
    """Parte dell'altezza del contenitore piena di liquido in questo fotogramma (0-1). La maschera è il ritaglio del
    box del contenitore (riga 0 = bordo alto, vero = liquido): servirà quando il modello darà la maschera."""
    altezza = maschera_liquido.shape[0]
    return (altezza - riga_del_livello(maschera_liquido)) / altezza


def percentuale_scesa(frazione_prima: float, frazione_dopo: float) -> float:
    """Percentuale dell'altezza del contenitore di cui è sceso il liquido (0 se non è sceso)."""
    return max(0.0, (frazione_prima - frazione_dopo) * 100)


def frazione_piena_dai_bordi(immagine: np.ndarray, box: np.ndarray) -> float | None:
    """Controllo in pixel provvisorio: la riga del liquido è il bordo orizzontale più netto nella parte centrale del
    contenitore. None se il contenitore è troppo piccolo o il bordo non si vede (es. tazza non trasparente)."""
    altezza_immagine = immagine.shape[0]
    larghezza_immagine = immagine.shape[1]
    x1 = max(int(box[0]), 0)
    y1 = max(int(box[1]), 0)
    x2 = min(int(box[2]), larghezza_immagine)
    y2 = min(int(box[3]), altezza_immagine)
    altezza = y2 - y1
    larghezza = x2 - x1
    if altezza < 20 or larghezza < 8:
        return None
    grigio = cv2.cvtColor(immagine[y1:y2, x1:x2], cv2.COLOR_BGR2GRAY).astype(np.float32)
    centrale = grigio[:, larghezza // 4:larghezza - larghezza // 4]
    # salto di grigio tra ogni riga e quella sotto, in media sulla parte centrale
    salti = np.abs(np.diff(centrale, axis=0)).mean(axis=1)
    prima_riga = int(altezza * MARGINE_ALTO)
    ultima_riga = int(altezza * (1 - MARGINE_BASSO))
    if ultima_riga <= prima_riga:
        return None
    riga = prima_riga + int(np.argmax(salti[prima_riga:ultima_riga]))
    if salti[riga] < SOGLIA_BORDO:
        return None
    # il salto è tra la riga e quella sotto: il liquido comincia alla riga dopo
    return (altezza - (riga + 1)) / altezza


def contenitore_della_personalizzazione(personalizzazione: Personalizzazione, classe: str) -> Contenitore | None:
    for tipo in TIPI_DA_CLASSE[classe]:
        for contenitore in personalizzazione.contenitori:
            if contenitore.tipo == tipo:
                return contenitore
    return None


@dataclass
class MisuraLivello:
    frazione: float
    altezza_px: float


@dataclass
class Sorso:
    inizio: datetime.datetime
    ultima_alla_bocca: datetime.datetime
    classe: str
    confidenza: float
    altezza_px: float          # altezza del contenitore l'ultima volta che si è visto (se il livello non si misura)
    prima: list                # MisuraLivello prima della bevuta
    dopo: list                 # MisuraLivello dopo
    finito: bool               # contenitore lontano dalla bocca: si aspettano le misure dopo
    immagine: np.ndarray


def alla_bocca(persona: Persona, contenitore: Oggetto) -> bool:
    """Il contenitore tocca la bocca (naso) ed è tenuto in mano."""
    naso = punto(persona, NASO)
    if naso is None:
        return False
    vicino = FRAZIONE_SPALLE_CONTENITORE * misura(persona)
    if distanza_dal_box(naso, contenitore.box) > vicino:
        return False
    for polso in polsi(persona):
        if distanza_dal_box(polso, contenitore.box) <= vicino:
            return True
    return False


class AnalizzatoreBevuta:
    usa_oggetti = True

    def __init__(self, telecamera: TelecameraLocale, personalizzazione: Personalizzazione):
        self.telecamera_id = telecamera.id
        self.stanza = telecamera.stanza
        self.personalizzazione = personalizzazione
        self.misure_recenti = {}  # classe → ultime MisuraLivello dei contenitori lontani dalla bocca
        self.sorsi = {}           # id traccia → Sorso in corso

    def elabora(self, osservazione: Osservazione) -> list[EventoBevuta]:
        ora = osservazione.ora
        contenitori_alla_bocca = {}  # id traccia → contenitore
        lontani = []
        for oggetto in osservazione.oggetti:
            if oggetto.classe not in TIPI_DA_CLASSE:
                continue
            bevitore = None
            for persona in osservazione.persone:
                if alla_bocca(persona, oggetto):
                    bevitore = persona
            if bevitore is None:
                lontani.append(oggetto)
            else:
                contenitori_alla_bocca[bevitore.id_traccia] = oggetto

        for oggetto in lontani:
            self.misura_livello(osservazione.immagine, oggetto)

        for persona in osservazione.persone:
            if persona.id_traccia not in contenitori_alla_bocca:
                continue
            oggetto = contenitori_alla_bocca[persona.id_traccia]
            confidenza = min(persona.confidenza, oggetto.confidenza)
            altezza = float(oggetto.box[3] - oggetto.box[1])
            sorso = self.sorsi.get(persona.id_traccia)
            if sorso is None:
                prima = list(self.misure_recenti.get(oggetto.classe, []))
                sorso = Sorso(ora, ora, oggetto.classe, confidenza, altezza, prima, [], False, osservazione.immagine)
                self.sorsi[persona.id_traccia] = sorso
            # un altro sorso prima di rimettere giù il contenitore: è la stessa bevuta
            sorso.ultima_alla_bocca = ora
            sorso.finito = False
            sorso.dopo = []
            sorso.confidenza = max(sorso.confidenza, confidenza)

        eventi = []
        chiusi = []
        for id_traccia in self.sorsi:
            sorso = self.sorsi[id_traccia]
            lontano_da = (ora - sorso.ultima_alla_bocca).total_seconds()
            if not sorso.finito and lontano_da >= SECONDI_FINE_SORSO:
                sorso.finito = True
                if (sorso.ultima_alla_bocca - sorso.inizio).total_seconds() < SECONDI_MINIMI_ALLA_BOCCA:
                    chiusi.append(id_traccia)  # troppo breve: non era un sorso
                    continue
            if sorso.finito and (len(sorso.dopo) >= MISURE_PER_LIVELLO or lontano_da >= SECONDI_ATTESA_DOPO):
                eventi.append(self.evento(sorso))
                chiusi.append(id_traccia)
        for id_traccia in chiusi:
            self.sorsi.pop(id_traccia)
        return eventi

    def misura_livello(self, immagine: np.ndarray, oggetto: Oggetto) -> None:
        frazione = frazione_piena_dai_bordi(immagine, oggetto.box)
        if frazione is None:
            return
        nuova = MisuraLivello(frazione, float(oggetto.box[3] - oggetto.box[1]))
        recenti = self.misure_recenti.get(oggetto.classe, [])
        recenti.append(nuova)
        self.misure_recenti[oggetto.classe] = recenti[-MISURE_PER_LIVELLO:]
        for sorso in self.sorsi.values():
            if sorso.finito and sorso.classe == oggetto.classe:
                sorso.dopo.append(nuova)

    def fine(self) -> list[EventoBevuta]:
        eventi = []
        for sorso in self.sorsi.values():
            if (sorso.ultima_alla_bocca - sorso.inizio).total_seconds() >= SECONDI_MINIMI_ALLA_BOCCA:
                eventi.append(self.evento(sorso))
        self.sorsi = {}
        return eventi

    def evento(self, sorso: Sorso) -> EventoBevuta:
        confidenza = sorso.confidenza
        altezza = sorso.altezza_px
        percentuale = 0.0
        if len(sorso.prima) > 0 and len(sorso.dopo) > 0:
            frazioni_prima = []
            altezze_prima = []
            for misura_prima in sorso.prima:
                frazioni_prima.append(misura_prima.frazione)
                altezze_prima.append(misura_prima.altezza_px)
            frazioni_dopo = []
            for misura_dopo in sorso.dopo:
                frazioni_dopo.append(misura_dopo.frazione)
            percentuale = percentuale_scesa(statistics.median(frazioni_prima), statistics.median(frazioni_dopo))
            altezza = statistics.median(altezze_prima)
        else:
            # bevuta vista ma livello non misurato (es. tazza non trasparente): 0 ml e confidenza dimezzata
            confidenza = confidenza / 2
            print("telecamera " + self.telecamera_id + ": bevuta vista, livello non misurato")
        contenitore = contenitore_della_personalizzazione(self.personalizzazione, sorso.classe)
        if contenitore is None:
            tipo = TIPI_DA_CLASSE[sorso.classe][0]
            valori = valori_bevuta(tipo, None, CAPIENZA_PREDEFINITA[tipo], altezza, percentuale)
        else:
            valori = valori_bevuta(contenitore.tipo, contenitore.id, contenitore.capienza_ml, altezza, percentuale)
        fonte = Fonte(telecamera_id=self.telecamera_id, analizzatore="bevuta", confidenza=confidenza)
        return EventoBevuta(
            id=str(uuid.uuid4()),
            tipo="bevuta",
            inizio=sorso.inizio,
            fine=sorso.ultima_alla_bocca,
            stanza=self.stanza,
            confidenza=confidenza,
            fonti=[fonte],
            foto_prova=foto_prova(sorso.immagine),
            valori=valori,
        )
