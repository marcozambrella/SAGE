"""Test del bot Telegram e dei promemoria delle dosi, senza rete vera: al posto della connessione a Telegram c'è una
RichiestaFinta che ricorda le chiamate e risponde come Telegram.

Il token del bot qui è finto ("123:ABC"); quello vero (backend/.env) non viene mai letto nei test.
"""

import asyncio
import base64
import datetime
import json
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from telegram import Update
from telegram.ext import Application
from telegram.request import BaseRequest

from backend.allarmi import ORE_CASA_ATTIVA, promemoria_da_mandare
from backend.app import app
from backend.archivio import ArchivioDatabase
from backend.bot_telegram import (
    manda_a_tutte_le_chat,
    prepara_applicazione,
    risposta_a_pulsante,
    risposta_a_riattiva,
    risposta_a_start,
)
from contratti.configurazione import Personalizzazione
from contratti.eventi import leggi_evento

CODICE = "codice-di-prova"
TOKEN_CASA = "token-casa-di-prova"
TOKEN_CRON = "token-cron-di-prova"
SEGRETO = "segreto-di-prova"
CHAT = 4242
FOTO = b"\xff\xd8\xff\xe0finto jpeg"
ROMA = ZoneInfo("Europe/Rome")
FONTI = [{"telecamera_id": "cucina", "analizzatore": "prova", "confidenza": 0.9}]
PERSONALIZZAZIONE = {
    "anziano": {"nome": "Anna"},
    "farmaci": [{"id": "donepezil", "nome": "Donepezil", "dose": "1 tablet", "orari": ["08:00"]}],
    "regole": {"orari_uscita_vietati": [{"dalle": "21:00", "alle": "07:00"}]},
}


class RichiestaFinta(BaseRequest):
    """Al posto della connessione a Telegram: ricorda le chiamate (metodo, parametri) e risponde come Telegram."""

    def __init__(self) -> None:
        self.chiamate = []
        # True: Telegram rifiuta le foto (per provare che arriva almeno il testo)
        self.rifiuta_foto = False

    @property
    def read_timeout(self) -> float:
        return 1.0

    async def initialize(self) -> None:
        return None

    async def shutdown(self) -> None:
        return None

    async def do_request(self, url, method, request_data=None, read_timeout=None, write_timeout=None,
                         connect_timeout=None, pool_timeout=None) -> tuple[int, bytes]:
        metodo = url.split("/")[-1]
        parametri = {}
        if request_data is not None:
            parametri = request_data.parameters
        self.chiamate.append((metodo, parametri))
        if metodo == "sendPhoto" and self.rifiuta_foto:
            errore = {"ok": False, "error_code": 400, "description": "Bad Request: IMAGE_PROCESS_FAILED"}
            return 400, json.dumps(errore).encode()
        if metodo == "getMe":
            risultato = {"id": 1, "is_bot": True, "first_name": "SAGE", "username": "sage_prova_bot"}
        elif metodo == "sendMessage" or metodo == "sendPhoto":
            risultato = {"message_id": 1, "date": 0, "chat": {"id": parametri["chat_id"], "type": "private"}}
        else:
            risultato = True
        return 200, json.dumps({"ok": True, "result": risultato}).encode()

    def metodi(self) -> list[str]:
        nomi = []
        for metodo, parametri in self.chiamate:
            nomi.append(metodo)
        return nomi

    def ultima(self, metodo: str) -> dict:
        trovata = None
        for nome, parametri in self.chiamate:
            if nome == metodo:
                trovata = parametri
        return trovata


@pytest.fixture
def archivio(tmp_path):
    return ArchivioDatabase(str(tmp_path / "prova.sqlite3"))


def configura(archivio: ArchivioDatabase) -> None:
    archivio.salva_personalizzazione(Personalizzazione.model_validate(PERSONALIZZAZIONE))


def crea_bot_finto(archivio: ArchivioDatabase) -> tuple[Application, RichiestaFinta]:
    richiesta = RichiestaFinta()
    costruttore = Application.builder().token("123:ABC").request(richiesta).get_updates_request(RichiestaFinta())
    applicazione = costruttore.build()
    prepara_applicazione(applicazione, archivio, CODICE)
    asyncio.run(applicazione.initialize())
    return applicazione, richiesta


def messaggio(testo: str) -> dict:
    dati = {"update_id": 1, "message": {
        "message_id": 1, "date": 0, "text": testo,
        "chat": {"id": CHAT, "type": "private"},
        "from": {"id": CHAT, "is_bot": False, "first_name": "Marco"},
    }}
    if testo.startswith("/"):
        lunghezza = len(testo.split(" ")[0])
        dati["message"]["entities"] = [{"type": "bot_command", "offset": 0, "length": lunghezza}]
    return dati


def pulsante(dati_pulsante: str) -> dict:
    return {"update_id": 2, "callback_query": {
        "id": "q1", "chat_instance": "c", "data": dati_pulsante,
        "from": {"id": CHAT, "is_bot": False, "first_name": "Marco"},
        "message": {"message_id": 5, "date": 0, "chat": {"id": CHAT, "type": "private"}},
    }}


def evento(id_evento: str, tipo: str, inizio: datetime.datetime, valori: dict, foto: bytes | None = None) -> dict:
    dati = {"id": id_evento, "tipo": tipo, "inizio": inizio.isoformat(), "stanza": "kitchen", "confidenza": 0.9,
            "fonti": FONTI, "valori": valori}
    if foto is not None:
        dati["foto_prova"] = base64.b64encode(foto).decode()
    return dati


# --- risposte a comandi e pulsanti ---

def test_start_collega_solo_con_il_codice_giusto(archivio):
    assert risposta_a_start(archivio, CHAT, [], CODICE).startswith("To link this chat")
    assert risposta_a_start(archivio, CHAT, ["sbagliato"], CODICE) == "Wrong code."
    assert archivio.chat_collegate() == []
    assert risposta_a_start(archivio, CHAT, [CODICE], CODICE).startswith("This chat is now linked")
    assert archivio.chat_collegate() == [CHAT]


def test_start_senza_codice_configurato_non_collega(archivio):
    assert risposta_a_start(archivio, CHAT, [""], "") == "Linking is not enabled on this server."
    assert archivio.chat_collegate() == []


def test_riattiva(archivio):
    assert risposta_a_riattiva(archivio, CHAT).startswith("This chat is not linked")
    archivio.collega_chat(CHAT)
    assert risposta_a_riattiva(archivio, CHAT) == "The demo home is not configured yet."
    configura(archivio)
    archivio.cambia_allarme_uscita(False, datetime.datetime(2026, 12, 1, tzinfo=datetime.UTC))
    assert risposta_a_riattiva(archivio, CHAT) == "Exit alerts are back on."
    regole = archivio.leggi_personalizzazione().regole
    assert regole.allarme_uscita_attivo is True
    assert regole.pausa_fino_a is None


def test_pulsanti_pausa_e_spegni(archivio):
    adesso = datetime.datetime(2026, 12, 1, 21, 15, tzinfo=datetime.UTC)
    assert risposta_a_pulsante(archivio, CHAT, "pausa:1", adesso).startswith("This chat is not linked")
    archivio.collega_chat(CHAT)
    configura(archivio)
    # 22:15 UTC = 23:15 a Roma
    assert risposta_a_pulsante(archivio, CHAT, "pausa:1", adesso) == "Exit alerts paused for 1 h, until 23:15."
    assert archivio.leggi_personalizzazione().regole.pausa_fino_a == adesso + datetime.timedelta(hours=1)
    risposta_a_pulsante(archivio, CHAT, "pausa:3", adesso)
    assert archivio.leggi_personalizzazione().regole.pausa_fino_a == adesso + datetime.timedelta(hours=3)
    assert risposta_a_pulsante(archivio, CHAT, "spegni", adesso).startswith("Exit alerts are off.")
    assert archivio.leggi_personalizzazione().regole.allarme_uscita_attivo is False
    assert risposta_a_pulsante(archivio, CHAT, "ballo", adesso) == "Unknown button."


# --- python-telegram-bot con la finta connessione ---

def test_start_passando_da_python_telegram_bot(archivio):
    applicazione, richiesta = crea_bot_finto(archivio)
    asyncio.run(applicazione.process_update(Update.de_json(messaggio("/start " + CODICE), applicazione.bot)))
    assert archivio.chat_collegate() == [CHAT]
    risposta = richiesta.ultima("sendMessage")
    assert risposta["chat_id"] == CHAT
    assert risposta["text"].startswith("This chat is now linked")


def test_pulsante_passando_da_python_telegram_bot(archivio):
    archivio.collega_chat(CHAT)
    configura(archivio)
    applicazione, richiesta = crea_bot_finto(archivio)
    asyncio.run(applicazione.process_update(Update.de_json(pulsante("pausa:3"), applicazione.bot)))
    assert "answerCallbackQuery" in richiesta.metodi()
    assert richiesta.ultima("sendMessage")["text"].startswith("Exit alerts paused for 3 h")
    assert archivio.leggi_personalizzazione().regole.pausa_fino_a is not None


def test_allarme_a_tutte_le_chat_con_foto_e_pulsanti(archivio):
    archivio.collega_chat(CHAT)
    archivio.collega_chat(CHAT + 1)
    applicazione, richiesta = crea_bot_finto(archivio)
    arrivati = asyncio.run(manda_a_tutte_le_chat(applicazione.bot, archivio, "Exit alert", FOTO, True))
    assert arrivati == 2
    assert richiesta.metodi().count("sendPhoto") == 2
    foto = richiesta.ultima("sendPhoto")
    assert foto["caption"] == "Exit alert"
    pulsanti = foto["reply_markup"]["inline_keyboard"][0]
    dati_pulsanti = []
    for pulsante_tastiera in pulsanti:
        dati_pulsanti.append(pulsante_tastiera["callback_data"])
    assert dati_pulsanti == ["pausa:1", "pausa:3", "spegni"]


def test_foto_rifiutata_arriva_almeno_il_testo(archivio):
    archivio.collega_chat(CHAT)
    applicazione, richiesta = crea_bot_finto(archivio)
    richiesta.rifiuta_foto = True
    arrivati = asyncio.run(manda_a_tutte_le_chat(applicazione.bot, archivio, "Possible fall", FOTO, False))
    assert arrivati == 1
    assert richiesta.metodi() == ["getMe", "sendPhoto", "sendMessage"]
    assert "reply_markup" not in richiesta.ultima("sendMessage")


# --- dall'app: eventi, webhook, cron ---

@pytest.fixture
def con_bot(archivio):
    """Client di test dell'app con il bot finto e una chat collegata."""
    applicazione, richiesta = crea_bot_finto(archivio)
    app.state.archivio = archivio
    app.state.token_casa = TOKEN_CASA
    app.state.token_cron = TOKEN_CRON
    app.state.segreto_webhook = SEGRETO
    app.state.telegram = applicazione
    archivio.collega_chat(CHAT)
    configura(archivio)
    return TestClient(app), richiesta


def test_caduta_arriva_su_telegram_con_la_foto(con_bot):
    client, richiesta = con_bot
    inizio = datetime.datetime(2025, 12, 1, 10, 0, tzinfo=ROMA)
    caduta = evento("c1", "caduta", inizio, {}, foto=FOTO)
    client.post("/programma-casa/eventi", json=[caduta], headers={"Authorization": "Bearer " + TOKEN_CASA})
    foto = richiesta.ultima("sendPhoto")
    assert foto["chat_id"] == CHAT
    assert foto["caption"] == "Possible fall: Anna may have fallen in the kitchen at 10:00."
    # niente pulsanti sulle cadute
    assert "reply_markup" not in foto


def test_caduta_da_due_telecamere_un_solo_messaggio(con_bot):
    client, richiesta = con_bot
    inizio = datetime.datetime(2025, 12, 1, 10, 0, tzinfo=ROMA)
    dalla_cucina = evento("c-cucina", "caduta", inizio, {}, foto=FOTO)
    dal_salotto = evento("c-salotto", "caduta", inizio + datetime.timedelta(seconds=3), {}, foto=FOTO)
    dal_salotto["fonti"] = [{"telecamera_id": "salotto", "analizzatore": "caduta", "confidenza": 0.8}]
    con_token = {"Authorization": "Bearer " + TOKEN_CASA}
    client.post("/programma-casa/eventi", json=[dalla_cucina], headers=con_token)
    client.post("/programma-casa/eventi", json=[dal_salotto], headers=con_token)
    assert richiesta.metodi().count("sendPhoto") == 1


def test_uscita_vietata_arriva_con_i_pulsanti(con_bot):
    client, richiesta = con_bot
    uscita = evento("u1", "uscita", datetime.datetime(2025, 12, 1, 23, 0, tzinfo=ROMA), {"zona_id": "porta"})
    client.post("/programma-casa/eventi", json=[uscita], headers={"Authorization": "Bearer " + TOKEN_CASA})
    testo = richiesta.ultima("sendMessage")
    assert testo["text"] == "Exit alert: Anna left the house at 23:00, during restricted hours."
    assert len(testo["reply_markup"]["inline_keyboard"][0]) == 3


def test_inattivita_arriva_su_telegram_con_l_ultima_volta_vista(con_bot):
    client, richiesta = con_bot
    inizio = datetime.datetime(2025, 12, 1, 13, 5, tzinfo=ROMA)
    allarme = evento("i1", "inattivita", inizio, {"ultima_telecamera_id": "cucina"})
    con_token = {"Authorization": "Bearer " + TOKEN_CASA}
    client.post("/programma-casa/eventi", json=[allarme], headers=con_token)
    testo = richiesta.ultima("sendMessage")
    assert testo["chat_id"] == CHAT
    assert testo["text"] == "Inactivity alert: Anna has not been seen since 13:05. Last seen by the cucina camera."
    # i pulsanti pausa / spegni sono solo per le uscite
    assert "reply_markup" not in testo
    # quando ricompare arriva la fine: nessun secondo messaggio
    ricomparsa = dict(allarme)
    ricomparsa["id"] = "i2"
    ricomparsa["fine"] = (inizio + datetime.timedelta(hours=4)).isoformat()
    client.post("/programma-casa/eventi", json=[ricomparsa], headers=con_token)
    assert richiesta.metodi().count("sendMessage") == 1


def test_webhook_vuole_il_segreto(con_bot):
    client, richiesta = con_bot
    dati = messaggio("/riattiva")
    assert client.post("/telegram/webhook", json=dati).status_code == 401
    sbagliato = {"X-Telegram-Bot-Api-Secret-Token": "altro"}
    assert client.post("/telegram/webhook", json=dati, headers=sbagliato).status_code == 401
    giusto = {"X-Telegram-Bot-Api-Secret-Token": SEGRETO}
    assert client.post("/telegram/webhook", json=dati, headers=giusto).status_code == 200
    assert richiesta.ultima("sendMessage")["text"] == "Exit alerts are back on."


def test_cron_vuole_il_suo_token(con_bot):
    client, richiesta = con_bot
    assert client.post("/cron/controlli").status_code == 401
    con_token_casa = {"Authorization": "Bearer " + TOKEN_CASA}
    assert client.post("/cron/controlli", headers=con_token_casa).status_code == 401


def test_cron_manda_il_promemoria_una_volta_sola(con_bot, archivio):
    client, richiesta = con_bot
    # una dose prevista 2 ore e mezza fa: la finestra è finita da mezz'ora, nessuna presa
    adesso = datetime.datetime.now(ROMA)
    orario = (adesso - datetime.timedelta(minutes=150)).strftime("%H:%M")
    personalizzazione = dict(PERSONALIZZAZIONE)
    personalizzazione["farmaci"] = [{"id": "donepezil", "nome": "Donepezil", "dose": "1 tablet", "orari": [orario]}]
    archivio.salva_personalizzazione(Personalizzazione.model_validate(personalizzazione))
    con_token = {"Authorization": "Bearer " + TOKEN_CRON}
    # la casa non ha mandato eventi veri: niente promemoria (regola provvisoria)
    assert client.post("/cron/controlli", headers=con_token).json() == {"promemoria": 0}

    bevuta = evento("b1", "bevuta", adesso - datetime.timedelta(minutes=10), {
        "contenitore": "bicchiere", "capienza_ml": 250, "altezza_contenitore_px": 100, "livello_sceso_px": 50,
        "percentuale": 50, "ml": 125})
    client.post("/programma-casa/eventi", json=[bevuta], headers={"Authorization": "Bearer " + TOKEN_CASA})
    assert client.post("/cron/controlli", headers=con_token).json() == {"promemoria": 1}
    testo = richiesta.ultima("sendMessage")["text"]
    assert testo == "Medication reminder: Anna has not taken Donepezil (1 tablet), due at " + orario + "."
    # il cron ripassa dopo 5 minuti: lo stesso promemoria non riparte
    assert client.post("/cron/controlli", headers=con_token).json() == {"promemoria": 0}


# --- promemoria (logica pura) ---

def promemoria_alle(ora: str, eventi: list) -> list:
    personalizzazione = Personalizzazione.model_validate(PERSONALIZZAZIONE)
    adesso = datetime.datetime.fromisoformat("2026-12-01T" + ora + ":00+01:00")
    letti = []
    for dati in eventi:
        letti.append(leggi_evento(dati))
    return promemoria_da_mandare(personalizzazione, letti, adesso)


# un evento vero delle 9: la casa è attiva
ATTIVA = evento("c1", "caduta", datetime.datetime(2026, 12, 1, 9, 0, tzinfo=ROMA), {})


def test_promemoria_dopo_la_fine_della_finestra():
    # la dose delle 8 diventa saltata alle 10:00
    assert promemoria_alle("09:59", [ATTIVA]) == []
    promemoria = promemoria_alle("10:05", [ATTIVA])
    assert promemoria == [("2026-12-01 donepezil 08:00",
                           "Medication reminder: Anna has not taken Donepezil (1 tablet), due at 08:00.")]
    # oltre un'ora dopo non parte più (per esempio al primo avvio del server)
    assert promemoria_alle("11:01", [ATTIVA]) == []


def test_niente_promemoria_se_la_dose_e_presa():
    presa = evento("f1", "farmaco", datetime.datetime(2026, 12, 1, 9, 30, tzinfo=ROMA),
                   {"farmaco_id": "donepezil", "portapillole_aperto": True, "mano_alla_bocca": True})
    assert promemoria_alle("10:05", [ATTIVA, presa]) == []


def test_niente_promemoria_se_la_casa_non_manda_eventi_veri():
    vecchio = evento("c0", "caduta", datetime.datetime(2026, 11, 29, 9, 0, tzinfo=ROMA), {})
    simulato = dict(ATTIVA)
    simulato["simulato"] = True
    assert ORE_CASA_ATTIVA == 24
    assert promemoria_alle("10:05", [vecchio, simulato]) == []
