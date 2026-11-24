"""Test della bevuta: formula di Marco (D9), percentuale misurata fotogramma per fotogramma, controllo in pixel del
livello e analizzatore provvisorio su una scena sintetica."""

import datetime
from zoneinfo import ZoneInfo

import numpy as np
import pytest

from contratti.configurazione import Personalizzazione, TelecameraLocale
from contratti.eventi import LETTORE_EVENTO, leggi_evento

from casa.bevuta import (AnalizzatoreBevuta, contenitore_della_personalizzazione, frazione_piena,
                         frazione_piena_dai_bordi, percentuale_scesa, valori_bevuta)
from casa.percezione import Oggetto, Osservazione, Persona

ROMA = ZoneInfo("Europe/Rome")
CUCINA = TelecameraLocale.model_validate({
    "id": "cucina", "nome": "Kitchen", "stanza": "kitchen", "sorgente": "x.mp4", "analizzatori": ["bevuta"],
})
PERSONALIZZAZIONE = Personalizzazione.model_validate({
    "anziano": {"nome": "Anna"},
    "contenitori": [
        {"id": "bottiglia-acqua", "nome": "Water bottle", "tipo": "bottiglia", "capienza_ml": 1500},
        {"id": "bicchiere", "nome": "Glass", "tipo": "bicchiere", "capienza_ml": 250},
    ],
})


def maschera_liquido(altezza: int, larghezza: int, riga_livello: int) -> np.ndarray:
    """Ritaglio del contenitore con il liquido dalla riga del livello fino al fondo."""
    maschera = np.zeros((altezza, larghezza), bool)
    maschera[riga_livello:, 2:larghezza - 2] = True
    return maschera


def test_esempio_di_marco():
    # scende 10 px su una bottiglia alta 100 px da 2 L → 10% → 200 ml
    valori = valori_bevuta("bottiglia", None, 2000, 100, 10)
    assert valori.livello_sceso_px == pytest.approx(10)
    assert valori.ml == pytest.approx(200)
    assert valori.contenitore == "bottiglia"
    assert valori.contenitore_id is None
    assert valori.altezza_contenitore_px == 100


def test_percentuale_in_ogni_fotogramma_anche_se_cambia_la_distanza():
    # prima: bottiglia alta 100 px piena per l'80%; dopo è più vicina (200 px) e piena per il 70%
    prima = frazione_piena(maschera_liquido(100, 30, 20))
    dopo = frazione_piena(maschera_liquido(200, 60, 60))
    assert prima == pytest.approx(0.8)
    assert dopo == pytest.approx(0.7)
    assert percentuale_scesa(prima, dopo) == pytest.approx(10)
    # contenitore vuoto: livello sul fondo
    assert frazione_piena(np.zeros((100, 30), bool)) == 0
    # livello salito (riempito): non è sceso niente
    assert percentuale_scesa(0.5, 0.9) == 0


def immagine_con_bottiglia(riga_liquido: int) -> np.ndarray:
    """Cucina grigia 200×200 con una bottiglia sul tavolo nel box (150, 100)-(170, 160): aria sopra, liquido sotto."""
    immagine = np.full((200, 200, 3), 60, np.uint8)
    immagine[100:160, 150:170] = 90
    immagine[riga_liquido:160, 150:170] = 180
    return immagine


BOX_SUL_TAVOLO = np.array([150, 100, 170, 160], np.float32)


def test_livello_dai_bordi():
    # liquido dalla riga 112: 12 righe vuote su 60 → piena per l'80%
    assert frazione_piena_dai_bordi(immagine_con_bottiglia(112), BOX_SUL_TAVOLO) == pytest.approx(0.8)
    assert frazione_piena_dai_bordi(immagine_con_bottiglia(124), BOX_SUL_TAVOLO) == pytest.approx(0.6)
    # nessun bordo (es. tazza non trasparente) o contenitore troppo piccolo: non si misura
    assert frazione_piena_dai_bordi(np.full((200, 200, 3), 60, np.uint8), BOX_SUL_TAVOLO) is None
    assert frazione_piena_dai_bordi(immagine_con_bottiglia(112), np.array([150, 100, 155, 110])) is None


def test_contenitore_della_personalizzazione():
    assert contenitore_della_personalizzazione(PERSONALIZZAZIONE, "bottle").id == "bottiglia-acqua"
    # "cup" di COCO: prima tazza, poi bicchiere
    assert contenitore_della_personalizzazione(PERSONALIZZAZIONE, "cup").id == "bicchiere"
    vuota = Personalizzazione.model_validate({"anziano": {"nome": "Anna"}})
    assert contenitore_della_personalizzazione(vuota, "wine glass") is None


def persona_al_tavolo(beve: bool) -> Persona:
    """Seduta al tavolo: naso in (110, 40), spalle larghe 40 px; se beve il polso destro è alla bocca."""
    keypoint = np.zeros((17, 3), np.float32)
    keypoint[0] = [110, 40, 0.9]    # naso
    keypoint[5] = [90, 60, 0.9]     # spalla sinistra
    keypoint[6] = [130, 60, 0.9]    # spalla destra
    keypoint[9] = [90, 120, 0.9]    # polso sinistro
    keypoint[10] = [130, 120, 0.9]  # polso destro
    if beve:
        keypoint[10] = [112, 55, 0.9]
    return Persona(1, np.array([80, 20, 160, 190], np.float32), 0.9, keypoint)


def passo(ora: datetime.datetime, beve: bool, riga_liquido: int, classe: str = "bottle") -> Osservazione:
    if beve:
        bottiglia = Oggetto(classe, np.array([105, 30, 120, 90], np.float32), 0.7)
    else:
        bottiglia = Oggetto(classe, BOX_SUL_TAVOLO, 0.7)
    persona = persona_al_tavolo(beve)
    return Osservazione("cucina", "kitchen", ora, immagine_con_bottiglia(riga_liquido), [persona], [bottiglia])


def scena_bevuta(secondi_alla_bocca: int, riga_dopo: int, classe: str = "bottle",
                 personalizzazione: Personalizzazione = PERSONALIZZAZIONE) -> list:
    """6 s con la bottiglia sul tavolo (piena all'80%), il sorso, poi 15 s con la bottiglia di nuovo sul tavolo."""
    analizzatore = AnalizzatoreBevuta(CUCINA, personalizzazione)
    inizio = datetime.datetime(2026, 12, 1, 10, 0, tzinfo=ROMA)
    sequenza = []
    for secondo in range(6):
        sequenza.append((False, 112))
    for secondo in range(secondi_alla_bocca):
        sequenza.append((True, 112))
    for secondo in range(15):
        sequenza.append((False, riga_dopo))
    eventi = []
    for indice in range(len(sequenza)):
        ora = inizio + datetime.timedelta(seconds=indice)
        osservazione = passo(ora, sequenza[indice][0], sequenza[indice][1], classe)
        for evento in analizzatore.elabora(osservazione):
            eventi.append(evento)
    for evento in analizzatore.fine():
        eventi.append(evento)
    return eventi


def test_bevuta_dalla_bottiglia():
    eventi = scena_bevuta(3, 124)
    assert len(eventi) == 1
    evento = eventi[0]
    inizio = datetime.datetime(2026, 12, 1, 10, 0, tzinfo=ROMA)
    assert evento.tipo == "bevuta"
    assert evento.inizio == inizio + datetime.timedelta(seconds=6)
    assert evento.fine == inizio + datetime.timedelta(seconds=8)
    # dall'80% al 60% della bottiglia da 1,5 L della personalizzazione
    assert evento.valori.percentuale == pytest.approx(20)
    assert evento.valori.ml == pytest.approx(300)
    assert evento.valori.contenitore == "bottiglia"
    assert evento.valori.contenitore_id == "bottiglia-acqua"
    assert evento.valori.altezza_contenitore_px == pytest.approx(60)
    assert evento.valori.livello_sceso_px == pytest.approx(12)
    assert evento.confidenza == pytest.approx(0.7)
    assert evento.foto_prova is not None
    assert leggi_evento(LETTORE_EVENTO.dump_python(evento, mode="json")) == evento


def test_un_attimo_alla_bocca_non_e_un_sorso():
    assert scena_bevuta(1, 124) == []


def test_livello_non_misurabile_zero_ml_e_confidenza_dimezzata():
    # la bottiglia rimessa giù è tutta uguale (nessun bordo): bevuta vista, quantità non misurata
    eventi = scena_bevuta(3, 100)
    assert len(eventi) == 1
    assert eventi[0].valori.ml == 0
    assert eventi[0].confidenza == pytest.approx(0.35)


def test_contenitore_non_nella_personalizzazione():
    vuota = Personalizzazione.model_validate({"anziano": {"nome": "Anna"}})
    eventi = scena_bevuta(3, 124, "wine glass", vuota)
    assert len(eventi) == 1
    assert eventi[0].valori.contenitore == "bicchiere"
    assert eventi[0].valori.contenitore_id is None
    assert eventi[0].valori.capienza_ml == 250
    assert eventi[0].valori.ml == pytest.approx(50)
