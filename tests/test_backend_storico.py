"""Test dello storico simulato della casa demo (D22): riproducibile, valido per i contratti, plausibile, e caricato
nel backend con la stessa chiamata del programma di casa (client di test di FastAPI, niente rete vera)."""

import datetime
from collections import Counter
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from backend.app import app
from backend.archivio import ArchivioDatabase
from backend.coordinatore import coordina
from backend.report import calcola_report_giornaliero, calcola_report_periodo
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


def test_sonno_credibile_e_notti_agitate_nei_giorni_di_poca_acqua():
    eventi = genera_storico(PERSONALIZZAZIONE_DEMO, DAL, AL, SEME_PREDEFINITO)
    roma = ZoneInfo(PERSONALIZZAZIONE_DEMO.fuso_orario)
    sonno_difficili = []
    alzate_difficili = []
    sonno_altri = []
    alzate_altri = []
    for indice in range(28):
        data = DAL + datetime.timedelta(days=indice)
        report = calcola_report_giornaliero(data, eventi, PERSONALIZZAZIONE_DEMO, DOPO)
        if indice == 0:
            # il sonno del primo giorno comincerebbe prima dello storico
            assert report.sonno_minuti is None
            continue
        assert 6 * 60 <= report.sonno_minuti <= 8 * 60
        addormentato = report.addormentato_alle.astimezone(roma)
        assert addormentato.date() == data - datetime.timedelta(days=1)
        assert datetime.time(22, 0) <= addormentato.time() <= datetime.time(23, 30)
        # sveglio dopo l'ultima alzata: le alzate sono i buchi tra i pezzi di sonno
        assert report.sveglio_alle > report.addormentato_alle
        if report.acqua_ml < 750:
            sonno_difficili.append(report.sonno_minuti)
            alzate_difficili.append(report.alzate_notturne)
        else:
            sonno_altri.append(report.sonno_minuti)
            alzate_altri.append(report.alzate_notturne)
    # la settimana difficile si vede anche di notte: più alzate e meno sonno
    assert len(sonno_difficili) >= 2
    assert sum(alzate_difficili) / len(alzate_difficili) > 2 * sum(alzate_altri) / len(alzate_altri)
    assert sum(sonno_difficili) / len(sonno_difficili) < sum(sonno_altri) / len(sonno_altri) - 30


def test_storico_comincia_dal_primo_giorno():
    eventi = genera_storico(PERSONALIZZAZIONE_DEMO, DAL, AL, SEME_PREDEFINITO)
    roma = ZoneInfo(PERSONALIZZAZIONE_DEMO.fuso_orario)
    primo = eventi[0].inizio
    for evento in eventi:
        primo = min(primo, evento.inizio)
    # /demo/periodo apre lo storico dal primo evento: niente sonno iniziato il giorno prima
    assert primo.astimezone(roma).date() == DAL


def report_dei_giorni(eventi: list) -> list:
    report = []
    for indice in range(28):
        data = DAL + datetime.timedelta(days=indice)
        report.append(calcola_report_giornaliero(data, eventi, PERSONALIZZAZIONE_DEMO, DOPO))
    return report


def media_nei_giorni_difficili_e_negli_altri(report: list, campo: str) -> tuple[float, float]:
    """I giorni difficili sono quelli di poca acqua (meno di metà dell'obiettivo)."""
    difficili = []
    altri = []
    for giorno in report:
        if giorno.acqua_ml < 750:
            difficili.append(getattr(giorno, campo))
        else:
            altri.append(getattr(giorno, campo))
    return sum(difficili) / len(difficili), sum(altri) / len(altri)


def test_agitazione_di_sera_e_di_piu_nei_giorni_difficili():
    eventi = genera_storico(PERSONALIZZAZIONE_DEMO, DAL, AL, SEME_PREDEFINITO)
    roma = ZoneInfo(PERSONALIZZAZIONE_DEMO.fuso_orario)
    di_sera = 0
    episodi = 0
    for evento in eventi:
        if evento.tipo == "agitazione":
            episodi = episodi + 1
            if 16 <= evento.inizio.astimezone(roma).hour < 20:
                di_sera = di_sera + 1
    # sundowning: quasi sempre nel tardo pomeriggio e la sera
    assert episodi > 10
    assert di_sera / episodi > 0.6
    difficili, altri = media_nei_giorni_difficili_e_negli_altri(report_dei_giorni(eventi), "agitazione_minuti")
    assert difficili > 3 * altri


def test_visite_al_bagno_e_piu_di_notte_nei_giorni_difficili():
    eventi = genera_storico(PERSONALIZZAZIONE_DEMO, DAL, AL, SEME_PREDEFINITO)
    report = report_dei_giorni(eventi)
    for giorno in report:
        assert 2 <= giorno.visite_bagno <= 12
    difficili, altri = media_nei_giorni_difficili_e_negli_altri(report, "visite_bagno_notte")
    assert difficili > 2 * altri
    for evento in eventi:
        if evento.tipo == "visita_bagno":
            assert evento.fonti[0].analizzatore == "bagno"


def test_una_sola_inattivita_e_nessuno_visto_in_quelle_ore():
    eventi = genera_storico(PERSONALIZZAZIONE_DEMO, DAL, AL, SEME_PREDEFINITO)
    grezzi_inattivita = []
    for evento in eventi:
        if evento.tipo == "inattivita":
            grezzi_inattivita.append(evento)
    # due grezzi come dal programma di casa (allarme e fine), un solo fatto coordinato
    assert len(grezzi_inattivita) == 2
    assert grezzi_inattivita[0].fine is None
    assert len(coordina(grezzi_inattivita)) == 1
    ultima_volta = grezzi_inattivita[1].inizio
    ricompare = grezzi_inattivita[1].fine
    ore = (ricompare - ultima_volta).total_seconds() / 3600
    assert PERSONALIZZAZIONE_DEMO.regole.ore_inattivita < ore < PERSONALIZZAZIONE_DEMO.regole.ore_inattivita + 1.5
    for evento in eventi:
        if evento.tipo == "inattivita":
            continue
        fine = evento.fine
        if fine is None:
            fine = evento.inizio
        assert fine < ultima_volta or evento.inizio > ricompare
    # i report del backend usano gli eventi coordinati
    coordinati = []
    for coordinato in coordina(eventi):
        coordinati.append(coordinato.evento)
    allarmi_inattivita = 0
    for giorno in report_dei_giorni(coordinati):
        allarmi_inattivita = allarmi_inattivita + giorno.allarmi_inattivita
    assert allarmi_inattivita == 1


def test_cambiamenti_solo_nella_settimana_difficile():
    eventi = genera_storico(PERSONALIZZAZIONE_DEMO, DAL, AL, SEME_PREDEFINITO)
    ultima_settimana = calcola_report_periodo("settimanale", AL - datetime.timedelta(days=6), AL, eventi,
                                              PERSONALIZZAZIONE_DEMO, DOPO)
    cosa = []
    for cambiamento in ultima_settimana.cambiamenti:
        cosa.append(cambiamento.cosa)
    # tre giorni con poca acqua e più agitazione la sera
    assert "acqua" in cosa
    assert "agitazione" in cosa
    # le settimane normali non hanno cambiamenti, anche con le visite al bagno accese
    regole = PERSONALIZZAZIONE_DEMO.regole.model_copy(update={"visite_bagno_attive": True})
    con_bagno = PERSONALIZZAZIONE_DEMO.model_copy(update={"regole": regole})
    # dal 15° giorno ci sono due settimane prima; fino al 18° la settimana non tocca i giorni difficili
    for inizio in range(14, 18):
        dal = DAL + datetime.timedelta(days=inizio)
        settimana = calcola_report_periodo("settimanale", dal, dal + datetime.timedelta(days=6), eventi, con_bagno,
                                           DOPO)
        assert settimana.cambiamenti == []


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
