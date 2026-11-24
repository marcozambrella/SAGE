"""Test della regola provvisoria "la zona ha cambiato aspetto" (porta aperta, portapillole aperto)."""

import numpy as np

from contratti.configurazione import Zona

from casa.aspetto_zona import RiferimentoZona

# zona nel quarto sinistro di un'immagine 200×100
ZONA = Zona(id="porta", tipo="porta", punti=[[0, 0], [0.25, 0], [0.25, 1], [0, 1]])


def immagine(valore_zona: int, valore_stanza: int = 80) -> np.ndarray:
    risultato = np.full((100, 200, 3), valore_stanza, np.uint8)
    risultato[:, 0:50] = valore_zona
    return risultato


def test_senza_riferimento_non_si_sa():
    assert RiferimentoZona(ZONA).cambiata(immagine(100), []) is None


def test_uguale_e_cambiata():
    riferimento = RiferimentoZona(ZONA)
    riferimento.aggiorna(immagine(100))
    assert riferimento.cambiata(immagine(100), []) is False
    assert riferimento.cambiata(immagine(200), []) is True
    # fuori dalla zona non conta
    assert riferimento.cambiata(immagine(100, valore_stanza=250), []) is False


def test_la_persona_davanti_non_conta():
    riferimento = RiferimentoZona(ZONA)
    riferimento.aggiorna(immagine(100))
    con_persona = immagine(100)
    con_persona[10:90, 10:30] = 0  # la persona copre un pezzo della porta
    box = np.array([10, 10, 30, 90], np.float32)
    assert riferimento.cambiata(con_persona, [box]) is False


def test_zona_tutta_coperta_non_si_sa():
    riferimento = RiferimentoZona(ZONA)
    riferimento.aggiorna(immagine(100))
    box = np.array([0, 0, 60, 100], np.float32)
    assert riferimento.cambiata(immagine(200), [box]) is None


def test_il_riferimento_segue_la_luce():
    riferimento = RiferimentoZona(ZONA)
    riferimento.aggiorna(immagine(100))
    # la luce cambia piano piano (sera): il riferimento la segue e non sembra una porta aperta
    for passo in range(100):
        riferimento.aggiorna(immagine(140))
    assert riferimento.cambiata(immagine(140), []) is False
