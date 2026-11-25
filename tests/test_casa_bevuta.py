"""Test della bevuta: formula di Marco (D9), controllo sui pixel del livello (percentuale nello stesso fotogramma, da
vicino e da lontano, bottiglia, bicchiere e tazza opaca) e analizzatore provvisorio su una scena sintetica."""

import datetime
from zoneinfo import ZoneInfo

import cv2
import numpy as np
import pytest

from contratti.configurazione import Personalizzazione, TelecameraLocale
from contratti.eventi import LETTORE_EVENTO, leggi_evento

from casa.bevuta import (AnalizzatoreBevuta, alla_bocca, contenitore_della_personalizzazione, frazione_piena_dai_pixel,
                         percentuale_scesa, valori_bevuta)
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


def test_esempio_di_marco():
    # scende 10 px su una bottiglia alta 100 px da 2 L → 10% → 200 ml
    valori = valori_bevuta("bottiglia", None, 2000, 100, 10, True)
    assert valori.livello_sceso_px == pytest.approx(10)
    assert valori.ml == pytest.approx(200)
    assert valori.contenitore == "bottiglia"
    assert valori.contenitore_id is None
    assert valori.altezza_contenitore_px == 100


def contenitore_disegnato(classe: str, frazione_piena: float, altezza_px: float, tazza: str = "liscia"):
    """Cucina con un contenitore alto 200 px, poi rimpicciolita perché sia alto altezza_px (più lontano), con un po'
    di sfocatura e di rumore. Bottiglia (tappo blu) e bicchiere (bordo e fondo spesso) sono trasparenti: sopra il
    livello si vede il muro, sotto il liquido; hanno un riflesso verticale. La tazza ("cup") è opaca: liscia,
    sfumata dalla luce o con una striscia disegnata. Ritorna l'immagine e il box del rilevatore (un po' più largo)."""
    immagine = np.zeros((400, 600, 3), np.float32)
    for riga in range(400):
        immagine[riga] = (150 + riga * 0.1, 160, 170 - riga * 0.05)  # muro con una sfumatura
    immagine[300:] = (60, 90, 120)  # tavolo
    larghezze = {"bottle": 64, "wine glass": 90, "cup": 150}
    x1 = 250
    y1 = 100
    x2 = x1 + larghezze[classe]
    y2 = y1 + 200
    if classe == "cup":
        for colonna in range(x1, x2):
            ombra = 1 - 0.5 * abs(colonna - (x1 + x2) / 2) / ((x2 - x1) / 2)  # più scura ai lati
            immagine[y1:y2, colonna] = np.array((40, 60, 200)) * ombra
        if tazza == "sfumata":
            for riga in range(y1, y2):
                immagine[riga, x1:x2] = immagine[riga, x1:x2] * (1 - 0.6 * (riga - y1) / 200)
        if tazza == "striscia":
            immagine[160:180, x1:x2] = 220
        cv2.ellipse(immagine, (x2 + 15, y1 + 90), (25, 45), 0, -90, 90, (40, 60, 180), 12)  # manico
    else:
        riga_liquido = y2 - int(200 * frazione_piena)
        immagine[y1:riga_liquido, x1:x2] = immagine[y1:riga_liquido, x1:x2] * 1.08 + 5
        immagine[riga_liquido:y2, x1:x2] = immagine[riga_liquido:y2, x1:x2] * 0.85 + np.array((15, 5, -5))
        immagine[y1:y2, x1 + 8:x1 + 14] = immagine[y1:y2, x1 + 8:x1 + 14] + 50  # riflesso
        if classe == "bottle":
            immagine[y1:y1 + 16, x1:x2] = immagine[y1:y1 + 16, x1 - 64:x2 - 64]  # collo: si vede il muro
            immagine[y1:y1 + 16, x1 + 16:x2 - 16] = (200, 90, 30)              # tappo
        else:
            immagine[y1:y1 + 3, x1:x2] = 230                                        # bordo
            immagine[y2 - 14:y2, x1:x2] = immagine[y2 - 14:y2, x1:x2] * 1.15 + 10  # fondo spesso
    immagine = cv2.GaussianBlur(np.clip(immagine, 0, 255).astype(np.uint8), (5, 5), 1.2)
    scala = altezza_px / 200
    lontana = cv2.resize(immagine, None, fx=scala, fy=scala, interpolation=cv2.INTER_AREA)
    rumore = np.random.default_rng(0).normal(0, 4, lontana.shape)
    lontana = np.clip(lontana + rumore, 0, 255).astype(np.uint8)
    box = np.array([x1 - 4, y1 - 3, x2 + 4, y2 + 3], np.float32)
    if classe == "cup":
        box[2] = x2 + 45  # il manico è nel box
    return lontana, box * scala


@pytest.mark.parametrize("classe", ["bottle", "wine glass"])
@pytest.mark.parametrize("piena", [0.8, 0.5, 0.3])
@pytest.mark.parametrize("altezza_px", [200, 60, 24])
def test_livello_di_bottiglia_e_bicchiere_vicini_e_lontani(classe, piena, altezza_px):
    immagine, box = contenitore_disegnato(classe, piena, altezza_px)
    assert frazione_piena_dai_pixel(immagine, box, classe) == pytest.approx(piena, abs=0.03)


def test_percentuale_in_ogni_fotogramma_anche_se_cambia_la_distanza():
    # prima la bottiglia è lontana (alta 30 px) e piena all'80%; dopo è vicina (150 px) e piena al 60%
    lontana, box_lontano = contenitore_disegnato("bottle", 0.8, 30)
    vicina, box_vicino = contenitore_disegnato("bottle", 0.6, 150)
    prima = frazione_piena_dai_pixel(lontana, box_lontano, "bottle")
    dopo = frazione_piena_dai_pixel(vicina, box_vicino, "bottle")
    assert percentuale_scesa(prima, dopo) == pytest.approx(20, abs=3)
    # livello salito (riempito): non è sceso niente
    assert percentuale_scesa(0.5, 0.9) == 0


@pytest.mark.parametrize("tazza", ["liscia", "sfumata", "striscia"])
@pytest.mark.parametrize("altezza_px", [200, 40])
def test_tazza_opaca_livello_non_visibile(tazza, altezza_px):
    immagine, box = contenitore_disegnato("cup", 0.5, altezza_px, tazza)
    assert frazione_piena_dai_pixel(immagine, box, "cup") is None


def test_contenitore_troppo_lontano_non_si_misura():
    immagine, box = contenitore_disegnato("bottle", 0.5, 12)
    assert frazione_piena_dai_pixel(immagine, box, "bottle") is None


def immagine_con_bottiglia(riga_liquido: int, x1: int = 150) -> np.ndarray:
    """Cucina grigia 200×200 con una bottiglia alta 60 px (righe 100-160) larga 20 px: aria sopra, liquido sotto."""
    immagine = np.full((200, 200, 3), 60, np.uint8)
    immagine[100:160, x1:x1 + 20] = 90
    immagine[riga_liquido:160, x1:x1 + 20] = 180
    return immagine


BOX_SUL_TAVOLO = np.array([150, 100, 170, 160], np.float32)


def test_livello_nella_scena_semplice():
    # liquido dalla riga 112: 12 righe vuote su 60 → piena per l'80%
    assert frazione_piena_dai_pixel(immagine_con_bottiglia(112), BOX_SUL_TAVOLO, "bottle") == pytest.approx(0.8)
    assert frazione_piena_dai_pixel(immagine_con_bottiglia(124), BOX_SUL_TAVOLO, "bottle") == pytest.approx(0.6)
    # tutta uguale: nessuna riga del liquido
    assert frazione_piena_dai_pixel(immagine_con_bottiglia(100), BOX_SUL_TAVOLO, "bottle") is None


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


def passo(ora: datetime.datetime, dove: str, riga_liquido: int, classe: str = "bottle") -> Osservazione:
    """La bottiglia è "tavolo", "bocca" o "mano" (tenuta vicino al polso sinistro, inclinata: livello sbagliato)."""
    immagine = immagine_con_bottiglia(riga_liquido)
    if dove == "bocca":
        bottiglia = Oggetto(classe, np.array([105, 30, 120, 90], np.float32), 0.7)
    elif dove == "mano":
        immagine = immagine_con_bottiglia(riga_liquido, 80)
        bottiglia = Oggetto(classe, np.array([80, 100, 100, 160], np.float32), 0.7)
    else:
        bottiglia = Oggetto(classe, BOX_SUL_TAVOLO, 0.7)
    persona = persona_al_tavolo(dove == "bocca")
    return Osservazione("cucina", "kitchen", ora, immagine, [persona], [bottiglia])


def scena_bevuta(secondi_alla_bocca: int, riga_dopo: int, classe: str = "bottle",
                 personalizzazione: Personalizzazione = PERSONALIZZAZIONE, secondi_in_mano: int = 0) -> list:
    """6 s con la bottiglia sul tavolo (piena all'80%), il sorso, qualche secondo in mano, poi 15 s con la bottiglia
    di nuovo sul tavolo."""
    analizzatore = AnalizzatoreBevuta(CUCINA, personalizzazione)
    inizio = datetime.datetime(2026, 12, 1, 10, 0, tzinfo=ROMA)
    sequenza = []
    for secondo in range(6):
        sequenza.append(("tavolo", 112))
    for secondo in range(secondi_alla_bocca):
        sequenza.append(("bocca", 112))
    for secondo in range(secondi_in_mano):
        sequenza.append(("mano", 145))
    for secondo in range(15):
        sequenza.append(("tavolo", riga_dopo))
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
    assert evento.valori.livello_visibile
    assert evento.confidenza == pytest.approx(0.7)
    assert evento.foto_prova is not None
    assert leggi_evento(LETTORE_EVENTO.dump_python(evento, mode="json")) == evento


def test_in_mano_il_livello_non_si_misura():
    # in mano la bottiglia sembra quasi vuota (inclinata): conta solo il livello quando è di nuovo appoggiata
    eventi = scena_bevuta(3, 124, secondi_in_mano=8)
    assert len(eventi) == 1
    assert eventi[0].valori.percentuale == pytest.approx(20)


def test_un_attimo_alla_bocca_non_e_un_sorso():
    assert scena_bevuta(1, 124) == []


def test_livello_non_visibile_zero_ml_e_confidenza_dimezzata():
    # la bottiglia rimessa giù è tutta uguale (nessuna riga del liquido): bevuta vista, quantità non misurata
    eventi = scena_bevuta(3, 100)
    assert len(eventi) == 1
    assert eventi[0].valori.ml == 0
    assert not eventi[0].valori.livello_visibile
    assert eventi[0].confidenza == pytest.approx(0.35)


def test_livello_non_visibile_arriva_al_backend():
    # nel JSON mandato al backend: ml 0 vuol dire "non misurato", non "non ha bevuto"
    evento = scena_bevuta(3, 100)[0]
    dati = LETTORE_EVENTO.dump_python(evento, mode="json")
    assert dati["valori"]["livello_visibile"] is False
    assert dati["valori"]["ml"] == 0
    assert not leggi_evento(dati).valori.livello_visibile


def test_contenitore_non_nella_personalizzazione():
    vuota = Personalizzazione.model_validate({"anziano": {"nome": "Anna"}})
    eventi = scena_bevuta(3, 124, "wine glass", vuota)
    assert len(eventi) == 1
    assert eventi[0].valori.contenitore == "bicchiere"
    assert eventi[0].valori.contenitore_id is None
    assert eventi[0].valori.capienza_ml == 250
    assert eventi[0].valori.ml == pytest.approx(50)


def test_regola_dei_gesti_polso_al_naso_e_contenitore_alla_testa():
    bottiglia_alla_bocca = Oggetto("bottle", np.array([105, 30, 120, 90], np.float32), 0.7)
    assert alla_bocca(persona_al_tavolo(True), bottiglia_alla_bocca)
    # la bottiglia tocca il naso ma i polsi sono giù: non è un sorso
    assert not alla_bocca(persona_al_tavolo(False), bottiglia_alla_bocca)
    # polso al naso, bottiglia sul tavolo: nemmeno
    assert not alla_bocca(persona_al_tavolo(True), Oggetto("bottle", BOX_SUL_TAVOLO, 0.7))


# tazza alla bocca vista male dal rilevatore: coperta dalla mano, confidenza bassa
TAZZA_COPERTA = Oggetto("cup", np.array([100, 35, 125, 60], np.float32), 0.08)


def scena_gesti(sequenza: list) -> list:
    """Un passo al secondo: sequenza[i] = (polso alla bocca, tazza coperta vista vicino alla testa)."""
    analizzatore = AnalizzatoreBevuta(CUCINA, PERSONALIZZAZIONE)
    inizio = datetime.datetime(2026, 12, 1, 10, 0, tzinfo=ROMA)
    eventi = []
    for indice in range(len(sequenza)):
        ora = inizio + datetime.timedelta(seconds=indice)
        polso_alla_bocca = sequenza[indice][0]
        incerti = []
        if sequenza[indice][1]:
            incerti.append(TAZZA_COPERTA)
        immagine = np.full((200, 200, 3), 80, np.uint8)
        osservazione = Osservazione("cucina", "kitchen", ora, immagine, [persona_al_tavolo(polso_alla_bocca)], [],
                                    incerti)
        for evento in analizzatore.elabora(osservazione):
            eventi.append(evento)
    for evento in analizzatore.fine():
        eventi.append(evento)
    return eventi


def test_contenitore_visto_male_intorno_al_gesto():
    # gesto ai secondi 3-4; la tazza (confidenza 0,08) vista al secondo 1, 2 s prima: è un sorso
    prima = [(False, False), (False, True), (False, False), (True, False), (True, False)] + [(False, False)] * 3
    eventi = scena_gesti(prima)
    assert len(eventi) == 1
    assert eventi[0].valori.contenitore in ("tazza", "bicchiere")  # "cup" di COCO: dipende dalla personalizzazione
    assert not eventi[0].valori.livello_visibile
    # vista al secondo 0, 3 s prima: no
    troppo_prima = [(False, True)] + [(False, False)] * 2 + [(True, False)] * 2 + [(False, False)] * 3
    assert scena_gesti(troppo_prima) == []
    # gesto ai secondi 1-2, tazza vista al secondo 4 (2 s dopo): sì; al secondo 5: no
    dopo = [(False, False), (True, False), (True, False), (False, False), (False, True)] + [(False, False)] * 3
    assert len(scena_gesti(dopo)) == 1
    troppo_dopo = [(False, False), (True, False), (True, False)] + [(False, False)] * 2 + [(False, True)]
    assert scena_gesti(troppo_dopo + [(False, False)] * 2) == []
    # senza tazza il solo polso non è una bevuta
    assert scena_gesti([(True, False)] * 4 + [(False, False)] * 3) == []
