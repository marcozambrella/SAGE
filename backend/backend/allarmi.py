"""Quali eventi fanno partire subito l'allarme Telegram e quali promemoria mandare, con che testo
(API.md, D10, D15, D16, D24, D38).

Logica pura: qui si decide, l'invio vero lo fa il bot Telegram (bot_telegram.py). I testi sono in inglese (D13).
"""

import datetime
import logging

from contratti.configurazione import Farmaco, Personalizzazione
from contratti.eventi import TIPI_URGENTI, EventoBase

from backend.regole import (
    FUSO_ORARIO_PREDEFINITO,
    fine_della_finestra,
    giorno_locale,
    ora_locale,
    stato_delle_dosi,
    uscita_in_orario_vietato,
)

# PROVVISORIO, da decidere con Marco: i promemoria partono solo se il programma di casa ha mandato eventi veri (non
# simulati) nelle ultime ORE_CASA_ATTIVA ore. Senza, la casa demo (che riceve eventi solo quando Marco elabora i
# video) manderebbe ogni giorno un promemoria per ogni dose.
ORE_CASA_ATTIVA = 24
# Il cron passa ogni 5-10 minuti (D39); se il server dormiva o il cron ha saltato un giro, il promemoria parte
# comunque, ma non più di un'ora dopo la fine della finestra della dose.
MINUTI_VALIDITA_PROMEMORIA = 60

registro = logging.getLogger("sage.allarmi")


def serve_allarme(evento: EventoBase, personalizzazione: Personalizzazione | None) -> bool:
    """True se l'evento deve far partire subito un messaggio Telegram."""
    # lo storico simulato (D22) non fa mai partire allarmi
    if evento.simulato:
        return False
    if evento.tipo not in TIPI_URGENTI:
        return False
    # caduta e inattività (Marco, 25/11): sempre, subito
    if evento.tipo == "caduta" or evento.tipo == "inattivita":
        return True
    # uscita: senza personalizzazione non si sanno gli orari vietati
    if personalizzazione is None:
        return False
    regole = personalizzazione.regole
    if not regole.allarme_uscita_attivo:
        return False
    # in pausa (D16): l'uscita è iniziata prima della fine della pausa
    if regole.pausa_fino_a is not None and evento.inizio < regole.pausa_fino_a:
        return False
    return uscita_in_orario_vietato(evento, personalizzazione)


def nome_della_telecamera(personalizzazione: Personalizzazione | None, telecamera_id: str) -> str:
    """Il nome scelto nell'app ("Kitchen"); senza, l'id della telecamera."""
    if personalizzazione is not None:
        for telecamera in personalizzazione.telecamere:
            if telecamera.id == telecamera_id:
                return telecamera.nome
    return telecamera_id


def messaggio_allarme(evento: EventoBase, personalizzazione: Personalizzazione | None) -> str:
    """Il testo del messaggio Telegram, con l'ora locale della casa."""
    nome = "your relative"
    fuso_orario = FUSO_ORARIO_PREDEFINITO
    if personalizzazione is not None:
        nome = personalizzazione.anziano.nome
        fuso_orario = personalizzazione.fuso_orario
    ora = ora_locale(evento.inizio, fuso_orario).strftime("%H:%M")
    if evento.tipo == "caduta":
        return "Possible fall: " + nome + " may have fallen in the " + evento.stanza + " at " + ora + "."
    if evento.tipo == "inattivita":
        # inizio = l'ultima volta che si è vista una persona (contratti/eventi.py)
        telecamera = nome_della_telecamera(personalizzazione, evento.valori.ultima_telecamera_id)
        ultima_volta = " Last seen by the " + telecamera + " camera."
        # se il grezzo con la fine arriva insieme al primo (rete tornata dopo ore) la persona è già ricomparsa
        if evento.fine is not None:
            ricomparsa = ora_locale(evento.fine, fuso_orario).strftime("%H:%M")
            return "Inactivity alert: " + nome + " was not seen from " + ora + " to " + ricomparsa + "." + ultima_volta
        return "Inactivity alert: " + nome + " has not been seen since " + ora + "." + ultima_volta
    return "Exit alert: " + nome + " left the house at " + ora + ", during restricted hours."


def scrivi_allarme_nel_log(testo: str, foto: bytes | None) -> None:
    """Quando il bot Telegram è spento (TELEGRAM_TOKEN mancante o Telegram non raggiungibile all'avvio): l'allarme
    finisce solo nel log del server."""
    registro.warning("Allarme (bot Telegram spento): %s", testo)


def casa_attiva(eventi: list[EventoBase], adesso: datetime.datetime) -> bool:
    """True se tra gli eventi ce n'è uno vero (non simulato) delle ultime ORE_CASA_ATTIVA ore."""
    limite = adesso - datetime.timedelta(hours=ORE_CASA_ATTIVA)
    for evento in eventi:
        if not evento.simulato and evento.inizio >= limite:
            return True
    return False


def farmaco_con_id(personalizzazione: Personalizzazione, farmaco_id: str) -> Farmaco:
    for farmaco in personalizzazione.farmaci:
        if farmaco.id == farmaco_id:
            return farmaco
    raise ValueError("Farmaco sconosciuto: " + farmaco_id)


def promemoria_da_mandare(
    personalizzazione: Personalizzazione,
    eventi: list[EventoBase],
    adesso: datetime.datetime,
) -> list[tuple[str, str]]:
    """I promemoria delle dosi diventate "saltate" da poco (D15, D38), come coppie (chiave, testo).

    La chiave (giorno, farmaco, orario) serve all'archivio per non mandare lo stesso promemoria due volte.
    `eventi`: almeno quelli da due giorni fa a oggi (una dose di ieri sera diventa saltata dopo mezzanotte).
    """
    if not casa_attiva(eventi, adesso):
        return []
    fuso_orario = personalizzazione.fuso_orario
    eventi_farmaco = []
    for evento in eventi:
        if evento.tipo == "farmaco":
            eventi_farmaco.append(evento)

    oggi = giorno_locale(adesso, fuso_orario)
    ieri = oggi - datetime.timedelta(days=1)
    validita = datetime.timedelta(minutes=MINUTI_VALIDITA_PROMEMORIA)
    promemoria = []
    for data in [ieri, oggi]:
        for dose in stato_delle_dosi(data, personalizzazione, eventi_farmaco, adesso):
            if dose.stato != "saltata":
                continue
            farmaco = farmaco_con_id(personalizzazione, dose.farmaco_id)
            fine = fine_della_finestra(data, dose.orario_previsto, farmaco, fuso_orario)
            if adesso - fine > validita:
                continue
            chiave = data.isoformat() + " " + farmaco.id + " " + dose.orario_previsto
            testo = ("Medication reminder: " + personalizzazione.anziano.nome + " has not taken " + farmaco.nome
                     + " (" + farmaco.dose + "), due at " + dose.orario_previsto + ".")
            promemoria.append((chiave, testo))
    return promemoria
