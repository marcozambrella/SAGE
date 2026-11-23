"""Registro locale degli eventi (SQLite, libreria standard). Ogni evento uscito dall'unione si salva qui prima di
mandarlo al backend: se manca la rete resta "da inviare" e si rimanda dopo. Il backend ignora un id già visto,
quindi rimandare non crea doppioni (API.md)."""

import datetime
import json
from pathlib import Path
import sqlite3

from contratti.eventi import LETTORE_EVENTO, TIPI_URGENTI, EventoBase, leggi_evento


class RegistroLocale:
    def __init__(self, percorso: str):
        Path(percorso).parent.mkdir(parents=True, exist_ok=True)
        self.connessione = sqlite3.connect(percorso)
        self.connessione.execute(
            "CREATE TABLE IF NOT EXISTS eventi ("
            " id TEXT PRIMARY KEY,"
            " tipo TEXT NOT NULL,"
            " inizio_utc TEXT NOT NULL,"  # in UTC così l'ordine alfabetico è anche l'ordine nel tempo
            " dati TEXT NOT NULL,"         # l'evento in JSON, formato dei contratti
            " inviato INTEGER NOT NULL DEFAULT 0)"
        )
        self.connessione.commit()

    def salva(self, evento: EventoBase) -> None:
        testo = LETTORE_EVENTO.dump_json(evento).decode("utf-8")
        inizio_utc = evento.inizio.astimezone(datetime.timezone.utc).isoformat()
        self.connessione.execute("INSERT OR IGNORE INTO eventi (id, tipo, inizio_utc, dati) VALUES (?, ?, ?, ?)",
                                 (evento.id, evento.tipo, inizio_utc, testo))
        self.connessione.commit()

    def leggi(self, condizione: str) -> list:
        righe = self.connessione.execute("SELECT tipo, dati FROM eventi " + condizione + " ORDER BY inizio_utc")
        eventi = []
        for tipo, dati in righe.fetchall():
            eventi.append(leggi_evento(json.loads(dati)))
        return eventi

    def da_inviare(self, solo_urgenti: bool) -> list:
        eventi = []
        for evento in self.leggi("WHERE inviato = 0"):
            if solo_urgenti and evento.tipo not in TIPI_URGENTI:
                continue
            eventi.append(evento)
        return eventi

    def tutti(self) -> list:
        return self.leggi("")

    def segna_inviati(self, eventi: list) -> None:
        for evento in eventi:
            self.connessione.execute("UPDATE eventi SET inviato = 1 WHERE id = ?", (evento.id,))
        self.connessione.commit()

    def chiudi(self) -> None:
        self.connessione.close()
