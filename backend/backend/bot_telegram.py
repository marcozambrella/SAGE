"""Bot Telegram della casa demo, con python-telegram-bot (D10, D16, D24, D37). Testi per l'utente in inglese (D13).

- Collegamento: si scrive al bot "/start <codice>", con il codice di TELEGRAM_CODICE_COLLEGAMENTO. Tutte le chat
  collegate ricevono allarmi e promemoria (API.md).
- Allarmi con la foto di prova; i messaggi di uscita hanno i pulsanti pausa 1 h / pausa 3 h / spegni.
  "/riattiva" riaccende l'allarme uscita. Pulsanti e comando cambiano la personalizzazione sul backend.
- I promemoria delle dosi li fa partire la chiamata /cron/controlli (app.py).

Variabili d'ambiente (backend/.env in sviluppo, impostazioni di Render online):
- TELEGRAM_TOKEN: il token del bot (da BotFather). Senza, allarmi e promemoria finiscono solo nel log.
- TELEGRAM_CODICE_COLLEGAMENTO: il codice da scrivere dopo /start. Senza, nessuna chat si può collegare.
- Come il bot riceve i messaggi (comandi e pulsanti):
  - online: TELEGRAM_WEBHOOK_URL (https://<server>/telegram/webhook) e TELEGRAM_SEGRETO_WEBHOOK; Telegram manda ogni
    messaggio a quell'indirizzo e così sveglia anche il server addormentato (D39);
  - in sviluppo: TELEGRAM_POLLING=1, il server chiede lui i messaggi a Telegram, senza un indirizzo pubblico.
    Attenzione: il polling cancella il webhook, quindi non va usato con lo stesso bot mentre il server online gira;
  - con nessuna delle due il bot manda soltanto.
"""

import datetime
import logging
import os
import secrets

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import TelegramError
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes

from backend.archivio import ArchivioDatabase
from backend.regole import ora_locale

# Gli indirizzi delle richieste a Telegram contengono il token: il registro di httpx non deve scriverli mai.
logging.getLogger("httpx").setLevel(logging.WARNING)

registro = logging.getLogger("sage.telegram")

# i soli aggiornamenti che servono al bot: messaggi (comandi) e pulsanti
AGGIORNAMENTI = ["message", "callback_query"]

TASTIERA_USCITA = InlineKeyboardMarkup([[
    InlineKeyboardButton("Pause 1 h", callback_data="pausa:1"),
    InlineKeyboardButton("Pause 3 h", callback_data="pausa:3"),
    InlineKeyboardButton("Turn off", callback_data="spegni"),
]])

NON_COLLEGATA = "This chat is not linked to SAGE. Send /start followed by the code."
NON_CONFIGURATA = "The demo home is not configured yet."


# --- risposte ai comandi e ai pulsanti (senza Telegram: si provano anche da sole) ---

def risposta_a_start(archivio: ArchivioDatabase, chat_id: int, argomenti: list[str], codice_atteso: str) -> str:
    if codice_atteso == "":
        return "Linking is not enabled on this server."
    if len(argomenti) != 1:
        return "To link this chat, send /start followed by the code."
    # confronto a tempo costante, come per i token
    if not secrets.compare_digest(argomenti[0].encode(), codice_atteso.encode()):
        return "Wrong code."
    archivio.collega_chat(chat_id)
    return "This chat is now linked to the SAGE demo home: alerts and reminders will arrive here."


def risposta_a_riattiva(archivio: ArchivioDatabase, chat_id: int) -> str:
    if chat_id not in archivio.chat_collegate():
        return NON_COLLEGATA
    if archivio.cambia_allarme_uscita(True, None) is None:
        return NON_CONFIGURATA
    return "Exit alerts are back on."


def risposta_a_pulsante(archivio: ArchivioDatabase, chat_id: int, dati: str, adesso: datetime.datetime) -> str:
    """dati: "pausa:1", "pausa:3" o "spegni" (TASTIERA_USCITA)."""
    if chat_id not in archivio.chat_collegate():
        return NON_COLLEGATA
    personalizzazione = archivio.leggi_personalizzazione()
    if personalizzazione is None:
        return NON_CONFIGURATA
    if dati == "spegni":
        archivio.cambia_allarme_uscita(False, None)
        return "Exit alerts are off. Send /riattiva to turn them back on."
    if dati == "pausa:1" or dati == "pausa:3":
        ore = int(dati.split(":")[1])
        fine_pausa = adesso + datetime.timedelta(hours=ore)
        archivio.cambia_allarme_uscita(True, fine_pausa)
        ora = ora_locale(fine_pausa, personalizzazione.fuso_orario).strftime("%H:%M")
        return "Exit alerts paused for " + str(ore) + " h, until " + ora + "."
    return "Unknown button."


# --- gestori di python-telegram-bot: leggono archivio e codice da bot_data ---

async def gestisci_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    archivio = context.bot_data["archivio"]
    codice = context.bot_data["codice"]
    testo = risposta_a_start(archivio, update.effective_chat.id, context.args, codice)
    await update.effective_message.reply_text(testo)


async def gestisci_riattiva(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    testo = risposta_a_riattiva(context.bot_data["archivio"], update.effective_chat.id)
    await update.effective_message.reply_text(testo)


async def gestisci_pulsante(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    domanda = update.callback_query
    # Telegram aspetta la risposta al pulsante, altrimenti lo lascia "in caricamento"
    await domanda.answer()
    adesso = datetime.datetime.now(datetime.UTC)
    testo = risposta_a_pulsante(context.bot_data["archivio"], update.effective_chat.id, domanda.data, adesso)
    await context.bot.send_message(chat_id=update.effective_chat.id, text=testo)


def prepara_applicazione(applicazione: Application, archivio: ArchivioDatabase, codice: str) -> None:
    """Comandi e pulsanti del bot. I test la usano con una finta connessione a Telegram."""
    applicazione.bot_data["archivio"] = archivio
    applicazione.bot_data["codice"] = codice
    applicazione.add_handler(CommandHandler("start", gestisci_start))
    applicazione.add_handler(CommandHandler("riattiva", gestisci_riattiva))
    applicazione.add_handler(CallbackQueryHandler(gestisci_pulsante))


async def avvia_bot(archivio: ArchivioDatabase) -> Application | None:
    """All'avvio del server. None se il bot non è configurato o Telegram non risponde: il server parte lo stesso."""
    token = os.environ.get("TELEGRAM_TOKEN", "")
    if token == "":
        registro.warning("TELEGRAM_TOKEN mancante: allarmi e promemoria solo nel log")
        return None
    applicazione = Application.builder().token(token).build()
    prepara_applicazione(applicazione, archivio, os.environ.get("TELEGRAM_CODICE_COLLEGAMENTO", ""))
    indirizzo_webhook = os.environ.get("TELEGRAM_WEBHOOK_URL", "")
    segreto_webhook = os.environ.get("TELEGRAM_SEGRETO_WEBHOOK", "")
    try:
        await applicazione.initialize()
        if indirizzo_webhook != "" and segreto_webhook == "":
            registro.warning("TELEGRAM_SEGRETO_WEBHOOK mancante: webhook non impostato, il bot manda soltanto")
        elif indirizzo_webhook != "":
            # a ogni avvio (anche quando Render sveglia il server): non costa niente e ripara un webhook cancellato
            await applicazione.bot.set_webhook(
                indirizzo_webhook, secret_token=segreto_webhook, allowed_updates=AGGIORNAMENTI)
            registro.info("Telegram: webhook impostato")
        elif os.environ.get("TELEGRAM_POLLING", "") == "1":
            await applicazione.start()
            await applicazione.updater.start_polling(allowed_updates=AGGIORNAMENTI)
            registro.info("Telegram: polling avviato")
    except TelegramError as errore:
        registro.warning("Telegram non raggiungibile, allarmi e promemoria solo nel log: %s", errore)
        return None
    return applicazione


async def ferma_bot(applicazione: Application | None) -> None:
    """Alla chiusura del server. Il webhook resta impostato: al prossimo avvio serve ancora."""
    if applicazione is None:
        return
    if applicazione.updater is not None and applicazione.updater.running:
        await applicazione.updater.stop()
    if applicazione.running:
        await applicazione.stop()
    await applicazione.shutdown()


# --- invio di allarmi e promemoria ---

async def manda_a_una_chat(
    bot: Bot, chat_id: int, testo: str, foto: bytes | None, tastiera: InlineKeyboardMarkup | None
) -> bool:
    """True se il messaggio è arrivato. Se Telegram rifiuta la foto si manda almeno il testo: l'allarme conta di più."""
    if foto is not None:
        try:
            await bot.send_photo(chat_id=chat_id, photo=foto, caption=testo, reply_markup=tastiera)
            return True
        except TelegramError as errore:
            registro.warning("Foto non mandata alla chat %s, mando solo il testo: %s", chat_id, errore)
    try:
        await bot.send_message(chat_id=chat_id, text=testo, reply_markup=tastiera)
        return True
    except TelegramError as errore:
        registro.warning("Messaggio non mandato alla chat %s: %s", chat_id, errore)
        return False


async def manda_a_tutte_le_chat(
    bot: Bot, archivio: ArchivioDatabase, testo: str, foto: bytes | None, pulsanti_uscita: bool
) -> int:
    """Manda a tutte le chat collegate; dà quante l'hanno ricevuto."""
    tastiera = None
    if pulsanti_uscita:
        tastiera = TASTIERA_USCITA
    arrivati = 0
    for chat_id in archivio.chat_collegate():
        if await manda_a_una_chat(bot, chat_id, testo, foto, tastiera):
            arrivati = arrivati + 1
    return arrivati
