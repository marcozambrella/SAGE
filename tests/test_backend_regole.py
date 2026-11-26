"""Test della logica pura del backend: fasce orarie, dosi, uscite, notte, report e scelta degli allarmi.

La casa è a Roma: a dicembre l'ora locale è UTC+1.
"""

import datetime

import pytest

from backend.allarmi import messaggio_allarme, serve_allarme
from backend.regole import (
    alzata_di_notte,
    con_regole_del_backend,
    errore_nella_personalizzazione,
    ora_nella_fascia,
    stato_delle_dosi,
    uscita_in_orario_vietato,
)
from backend.report import calcola_report_giornaliero, calcola_report_periodo, giorni_del_mese
from contratti.configurazione import FasciaOraria, Personalizzazione
from contratti.eventi import leggi_evento

GIORNO = datetime.date(2026, 12, 1)
# molto dopo il giorno di prova: tutte le finestre delle dosi sono finite
DOPO = datetime.datetime(2026, 12, 10, 12, 0, tzinfo=datetime.UTC)
FONTI = [{"telecamera_id": "cucina", "analizzatore": "prova", "confidenza": 0.9}]


def crea_personalizzazione(farmaci: list[dict] | None = None, regole: dict | None = None) -> Personalizzazione:
    dati = {"anziano": {"nome": "Anna", "obiettivo_acqua_ml": 1500}}
    if farmaci is not None:
        dati["farmaci"] = farmaci
    if regole is not None:
        dati["regole"] = regole
    return Personalizzazione.model_validate(dati)


def crea_evento(tipo: str, inizio: str, valori: dict, fine: str | None = None, simulato: bool = False):
    # l'id viene dal tipo e dall'ora: basta per i test, dove non ci sono due eventi uguali
    dati = {
        "id": tipo + "-" + inizio,
        "tipo": tipo,
        "inizio": inizio,
        "fine": fine,
        "stanza": "kitchen",
        "confidenza": 0.9,
        "fonti": FONTI,
        "valori": valori,
        "simulato": simulato,
    }
    return leggi_evento(dati)


def presa(inizio: str, farmaco_id: str | None):
    valori = {"farmaco_id": farmaco_id, "portapillole_aperto": True, "mano_alla_bocca": True}
    return crea_evento("farmaco", inizio, valori)


def bevuta(inizio: str, ml: float):
    valori = {"contenitore": "bicchiere", "capienza_ml": 250, "altezza_contenitore_px": 100,
              "livello_sceso_px": ml / 250 * 100, "percentuale": ml / 250 * 100, "ml": ml}
    return crea_evento("bevuta", inizio, valori)


DONEPEZIL = {"id": "donepezil", "nome": "Donepezil", "dose": "1 tablet", "orari": ["08:00"], "tolleranza_minuti": 30}


# --- fasce orarie ---

@pytest.mark.parametrize("ora, dentro", [
    ("09:00", True), ("16:59", True), ("17:00", False), ("08:59", False),
])
def test_fascia_normale(ora, dentro):
    fascia = FasciaOraria(dalle="09:00", alle="17:00")
    assert ora_nella_fascia(datetime.time.fromisoformat(ora), fascia) == dentro


@pytest.mark.parametrize("ora, dentro", [
    ("22:00", True), ("23:30", True), ("00:00", True), ("06:59", True), ("07:00", False), ("12:00", False),
    ("21:59", False),
])
def test_fascia_che_passa_la_mezzanotte(ora, dentro):
    fascia = FasciaOraria(dalle="22:00", alle="07:00")
    assert ora_nella_fascia(datetime.time.fromisoformat(ora), fascia) == dentro


def test_uscita_in_orario_vietato_nel_fuso_della_casa():
    personalizzazione = crea_personalizzazione(regole={"orari_uscita_vietati": [{"dalle": "22:00", "alle": "07:00"}]})
    # 21:30 UTC = 22:30 a Roma: vietata; 20:30 UTC = 21:30 a Roma: permessa
    di_notte = crea_evento("uscita", "2026-12-01T21:30:00+00:00", {"zona_id": "porta"})
    di_sera = crea_evento("uscita", "2026-12-01T20:30:00+00:00", {"zona_id": "porta"})
    assert uscita_in_orario_vietato(di_notte, personalizzazione)
    assert not uscita_in_orario_vietato(di_sera, personalizzazione)


def test_uscita_con_piu_fasce_vietate():
    fasce = [{"dalle": "22:00", "alle": "07:00"}, {"dalle": "13:00", "alle": "15:00"}]
    personalizzazione = crea_personalizzazione(regole={"orari_uscita_vietati": fasce})
    dopo_pranzo = crea_evento("uscita", "2026-12-01T14:00:00+01:00", {"zona_id": "porta"})
    assert uscita_in_orario_vietato(dopo_pranzo, personalizzazione)


def test_senza_fasce_vietate_nessuna_uscita_vietata():
    personalizzazione = crea_personalizzazione()
    uscita = crea_evento("uscita", "2026-12-01T03:00:00+01:00", {"zona_id": "porta"})
    assert not uscita_in_orario_vietato(uscita, personalizzazione)


def test_alzata_conta_solo_di_notte():
    personalizzazione = crea_personalizzazione()
    alle_tre = crea_evento("alzata_notturna", "2026-12-01T03:00:00+01:00", {"stanze": ["bathroom"]})
    di_pomeriggio = crea_evento("alzata_notturna", "2026-12-01T15:00:00+01:00", {"stanze": ["bathroom"]})
    assert alzata_di_notte(alle_tre, personalizzazione)
    assert not alzata_di_notte(di_pomeriggio, personalizzazione)


def test_personalizzazione_controllata():
    assert errore_nella_personalizzazione(crea_personalizzazione(farmaci=[DONEPEZIL])) is None
    fuso_sbagliato = crea_personalizzazione()
    fuso_sbagliato.fuso_orario = "Europe/Atlantide"
    assert "time zone" in errore_nella_personalizzazione(fuso_sbagliato)


# --- stato delle dosi (D38): in orario da un'ora prima fino a 30 minuti dopo, in ritardo fino a 2 ore dopo ---

def stato_unico(prese: list, adesso: datetime.datetime = DOPO, farmaci: list[dict] | None = None):
    if farmaci is None:
        farmaci = [DONEPEZIL]
    dosi = stato_delle_dosi(GIORNO, crea_personalizzazione(farmaci=farmaci), prese, adesso)
    assert len(dosi) == 1
    return dosi[0]


def test_dose_in_orario():
    dose = stato_unico([presa("2026-12-01T08:20:00+01:00", "donepezil")])
    assert dose.stato == "in_orario"
    assert dose.minuti_ritardo is None
    assert dose.farmaco_riconosciuto is True
    assert dose.ora_presa == datetime.datetime.fromisoformat("2026-12-01T08:20:00+01:00")


def test_dose_presa_fino_a_un_ora_prima_e_in_orario():
    assert stato_unico([presa("2026-12-01T07:20:00+01:00", "donepezil")]).stato == "in_orario"
    assert stato_unico([presa("2026-12-01T07:00:00+01:00", "donepezil")]).stato == "in_orario"


def test_dose_presa_piu_di_un_ora_prima_non_conta():
    assert stato_unico([presa("2026-12-01T06:59:00+01:00", "donepezil")]).stato == "saltata"


def test_dose_in_ritardo_con_minuti():
    dose = stato_unico([presa("2026-12-01T08:47:30+01:00", "donepezil")])
    assert dose.stato == "in_ritardo"
    assert dose.minuti_ritardo == 47


def test_fino_a_due_ore_dopo_e_in_ritardo_poi_saltata():
    dose = stato_unico([presa("2026-12-01T10:00:00+01:00", "donepezil")])
    assert dose.stato == "in_ritardo"
    assert dose.minuti_ritardo == 120
    assert stato_unico([presa("2026-12-01T10:01:00+01:00", "donepezil")]).stato == "saltata"


def test_dose_in_attesa_poi_saltata():
    # le 10:00 di Roma: la finestra della dose delle 8 finisce proprio adesso
    fine_finestra = datetime.datetime(2026, 12, 1, 9, 0, tzinfo=datetime.UTC)
    assert stato_unico([], adesso=fine_finestra).stato == "in_attesa"
    dose = stato_unico([], adesso=fine_finestra + datetime.timedelta(seconds=1))
    assert dose.stato == "saltata"
    assert dose.ora_presa is None
    assert dose.farmaco_riconosciuto is None


def test_tolleranza_piu_lunga_di_due_ore():
    farmaco = dict(DONEPEZIL)
    farmaco["tolleranza_minuti"] = 180
    assert stato_unico([presa("2026-12-01T10:30:00+01:00", "donepezil")], farmaci=[farmaco]).stato == "in_orario"
    assert stato_unico([presa("2026-12-01T11:01:00+01:00", "donepezil")], farmaci=[farmaco]).stato == "saltata"


def test_presa_non_riconosciuta_vale_per_la_dose():
    dose = stato_unico([presa("2026-12-01T08:10:00+01:00", None)])
    assert dose.stato == "in_orario"
    assert dose.farmaco_riconosciuto is False


def test_presa_di_un_altro_farmaco_non_conta():
    assert stato_unico([presa("2026-12-01T08:10:00+01:00", "memantine")]).stato == "saltata"


def test_presa_riconosciuta_preferita_a_quella_non_riconosciuta():
    prese = [presa("2026-12-01T08:00:00+01:00", None), presa("2026-12-01T08:50:00+01:00", "donepezil")]
    dose = stato_unico(prese)
    assert dose.stato == "in_ritardo"
    assert dose.farmaco_riconosciuto is True


def test_una_presa_conta_per_una_sola_dose():
    memantine = {"id": "memantine", "nome": "Memantine", "dose": "1 tablet", "orari": ["08:00"]}
    personalizzazione = crea_personalizzazione(farmaci=[DONEPEZIL, memantine])
    dosi = stato_delle_dosi(GIORNO, personalizzazione, [presa("2026-12-01T08:05:00+01:00", None)], DOPO)
    assert dosi[0].stato == "in_orario"
    assert dosi[1].stato == "saltata"


def test_due_dosi_dello_stesso_farmaco():
    farmaco = dict(DONEPEZIL)
    farmaco["orari"] = ["20:00", "08:00"]
    personalizzazione = crea_personalizzazione(farmaci=[farmaco])
    dosi = stato_delle_dosi(GIORNO, personalizzazione, [presa("2026-12-01T08:10:00+01:00", "donepezil")], DOPO)
    # in ordine di orario, e la presa delle 8 non vale anche per le 20
    assert dosi[0].orario_previsto == "08:00"
    assert dosi[0].stato == "in_orario"
    assert dosi[1].orario_previsto == "20:00"
    assert dosi[1].stato == "saltata"


def test_dose_di_sera_presa_dopo_mezzanotte():
    farmaco = dict(DONEPEZIL)
    farmaco["orari"] = ["23:30"]
    dose = stato_unico([presa("2026-12-02T00:10:00+01:00", "donepezil")], farmaci=[farmaco])
    assert dose.stato == "in_ritardo"
    assert dose.minuti_ritardo == 40


# --- report giornaliero ---

def eventi_di_una_giornata() -> tuple[list, Personalizzazione]:
    regole = {"orari_uscita_vietati": [{"dalle": "21:00", "alle": "07:00"}]}
    pasto = {"cibi": ["pasta", "salad"], "quanto_mangiato": "tutto"}
    eventi = [
        bevuta("2026-12-01T09:00:00+01:00", 200),
        bevuta("2026-12-01T13:00:00+01:00", 250.5),
        # 23:30 UTC = 00:30 del 2 dicembre a Roma: è del giorno dopo
        bevuta("2026-12-01T23:30:00+00:00", 300),
        crea_evento("pasto", "2026-12-01T12:30:00+01:00", pasto),
        crea_evento("pasto", "2026-12-01T19:30:00+01:00", {"cibi": ["soup"], "quanto_mangiato": "meno_di_meta"}),
        # piatto coperto: il pasto c'è, ma quanto ha mangiato non si sa
        crea_evento("pasto", "2026-12-01T08:00:00+01:00", {"cibi": ["coffee"], "quanto_mangiato": None}),
        crea_evento("alzata_notturna", "2026-12-01T02:00:00+01:00", {"stanze": ["bathroom"]},
                    fine="2026-12-01T02:12:00+01:00"),
        crea_evento("alzata_notturna", "2026-12-01T04:00:00+01:00", {"stanze": ["kitchen"]},
                    fine="2026-12-01T04:06:30+01:00"),
        # ancora in corso: conta, ma senza minuti
        crea_evento("alzata_notturna", "2026-12-01T23:00:00+01:00", {"stanze": ["hall"]}),
        # di giorno: non è un'alzata notturna
        crea_evento("alzata_notturna", "2026-12-01T15:00:00+01:00", {"stanze": ["hall"]},
                    fine="2026-12-01T15:30:00+01:00"),
        crea_evento("caduta", "2026-12-01T10:00:00+01:00", {"secondi_a_terra": 30}),
        crea_evento("uscita", "2026-12-01T11:00:00+01:00", {"zona_id": "porta"}),
        crea_evento("uscita", "2026-12-01T22:15:00+01:00", {"zona_id": "porta"}),
        presa("2026-12-01T08:40:00+01:00", "donepezil"),
    ]
    return eventi, crea_personalizzazione(farmaci=[DONEPEZIL], regole=regole)


def test_report_giornaliero():
    eventi, personalizzazione = eventi_di_una_giornata()
    report = calcola_report_giornaliero(GIORNO, eventi, personalizzazione, DOPO)
    assert report.data == GIORNO
    assert report.acqua_ml == 450.5
    assert report.bevute == 2
    assert report.obiettivo_acqua_ml == 1500
    # in ordine di ora: colazione non misurata, pranzo tutto, cena meno di metà
    assert len(report.pasti) == 3
    assert report.pasti[0].quanto_mangiato is None
    assert report.pasti[1].cibi == ["pasta", "salad"]
    assert report.pasti[1].quanto_mangiato == "tutto"
    assert report.pasti[2].quanto_mangiato == "meno_di_meta"
    assert report.alzate_notturne == 3
    assert report.minuti_fuori_letto_notte == 18.5
    assert report.cadute == 1
    assert report.uscite == 2
    assert report.uscite_in_orario_vietato == 1
    assert report.dosi[0].stato == "in_ritardo"
    assert report.dosi[0].minuti_ritardo == 40
    assert report.simulato is False


def test_giorno_dopo_prende_la_bevuta_dopo_mezzanotte():
    eventi, personalizzazione = eventi_di_una_giornata()
    report = calcola_report_giornaliero(datetime.date(2026, 12, 2), eventi, personalizzazione, DOPO)
    assert report.acqua_ml == 300
    assert report.bevute == 1


def test_report_di_un_giorno_simulato():
    eventi = [crea_evento("caduta", "2026-12-01T10:00:00+01:00", {}, simulato=True)]
    report = calcola_report_giornaliero(GIORNO, eventi, crea_personalizzazione(), DOPO)
    assert report.simulato is True
    assert report.cadute == 1


def test_report_di_un_giorno_vuoto():
    report = calcola_report_giornaliero(GIORNO, [], crea_personalizzazione(farmaci=[DONEPEZIL]), DOPO)
    assert report.acqua_ml == 0
    assert report.pasti == []
    assert report.dosi[0].stato == "saltata"


# --- ore di sonno (API.md, "Ore di sonno") ---

def sonno(inizio: str, fine: str | None):
    return crea_evento("sonno", inizio, {"zona_id": "letto"}, fine=fine)


def test_notte_normale():
    eventi = [sonno("2026-11-30T22:40:00+01:00", "2026-12-01T06:40:00+01:00")]
    report = calcola_report_giornaliero(GIORNO, eventi, crea_personalizzazione(), DOPO)
    assert report.sonno_minuti == 480
    assert report.addormentato_alle == datetime.datetime(2026, 11, 30, 21, 40, tzinfo=datetime.UTC)
    assert report.sveglio_alle == datetime.datetime(2026, 12, 1, 5, 40, tzinfo=datetime.UTC)


def test_notte_a_pezzi_con_un_alzata():
    eventi = [
        sonno("2026-11-30T23:00:00+01:00", "2026-12-01T02:00:00+01:00"),
        crea_evento("alzata_notturna", "2026-12-01T02:00:00+01:00", {"stanze": ["bathroom"]},
                    fine="2026-12-01T02:15:00+01:00"),
        sonno("2026-12-01T02:15:00+01:00", "2026-12-01T06:30:00+01:00"),
    ]
    report = calcola_report_giornaliero(GIORNO, eventi, crea_personalizzazione(), DOPO)
    # il buco dell'alzata non è sonno: 3 ore + 4 ore e 15
    assert report.sonno_minuti == 435
    assert report.alzate_notturne == 1
    assert report.minuti_fuori_letto_notte == 15
    assert report.addormentato_alle == datetime.datetime(2026, 11, 30, 22, 0, tzinfo=datetime.UTC)
    assert report.sveglio_alle == datetime.datetime(2026, 12, 1, 5, 30, tzinfo=datetime.UTC)


def test_nessun_sonno_visto():
    report = calcola_report_giornaliero(GIORNO, [], crea_personalizzazione(), DOPO)
    assert report.sonno_minuti is None
    assert report.addormentato_alle is None
    assert report.sveglio_alle is None


def test_sonno_a_cavallo_della_mezzanotte_conta_nel_giorno_dopo():
    # si addormenta la sera del primo dicembre: è la notte che finisce il 2
    eventi = [
        sonno("2026-12-01T23:30:00+01:00", "2026-12-02T01:00:00+01:00"),
        sonno("2026-12-02T01:10:00+01:00", "2026-12-02T07:00:00+01:00"),
    ]
    personalizzazione = crea_personalizzazione()
    report_del_primo = calcola_report_giornaliero(GIORNO, eventi, personalizzazione, DOPO)
    assert report_del_primo.sonno_minuti is None
    report_del_due = calcola_report_giornaliero(datetime.date(2026, 12, 2), eventi, personalizzazione, DOPO)
    assert report_del_due.sonno_minuti == 90 + 350
    assert report_del_due.addormentato_alle == datetime.datetime(2026, 12, 1, 22, 30, tzinfo=datetime.UTC)


def test_sonno_solo_nella_finestra_della_notte():
    # orari di notte 22:00 → 07:00: contano i pezzi che iniziano dalle 20:00 alle 11:00 (escluse)
    eventi = [
        sonno("2026-11-30T19:30:00+01:00", "2026-11-30T19:50:00+01:00"),
        sonno("2026-11-30T20:00:00+01:00", "2026-11-30T20:30:00+01:00"),
        sonno("2026-12-01T10:30:00+01:00", "2026-12-01T10:45:00+01:00"),
        # il riposino del pomeriggio non è sonno della notte
        sonno("2026-12-01T15:00:00+01:00", "2026-12-01T16:00:00+01:00"),
        # ancora in corso: non ha una durata e non conta
        sonno("2026-12-01T05:00:00+01:00", None),
    ]
    report = calcola_report_giornaliero(GIORNO, eventi, crea_personalizzazione(), DOPO)
    assert report.sonno_minuti == 30 + 15
    assert report.addormentato_alle == datetime.datetime(2026, 11, 30, 19, 0, tzinfo=datetime.UTC)
    assert report.sveglio_alle == datetime.datetime(2026, 12, 1, 9, 45, tzinfo=datetime.UTC)


def test_sonno_con_la_notte_della_personalizzazione():
    # notte tutta dopo la mezzanotte (01:00 → 06:00): la finestra va dalle 23:00 del giorno prima alle 10:00
    personalizzazione = crea_personalizzazione(regole={"orari_notte": {"dalle": "01:00", "alle": "06:00"}})
    eventi = [
        sonno("2026-11-30T22:30:00+01:00", "2026-11-30T22:50:00+01:00"),
        sonno("2026-11-30T23:10:00+01:00", "2026-12-01T06:10:00+01:00"),
    ]
    report = calcola_report_giornaliero(GIORNO, eventi, personalizzazione, DOPO)
    assert report.sonno_minuti == 420


def test_sonno_di_un_giorno_simulato():
    eventi = [crea_evento("sonno", "2026-11-30T22:40:00+01:00", {"zona_id": "letto"},
                          fine="2026-12-01T06:40:00+01:00", simulato=True)]
    report = calcola_report_giornaliero(GIORNO, eventi, crea_personalizzazione(), DOPO)
    assert report.simulato is True


def test_sonno_medio_sulle_notti_viste():
    eventi = [
        sonno("2026-11-30T22:00:00+01:00", "2026-12-01T06:00:00+01:00"),
        sonno("2026-12-01T23:00:00+01:00", "2026-12-02T05:00:00+01:00"),
    ]
    report = calcola_report_periodo("settimanale", GIORNO, datetime.date(2026, 12, 7), eventi,
                                    crea_personalizzazione(), DOPO)
    assert report.giorni[0].sonno_minuti == 480
    assert report.giorni[1].sonno_minuti == 360
    assert report.giorni[2].sonno_minuti is None
    # le notti senza dati non abbassano la media
    assert report.sonno_medio_minuti == 420


def test_sonno_medio_senza_notti_viste():
    report = calcola_report_periodo("settimanale", GIORNO, datetime.date(2026, 12, 7), [], crea_personalizzazione(),
                                    DOPO)
    assert report.sonno_medio_minuti is None


# --- agitazione, inattività, bagno (API.md, "Funzioni dalla ricerca su Alzheimer e demenza") ---

def test_agitazione_inattivita_e_bagno_nel_report():
    eventi = [
        crea_evento("agitazione", "2026-12-01T17:00:00+01:00", {"inversioni": 12},
                    fine="2026-12-01T17:20:00+01:00"),
        crea_evento("agitazione", "2026-12-01T18:30:00+01:00", {"inversioni": 6},
                    fine="2026-12-01T18:37:30+01:00"),
        # ancora in corso: non ha minuti
        crea_evento("agitazione", "2026-12-01T19:00:00+01:00", {"inversioni": 3}),
        crea_evento("inattivita", "2026-12-01T13:00:00+01:00", {"ultima_telecamera_id": "cucina"},
                    fine="2026-12-01T16:30:00+01:00"),
        crea_evento("visita_bagno", "2026-12-01T03:10:00+01:00", {"zona_id": "porta-bagno"}),
        crea_evento("visita_bagno", "2026-12-01T10:00:00+01:00", {"zona_id": "porta-bagno"}),
        crea_evento("visita_bagno", "2026-12-01T23:15:00+01:00", {"zona_id": "porta-bagno"}),
        # del giorno dopo
        crea_evento("visita_bagno", "2026-12-02T01:00:00+01:00", {"zona_id": "porta-bagno"}),
    ]
    personalizzazione = crea_personalizzazione()
    report = calcola_report_giornaliero(GIORNO, eventi, personalizzazione, DOPO)
    assert report.agitazione_minuti == 27.5
    assert report.allarmi_inattivita == 1
    assert report.visite_bagno == 3
    # negli orari di notte (22:00 → 07:00): quella delle 3:10 e quella delle 23:15
    assert report.visite_bagno_notte == 2
    periodo = calcola_report_periodo("settimanale", GIORNO, datetime.date(2026, 12, 7), eventi, personalizzazione,
                                     DOPO)
    assert periodo.giorni[0].agitazione_minuti == 27.5
    assert periodo.giorni[0].visite_bagno == 3
    assert periodo.giorni[1].visite_bagno == 1


# --- report di periodo ---

def test_report_settimanale():
    eventi, personalizzazione = eventi_di_una_giornata()
    al = datetime.date(2026, 12, 7)
    report = calcola_report_periodo("settimanale", GIORNO, al, eventi, personalizzazione, DOPO)
    assert len(report.giorni) == 7
    assert report.giorni[0].acqua_ml == 450.5
    assert report.giorni[0].dosi_in_ritardo == 1
    assert report.giorni[0].pasti == 3
    assert report.giorni[0].pasti_meno_di_meta == 1
    assert report.giorni[1].acqua_ml == 300
    assert report.giorni[1].pasti == 0
    assert report.giorni[1].pasti_meno_di_meta == 0
    assert report.acqua_media_ml == round(750.5 / 7, 1)
    # 1 dose presa su 7 previste
    assert report.aderenza_farmaci_percentuale == round(1 / 7 * 100, 1)
    assert report.cadute == 1
    assert report.uscite_in_orario_vietato == 1
    assert report.alzate_notturne_medie == round(3 / 7, 2)


def test_report_di_periodo_senza_giorni_futuri():
    eventi, personalizzazione = eventi_di_una_giornata()
    # il 2 dicembre alle 8:15 di Roma: la dose delle 8 è ancora in attesa e non conta nell'aderenza
    adesso = datetime.datetime(2026, 12, 2, 7, 15, tzinfo=datetime.UTC)
    report = calcola_report_periodo("settimanale", GIORNO, datetime.date(2026, 12, 7), eventi, personalizzazione,
                                    adesso)
    assert len(report.giorni) == 2
    assert report.giorni[1].dosi_previste == 1
    assert report.giorni[1].dosi_saltate == 0
    assert report.aderenza_farmaci_percentuale == 100


def test_aderenza_senza_farmaci():
    report = calcola_report_periodo("settimanale", GIORNO, datetime.date(2026, 12, 7), [], crea_personalizzazione(),
                                    DOPO)
    # nessuna dose da valutare: la web app scrive "nessun dato"
    assert report.aderenza_farmaci_percentuale is None
    assert report.acqua_media_ml == 0


def test_giorni_del_mese():
    assert giorni_del_mese(2028, 2) == (datetime.date(2028, 2, 1), datetime.date(2028, 2, 29))
    assert giorni_del_mese(2026, 12) == (datetime.date(2026, 12, 1), datetime.date(2026, 12, 31))
    with pytest.raises(ValueError):
        giorni_del_mese(2026, 13)


# --- allarmi ---

def personalizzazione_uscite(regole_extra: dict | None = None) -> Personalizzazione:
    regole = {"orari_uscita_vietati": [{"dalle": "21:00", "alle": "07:00"}]}
    if regole_extra is not None:
        regole.update(regole_extra)
    return crea_personalizzazione(regole=regole)


USCITA_DI_NOTTE = crea_evento("uscita", "2026-12-01T23:00:00+01:00", {"zona_id": "porta"})


def test_caduta_sempre_allarme():
    caduta = crea_evento("caduta", "2026-12-01T10:00:00+01:00", {})
    assert serve_allarme(caduta, personalizzazione_uscite())
    assert serve_allarme(caduta, None)


def test_storico_simulato_mai_allarme():
    caduta = crea_evento("caduta", "2026-12-01T10:00:00+01:00", {}, simulato=True)
    assert not serve_allarme(caduta, personalizzazione_uscite())


def test_eventi_non_urgenti_nessun_allarme():
    assert not serve_allarme(bevuta("2026-12-01T09:00:00+01:00", 200), personalizzazione_uscite())


def test_uscita_vietata_allarme():
    assert serve_allarme(USCITA_DI_NOTTE, personalizzazione_uscite())
    di_giorno = crea_evento("uscita", "2026-12-01T11:00:00+01:00", {"zona_id": "porta"})
    assert not serve_allarme(di_giorno, personalizzazione_uscite())
    # senza personalizzazione non si sanno gli orari vietati
    assert not serve_allarme(USCITA_DI_NOTTE, None)


def test_uscita_con_allarme_spento():
    assert not serve_allarme(USCITA_DI_NOTTE, personalizzazione_uscite({"allarme_uscita_attivo": False}))


def test_uscita_durante_la_pausa():
    in_pausa = personalizzazione_uscite({"pausa_fino_a": "2026-12-02T00:00:00+01:00"})
    assert not serve_allarme(USCITA_DI_NOTTE, in_pausa)
    pausa_finita = personalizzazione_uscite({"pausa_fino_a": "2026-12-01T22:00:00+01:00"})
    assert serve_allarme(USCITA_DI_NOTTE, pausa_finita)


def test_messaggi_degli_allarmi_con_ora_locale():
    caduta = crea_evento("caduta", "2026-12-01T09:05:00+00:00", {})
    testo = messaggio_allarme(caduta, personalizzazione_uscite())
    assert testo == "Possible fall: Anna may have fallen in the kitchen at 10:05."
    testo = messaggio_allarme(USCITA_DI_NOTTE, personalizzazione_uscite())
    assert testo == "Exit alert: Anna left the house at 23:00, during restricted hours."


# --- valori che scrive il backend ---

def bevuta_con_contenitore(contenitore_id: str | None):
    # mezza bottiglia vista da lontano: 30 px su 60 px, il programma di casa pensava a una capienza di 1000 ml
    valori = {"contenitore": "bottiglia", "contenitore_id": contenitore_id, "capienza_ml": 1000,
              "altezza_contenitore_px": 60, "livello_sceso_px": 30, "percentuale": 50, "ml": 500}
    return crea_evento("bevuta", "2026-12-01T09:00:00+01:00", valori)


def test_ml_ricalcolati_con_la_capienza_del_contenitore():
    contenitori = [{"id": "bottiglia-anna", "nome": "Water bottle", "tipo": "bottiglia", "capienza_ml": 1500}]
    personalizzazione = Personalizzazione.model_validate({"anziano": {"nome": "Anna"}, "contenitori": contenitori})
    ricalcolata = con_regole_del_backend(bevuta_con_contenitore("bottiglia-anna"), personalizzazione)
    assert ricalcolata.valori.ml == 750
    assert ricalcolata.valori.capienza_ml == 1500
    # contenitore sconosciuto o non riconosciuto: restano i ml del programma di casa
    assert con_regole_del_backend(bevuta_con_contenitore("altro"), personalizzazione).valori.ml == 500
    assert con_regole_del_backend(bevuta_con_contenitore(None), personalizzazione).valori.ml == 500
    assert con_regole_del_backend(bevuta_con_contenitore("bottiglia-anna"), None).valori.ml == 500


def test_uscita_segnata_in_orario_vietato():
    personalizzazione = crea_personalizzazione(regole={"orari_uscita_vietati": [{"dalle": "22:00", "alle": "07:00"}]})
    di_notte = crea_evento("uscita", "2026-12-01T23:00:00+01:00", {"zona_id": "porta"})
    di_giorno = crea_evento("uscita", "2026-12-01T11:00:00+01:00", {"zona_id": "porta"})
    assert di_notte.valori.in_orario_vietato is None
    assert con_regole_del_backend(di_notte, personalizzazione).valori.in_orario_vietato is True
    assert con_regole_del_backend(di_giorno, personalizzazione).valori.in_orario_vietato is False
