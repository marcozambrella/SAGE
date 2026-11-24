"""Test dello storico simulato della casa demo (D22): riproducibile, valido per i contratti, plausibile, e caricato
nel backend con la stessa chiamata del programma di casa (client di test di FastAPI, niente rete vera)."""

import datetime
from collections import Counter

import pytest
from fastapi.testclient import TestClient

from backend.app import app
from backend.archivio import ArchivioDatabase
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


def test_tre_giorni_di_poca_acqua_nell_ultima_settimana():
    eventi = genera_storico(PERSONALIZZAZIONE_DEMO, DAL, AL, SEME_PREDEFINITO)
    report = calcola_report_periodo("mensile", DAL, AL, eventi, PERSONALIZZAZIONE_DEMO, DOPO)
    giorni_bassi = []
    for indice in range(len(report.giorni)):
        # meno della metà dell'obiettivo (1500 ml)
        if report.giorni[indice].acqua_ml < 750:
            giorni_bassi.append(indice)
    ultima_settimana = []
    for indice in giorni_bassi:
        if indice >= len(report.giorni) - 7:
            ultima_settimana.append(indice)
    assert len(ultima_settimana) >= 2
    assert ultima_settimana[-1] - ultima_settimana[0] <= 2


def test_pasti_in_categorie_credibili_e_scarsi_nei_giorni_di_poca_acqua():
    eventi = genera_storico(PERSONALIZZAZIONE_DEMO, DAL, AL, SEME_PREDEFINITO)
    report = calcola_report_periodo("mensile", DAL, AL, eventi, PERSONALIZZAZIONE_DEMO, DOPO)
    categorie = Counter()
    for evento in eventi:
        if evento.tipo == "pasto":
            categorie[evento.valori.quanto_mangiato] = categorie[evento.valori.quanto_mangiato] + 1
    # di solito mangia tutto o metà; qualche pasto lasciato e qualcuno non misurato
    assert categorie["tutto"] > categorie["meta"] > categorie["meno_di_meta"] > 0
    assert categorie[None] > 0

    # i giorni di poca acqua (meno di metà dell'obiettivo) sono anche quelli dei pasti scarsi
    scarsi_nei_giorni_difficili = 0
    scarsi_negli_altri = 0
    giorni_difficili = 0
    for giorno in report.giorni:
        if giorno.acqua_ml < 750:
            giorni_difficili = giorni_difficili + 1
            scarsi_nei_giorni_difficili = scarsi_nei_giorni_difficili + giorno.pasti_meno_di_meta
        else:
            scarsi_negli_altri = scarsi_negli_altri + giorno.pasti_meno_di_meta
    altri_giorni = len(report.giorni) - giorni_difficili
    assert scarsi_nei_giorni_difficili / giorni_difficili > 3 * scarsi_negli_altri / altri_giorni


def test_bevute_con_il_contenitore_della_personalizzazione():
    eventi = genera_storico(PERSONALIZZAZIONE_DEMO, DAL, DAL, SEME_PREDEFINITO)
    ids_contenitori = []
    for contenitore in PERSONALIZZAZIONE_DEMO.contenitori:
        ids_contenitori.append(contenitore.id)
    bevute = 0
    for evento in eventi:
        if evento.tipo == "bevuta":
            bevute = bevute + 1
            assert evento.valori.contenitore_id in ids_contenitori
    assert bevute > 0


@pytest.fixture
def client(tmp_path):
    app.state.archivio = ArchivioDatabase(str(tmp_path / "prova.sqlite3"))
    app.state.token_casa = TOKEN
    app.state.telegram = None
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
