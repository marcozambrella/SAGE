"""Test del classificatore delle cadute: finestre come nell'allenamento e lettura dei pesi nel formato dell'allenamento
(un modello con pesi a caso salvato nel test: i pesi veri non sono nel repo)."""

import datetime
from zoneinfo import ZoneInfo

import numpy as np
import pytest
import torch

from casa.classificatore_cadute import (ClassificatoreCadute, Scheletro, ScheletriDelFotogramma, StGcn,
                                        finestra_della_traccia)

ROMA = ZoneInfo("Europe/Rome")
INIZIO = datetime.datetime(2026, 12, 1, 11, 0, tzinfo=ROMA)


def scheletro(x: float, altezza: float = 100) -> Scheletro:
    """Tutti i punti visibili in (x, 50), tranne il naso invisibile."""
    punti = np.zeros((17, 3), np.float32)
    punti[:, 0] = x
    punti[:, 1] = 50
    punti[:, 2] = 0.9
    punti[0, 2] = 0.05
    return Scheletro(punti, altezza)


def fotogrammi_a_5_al_secondo(quanti: int, assente: list = []) -> list:
    """La persona 7 si sposta di 10 px a fotogramma; nei fotogrammi `assente` non c'è."""
    fotogrammi = []
    for numero in range(quanti):
        scheletri = {}
        if numero not in assente:
            scheletri[7] = scheletro(10 * numero)
        ora = INIZIO + datetime.timedelta(seconds=numero * 0.2)
        fotogrammi.append(ScheletriDelFotogramma(ora, scheletri))
    return fotogrammi


def test_finestra_a_10_al_secondo_dai_fotogrammi_analizzati_a_5():
    fotogrammi = fotogrammi_a_5_al_secondo(11)  # da 0 a 2 s
    finestra = finestra_della_traccia(fotogrammi, 7, fotogrammi[-1].ora, 10, 20)
    assert finestra.shape == (20, 17, 3)
    # istante 0,1 s: fotogramma più vicino a pari distanza tra 0 e 0,2 s, si prende il primo (x 0)
    # istanti dalla fine: 1,9 → 1,8 s (x 90)... la x di ogni istante prima di normalizzare
    x_attese = []
    for posizione in range(20):
        secondi = 0.1 + posizione * 0.1
        numero_vicino = int(np.floor(secondi / 0.2 + 1e-9))
        if secondi / 0.2 - numero_vicino > 0.5 + 1e-9:
            numero_vicino = numero_vicino + 1
        x_attese.append(10 * numero_vicino)
    x_attese = np.array(x_attese, np.float32)
    centro = x_attese.mean()
    assert finestra[:, 1, 0] == pytest.approx((x_attese - centro) / 100, abs=1e-5)
    assert finestra[:, 1, 1] == pytest.approx(0)          # y uguale per tutti: 0 dopo aver tolto il centro
    assert finestra[:, 1, 2] == pytest.approx(0.9)        # terzo canale: la confidenza
    assert np.all(finestra[:, 0] == 0)                    # naso invisibile (confidenza ≤ 0,1): zeri


def test_persona_assente_e_istanti_prima_del_primo_fotogramma_sono_zeri():
    fotogrammi = fotogrammi_a_5_al_secondo(6, assente=[3])  # da 0 a 1 s, assente a 0,6 s
    finestra = finestra_della_traccia(fotogrammi, 7, fotogrammi[-1].ora, 10, 20)
    # la finestra va da -0,9 a 1 s: gli istanti prima di -0,1 s (mezzo intervallo prima del primo) sono vuoti
    assert np.all(finestra[:8] == 0)
    assert np.any(finestra[9] != 0)
    # 0,6 s (posizione 15) e 0,5-0,7 s vicini al fotogramma senza la persona
    assert np.all(finestra[15] == 0)
    # un'altra traccia mai vista: tutto zero
    assert np.all(finestra_della_traccia(fotogrammi, 99, fotogrammi[-1].ora, 10, 20) == 0)


def salva_pesi_finti(percorso) -> None:
    modello = StGcn(3)
    torch.save({"stato": modello.state_dict(), "classi": ["normale", "caduta", "a_terra"], "lunghezza": 20,
                "informazioni": {"fps": 10, "secondi": 2, "soglia_allarme": 0.9, "posa": "yolo26n-pose"}},
               str(percorso))


def test_pesi_nel_formato_dell_allenamento(tmp_path):
    percorso = tmp_path / "cadute.pt"
    salva_pesi_finti(percorso)
    classificatore = ClassificatoreCadute(str(percorso), 0.9, 2, 0.995, 6)
    assert classificatore.fps == 10
    assert classificatore.secondi == 2
    assert classificatore.lunghezza == 20
    assert classificatore.soglia == 0.9
    assert classificatore.posa == "yolo26n-pose"
    assert classificatore.finestre_di_fila == 2
    assert classificatore.soglia_sicura == 0.995
    assert classificatore.finestre_sicure == 6
    fotogrammi = fotogrammi_a_5_al_secondo(11)
    finestra = finestra_della_traccia(fotogrammi, 7, fotogrammi[-1].ora, 10, 20)
    probabilita = classificatore.probabilita_caduta(finestra)
    assert 0 <= probabilita <= 1


def test_pesi_di_un_modello_diverso_si_fermano(tmp_path):
    percorso = tmp_path / "altro.pt"
    stato = StGcn(3).state_dict()
    stato.pop("classificatore.weight")
    torch.save({"stato": stato, "classi": ["normale", "caduta", "a_terra"], "lunghezza": 20,
                "informazioni": {"fps": 10, "secondi": 2, "soglia_allarme": 0.9, "posa": "yolo26n-pose"}},
               str(percorso))
    with pytest.raises(RuntimeError):
        ClassificatoreCadute(str(percorso), 0.9, 2, 0.995, 6)
