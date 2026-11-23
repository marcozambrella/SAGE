"""Dove il backend tiene i dati della casa demo: personalizzazione, eventi, foto di prova, chat Telegram collegate,
promemoria già mandati.

SQLite in sviluppo e PostgreSQL online (D12), con sqlite3 e psycopg scritti a mano (D36). L'SQL è scritto una volta
sola con i segnaposto "?" di sqlite3: per PostgreSQL diventano "%s" (adatta). Le tabelle sono le stesse sui due
database; cambia solo il tipo dei byte delle foto (BLOB / BYTEA). L'evento è salvato come JSON in una colonna.

Si apre una connessione nuova per ogni operazione: niente connessioni condivise tra le richieste e niente
connessioni scadute quando Neon si sospende dopo qualche minuto senza query.
"""

import datetime
import sqlite3

import psycopg

from contratti.configurazione import Personalizzazione
from contratti.eventi import LETTORE_EVENTO, EventoBase

TABELLE = [
    # una riga sola (id = 1): c'è una sola casa, la casa demo (D27)
    "CREATE TABLE IF NOT EXISTS personalizzazione (id INTEGER PRIMARY KEY, dati TEXT NOT NULL)",
    # inizio_utc: testo a lunghezza fissa in UTC, così l'ordine alfabetico è l'ordine nel tempo
    "CREATE TABLE IF NOT EXISTS eventi (id TEXT PRIMARY KEY, tipo TEXT NOT NULL, inizio_utc TEXT NOT NULL, "
    "dati TEXT NOT NULL)",
    "CREATE INDEX IF NOT EXISTS eventi_per_inizio ON eventi (inizio_utc)",
    "CREATE TABLE IF NOT EXISTS chat_telegram (chat_id BIGINT PRIMARY KEY)",
    # chiave = giorno + farmaco + orario: il cron passa ogni pochi minuti, il promemoria parte una volta sola
    "CREATE TABLE IF NOT EXISTS promemoria_mandati (chiave TEXT PRIMARY KEY)",
]
TABELLA_FOTO_SQLITE = "CREATE TABLE IF NOT EXISTS foto (id_evento TEXT PRIMARY KEY, jpeg BLOB NOT NULL)"
TABELLA_FOTO_POSTGRES = "CREATE TABLE IF NOT EXISTS foto (id_evento TEXT PRIMARY KEY, jpeg BYTEA NOT NULL)"

LEGGI_PERSONALIZZAZIONE = "SELECT dati FROM personalizzazione WHERE id = 1"
SCRIVI_PERSONALIZZAZIONE = (
    "INSERT INTO personalizzazione (id, dati) VALUES (1, ?) ON CONFLICT (id) DO UPDATE SET dati = excluded.dati"
)
# un id già visto viene ignorato (API.md): il numero di righe inserite dice se l'evento è nuovo
NUOVO_EVENTO = "INSERT INTO eventi (id, tipo, inizio_utc, dati) VALUES (?, ?, ?, ?) ON CONFLICT (id) DO NOTHING"
NUOVA_FOTO = "INSERT INTO foto (id_evento, jpeg) VALUES (?, ?) ON CONFLICT (id_evento) DO NOTHING"
LEGGI_FOTO = "SELECT jpeg FROM foto WHERE id_evento = ?"
NUOVA_CHAT = "INSERT INTO chat_telegram (chat_id) VALUES (?) ON CONFLICT (chat_id) DO NOTHING"
LEGGI_CHAT = "SELECT chat_id FROM chat_telegram ORDER BY chat_id"
NUOVO_PROMEMORIA = "INSERT INTO promemoria_mandati (chiave) VALUES (?) ON CONFLICT (chiave) DO NOTHING"


def testo_utc(momento: datetime.datetime) -> str:
    """Il momento in UTC come testo a lunghezza fissa (es. 2026-12-01T07:05:00.000000)."""
    return momento.astimezone(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")


def e_postgres(indirizzo: str) -> bool:
    return indirizzo.startswith("postgresql://") or indirizzo.startswith("postgres://")


class ArchivioDatabase:
    def __init__(self, indirizzo: str) -> None:
        """indirizzo: "postgresql://..." (Neon) oppure il percorso di un file SQLite. Crea le tabelle che mancano."""
        self.indirizzo = indirizzo
        self.postgres = e_postgres(indirizzo)
        self.crea_tabelle()

    # --- accesso al database ---

    def connetti(self) -> sqlite3.Connection | psycopg.Connection:
        if self.postgres:
            # prepare_threshold=None: niente istruzioni preparate, che passando dal pooler di Neon possono perdersi
            return psycopg.connect(self.indirizzo, prepare_threshold=None)
        return sqlite3.connect(self.indirizzo)

    def adatta(self, sql: str) -> str:
        """I segnaposto: "?" per sqlite3, "%s" per psycopg. L'SQL qui non contiene altri "?" né "%"."""
        if self.postgres:
            return sql.replace("?", "%s")
        return sql

    def esegui(self, sql: str, parametri: tuple) -> int:
        """Esegue un'istruzione che scrive e dà il numero di righe cambiate."""
        connessione = self.connetti()
        try:
            cursore = connessione.cursor()
            cursore.execute(self.adatta(sql), parametri)
            righe_cambiate = cursore.rowcount
            connessione.commit()
        finally:
            connessione.close()
        return righe_cambiate

    def leggi(self, sql: str, parametri: tuple) -> list[tuple]:
        connessione = self.connetti()
        try:
            cursore = connessione.cursor()
            cursore.execute(self.adatta(sql), parametri)
            righe = cursore.fetchall()
        finally:
            connessione.close()
        return righe

    def crea_tabelle(self) -> None:
        for istruzione in TABELLE:
            self.esegui(istruzione, ())
        if self.postgres:
            self.esegui(TABELLA_FOTO_POSTGRES, ())
        else:
            self.esegui(TABELLA_FOTO_SQLITE, ())

    # --- personalizzazione ---

    def leggi_personalizzazione(self) -> Personalizzazione | None:
        righe = self.leggi(LEGGI_PERSONALIZZAZIONE, ())
        if len(righe) == 0:
            return None
        return Personalizzazione.model_validate_json(righe[0][0])

    def scrivi_personalizzazione(self, personalizzazione: Personalizzazione) -> None:
        self.esegui(SCRIVI_PERSONALIZZAZIONE, (personalizzazione.model_dump_json(),))

    def salva_personalizzazione(self, nuova: Personalizzazione) -> Personalizzazione:
        """Salva quella mandata dal programma di casa, ma pausa e spegnimento dell'allarme uscita restano quelli già
        decisi da Telegram (API.md, D16, D27). La prima volta si prendono quelli mandati."""
        vecchia = self.leggi_personalizzazione()
        if vecchia is not None:
            modifiche = {
                "allarme_uscita_attivo": vecchia.regole.allarme_uscita_attivo,
                "pausa_fino_a": vecchia.regole.pausa_fino_a,
            }
            regole = nuova.regole.model_copy(update=modifiche)
            nuova = nuova.model_copy(update={"regole": regole})
        self.scrivi_personalizzazione(nuova)
        return nuova

    def cambia_allarme_uscita(
        self, attivo: bool, pausa_fino_a: datetime.datetime | None
    ) -> Personalizzazione | None:
        """Dai pulsanti e dai comandi Telegram (D16). None se la casa non è ancora configurata."""
        personalizzazione = self.leggi_personalizzazione()
        if personalizzazione is None:
            return None
        modifiche = {"allarme_uscita_attivo": attivo, "pausa_fino_a": pausa_fino_a}
        regole = personalizzazione.regole.model_copy(update=modifiche)
        personalizzazione = personalizzazione.model_copy(update={"regole": regole})
        self.scrivi_personalizzazione(personalizzazione)
        return personalizzazione

    # --- eventi e foto ---

    def aggiungi_eventi(self, eventi: list[EventoBase], foto_degli_eventi: list[bytes | None]) -> list[bool]:
        """Salva gli eventi nuovi con le loro foto, tutti in una transazione (lo storico simulato ne manda centinaia).
        Per ogni evento dice se era nuovo: un id già visto viene ignorato, anche dentro la stessa lista."""
        nuovi = []
        connessione = self.connetti()
        try:
            cursore = connessione.cursor()
            for evento, foto in zip(eventi, foto_degli_eventi):
                # la foto sta nella sua tabella: la lista degli eventi non la restituisce mai (API.md)
                senza_foto = evento.model_copy(update={"foto_prova": None})
                dati = LETTORE_EVENTO.dump_json(senza_foto).decode()
                parametri = (evento.id, evento.tipo, testo_utc(evento.inizio), dati)
                cursore.execute(self.adatta(NUOVO_EVENTO), parametri)
                nuovo = cursore.rowcount == 1
                if nuovo and foto is not None:
                    cursore.execute(self.adatta(NUOVA_FOTO), (evento.id, foto))
                nuovi.append(nuovo)
            connessione.commit()
        finally:
            connessione.close()
        return nuovi

    def leggi_eventi(
        self,
        dal: datetime.datetime | None,
        al: datetime.datetime | None,
        tipo: str | None,
    ) -> list[EventoBase]:
        """Gli eventi con inizio da `dal` (compreso) ad `al` (escluso), in ordine di inizio. None: nessun limite."""
        condizioni = []
        parametri = []
        if dal is not None:
            condizioni.append("inizio_utc >= ?")
            parametri.append(testo_utc(dal))
        if al is not None:
            condizioni.append("inizio_utc < ?")
            parametri.append(testo_utc(al))
        if tipo is not None:
            condizioni.append("tipo = ?")
            parametri.append(tipo)
        sql = "SELECT dati FROM eventi"
        if len(condizioni) > 0:
            sql = sql + " WHERE " + " AND ".join(condizioni)
        sql = sql + " ORDER BY inizio_utc, id"

        eventi = []
        for riga in self.leggi(sql, tuple(parametri)):
            eventi.append(LETTORE_EVENTO.validate_json(riga[0]))
        return eventi

    def leggi_foto(self, id_evento: str) -> bytes | None:
        righe = self.leggi(LEGGI_FOTO, (id_evento,))
        if len(righe) == 0:
            return None
        # psycopg può dare un memoryview per BYTEA: sempre bytes
        return bytes(righe[0][0])

    # --- Telegram ---

    def collega_chat(self, chat_id: int) -> None:
        self.esegui(NUOVA_CHAT, (chat_id,))

    def chat_collegate(self) -> list[int]:
        chat = []
        for riga in self.leggi(LEGGI_CHAT, ()):
            chat.append(riga[0])
        return chat

    def segna_promemoria(self, chiave: str) -> bool:
        """True se il promemoria non era ancora stato mandato (e adesso risulta mandato)."""
        return self.esegui(NUOVO_PROMEMORIA, (chiave,)) == 1
