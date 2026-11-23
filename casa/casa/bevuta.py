"""Bevuta: ml dalla percentuale di altezza (D9, scelta di Marco), senza correzioni per la forma del contenitore.

    ml = livello_sceso_px / altezza_contenitore_px × capienza_ml

Esempio di Marco: scende 10 px su una bottiglia alta 100 px da 2 L → 10% → 200 ml.
Il controllo in pixel confronta il liquido nel contenitore prima e dopo la bevuta. Le maschere sono ritagli del box
del contenitore dritto (riga 0 = bordo alto, vero = liquido): oggi si provano con maschere sintetiche, poi
arriveranno dal modello allenato. Il riconoscimento della bevuta (contenitore in mano vicino alla bocca, D14) lo
farà l'analizzatore.
"""

import cv2
import numpy as np

from contratti.configurazione import Personalizzazione
from contratti.eventi import ValoriBevuta


def valori_bevuta(contenitore: str, capienza_ml: float, altezza_contenitore_px: float,
                  livello_sceso_px: float) -> ValoriBevuta:
    """La formula di D9, così com'è."""
    if altezza_contenitore_px <= 0:
        raise ValueError("altezza del contenitore in pixel non positiva")
    percentuale = livello_sceso_px / altezza_contenitore_px * 100
    ml = percentuale / 100 * capienza_ml
    return ValoriBevuta(
        contenitore=contenitore,
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


def valori_bevuta_da_maschere(maschera_prima: np.ndarray, maschera_dopo: np.ndarray, contenitore: str,
                              capienza_ml: float) -> ValoriBevuta | None:
    """ml bevuti confrontando il liquido prima e dopo. None se il livello non è sceso (es. contenitore riempito).

    Il contenitore rimesso giù può essere un po' più vicino o lontano: il ritaglio "dopo" si porta alla grandezza
    del ritaglio "prima", così i pixel si contano sulla stessa scala (la formula resta quella di D9)."""
    altezza = maschera_prima.shape[0]
    larghezza = maschera_prima.shape[1]
    if maschera_dopo.shape[0:2] != (altezza, larghezza):
        maschera_dopo = cv2.resize(maschera_dopo.astype(np.uint8), (larghezza, altezza),
                                   interpolation=cv2.INTER_NEAREST)
    livello_sceso = riga_del_livello(maschera_dopo) - riga_del_livello(maschera_prima)
    if livello_sceso <= 0:
        return None
    return valori_bevuta(contenitore, capienza_ml, altezza, livello_sceso)


def capienza_del_tipo(personalizzazione: Personalizzazione, tipo: str) -> int | None:
    """Capienza del primo contenitore di quel tipo impostato nell'app (bicchiere, bottiglia, tazza)."""
    for contenitore in personalizzazione.contenitori:
        if contenitore.tipo == tipo:
            return contenitore.capienza_ml
    return None
