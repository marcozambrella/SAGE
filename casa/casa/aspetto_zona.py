"""Regola PROVVISORIA "la zona ha cambiato aspetto": porta aperta, portapillole aperto.

Si tiene un riferimento della zona com'è di solito (porta chiusa, portapillole chiuso), preso quando nessuno ci sta
davanti e aggiornato piano per seguire la luce del giorno. Una zona è "cambiata" quando una buona parte dei suoi
pixel, tolti quelli coperti dalle persone, è diversa dal riferimento. Quando arrivano i modelli allenati
(porta aperta/chiusa, rilevatore farmaci_det) prendono il posto di questa regola.
"""

import cv2
import numpy as np

from contratti.configurazione import Zona

SOGLIA_PIXEL = 25               # differenza in toni di grigio (0-255) perché un pixel conti come cambiato
FRAZIONE_CAMBIATA = 0.3         # parte della zona visibile che deve cambiare
FRAZIONE_MINIMA_VISIBILE = 0.2  # se le persone coprono più di così la zona, non si giudica
PESO_AGGIORNAMENTO = 0.05       # quanto conta il fotogramma nuovo nel riferimento (media che segue la luce)


class AreaZona:
    """Il poligono della zona in pixel: il riquadro che lo contiene e la maschera dei suoi pixel."""

    def __init__(self, zona: Zona, immagine: np.ndarray):
        altezza = immagine.shape[0]
        larghezza = immagine.shape[1]
        punti = np.array(zona.punti, np.float32) * np.array([larghezza, altezza], np.float32)
        punti = np.round(punti).astype(np.int32)
        self.x1 = max(int(punti[:, 0].min()), 0)
        self.y1 = max(int(punti[:, 1].min()), 0)
        self.x2 = min(int(punti[:, 0].max()) + 1, larghezza)
        self.y2 = min(int(punti[:, 1].max()) + 1, altezza)
        maschera = np.zeros((self.y2 - self.y1, self.x2 - self.x1), np.uint8)
        cv2.fillPoly(maschera, [punti - np.array([self.x1, self.y1], np.int32)], 1)
        self.maschera = maschera.astype(bool)  # True dentro il poligono, nelle coordinate del riquadro

    def ritaglio(self, immagine: np.ndarray) -> np.ndarray:
        return immagine[self.y1:self.y2, self.x1:self.x2]

    def dentro_i_box(self, box: list) -> np.ndarray:
        """True nei pixel del riquadro coperti da almeno uno dei box (x1, y1, x2, y2 in pixel dell'immagine)."""
        coperti = np.zeros(self.maschera.shape, bool)
        for un_box in box:
            bx1 = int(max(un_box[0] - self.x1, 0))
            by1 = int(max(un_box[1] - self.y1, 0))
            bx2 = int(min(un_box[2] - self.x1, self.x2 - self.x1))
            by2 = int(min(un_box[3] - self.y1, self.y2 - self.y1))
            if bx2 > bx1 and by2 > by1:
                coperti[by1:by2, bx1:bx2] = True
        return coperti

    def visibili(self, box_persone: list) -> np.ndarray:
        """Pixel della zona non coperti dalle persone."""
        return self.maschera & ~self.dentro_i_box(box_persone)


class RiferimentoZona:
    def __init__(self, zona: Zona):
        self.zona = zona
        self.area = None          # AreaZona, al primo fotogramma
        self.riferimento = None   # toni di grigio del riquadro, com'è di solito

    def grigio(self, immagine: np.ndarray) -> np.ndarray:
        if self.area is None:
            self.area = AreaZona(self.zona, immagine)
        ritaglio = cv2.cvtColor(self.area.ritaglio(immagine), cv2.COLOR_BGR2GRAY)
        # sfocato: il rumore della telecamera non deve sembrare un cambiamento
        ritaglio = cv2.GaussianBlur(ritaglio, (5, 5), 0)
        return ritaglio.astype(np.float32)

    def aggiorna(self, immagine: np.ndarray) -> None:
        """Da chiamare quando nessuno sta davanti alla zona (quindi è com'è di solito)."""
        grigio = self.grigio(immagine)
        if self.riferimento is None:
            self.riferimento = grigio
        else:
            self.riferimento = (1 - PESO_AGGIORNAMENTO) * self.riferimento + PESO_AGGIORNAMENTO * grigio

    def cambiata(self, immagine: np.ndarray, box_persone: list) -> bool | None:
        """True se la zona è diversa dal riferimento; None se non si può dire (niente riferimento, zona coperta)."""
        if self.riferimento is None:
            return None
        grigio = self.grigio(immagine)
        diversi = np.abs(grigio - self.riferimento) > SOGLIA_PIXEL
        # i pixel coperti dalle persone non contano: la persona davanti alla porta non è la porta aperta
        visibili = self.area.visibili(box_persone)
        quanti_visibili = int(visibili.sum())
        if quanti_visibili < FRAZIONE_MINIMA_VISIBILE * int(self.area.maschera.sum()):
            return None
        quanti_diversi = int((diversi & visibili).sum())
        return quanti_diversi >= FRAZIONE_CAMBIATA * quanti_visibili
