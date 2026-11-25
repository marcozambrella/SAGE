"""Test dell'archivio: gli stessi su SQLite e su PostgreSQL (D36).

SQLite gira sempre, in un file temporaneo. PostgreSQL solo se la variabile SAGE_POSTGRES_DI_PROVA contiene l'indirizzo
di un database di prova (che viene svuotato!), per esempio un secondo database su Neon; altrimenti quei test sono
saltati.
"""

import datetime
import os

import psycopg
import pytest

from backend.archivio import ArchivioDatabase
from contratti.configurazione import Personalizzazione
from contratti.eventi import leggi_evento

POSTGRES_DI_PROVA = os.environ.get("SAGE_POSTGRES_DI_PROVA", "")
TABELLE = ["personalizzazione", "eventi_grezzi", "foto", "chat_telegram", "allarmi_mandati",
           "promemoria_mandati"]
FONTI = [{"telecamera_id": "cucina", "analizzatore": "prova", "confidenza": 0.9}]
FOTO = b"\xff\xd8\xff\xe0finto jpeg"


@pytest.fixture(params=["sqlite", "postgres"])
def archivio(request, tmp_path):
    if request.param == "sqlite":
        return ArchivioDatabase(str(tmp_path / "prova.sqlite3"))
    if POSTGRES_DI_PROVA == "":
        pytest.skip("SAGE_POSTGRES_DI_PROVA non impostata")
    # si riparte da tabelle vuote
    with psycopg.connect(POSTGRES_DI_PROVA) as connessione:
        for tabella in TABELLE:
            connessione.execute("DROP TABLE IF EXISTS " + tabella)
    return ArchivioDatabase(POSTGRES_DI_PROVA)


def personalizzazione(nome: str, attivo: bool = True) -> Personalizzazione:
    return Personalizzazione.model_validate({"anziano": {"nome": nome}, "regole": {"allarme_uscita_attivo": attivo}})


def evento(id_evento: str, tipo: str, inizio: str, valori: dict):
    dati = {"id": id_evento, "tipo": tipo, "inizio": inizio, "stanza": "kitchen", "confidenza": 0.9,
            "fonti": FONTI, "valori": valori}
    return leggi_evento(dati)


def ids(eventi: list) -> list[str]:
    risultato = []
    for letto in eventi:
        risultato.append(letto.id)
    return risultato


def test_personalizzazione(archivio):
    assert archivio.leggi_personalizzazione() is None
    archivio.salva_personalizzazione(personalizzazione("Anna"))
    assert archivio.leggi_personalizzazione().anziano.nome == "Anna"
    archivio.salva_personalizzazione(personalizzazione("Bruno"))
    assert archivio.leggi_personalizzazione().anziano.nome == "Bruno"


def test_allarme_uscita_deciso_da_telegram_resta(archivio):
    assert archivio.cambia_allarme_uscita(False, None) is None
    # la prima volta si prende quello mandato
    archivio.salva_personalizzazione(personalizzazione("Anna", attivo=False))
    assert archivio.leggi_personalizzazione().regole.allarme_uscita_attivo is False
    pausa = datetime.datetime(2026, 12, 1, 23, 0, tzinfo=datetime.UTC)
    archivio.cambia_allarme_uscita(True, pausa)
    # il programma di casa rimanda la sua personalizzazione: pausa e allarme restano quelli di Telegram
    archivio.salva_personalizzazione(personalizzazione("Anna", attivo=False))
    regole = archivio.leggi_personalizzazione().regole
    assert regole.allarme_uscita_attivo is True
    assert regole.pausa_fino_a == pausa


def test_eventi_nuovi_una_volta_sola(archivio):
    prima = evento("a", "caduta", "2026-12-01T10:00:00+01:00", {})
    seconda = evento("b", "caduta", "2026-12-01T11:00:00+01:00", {})
    assert archivio.aggiungi_grezzi([prima, seconda], [None, None]) == [True, True]
    assert archivio.aggiungi_grezzi([seconda], [None]) == [False]
    # doppione dentro la stessa lista
    terza = evento("c", "caduta", "2026-12-01T12:00:00+01:00", {})
    assert archivio.aggiungi_grezzi([terza, terza], [None, None]) == [True, False]
    assert len(archivio.leggi_grezzi(None, None, None)) == 3


def test_evento_riletto_uguale_senza_foto(archivio):
    originale = evento("b1", "bevuta", "2026-12-01T09:00:00+01:00", {
        "contenitore": "bottiglia", "capienza_ml": 2000, "altezza_contenitore_px": 100, "livello_sceso_px": 10,
        "percentuale": 10, "ml": 200})
    originale = originale.model_copy(update={"foto_prova": "base64 qualsiasi", "simulato": True})
    archivio.aggiungi_grezzi([originale], [FOTO])
    riletto = archivio.leggi_grezzi(None, None, None)[0]
    # così com'è, ma la foto sta nella sua tabella e ha_foto lo dice
    assert riletto == originale.model_copy(update={"foto_prova": None, "ha_foto": True})
    assert archivio.leggi_grezzo("b1") == riletto
    assert archivio.leggi_grezzo("altro") is None
    # il fuso orario con cui è arrivato resta
    assert riletto.inizio.isoformat() == "2026-12-01T09:00:00+01:00"


def test_eventi_filtrati_e_in_ordine_di_tempo(archivio):
    eventi = [
        # 07:30 UTC
        evento("dopo", "caduta", "2026-12-01T07:30:00+00:00", {}),
        # 07:00 UTC, scritto con il fuso di Roma
        evento("prima", "caduta", "2026-12-01T08:00:00+01:00", {}),
        evento("uscita", "uscita", "2026-12-01T07:15:00+00:00", {"zona_id": "porta"}),
        evento("giorno-dopo", "caduta", "2026-12-02T07:00:00+00:00", {}),
    ]
    archivio.aggiungi_grezzi(eventi, [None, None, None, None])
    assert ids(archivio.leggi_grezzi(None, None, None)) == ["prima", "uscita", "dopo", "giorno-dopo"]
    dal = datetime.datetime(2026, 12, 1, 7, 15, tzinfo=datetime.UTC)
    al = datetime.datetime(2026, 12, 2, 7, 0, tzinfo=datetime.UTC)
    # dal compreso, al escluso
    assert ids(archivio.leggi_grezzi(dal, al, None)) == ["uscita", "dopo"]
    assert ids(archivio.leggi_grezzi(None, al, "caduta")) == ["prima", "dopo"]


def test_foto(archivio):
    con_foto = evento("c1", "caduta", "2026-12-01T10:00:00+01:00", {})
    archivio.aggiungi_grezzi([con_foto], [FOTO])
    assert archivio.leggi_foto("c1") == FOTO
    assert archivio.leggi_foto("altro") is None
    # un evento rimandato con un'altra foto non la cambia
    archivio.aggiungi_grezzi([con_foto], [b"altra foto"])
    assert archivio.leggi_foto("c1") == FOTO


def test_primo_e_ultimo_inizio(archivio):
    assert archivio.inizio_primo_e_ultimo() == (None, None)
    eventi = [
        evento("b", "caduta", "2026-12-03T10:00:00+01:00", {}),
        evento("a", "caduta", "2026-12-01T10:00:00+01:00", {}),
    ]
    archivio.aggiungi_grezzi(eventi, [None, None])
    primo, ultimo = archivio.inizio_primo_e_ultimo()
    assert primo == datetime.datetime(2026, 12, 1, 9, 0, tzinfo=datetime.UTC)
    assert ultimo == datetime.datetime(2026, 12, 3, 9, 0, tzinfo=datetime.UTC)


def test_allarmi_mandati(archivio):
    assert archivio.allarme_gia_mandato([]) is False
    assert archivio.allarme_gia_mandato(["a", "b"]) is False
    archivio.segna_allarme("b")
    archivio.segna_allarme("b")
    assert archivio.allarme_gia_mandato(["a", "b"]) is True
    assert archivio.allarme_gia_mandato(["c"]) is False


def test_chat_telegram(archivio):
    assert archivio.chat_collegate() == []
    archivio.collega_chat(123)
    archivio.collega_chat(123)
    # gli id delle chat di gruppo sono negativi e grandi
    archivio.collega_chat(-1001234567890)
    assert archivio.chat_collegate() == [-1001234567890, 123]


def test_promemoria_una_volta_sola(archivio):
    assert archivio.segna_promemoria("2026-12-01 donepezil 08:00") is True
    assert archivio.segna_promemoria("2026-12-01 donepezil 08:00") is False
    assert archivio.segna_promemoria("2026-12-01 donepezil 20:00") is True


def test_dati_restano_dopo_un_riavvio(tmp_path):
    percorso = str(tmp_path / "prova.sqlite3")
    primo = ArchivioDatabase(percorso)
    primo.salva_personalizzazione(personalizzazione("Anna"))
    primo.aggiungi_grezzi([evento("c1", "caduta", "2026-12-01T10:00:00+01:00", {})], [None])
    secondo = ArchivioDatabase(percorso)
    assert secondo.leggi_personalizzazione().anziano.nome == "Anna"
    assert len(secondo.leggi_grezzi(None, None, None)) == 1
