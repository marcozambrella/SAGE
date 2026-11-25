"""Zone disegnate sul fotogramma (porta, letto, tavolo, portapillole): poligoni con coordinate da 0 a 1."""

import cv2
import numpy as np

from contratti.configurazione import TelecameraLocale, Zona

from casa.percezione import Persona


def zone_del_tipo(telecamera: TelecameraLocale, tipo: str) -> list[Zona]:
    zone = []
    for zona in telecamera.zone:
        if zona.tipo == tipo:
            zone.append(zona)
    return zone


def punto_a_terra(persona: Persona) -> tuple[float, float]:
    """Centro del lato basso del box: dove la persona poggia (pavimento, o materasso se è sdraiata).
    Con il centro del box, una persona in piedi davanti al letto sembrerebbe dentro il letto."""
    x = float(persona.box[0] + persona.box[2]) / 2
    y = float(persona.box[3])
    return x, y


def dentro_zona(x: float, y: float, zona: Zona, larghezza: int, altezza: int) -> bool:
    """Il punto (in pixel) è dentro il poligono della zona (o sul bordo)?"""
    poligono = np.array(zona.punti, np.float32) * np.array([larghezza, altezza], np.float32)
    return cv2.pointPolygonTest(poligono, (x, y), False) >= 0


def zona_della_persona(persona: Persona, zone: list[Zona], larghezza: int, altezza: int) -> Zona | None:
    """La prima zona che contiene il punto a terra della persona, o None."""
    x, y = punto_a_terra(persona)
    for zona in zone:
        if dentro_zona(x, y, zona, larghezza, altezza):
            return zona
    return None


def zona_allargata(zona: Zona, fattore: float) -> Zona:
    """La zona ingrandita intorno al suo centro (es. 1,5: un quarto in più per lato), dentro l'immagine."""
    punti = np.array(zona.punti, np.float32)
    centro = punti.mean(axis=0)
    allargati = np.clip(centro + (punti - centro) * fattore, 0, 1)
    return zona.model_copy(update={"punti": allargati.tolist()})
