"""Bevuta: ml dalla percentuale di altezza (D9, scelta di Marco), senza correzioni per la forma del contenitore.

    ml = livello_sceso_px / altezza_contenitore_px × capienza_ml

Esempio di Marco: scende 10 px su una bottiglia alta 100 px da 2 L → 10% → 200 ml.
La percentuale si misura in ogni fotogramma come rapporto tra la riga del liquido e l'altezza del contenitore NELLO
STESSO fotogramma; "prima" e "dopo" si confrontano in percentuale, così non conta se il contenitore è più lontano o
più vicino (Marco, 24/11). Se il contenitore è uno della personalizzazione si manda il suo contenitore_id e il
backend ricalcola i ml con la sua capienza.

Il contenitore viene dal rilevatore pre-allenato (COCO). Il livello si trova SOLO con un controllo sui pixel: non
arriverà nessun modello del liquido (Marco, 24/11). Regola PROVVISORIA finché non arriva il modello del gesto:
- sorso: un contenitore (bottiglia, bicchiere, tazza) tenuto in mano vicino alla bocca per almeno 1 s; sorsi vicini
  della stessa persona (id del tracker) sono la stessa bevuta;
- livello: la riga orizzontale che divide il contenitore in aria sopra e liquido sotto, mediana di qualche misura
  prima e dopo, solo quando il contenitore è appoggiato (in mano può essere inclinato o coperto dalle dita);
- se il livello non si vede (tazza non trasparente, contenitore troppo lontano o sempre in mano) la bevuta si manda
  lo stesso, con 0 ml e confidenza dimezzata.
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
SECONDI_ATTESA_DOPO = 60.0         # tempo massimo per misurare il livello dopo il sorso (si aspetta che lo appoggi)
MISURE_PER_LIVELLO = 5             # mediana di tante misure, prima e dopo

# Controllo sui pixel del livello. Il ritaglio si porta sempre a 100 righe (una riga = 1% dell'altezza): soglie e
# margini valgono uguali da vicino e da lontano.
RIGHE_NORMALIZZATE = 100
STRISCE = 3                        # la riga del liquido deve attraversare tutta la larghezza del contenitore
ALTEZZA_MINIMA_PX = 16             # più piccolo di così, da lontano, una riga di pixel vale più del 6%
LARGHEZZA_MINIMA_PX = 6
# il tappo della bottiglia e il bordo di bicchiere e tazza non sono il liquido; in basso il fondo fa un bordo suo
MARGINE_ALTO = {"bottle": 0.12, "wine glass": 0.05, "cup": 0.05}
MARGINE_BASSO = 0.05
RIGHE_MINIME_PER_PARTE = 4         # aria e liquido alti almeno il 4%
SALTO_MINIMO_COLORE = 8.0          # differenza di colore (Lab) tra aria e liquido per dire che la riga si vede
QUOTA_SPIEGATA_MINIMA = 0.5        # "aria sopra, liquido sotto" deve spiegare almeno metà delle differenze tra righe
RIGHE_SALTO_VICINO = 8             # righe sopra e sotto la riga del liquido per misurare il salto vicino
RIGHE_SFOCATE = 2                  # righe vicinissime alla riga, sfocate (soprattutto da lontano): non si usano
SALTO_VICINO_MINIMO = 0.5          # salto vicino / salto tra le due parti: poco = sfumatura, tanto = una striscia
SALTO_VICINO_MASSIMO = 1.5
FRAZIONE_SALTO_STRISCIA = 0.5      # in ogni striscia il salto è almeno metà di quello su tutta la larghezza


def valori_bevuta(contenitore: str, contenitore_id: str | None, capienza_ml: float, altezza_contenitore_px: float,
                  percentuale: float, livello_visibile: bool) -> ValoriBevuta:
    """Valori del contratto dalla percentuale scesa, con la formula di D9: i pixel scesi sono la percentuale
    dell'altezza del contenitore. Se il livello non era visibile la percentuale è 0 e vuol dire "non misurato"."""
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
        livello_visibile=livello_visibile,
    )


def percentuale_scesa(frazione_prima: float, frazione_dopo: float) -> float:
    """Percentuale dell'altezza del contenitore di cui è sceso il liquido (0 se non è sceso)."""
    return max(0.0, (frazione_prima - frazione_dopo) * 100)


def colori_delle_righe(immagine: np.ndarray, box: np.ndarray) -> np.ndarray | None:
    """Colore medio (Lab) di ogni riga del contenitore, in STRISCE strisce verticali della metà centrale (i lati sono
    sfondo o bordi del vetro), portato a RIGHE_NORMALIZZATE righe. None se il contenitore è troppo piccolo."""
    altezza_immagine = immagine.shape[0]
    larghezza_immagine = immagine.shape[1]
    x1 = max(int(round(float(box[0]))), 0)
    y1 = max(int(round(float(box[1]))), 0)
    x2 = min(int(round(float(box[2]))), larghezza_immagine)
    y2 = min(int(round(float(box[3]))), altezza_immagine)
    altezza = y2 - y1
    larghezza = x2 - x1
    if altezza < ALTEZZA_MINIMA_PX or larghezza < LARGHEZZA_MINIMA_PX:
        return None
    centrale = immagine[y1:y2, x1 + larghezza // 4:x2 - larghezza // 4]
    lab = cv2.cvtColor(centrale, cv2.COLOR_BGR2LAB).astype(np.float32)
    colori = []
    for striscia in np.array_split(lab, STRISCE, axis=1):
        colori.append(striscia.mean(axis=1))  # (altezza, 3): colore medio di ogni riga della striscia
    tutte = np.concatenate(colori, axis=1)
    # da vicino si rimpicciolisce facendo la media delle righe (meno rumore), da lontano si ingrandisce
    if altezza > RIGHE_NORMALIZZATE:
        metodo = cv2.INTER_AREA
    else:
        metodo = cv2.INTER_LINEAR
    normalizzate = cv2.resize(tutte, (tutte.shape[1], RIGHE_NORMALIZZATE), interpolation=metodo)
    return normalizzate.reshape(RIGHE_NORMALIZZATE, STRISCE, 3)


def differenza_di_colore(sopra: np.ndarray, sotto: np.ndarray) -> float:
    """Distanza tra il colore medio di due gruppi di righe."""
    return float(np.linalg.norm(sopra.mean(axis=0) - sotto.mean(axis=0)))


def frazione_piena_dai_pixel(immagine: np.ndarray, box: np.ndarray, classe: str) -> float | None:
    """Parte dell'altezza del contenitore piena di liquido in questo fotogramma (0-1), dai soli pixel: la riga del
    liquido divide il contenitore in due parti di colore uniforme, aria sopra e liquido sotto. Si prova ogni riga e
    si tiene quella che separa meglio le due parti (come la soglia di Otsu, ma sulle righe).
    None se la riga non si vede: tazza non trasparente, contenitore troppo lontano, disegni o etichette."""
    righe_colori = colori_delle_righe(immagine, box)
    if righe_colori is None:
        return None
    prima_riga = int(RIGHE_NORMALIZZATE * MARGINE_ALTO[classe])
    ultima_riga = int(RIGHE_NORMALIZZATE * (1 - MARGINE_BASSO))
    zona = righe_colori[prima_riga:ultima_riga]
    centro = zona.mean(axis=1)  # colore medio di ogni riga su tutta la larghezza
    righe = len(centro)
    media = centro.mean(axis=0)
    variazione_totale = float(((centro - media) ** 2).sum())
    riga_migliore = None
    spiegata_migliore = 0.0
    for riga in range(RIGHE_MINIME_PER_PARTE, righe - RIGHE_MINIME_PER_PARTE + 1):
        media_sopra = centro[:riga].mean(axis=0)
        media_sotto = centro[riga:].mean(axis=0)
        # quanto delle differenze tra le righe si spiega con "due parti uniformi" divise qui
        spiegata_sopra = riga * float(((media_sopra - media) ** 2).sum())
        spiegata_sotto = (righe - riga) * float(((media_sotto - media) ** 2).sum())
        if spiegata_sopra + spiegata_sotto > spiegata_migliore:
            spiegata_migliore = spiegata_sopra + spiegata_sotto
            riga_migliore = riga
    if riga_migliore is None:
        return None
    salto = differenza_di_colore(centro[:riga_migliore], centro[riga_migliore:])
    if salto < SALTO_MINIMO_COLORE:
        return None  # nessuna riga si vede (es. tazza non trasparente tutta di un colore)
    if spiegata_migliore / variazione_totale < QUOTA_SPIEGATA_MINIMA:
        return None  # non sono due parti uniformi (disegni, etichette, mano davanti)
    # il salto vicino alla riga deve essere quello tra le due parti: se è molto più piccolo è una sfumatura (luce
    # sulla tazza), se è molto più grande è una striscia
    vicino_sopra = centro[max(riga_migliore - RIGHE_SALTO_VICINO, 0):riga_migliore - RIGHE_SFOCATE]
    vicino_sotto = centro[riga_migliore + RIGHE_SFOCATE:riga_migliore + RIGHE_SALTO_VICINO]
    salto_vicino = differenza_di_colore(vicino_sopra, vicino_sotto) / salto
    if salto_vicino < SALTO_VICINO_MINIMO or salto_vicino > SALTO_VICINO_MASSIMO:
        return None
    for striscia in range(STRISCE):
        salto_striscia = differenza_di_colore(zona[:riga_migliore, striscia], zona[riga_migliore:, striscia])
        if salto_striscia < FRAZIONE_SALTO_STRISCIA * salto:
            return None  # la riga non attraversa tutto il contenitore (riflesso, disegno)
    riga_del_liquido = prima_riga + riga_migliore
    return (RIGHE_NORMALIZZATE - riga_del_liquido) / RIGHE_NORMALIZZATE


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


def in_mano(persona: Persona, contenitore: Oggetto) -> bool:
    vicino = FRAZIONE_SPALLE_CONTENITORE * misura(persona)
    for polso in polsi(persona):
        if distanza_dal_box(polso, contenitore.box) <= vicino:
            return True
    return False


def alla_bocca(persona: Persona, contenitore: Oggetto) -> bool:
    """Il contenitore tocca la bocca (naso) ed è tenuto in mano."""
    naso = punto(persona, NASO)
    if naso is None:
        return False
    vicino = FRAZIONE_SPALLE_CONTENITORE * misura(persona)
    if distanza_dal_box(naso, contenitore.box) > vicino:
        return False
    return in_mano(persona, contenitore)


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
        appoggiati = []
        for oggetto in osservazione.oggetti:
            if oggetto.classe not in TIPI_DA_CLASSE:
                continue
            bevitore = None
            tenuto = False
            for persona in osservazione.persone:
                if alla_bocca(persona, oggetto):
                    bevitore = persona
                if in_mano(persona, oggetto):
                    tenuto = True
            if bevitore is not None:
                contenitori_alla_bocca[bevitore.id_traccia] = oggetto
            elif not tenuto:
                appoggiati.append(oggetto)

        # il livello si misura solo sui contenitori appoggiati: in mano possono essere inclinati o coperti dalle dita
        for oggetto in appoggiati:
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
        frazione = frazione_piena_dai_pixel(immagine, oggetto.box, oggetto.classe)
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
        livello_visibile = len(sorso.prima) > 0 and len(sorso.dopo) > 0
        if livello_visibile:
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
            # bevuta vista ma livello non visibile: 0 ml, confidenza dimezzata e livello_visibile False, così la web
            # app non lo confonde con "non ha bevuto niente"
            confidenza = confidenza / 2
            print("telecamera " + self.telecamera_id + ": bevuta vista, livello del liquido non visibile "
                  "(contenitore non trasparente, troppo lontano o sempre in mano)")
        contenitore = contenitore_della_personalizzazione(self.personalizzazione, sorso.classe)
        if contenitore is None:
            tipo = TIPI_DA_CLASSE[sorso.classe][0]
            capienza = CAPIENZA_PREDEFINITA[tipo]
            valori = valori_bevuta(tipo, None, capienza, altezza, percentuale, livello_visibile)
        else:
            capienza = contenitore.capienza_ml
            valori = valori_bevuta(contenitore.tipo, contenitore.id, capienza, altezza, percentuale, livello_visibile)
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
