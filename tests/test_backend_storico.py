"""Test dello storico simulato della casa demo (D22): riproducibile, valido per i contratti, plausibile, e caricato
nel backend con la stessa chiamata del programma di casa (client di test di FastAPI, niente rete vera)."""

import datetime

import pytest
from fastapi.testclient import TestClient

from backend.app import app
from backend.archivio import ArchivioMemoria
from backend.report import calcola_report_periodo
from backend.storico_simulato import PERSONALIZZAZIONE_DEMO, SEME_PREDEFINITO, carica_storico, genera_storico
from contratti.eventi import LETTORE_EVENTO

DAL = datetime.date(2026, 10, 26)
AL = datetime.date(2026, 11, 22)
DOPO = datetime.datetime(2026, 12, 1, 12, 0, tzinfo=datetime.UTC)
TOKEN = "token-di-prova"


def in_json(eventi: list) -> list:
    testi = []
    for evento in eventi:
        testi.append(LETTORE_EVENTO.dump_json(evento))
    return testi


def test_stesso_seme_stessi_eventi():
    primi = genera_storico(PERSONALIZZAZIONE_DEMO, DAL, AL, 7)
    secondi = genera_storico(PERSONALIZZAZIONE_DEMO, DAL, AL, 7)
    assert in_json(primi) == in_json(secondi)
    altri = genera_storico(PERSONALIZZAZIONE_DEMO, DAL, AL, 8)
    assert in_json(primi) != in_json(altri)


def test_eventi_simulati_con_id_diversi():
    eventi = genera_storico(PERSONALIZZAZIONE_DEMO, DAL, AL, 7)
    ids = set()
    for evento in eventi:
        assert evento.simulato is True
        assert evento.id.startswith("sim-7-")
        ids.add(evento.id)
    assert len(ids) == len(eventi)


def test_storico_plausibile():
    eventi = genera_storico(PERSONALIZZAZIONE_DEMO, DAL, AL, SEME_PREDEFINITO)
    report = calcola_report_periodo("mensile", DAL, AL, eventi, PERSONALIZZAZIONE_DEMO, DOPO)
    assert len(report.giorni) == 28
    assert 900 <= report.acqua_media_ml <= 1600
    assert 80 <= report.aderenza_farmaci_percentuale < 100
    assert report.cadute == 2
    assert 1 <= report.uscite_in_orario_vietato <= 6
    assert 0.5 <= report.alzate_notturne_medie <= 2
    dosi_in_ritardo = 0
    dosi_saltate = 0
    acqua_dei_giorni = set()
    for giorno in report.giorni:
        # ogni giorno ha eventi simulati, quindi la web app lo segna come simulato
        assert giorno.simulato is True
        dosi_in_ritardo = dosi_in_ritardo + giorno.dosi_in_ritardo
        dosi_saltate = dosi_saltate + giorno.dosi_saltate
        acqua_dei_giorni.add(giorno.acqua_ml)
    assert dosi_in_ritardo > 0
    assert dosi_saltate > 0
    # l'idratazione cambia da un giorno all'altro
    assert len(acqua_dei_giorni) > 20


@pytest.fixture
def client():
    app.state.archivio = ArchivioMemoria()
    app.state.token_casa = TOKEN
    return TestClient(app)


def test_caricato_nel_backend_una_volta_sola(client):
    risultato = carica_storico(client, TOKEN, 1, 7, datetime.date(2025, 12, 7))
    assert risultato["ricevuti"] == risultato["nuovi"]
    assert risultato["nuovi"] > 0
    # la casa non era configurata: lo script ha mandato la personalizzazione d'esempio
    assert client.get("/demo/personalizzazione").json()["anziano"]["nome"] == "Anna"
    report = client.get("/demo/report/settimanale", params={"dal": "2025-12-01"}).json()
    assert len(report["giorni"]) == 7
    assert report["giorni"][0]["simulato"] is True
    # stesso seme: rimandarlo non crea doppioni
    di_nuovo = carica_storico(client, TOKEN, 1, 7, datetime.date(2025, 12, 7))
    assert di_nuovo["nuovi"] == 0


def test_usa_la_personalizzazione_della_casa(client):
    personalizzazione = {
        "anziano": {"nome": "Bruno"},
        "farmaci": [{"id": "rivastigmine", "nome": "Rivastigmine", "dose": "1 patch", "orari": ["09:00"]}],
    }
    client.put("/programma-casa/personalizzazione", json=personalizzazione,
               headers={"Authorization": "Bearer " + TOKEN})
    carica_storico(client, TOKEN, 1, 7, datetime.date(2025, 12, 7))
    prese = client.get("/demo/eventi", params={"tipo": "farmaco"}).json()
    assert len(prese) > 0
    for presa in prese:
        assert presa["valori"]["farmaco_id"] in ["rivastigmine", None]
