"""Quali eventi fanno partire subito l'allarme Telegram e con che testo (API.md, D10, D16, D24).

Logica pura: qui si decide, l'invio vero lo fa il bot Telegram. I testi sono in inglese (D13).
"""

import logging

from contratti.configurazione import Personalizzazione
from contratti.eventi import TIPI_URGENTI, EventoBase

from backend.regole import ora_locale, uscita_in_orario_vietato

# Lo stesso valore predefinito di Personalizzazione.fuso_orario: serve solo se la casa non è ancora configurata.
FUSO_ORARIO_PREDEFINITO = "Europe/Rome"

registro = logging.getLogger("sage.allarmi")


def serve_allarme(evento: EventoBase, personalizzazione: Personalizzazione | None) -> bool:
    """True se l'evento deve far partire subito un messaggio Telegram."""
    # lo storico simulato (D22) non fa mai partire allarmi
    if evento.simulato:
        return False
    if evento.tipo not in TIPI_URGENTI:
        return False
    # caduta: sempre, subito
    if evento.tipo == "caduta":
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
    return "Exit alert: " + nome + " left the house at " + ora + ", during restricted hours."


def scrivi_allarme_nel_log(testo: str, foto: bytes | None) -> None:
    """Invio provvisorio finché il bot Telegram non c'è: l'allarme finisce solo nel log del server."""
    registro.warning("Allarme (Telegram non ancora collegato): %s", testo)
