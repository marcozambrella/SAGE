"""Test dei contratti: un evento d'esempio per ogni tipo, configurazione e report si leggono e si riscrivono uguali."""

import datetime
import json

import pytest
from pydantic import ValidationError

from contratti.configurazione import ConfigurazioneCasa, Personalizzazione
from contratti.eventi import LETTORE_EVENTO, TIPI_URGENTI, leggi_evento
from contratti.report import ReportGiornaliero, ReportPeriodo

INIZIO = "2026-12-01T08:05:00+01:00"
FONTI = [{"telecamera_id": "cucina", "analizzatore": "bevuta", "confidenza": 0.8}]


def evento_esempio(tipo: str, valori: dict) -> dict:
    evento = {
        "id": "id-" + tipo,
        "tipo": tipo,
        "inizio": INIZIO,
        "stanza": "kitchen",
        "confidenza": 0.8,
        "fonti": FONTI,
        "valori": valori,
    }
    return evento


ESEMPI = [
    evento_esempio("caduta", {"secondi_a_terra": 12.0}),
    evento_esempio("uscita", {"zona_id": "porta-ingresso"}),
    # esempio di Marco (D9): scende 10 px su una bottiglia alta 100 px da 2 L → 10% → 200 ml
    evento_esempio("bevuta", {
        "contenitore": "bottiglia",
        "capienza_ml": 2000,
        "altezza_contenitore_px": 100,
        "livello_sceso_px": 10,
        "percentuale": 10,
        "ml": 200,
    }),
    evento_esempio("farmaco", {"farmaco_id": "donepezil", "somiglianza": 0.91, "portapillole_aperto": True,
                               "mano_alla_bocca": True}),
    evento_esempio("pasto", {"cibi": ["pasta", "salad"], "quanto_mangiato": "meta"}),
    evento_esempio("pasto", {"cibi": ["soup"], "quanto_mangiato": None}),
    evento_esempio("alzata_notturna", {"stanze": ["bedroom", "bathroom"]}),
]


@pytest.mark.parametrize("dati", ESEMPI)
def test_ogni_tipo_si_legge_e_si_riscrive_uguale(dati):
    evento = leggi_evento(dati)
    assert evento.tipo == dati["tipo"]
    # andata e ritorno in JSON: è quello che succede tra programma di casa e backend
    testo = LETTORE_EVENTO.dump_json(evento)
    riletto = leggi_evento(json.loads(testo))
    assert riletto == evento


def test_tipi_urgenti():
    assert TIPI_URGENTI == ["caduta", "uscita"]


def test_valori_del_tipo_sbagliato_rifiutati():
    # una bevuta con i valori di un'uscita
    dati = evento_esempio("bevuta", {"zona_id": "porta-ingresso"})
    with pytest.raises(ValidationError):
        leggi_evento(dati)


def test_tipo_sconosciuto_rifiutato():
    with pytest.raises(ValidationError):
        leggi_evento(evento_esempio("ballo", {}))


def test_ora_senza_fuso_rifiutata():
    dati = evento_esempio("caduta", {})
    dati["inizio"] = "2026-12-01T08:05:00"
    with pytest.raises(ValidationError):
        leggi_evento(dati)


def test_confidenza_fuori_scala_rifiutata():
    dati = evento_esempio("caduta", {})
    dati["confidenza"] = 1.5
    with pytest.raises(ValidationError):
        leggi_evento(dati)


def test_personalizzazione_minima_ha_valori_predefiniti():
    personalizzazione = Personalizzazione.model_validate({"anziano": {"nome": "Anna"}})
    assert personalizzazione.anziano.obiettivo_acqua_ml == 1500
    assert personalizzazione.regole.orari_notte.dalle == "22:00"
    assert personalizzazione.regole.allarme_uscita_attivo
    assert personalizzazione.fuso_orario == "Europe/Rome"


def test_configurazione_casa_completa():
    dati = {
        "telecamere": [{
            "id": "ingresso",
            "nome": "Front door",
            "stanza": "hall",
            "sorgente": "rtsp://192.168.1.20:554/stream1",
            "analizzatori": ["uscita", "caduta"],
            "zone": [{"id": "porta-ingresso", "tipo": "porta", "punti": [[0.1, 0.2], [0.4, 0.2], [0.4, 0.9]]}],
        }],
        "personalizzazione": {
            "anziano": {"nome": "Anna", "anno_nascita": 1941},
            "farmaci": [{"id": "donepezil", "nome": "Donepezil", "dose": "1 tablet", "orari": ["08:00", "20:00"]}],
            "contenitori": [{"id": "bottiglia", "nome": "Water bottle", "tipo": "bottiglia", "capienza_ml": 1500}],
            "telecamere": [{"id": "ingresso", "nome": "Front door", "stanza": "hall"}],
            "regole": {"orari_uscita_vietati": [{"dalle": "21:00", "alle": "07:00"}],
                       "portone_zona_id": "porta-ingresso"},
        },
        "cartella_foto_farmaci": "data/foto_farmaci",
    }
    configurazione = ConfigurazioneCasa.model_validate(dati)
    assert configurazione.telecamere[0].zone[0].tipo == "porta"
    assert configurazione.personalizzazione.farmaci[0].tolleranza_minuti == 30
    assert configurazione.personalizzazione.regole.portone_zona_id == "porta-ingresso"


def test_analizzatore_sconosciuto_rifiutato():
    with pytest.raises(ValidationError):
        ConfigurazioneCasa.model_validate({
            "telecamere": [{"id": "a", "nome": "a", "stanza": "a", "sorgente": "0", "analizzatori": ["ballo"]}],
            "personalizzazione": {"anziano": {"nome": "Anna"}},
            "cartella_foto_farmaci": "x",
        })


def test_report_si_leggono():
    giorno = ReportGiornaliero.model_validate({
        "data": "2026-12-01",
        "acqua_ml": 1200,
        "obiettivo_acqua_ml": 1500,
        "bevute": 6,
        "dosi": [{"farmaco_id": "donepezil", "nome": "Donepezil", "orario_previsto": "08:00", "stato": "in_ritardo",
                  "ora_presa": "2026-12-01T08:47:00+01:00", "minuti_ritardo": 47, "farmaco_riconosciuto": True}],
        "pasti": [{"ora": "2026-12-01T12:30:00+01:00", "cibi": ["pasta"], "quanto_mangiato": "tutto"}],
        "alzate_notturne": 2,
        "minuti_fuori_letto_notte": 18,
        "cadute": 0,
        "uscite": 1,
        "uscite_in_orario_vietato": 0,
    })
    assert giorno.data == datetime.date(2026, 12, 1)
    periodo = ReportPeriodo.model_validate({
        "tipo": "settimanale",
        "dal": "2026-11-30",
        "al": "2026-12-06",
        "giorni": [{"data": "2026-12-01", "acqua_ml": 1200, "dosi_previste": 2, "dosi_in_orario": 1,
                    "dosi_in_ritardo": 1, "dosi_saltate": 0, "pasti": 3, "pasti_meno_di_meta": 1,
                    "alzate_notturne": 2, "cadute": 0, "uscite_in_orario_vietato": 0}],
        "acqua_media_ml": 1200,
        "aderenza_farmaci_percentuale": 100,
        "cadute": 0,
        "uscite_in_orario_vietato": 0,
        "alzate_notturne_medie": 2,
    })
    assert len(periodo.giorni) == 1


@pytest.mark.parametrize("ora", ["25:00", "7:00", "08:60", "8"])
def test_orario_scritto_male_rifiutato(ora):
    with pytest.raises(ValidationError):
        Personalizzazione.model_validate({"anziano": {"nome": "Anna"},
                                          "farmaci": [{"id": "f", "nome": "F", "dose": "1", "orari": [ora]}]})


def test_aderenza_senza_dosi_valutate_e_none():
    periodo = ReportPeriodo.model_validate({
        "tipo": "mensile", "dal": "2026-12-01", "al": "2026-12-31", "giorni": [], "acqua_media_ml": 0,
        "aderenza_farmaci_percentuale": None, "cadute": 0, "uscite_in_orario_vietato": 0, "alzate_notturne_medie": 0,
    })
    assert periodo.aderenza_farmaci_percentuale is None
