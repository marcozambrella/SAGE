"""Geometria dello scheletro (17 punti COCO della posa YOLO) per la regola dei gesti (bevuta e farmaco) e per la
geometria delle cadute."""

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

# Regola dei gesti (Marco, 25/11: nessun modello del gesto): un polso vicino al naso, di fila, + l'oggetto del
# rilevatore vicino alla testa (bicchiere o bottiglia: bevuta; scatola, blister o pillola: farmaco). Soglie del polso
# dall'agente di allenamento, tarate su Charades (25/11).
FRAZIONE_ALTEZZA_POLSO_NASO = 0.25   # polso dal naso, in altezze del box della persona
# dal primo all'ultimo fotogramma del gesto: 5 fotogrammi di fila a 5 al secondo (1 s nella taratura)
SECONDI_GESTO = 0.8
# box dell'oggetto dal naso, in altezze del box della persona come il polso (di lato le spalle sembrano strette):
# sono le 0,3 larghezze di spalle di prima, con le spalle a 0,14 dell'altezza (mediana su 47 mila scheletri in piedi
# dei dataset pubblici delle cadute, posa n). La tara su Charades l'agente di allenamento (25/11)
FRAZIONE_ALTEZZA_OGGETTO_TESTA = 0.04


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


def mano_alla_bocca(persona: Persona) -> bool:
    """Un polso vicino al naso (la bocca non è tra i punti della posa; il naso è il più vicino)."""
    naso = punto(persona, NASO)
    if naso is None:
        return False
    altezza = float(persona.box[3] - persona.box[1])
    for polso in polsi(persona):
        if distanza(naso, polso) < FRAZIONE_ALTEZZA_POLSO_NASO * altezza:
            return True
    return False


def oggetto_alla_testa(persona: Persona, box: np.ndarray) -> bool:
    """Il box dell'oggetto (x1, y1, x2, y2 in pixel) tocca quasi il naso."""
    naso = punto(persona, NASO)
    if naso is None:
        return False
    altezza = float(persona.box[3] - persona.box[1])
    return distanza_dal_box(naso, box) <= FRAZIONE_ALTEZZA_OGGETTO_TESTA * altezza


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
