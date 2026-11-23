"""Test del calcolo dei ml della bevuta (D9) con maschere sintetiche."""

import numpy as np
import pytest

from contratti.configurazione import Personalizzazione

from casa.bevuta import capienza_del_tipo, riga_del_livello, valori_bevuta, valori_bevuta_da_maschere


def maschera_liquido(altezza: int, larghezza: int, riga_livello: int) -> np.ndarray:
    """Ritaglio del contenitore con il liquido dalla riga del livello fino al fondo."""
    maschera = np.zeros((altezza, larghezza), bool)
    maschera[riga_livello:, 2:larghezza - 2] = True
    return maschera


def test_esempio_di_marco():
    # scende 10 px su una bottiglia alta 100 px da 2 L → 10% → 200 ml
    valori = valori_bevuta("bottiglia", 2000, 100, 10)
    assert valori.percentuale == pytest.approx(10)
    assert valori.ml == pytest.approx(200)
    assert valori.contenitore == "bottiglia"
    assert valori.altezza_contenitore_px == 100
    assert valori.livello_sceso_px == 10


def test_bicchiere_mezzo():
    valori = valori_bevuta("bicchiere", 250, 80, 40)
    assert valori.percentuale == pytest.approx(50)
    assert valori.ml == pytest.approx(125)


def test_altezza_zero_rifiutata():
    with pytest.raises(ValueError):
        valori_bevuta("tazza", 300, 0, 5)


def test_riga_del_livello():
    assert riga_del_livello(maschera_liquido(100, 30, 20)) == 20
    # contenitore vuoto: livello sul fondo
    assert riga_del_livello(np.zeros((100, 30), bool)) == 100


def test_maschere_prima_e_dopo():
    prima = maschera_liquido(100, 30, 20)
    dopo = maschera_liquido(100, 30, 30)
    valori = valori_bevuta_da_maschere(prima, dopo, "bottiglia", 2000)
    assert valori.livello_sceso_px == 10
    assert valori.altezza_contenitore_px == 100
    assert valori.ml == pytest.approx(200)


def test_bevuto_tutto():
    prima = maschera_liquido(100, 30, 60)
    dopo = np.zeros((100, 30), bool)
    valori = valori_bevuta_da_maschere(prima, dopo, "bicchiere", 250)
    assert valori.percentuale == pytest.approx(40)
    assert valori.ml == pytest.approx(100)


def test_contenitore_rimesso_piu_vicino():
    # dopo la bevuta la bottiglia è più vicina: ritaglio alto 200 px invece di 100, livello alla riga 60 (= 30 su 100)
    prima = maschera_liquido(100, 30, 20)
    dopo = maschera_liquido(200, 60, 60)
    valori = valori_bevuta_da_maschere(prima, dopo, "bottiglia", 2000)
    assert valori.livello_sceso_px == 10
    assert valori.ml == pytest.approx(200)


def test_livello_salito_non_e_bevuta():
    prima = maschera_liquido(100, 30, 50)
    dopo = maschera_liquido(100, 30, 10)
    assert valori_bevuta_da_maschere(prima, dopo, "bottiglia", 2000) is None
    assert valori_bevuta_da_maschere(prima, prima, "bottiglia", 2000) is None


def test_capienza_dalla_personalizzazione():
    personalizzazione = Personalizzazione.model_validate({
        "anziano": {"nome": "Anna"},
        "contenitori": [
            {"id": "b", "nome": "Water bottle", "tipo": "bottiglia", "capienza_ml": 1500},
            {"id": "t", "nome": "Mug", "tipo": "tazza", "capienza_ml": 300},
        ],
    })
    assert capienza_del_tipo(personalizzazione, "tazza") == 300
    assert capienza_del_tipo(personalizzazione, "bottiglia") == 1500
    assert capienza_del_tipo(personalizzazione, "bicchiere") is None
