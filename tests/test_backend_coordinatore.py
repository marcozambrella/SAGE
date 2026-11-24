"""Test del coordinatore degli eventi (contratti/API.md, "Coordinamento degli eventi"): logica pura."""

import datetime

from backend.coordinatore import coordina
from contratti.eventi import leggi_evento

ORA = datetime.datetime(2026, 12, 1, 10, 0, 0, tzinfo=datetime.timezone(datetime.timedelta(hours=1)))


def grezzo(id_evento: str, tipo: str, secondi: float, telecamera: str, confidenza: float, valori: dict,
           durata: float | None = None, ha_foto: bool = False, simulato: bool = False):
    """Un evento grezzo `secondi` dopo le 10:00, visto da una telecamera."""
    inizio = ORA + datetime.timedelta(seconds=secondi)
    fine = None
    if durata is not None:
        fine = (inizio + datetime.timedelta(seconds=durata)).isoformat()
    dati = {
        "id": id_evento, "tipo": tipo, "inizio": inizio.isoformat(), "fine": fine, "stanza": "kitchen",
        "confidenza": confidenza, "valori": valori, "ha_foto": ha_foto, "simulato": simulato,
        "fonti": [{"telecamera_id": telecamera, "analizzatore": tipo, "confidenza": confidenza}],
    }
    return leggi_evento(dati)


def bevuta_valori(ml: float) -> dict:
    return {"contenitore": "bicchiere", "capienza_ml": 250, "altezza_contenitore_px": 100,
            "livello_sceso_px": ml / 250 * 100, "percentuale": ml / 250 * 100, "ml": ml}


def presa_valori(farmaco_id: str | None) -> dict:
    return {"farmaco_id": farmaco_id, "portapillole_aperto": True, "mano_alla_bocca": True}


def test_caduta_vista_da_due_telecamere_e_un_solo_fatto():
    prima = grezzo("cucina-1", "caduta", 0, "cucina", 0.7, {"secondi_a_terra": 20})
    seconda = grezzo("salotto-1", "caduta", 3, "salotto", 0.9, {"secondi_a_terra": 25}, ha_foto=True)
    coordinati = coordina([seconda, prima])
    assert len(coordinati) == 1
    unito = coordinati[0]
    # id e inizio dal primo grezzo, confidenza e valori dal più sicuro
    assert unito.evento.id == "cucina-1"
    assert unito.evento.inizio == ORA
    assert unito.evento.confidenza == 0.9
    assert unito.evento.valori.secondi_a_terra == 25
    assert len(unito.evento.fonti) == 2
    assert unito.grezzi == ["cucina-1", "salotto-1"]
    assert unito.id_foto == "salotto-1"
    assert unito.evento.ha_foto is True
    assert unito.evento.foto_prova is None


def test_la_foto_viene_dal_grezzo_che_ce_l_ha():
    sicuro_senza_foto = grezzo("a", "caduta", 0, "cucina", 0.9, {})
    con_foto = grezzo("b", "caduta", 2, "salotto", 0.6, {}, ha_foto=True)
    unito = coordina([sicuro_senza_foto, con_foto])[0]
    assert unito.evento.confidenza == 0.9
    assert unito.id_foto == "b"


def test_bevuta_da_due_telecamere_i_ml_non_si_sommano():
    prima = grezzo("a", "bevuta", 0, "cucina", 0.6, bevuta_valori(150), durata=5)
    seconda = grezzo("b", "bevuta", 1, "salotto", 0.8, bevuta_valori(200), durata=6)
    coordinati = coordina([prima, seconda])
    assert len(coordinati) == 1
    assert coordinati[0].evento.valori.ml == 200
    # dalla prima inizio alla fine più tardi
    assert coordinati[0].evento.fine == ORA + datetime.timedelta(seconds=7)


def test_alzata_in_pezzi_dalla_stessa_telecamera_con_le_stanze_unite():
    pezzo_uno = grezzo("a", "alzata_notturna", 0, "camera", 0.8, {"stanze": ["bedroom", "hall"]}, durata=60)
    pezzo_due = grezzo("b", "alzata_notturna", 65, "camera", 0.7, {"stanze": ["hall", "bathroom"]}, durata=120)
    coordinati = coordina([pezzo_due, pezzo_uno])
    assert len(coordinati) == 1
    assert coordinati[0].evento.valori.stanze == ["bedroom", "hall", "bathroom"]
    assert coordinati[0].evento.fine == ORA + datetime.timedelta(seconds=185)


def test_eventi_lontani_restano_separati():
    prima = grezzo("a", "bevuta", 0, "cucina", 0.8, bevuta_valori(150))
    dopo_un_minuto = grezzo("b", "bevuta", 60, "cucina", 0.8, bevuta_valori(100))
    appena_oltre = grezzo("c", "bevuta", 70.5, "salotto", 0.8, bevuta_valori(100))
    coordinati = coordina([prima, dopo_un_minuto, appena_oltre])
    assert len(coordinati) == 3


def test_tipi_diversi_restano_separati():
    caduta = grezzo("a", "caduta", 0, "cucina", 0.8, {})
    uscita = grezzo("b", "uscita", 0, "cucina", 0.8, {"zona_id": "porta"})
    assert len(coordina([caduta, uscita])) == 2


def test_dieci_secondi_sono_ancora_lo_stesso_fatto():
    prima = grezzo("a", "caduta", 0, "cucina", 0.8, {})
    seconda = grezzo("b", "caduta", 10, "salotto", 0.8, {})
    assert len(coordina([prima, seconda])) == 1


def test_due_pillole_prese_di_fila_sono_due_fatti():
    eventi = [
        grezzo("don-cucina", "farmaco", 0, "cucina", 0.9, presa_valori("donepezil")),
        grezzo("don-salotto", "farmaco", 1, "salotto", 0.7, presa_valori("donepezil")),
        grezzo("mem-cucina", "farmaco", 5, "cucina", 0.9, presa_valori("memantine")),
        # la seconda telecamera vede la seconda presa ma non riconosce la scatola: va con quella più vicina
        grezzo("non-riconosciuta", "farmaco", 6, "salotto", 0.6, presa_valori(None)),
    ]
    coordinati = coordina(eventi)
    assert len(coordinati) == 2
    assert coordinati[0].grezzi == ["don-cucina", "don-salotto"]
    assert coordinati[1].grezzi == ["mem-cucina", "non-riconosciuta"]
    assert coordinati[1].evento.valori.farmaco_id == "memantine"


def test_simulato_e_vero_non_si_uniscono():
    vero = grezzo("a", "caduta", 0, "cucina", 0.8, {})
    simulato = grezzo("b", "caduta", 1, "cucina", 0.8, {}, simulato=True)
    assert len(coordina([vero, simulato])) == 2


def test_l_ordine_di_arrivo_non_cambia_il_risultato():
    eventi = [
        grezzo("a", "caduta", 0, "cucina", 0.7, {}),
        grezzo("b", "caduta", 4, "salotto", 0.9, {}),
        grezzo("c", "caduta", 40, "cucina", 0.8, {}),
        grezzo("d", "bevuta", 2, "cucina", 0.8, bevuta_valori(100)),
    ]
    al_contrario = list(reversed(eventi))
    primi = []
    for coordinato in coordina(eventi):
        primi.append((coordinato.evento.id, coordinato.grezzi))
    secondi = []
    for coordinato in coordina(al_contrario):
        secondi.append((coordinato.evento.id, coordinato.grezzi))
    assert primi == secondi
    assert primi == [("a", ["a", "b"]), ("d", ["d"]), ("c", ["c"])]


def test_istantanei_restano_senza_fine():
    prima = grezzo("a", "caduta", 0, "cucina", 0.8, {})
    seconda = grezzo("b", "caduta", 2, "salotto", 0.8, {})
    assert coordina([prima, seconda])[0].evento.fine is None
