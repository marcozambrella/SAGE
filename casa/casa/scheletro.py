"""Geometria dello scheletro (17 punti COCO della posa YOLO) per le regole provvisorie di bevuta, farmaco e caduta,
finché non arrivano i classificatori allenati sugli scheletri."""

import math

import numpy as np

from casa.percezione import Persona

NASO = 0
SPALLA_SX = 5
SPALLA_DX = 6
POLSO_SX = 9
POLSO_DX = 10
ANCA_SX = 11
ANCA_DX = 12
CAVIGLIA_SX = 15
CAVIGLIA_DX = 16

VISIBILITA_MINIMA = 0.3       # sotto questa confidenza il punto non si usa
# "vicino alla bocca": entro questa parte della larghezza delle spalle (circa 40 cm → ~25 cm)
FRAZIONE_SPALLE_BOCCA = 0.6


def punto(persona: Persona, indice: int) -> np.ndarray | None:
    """(x, y) in pixel del punto, o None se la posa non lo vede bene."""
    if persona.keypoint[indice, 2] < VISIBILITA_MINIMA:
        return None
    return persona.keypoint[indice, 0:2]


def media_dei_punti(persona: Persona, indici: list) -> np.ndarray | None:
    visti = []
    for indice in indici:
        punto_visto = punto(persona, indice)
        if punto_visto is not None:
            visti.append(punto_visto)
    if len(visti) == 0:
        return None
    return np.mean(np.stack(visti), axis=0)


def distanza(punto_a: np.ndarray, punto_b: np.ndarray) -> float:
    return float(np.linalg.norm(punto_a - punto_b))


def misura(persona: Persona) -> float:
    """Scala della persona in pixel: larghezza delle spalle, o un quarto dell'altezza del box se non si vedono."""
    spalla_sx = punto(persona, SPALLA_SX)
    spalla_dx = punto(persona, SPALLA_DX)
    if spalla_sx is not None and spalla_dx is not None:
        larghezza = distanza(spalla_sx, spalla_dx)
        if larghezza > 10:
            return larghezza
    return float(persona.box[3] - persona.box[1]) / 4


def polsi(persona: Persona) -> list:
    risultato = []
    for indice in (POLSO_SX, POLSO_DX):
        polso = punto(persona, indice)
        if polso is not None:
            risultato.append(polso)
    return risultato


def vicino_alla_bocca(persona: Persona, posizione: np.ndarray) -> bool:
    """La posizione (es. un polso o un contenitore) è vicina alla bocca (il naso, il punto più vicino)?"""
    naso = punto(persona, NASO)
    if naso is None:
        return False
    return distanza(naso, posizione) <= FRAZIONE_SPALLE_BOCCA * misura(persona)


def mano_alla_bocca(persona: Persona) -> bool:
    for polso in polsi(persona):
        if vicino_alla_bocca(persona, polso):
            return True
    return False


def angolo_del_busto(persona: Persona) -> float | None:
    """Gradi del busto (dal centro delle anche al centro delle spalle) rispetto alla verticale: 0 in piedi,
    90 sdraiato. None se la posa non vede spalle o anche."""
    spalle = media_dei_punti(persona, [SPALLA_SX, SPALLA_DX])
    anche = media_dei_punti(persona, [ANCA_SX, ANCA_DX])
    if spalle is None or anche is None:
        return None
    dx = float(spalle[0] - anche[0])
    dy = float(anche[1] - spalle[1])  # in su è positivo (le y dell'immagine crescono in giù)
    if dx == 0 and dy == 0:
        return None
    return math.degrees(math.atan2(abs(dx), dy))


def distanza_dal_box(posizione: np.ndarray, box: np.ndarray) -> float:
    """Distanza in pixel da un punto al rettangolo x1, y1, x2, y2 (0 se il punto è dentro)."""
    dx = max(float(box[0]) - float(posizione[0]), 0.0, float(posizione[0]) - float(box[2]))
    dy = max(float(box[1]) - float(posizione[1]), 0.0, float(posizione[1]) - float(box[3]))
    return math.hypot(dx, dy)
