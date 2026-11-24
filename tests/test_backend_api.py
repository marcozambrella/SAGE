"""Test delle chiamate del backend (contratti/API.md) con il client di test di FastAPI: niente rete vera.

Date nel passato (dicembre 2025): i report non hanno righe per i giorni che non sono ancora cominciati.
"""

import base64
import datetime

import pytest
from fastapi.testclient import TestClient

from backend.app import app
from backend.archivio import ArchivioDatabase

TOKEN = "token-di-prova"
CON_TOKEN = {"Authorization": "Bearer " + TOKEN}
# un finto JPEG: al backend basta che sia base64 valido
FOTO = b"\xff\xd8\xff\xe0finto jpeg"
FONTI = [{"telecamera_id": "cucina", "analizzatore": "prova", "confidenza": 0.9}]

PERSONALIZZAZIONE = {
    "anziano": {"nome": "Anna", "obiettivo_acqua_ml": 1500},
    "farmaci": [{"id": "donepezil", "nome": "Donepezil", "dose": "1 tablet", "orari": ["08:00"]}],
    "regole": {"orari_uscita_vietati": [{"dalle": "21:00", "alle": "07:00"}]},
}

@pytest.fixture
def client(tmp_path):
    # ogni test parte da una casa demo vuota, in un file SQLite temporaneo
    app.state.archivio = ArchivioDatabase(str(tmp_path / "prova.sqlite3"))
    app.state.token_casa = TOKEN
    app.state.token_cron = ""
    app.state.segreto_webhook = ""
    # senza bot gli allarmi finiscono nel log: i test li cercano lì (il bot ha i suoi test in test_backend_telegram)
    app.state.telegram = None
    return TestClient(app)


def allarmi_nel_log(caplog) -> list[str]:
    allarmi = []
    for riga in caplog.records:
        if riga.name == "sage.allarmi":
            allarmi.append(riga.getMessage())
    return allarmi


def evento(id_evento: str, tipo: str, inizio: str, valori: dict, foto: bytes | None = None) -> dict:
    dati = {"id": id_evento, "tipo": tipo, "inizio": inizio, "stanza": "kitchen", "confidenza": 0.9,
            "fonti": FONTI, "valori": valori}
    if foto is not None:
        dati["foto_prova"] = base64.b64encode(foto).decode()
    return dati


def bevuta(id_evento: str, inizio: str, ml: float) -> dict:
    valori = {"contenitore": "bicchiere", "capienza_ml": 250, "altezza_contenitore_px": 100,
              "livello_sceso_px": ml / 250 * 100, "percentuale": ml / 250 * 100, "ml": ml}
    return evento(id_evento, "bevuta", inizio, valori)


def configura(client: TestClient) -> None:
    risposta = client.put("/programma-casa/personalizzazione", json=PERSONALIZZAZIONE, headers=CON_TOKEN)
    assert risposta.status_code == 200


# --- token del programma di casa ---

def test_senza_token_rifiutato(client):
    assert client.put("/programma-casa/personalizzazione", json=PERSONALIZZAZIONE).status_code == 401
    assert client.post("/programma-casa/eventi", json=[]).status_code == 401


def test_token_sbagliato_rifiutato(client):
    sbagliato = {"Authorization": "Bearer altro"}
    assert client.post("/programma-casa/eventi", json=[], headers=sbagliato).status_code == 401


def test_senza_token_configurato_nessuno_scrive(client):
    app.state.token_casa = ""
    assert client.post("/programma-casa/eventi", json=[], headers={"Authorization": "Bearer "}).status_code == 401


# --- personalizzazione ---

def test_casa_non_configurata(client):
    assert client.get("/demo/personalizzazione").status_code == 404
    assert client.get("/demo/report/giornaliero", params={"data": "2025-12-01"}).status_code == 404


def test_personalizzazione_salvata_e_letta(client):
    configura(client)
    letta = client.get("/demo/personalizzazione").json()
    assert letta["anziano"]["nome"] == "Anna"
    assert letta["farmaci"][0]["tolleranza_minuti"] == 30
    assert letta["fuso_orario"] == "Europe/Rome"


def test_personalizzazione_con_orario_sbagliato_rifiutata(client):
    sbagliata = {"anziano": {"nome": "Anna"}, "regole": {"orari_notte": {"dalle": "22", "alle": "07:00"}}}
    risposta = client.put("/programma-casa/personalizzazione", json=sbagliata, headers=CON_TOKEN)
    assert risposta.status_code == 422


def test_pausa_e_spegnimento_restano_quelli_del_backend(client):
    configura(client)
    # come fa il bot Telegram: pausa e allarme spento cambiati sul backend
    pausa_fino_a = datetime.datetime.fromisoformat("2025-12-01T23:00:00+01:00")
    app.state.archivio.cambia_allarme_uscita(False, pausa_fino_a)
    # il programma di casa rimanda la sua personalizzazione con l'allarme attivo
    client.put("/programma-casa/personalizzazione", json=PERSONALIZZAZIONE, headers=CON_TOKEN)
    letta = client.get("/demo/personalizzazione").json()
    assert letta["regole"]["allarme_uscita_attivo"] is False
    assert letta["regole"]["pausa_fino_a"] == "2025-12-01T23:00:00+01:00"


# --- eventi ---

def test_eventi_ricevuti_una_volta_sola(client):
    eventi = [bevuta("b1", "2025-12-01T09:00:00+01:00", 200), bevuta("b2", "2025-12-01T10:00:00+01:00", 150)]
    risposta = client.post("/programma-casa/eventi", json=eventi, headers=CON_TOKEN)
    assert risposta.json() == {"ricevuti": 2, "nuovi": 2}
    # rimandati (per esempio dopo un errore di rete) non si duplicano
    risposta = client.post("/programma-casa/eventi", json=eventi, headers=CON_TOKEN)
    assert risposta.json() == {"ricevuti": 2, "nuovi": 0}
    assert len(client.get("/demo/eventi").json()) == 2


def test_evento_non_valido_rifiutato(client):
    sbagliato = evento("x", "bevuta", "2025-12-01T09:00:00+01:00", {"zona_id": "porta"})
    assert client.post("/programma-casa/eventi", json=[sbagliato], headers=CON_TOKEN).status_code == 422


def test_foto_non_base64_rifiutata_e_niente_salvato(client):
    buono = bevuta("b1", "2025-12-01T09:00:00+01:00", 200)
    sbagliato = evento("c1", "caduta", "2025-12-01T10:00:00+01:00", {})
    sbagliato["foto_prova"] = "non è base64!"
    risposta = client.post("/programma-casa/eventi", json=[buono, sbagliato], headers=CON_TOKEN)
    assert risposta.status_code == 422
    assert client.get("/demo/eventi").json() == []


def test_lista_eventi_filtrata_in_ordine_e_senza_foto(client):
    eventi = [
        bevuta("b2", "2025-12-02T10:00:00+01:00", 150),
        bevuta("b1", "2025-12-01T09:00:00+01:00", 200),
        evento("c1", "caduta", "2025-12-01T10:00:00+01:00", {}, foto=FOTO),
        # 23:30 UTC del 2 = 00:30 del 3 dicembre a Roma
        bevuta("b3", "2025-12-02T23:30:00+00:00", 100),
    ]
    client.post("/programma-casa/eventi", json=eventi, headers=CON_TOKEN)

    tutti = client.get("/demo/eventi").json()
    ids = []
    for letto in tutti:
        ids.append(letto["id"])
        assert letto["foto_prova"] is None
    assert ids == ["b1", "c1", "b2", "b3"]

    del_primo = client.get("/demo/eventi", params={"dal": "2025-12-01", "al": "2025-12-01"}).json()
    assert len(del_primo) == 2
    del_secondo = client.get("/demo/eventi", params={"dal": "2025-12-02", "al": "2025-12-02"}).json()
    assert len(del_secondo) == 1
    bevute = client.get("/demo/eventi", params={"tipo": "bevuta"}).json()
    assert len(bevute) == 3


def test_foto_di_prova(client):
    client.post("/programma-casa/eventi", json=[evento("c1", "caduta", "2025-12-01T10:00:00+01:00", {}, foto=FOTO)],
                headers=CON_TOKEN)
    risposta = client.get("/demo/eventi/c1/foto")
    assert risposta.status_code == 200
    assert risposta.headers["content-type"] == "image/jpeg"
    assert risposta.content == FOTO
    assert client.get("/demo/eventi/altro/foto").status_code == 404


# --- allarmi ---

def test_caduta_fa_partire_l_allarme(client, caplog):
    configura(client)
    caduta = evento("c1", "caduta", "2025-12-01T10:00:00+01:00", {}, foto=FOTO)
    client.post("/programma-casa/eventi", json=[caduta], headers=CON_TOKEN)
    allarmi = allarmi_nel_log(caplog)
    assert len(allarmi) == 1
    assert "Possible fall: Anna may have fallen in the kitchen at 10:00." in allarmi[0]
    # rimandata: l'allarme non riparte
    client.post("/programma-casa/eventi", json=[caduta], headers=CON_TOKEN)
    assert len(allarmi_nel_log(caplog)) == 1


def test_uscita_allarme_solo_in_orario_vietato(client, caplog):
    configura(client)
    di_giorno = evento("u1", "uscita", "2025-12-01T11:00:00+01:00", {"zona_id": "porta"})
    di_notte = evento("u2", "uscita", "2025-12-01T23:00:00+01:00", {"zona_id": "porta"})
    client.post("/programma-casa/eventi", json=[di_giorno, di_notte], headers=CON_TOKEN)
    allarmi = allarmi_nel_log(caplog)
    assert len(allarmi) == 1
    assert "Exit alert: Anna left the house at 23:00, during restricted hours." in allarmi[0]


def test_eventi_simulati_senza_allarmi(client, caplog):
    configura(client)
    caduta = evento("c1", "caduta", "2025-12-01T10:00:00+01:00", {})
    caduta["simulato"] = True
    client.post("/programma-casa/eventi", json=[caduta], headers=CON_TOKEN)
    assert allarmi_nel_log(caplog) == []


# --- report ---

def manda_una_giornata(client: TestClient) -> None:
    configura(client)
    presa = {"farmaco_id": "donepezil", "portapillole_aperto": True, "mano_alla_bocca": True}
    eventi = [
        bevuta("b1", "2025-12-01T09:00:00+01:00", 200),
        bevuta("b2", "2025-12-01T15:00:00+01:00", 300),
        evento("f1", "farmaco", "2025-12-01T08:45:00+01:00", presa),
        evento("p1", "pasto", "2025-12-01T12:30:00+01:00", {"cibi": ["pasta"], "quanto_mangiato": "meta"}),
        evento("u1", "uscita", "2025-12-01T22:00:00+01:00", {"zona_id": "porta"}),
    ]
    client.post("/programma-casa/eventi", json=eventi, headers=CON_TOKEN)


def test_report_giornaliero(client):
    manda_una_giornata(client)
    report = client.get("/demo/report/giornaliero", params={"data": "2025-12-01"}).json()
    assert report["acqua_ml"] == 500
    assert report["bevute"] == 2
    assert report["dosi"][0]["stato"] == "in_ritardo"
    assert report["dosi"][0]["minuti_ritardo"] == 45
    assert report["pasti"][0]["cibi"] == ["pasta"]
    assert report["pasti"][0]["quanto_mangiato"] == "meta"
    assert report["uscite_in_orario_vietato"] == 1


def test_report_settimanale(client):
    manda_una_giornata(client)
    report = client.get("/demo/report/settimanale", params={"dal": "2025-11-30"}).json()
    assert report["tipo"] == "settimanale"
    assert report["dal"] == "2025-11-30"
    assert report["al"] == "2025-12-06"
    assert len(report["giorni"]) == 7
    assert report["giorni"][1]["acqua_ml"] == 500


def test_report_mensile(client):
    manda_una_giornata(client)
    report = client.get("/demo/report/mensile", params={"mese": "2025-12"}).json()
    assert report["dal"] == "2025-12-01"
    assert report["al"] == "2025-12-31"
    assert report["giorni"][0]["dosi_in_ritardo"] == 1


def test_report_mensile_mese_sbagliato(client):
    configura(client)
    assert client.get("/demo/report/mensile", params={"mese": "2025-13"}).status_code == 422
    assert client.get("/demo/report/mensile", params={"mese": "dicembre"}).status_code == 422


def test_cors_aperto_per_la_web_app(client):
    risposta = client.get("/demo/eventi", headers={"Origin": "http://localhost:5173"})
    assert risposta.headers["access-control-allow-origin"] == "*"


# --- coordinamento degli eventi (API.md): i doppioni non si duplicano e non si perdono ---

def da_telecamera(dati: dict, telecamera: str, confidenza: float) -> dict:
    """Lo stesso evento come lo manderebbe un'altra telecamera."""
    copia = dict(dati)
    copia["fonti"] = [{"telecamera_id": telecamera, "analizzatore": dati["tipo"], "confidenza": confidenza}]
    copia["confidenza"] = confidenza
    return copia


def test_caduta_da_due_telecamere_un_solo_evento_e_un_solo_allarme(client, caplog):
    configura(client)
    dalla_cucina = da_telecamera(evento("c-cucina", "caduta", "2025-12-01T10:00:00+01:00", {}), "cucina", 0.7)
    dal_salotto = da_telecamera(evento("c-salotto", "caduta", "2025-12-01T10:00:04+01:00", {}, foto=FOTO),
                                "salotto", 0.9)
    client.post("/programma-casa/eventi", json=[dalla_cucina], headers=CON_TOKEN)
    # il doppione arriva dopo, in un'altra chiamata: aggiorna l'evento ma non rimanda l'allarme
    risposta = client.post("/programma-casa/eventi", json=[dal_salotto], headers=CON_TOKEN)
    assert risposta.json() == {"ricevuti": 1, "nuovi": 1}
    assert len(allarmi_nel_log(caplog)) == 1

    eventi = client.get("/demo/eventi").json()
    assert len(eventi) == 1
    assert eventi[0]["id"] == "c-cucina"
    assert eventi[0]["confidenza"] == 0.9
    assert len(eventi[0]["fonti"]) == 2
    assert eventi[0]["ha_foto"] is True
    assert eventi[0]["foto_prova"] is None
    # la foto dell'evento coordinato è quella del salotto, l'unica che c'è
    assert client.get("/demo/eventi/c-cucina/foto").content == FOTO


def test_doppioni_nella_stessa_chiamata_e_rinvii(client, caplog):
    configura(client)
    prima = da_telecamera(evento("a", "caduta", "2025-12-01T10:00:00+01:00", {}), "cucina", 0.8)
    seconda = da_telecamera(evento("b", "caduta", "2025-12-01T10:00:02+01:00", {}), "salotto", 0.8)
    client.post("/programma-casa/eventi", json=[prima, seconda], headers=CON_TOKEN)
    # rimandati dopo un errore di rete
    risposta = client.post("/programma-casa/eventi", json=[prima, seconda], headers=CON_TOKEN)
    assert risposta.json() == {"ricevuti": 2, "nuovi": 0}
    assert len(allarmi_nel_log(caplog)) == 1
    assert len(client.get("/demo/eventi").json()) == 1


def test_cadute_lontane_due_eventi_e_due_allarmi(client, caplog):
    configura(client)
    prima = evento("a", "caduta", "2025-12-01T10:00:00+01:00", {})
    dopo = evento("b", "caduta", "2025-12-01T10:05:00+01:00", {})
    client.post("/programma-casa/eventi", json=[prima, dopo], headers=CON_TOKEN)
    assert len(allarmi_nel_log(caplog)) == 2
    assert len(client.get("/demo/eventi").json()) == 2


def test_bevuta_da_due_telecamere_contata_una_volta(client):
    configura(client)
    dalla_cucina = da_telecamera(bevuta("b-cucina", "2025-12-01T09:00:00+01:00", 200), "cucina", 0.9)
    dal_salotto = da_telecamera(bevuta("b-salotto", "2025-12-01T09:00:03+01:00", 180), "salotto", 0.6)
    client.post("/programma-casa/eventi", json=[dalla_cucina, dal_salotto], headers=CON_TOKEN)
    report = client.get("/demo/report/giornaliero", params={"data": "2025-12-01"}).json()
    assert report["bevute"] == 1
    assert report["acqua_ml"] == 200


# --- valori scritti dal backend e periodo ---

def test_eventi_con_i_valori_del_backend(client):
    personalizzazione = dict(PERSONALIZZAZIONE)
    personalizzazione["contenitori"] = [{"id": "bicchiere-anna", "nome": "Glass", "tipo": "bicchiere",
                                         "capienza_ml": 300}]
    client.put("/programma-casa/personalizzazione", json=personalizzazione, headers=CON_TOKEN)
    bevuta_riconosciuta = bevuta("b1", "2025-12-01T09:00:00+01:00", 125)
    bevuta_riconosciuta["valori"]["contenitore_id"] = "bicchiere-anna"
    uscita = evento("u1", "uscita", "2025-12-01T23:00:00+01:00", {"zona_id": "porta"})
    client.post("/programma-casa/eventi", json=[bevuta_riconosciuta, uscita], headers=CON_TOKEN)
    eventi = client.get("/demo/eventi").json()
    # 50% di un bicchiere da 300 ml
    assert eventi[0]["valori"]["ml"] == 150
    assert eventi[1]["valori"]["in_orario_vietato"] is True
    assert eventi[1]["ha_foto"] is False
    report = client.get("/demo/report/giornaliero", params={"data": "2025-12-01"}).json()
    assert report["acqua_ml"] == 150


def test_periodo_della_casa_demo(client):
    assert client.get("/demo/periodo").json() == {"dal": None, "al": None}
    configura(client)
    eventi = [
        bevuta("b1", "2025-12-03T09:00:00+01:00", 100),
        # 23:30 UTC del 30 novembre = 00:30 del primo dicembre a Roma
        bevuta("b2", "2025-11-30T23:30:00+00:00", 100),
        bevuta("b3", "2025-12-05T20:00:00+01:00", 100),
    ]
    client.post("/programma-casa/eventi", json=eventi, headers=CON_TOKEN)
    assert client.get("/demo/periodo").json() == {"dal": "2025-12-01", "al": "2025-12-05"}


def test_aderenza_nulla_senza_dosi_valutate(client):
    client.put("/programma-casa/personalizzazione", json={"anziano": {"nome": "Anna"}}, headers=CON_TOKEN)
    report = client.get("/demo/report/settimanale", params={"dal": "2025-12-01"}).json()
    assert report["aderenza_farmaci_percentuale"] is None
