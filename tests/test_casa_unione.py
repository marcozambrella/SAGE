"""Test dell'unione: doppioni tra telecamere, stime pesate con la confidenza, urgenti subito, stanze dell'alzata."""

import datetime
import uuid
from zoneinfo import ZoneInfo

import pytest

from contratti.eventi import leggi_evento

from casa.unione import FINESTRA_SECONDI, Unione

ROMA = ZoneInfo("Europe/Rome")
ORA = datetime.datetime(2026, 12, 1, 10, 0, tzinfo=ROMA)


def secondi(quanti: float) -> datetime.datetime:
    return ORA + datetime.timedelta(seconds=quanti)


def evento(tipo: str, valori: dict, telecamera: str, confidenza: float, inizio: datetime.datetime,
           fine: datetime.datetime | None = None, stanza: str = "kitchen"):
    return leggi_evento({
        "id": str(uuid.uuid4()),
        "tipo": tipo,
        "inizio": inizio,
        "fine": fine,
        "stanza": stanza,
        "confidenza": confidenza,
        "fonti": [{"telecamera_id": telecamera, "analizzatore": tipo, "confidenza": confidenza}],
        "valori": valori,
    })


def bevuta(telecamera: str, confidenza: float, percentuale: float, inizio: datetime.datetime):
    valori = {"contenitore": "bottiglia", "capienza_ml": 2000, "altezza_contenitore_px": 100,
              "livello_sceso_px": percentuale, "percentuale": percentuale, "ml": percentuale * 20}
    return evento("bevuta", valori, telecamera, confidenza, inizio)


def test_stessa_bevuta_da_due_telecamere_pesata_con_la_confidenza():
    unione = Unione()
    piu_sicura = bevuta("cucina", 0.9, 10, secondi(0))
    assert unione.aggiungi(piu_sicura, secondi(0)) == []
    assert unione.aggiungi(bevuta("soggiorno", 0.3, 20, secondi(2)), secondi(2)) == []
    # finestra ancora aperta: niente
    assert unione.pronti(secondi(5)) == []
    eventi = unione.pronti(secondi(2 + FINESTRA_SECONDI + 1))
    assert len(eventi) == 1
    unito = eventi[0]
    assert len(unito.fonti) == 2
    assert unito.confidenza == 0.9
    assert unito.id == piu_sicura.id
    # (0,9×10 + 0,3×20) / 1,2 = 12,5% di 2 L
    assert unito.valori.percentuale == pytest.approx(12.5)
    assert unito.valori.ml == pytest.approx(250)
    assert unito.valori.livello_sceso_px == pytest.approx(12.5)
    assert unito.inizio == secondi(0)
    # e nel frattempo il gruppo è chiuso
    assert unione.chiudi_tutti() == []


def test_la_stessa_telecamera_non_fa_doppioni():
    unione = Unione()
    unione.aggiungi(bevuta("cucina", 0.9, 10, secondi(0)), secondi(0))
    unione.aggiungi(bevuta("cucina", 0.8, 5, secondi(3)), secondi(3))
    assert len(unione.chiudi_tutti()) == 2


def test_lontani_nel_tempo_sono_due_fatti():
    unione = Unione()
    unione.aggiungi(bevuta("cucina", 0.9, 10, secondi(0)), secondi(0))
    unione.aggiungi(bevuta("soggiorno", 0.8, 5, secondi(FINESTRA_SECONDI + 5)), secondi(FINESTRA_SECONDI + 5))
    assert len(unione.chiudi_tutti()) == 2


def test_tipi_diversi_non_si_uniscono():
    unione = Unione()
    unione.aggiungi(bevuta("cucina", 0.9, 10, secondi(0)), secondi(0))
    unione.aggiungi(evento("caduta", {"secondi_a_terra": None}, "soggiorno", 0.8, secondi(1)), secondi(1))
    assert len(unione.chiudi_tutti()) == 1  # la caduta è urgente: era già uscita


def test_urgente_esce_subito_e_assorbe_i_doppioni():
    unione = Unione()
    prima = evento("uscita", {"zona_id": "porta-ingresso"}, "ingresso", 0.7, secondi(0), stanza="hall")
    seconda = evento("uscita", {"zona_id": "porta-ingresso"}, "corridoio", 0.9, secondi(3), stanza="hall")
    usciti = unione.aggiungi(prima, secondi(0))
    assert usciti == [prima]
    assert unione.aggiungi(seconda, secondi(3)) == []
    assert unione.pronti(secondi(30)) == []
    assert unione.chiudi_tutti() == []


def test_caduta_secondi_a_terra_pesati_ignorando_i_mancanti():
    unione = Unione()
    eventi = [
        evento("caduta", {"secondi_a_terra": 10}, "cucina", 0.5, secondi(0)),
        evento("caduta", {"secondi_a_terra": None}, "soggiorno", 0.9, secondi(1)),
        evento("caduta", {"secondi_a_terra": 30}, "corridoio", 0.5, secondi(2)),
    ]
    unito = unione.unisci(eventi)
    assert unito.valori.secondi_a_terra == pytest.approx(20)
    assert unito.confidenza == 0.9
    assert len(unito.fonti) == 3


def test_pasto_cibi_uniti():
    unione = Unione()
    eventi = [
        evento("pasto", {"cibi": ["pasta", "salad"], "percentuale_mangiata": 80}, "cucina", 0.6, secondi(0)),
        evento("pasto", {"cibi": ["salad", "bread"], "percentuale_mangiata": 40}, "sala", 0.2, secondi(1)),
    ]
    unito = unione.unisci(eventi)
    assert unito.valori.cibi == ["pasta", "salad", "bread"]
    assert unito.valori.percentuale_mangiata == pytest.approx(70)


def test_alzata_notturna_con_le_stanze_attraversate():
    unione = Unione()
    notte = datetime.datetime(2026, 12, 2, 2, 0, tzinfo=ROMA)
    # bagno dopo 2 minuti, cucina dopo 5; il soggiorno solo prima dell'alzata
    unione.registra_presenza("living room", notte - datetime.timedelta(hours=3))
    for secondo in range(0, 60, 2):
        unione.registra_presenza("bathroom", notte + datetime.timedelta(seconds=120 + secondo))
        unione.registra_presenza("kitchen", notte + datetime.timedelta(seconds=300 + secondo))
    fine = notte + datetime.timedelta(minutes=10)
    alzata = evento("alzata_notturna", {"stanze": ["bedroom"]}, "camera-letto", 0.8, notte, fine, stanza="bedroom")
    unione.aggiungi(alzata, fine)
    eventi = unione.chiudi_tutti()
    assert len(eventi) == 1
    assert eventi[0].valori.stanze == ["bedroom", "bathroom", "kitchen"]
    assert eventi[0].fine == fine


def test_presenze_vicine_sono_un_solo_intervallo():
    unione = Unione()
    unione.registra_presenza("kitchen", secondi(0))
    unione.registra_presenza("kitchen", secondi(3))
    unione.registra_presenza("kitchen", secondi(30))
    assert len(unione.presenze["kitchen"]) == 2
    assert unione.stanze_attraversate(secondi(10), secondi(20)) == []
    assert unione.stanze_attraversate(secondi(2), None) == ["kitchen"]
