"""Registro locale degli eventi (SQLite, libreria standard). Ogni evento uscito dall'unione si salva qui prima di
mandarlo al backend: se manca la rete resta "da inviare" e si rimanda dopo. Il backend ignora un id già visto,
quindi rimandare non crea doppioni (API.md). Un evento che il backend rifiuta (errore 4xx) diventa "rifiutato",
con il messaggio d'errore, ed esce dalla coda: rimandarlo uguale non servirebbe.
"""

from dataclasses import dataclass
import datetime
import json
from pathlib import Path
import sqlite3

from contratti.eventi import LETTORE_EVENTO, TIPI_URGENTI, EventoBase, leggi_evento


@dataclass
class EventoRifiutato:
    evento: EventoBase
    errore: str  # codice e messaggio del backend


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
            " stato TEXT NOT NULL DEFAULT 'da_inviare',"  # da_inviare, inviato o rifiutato
            " errore TEXT)"                # per i rifiutati: il messaggio del backend
        )
        self.connessione.commit()

    def salva(self, evento: EventoBase) -> None:
        testo = LETTORE_EVENTO.dump_json(evento).decode("utf-8")
        inizio_utc = evento.inizio.astimezone(datetime.timezone.utc).isoformat()
        self.connessione.execute("INSERT OR IGNORE INTO eventi (id, tipo, inizio_utc, dati) VALUES (?, ?, ?, ?)",
                                 (evento.id, evento.tipo, inizio_utc, testo))
        self.connessione.commit()

    def leggi(self, condizione: str) -> list:
        righe = self.connessione.execute("SELECT dati FROM eventi " + condizione + " ORDER BY inizio_utc")
        eventi = []
        for riga in righe.fetchall():
            eventi.append(leggi_evento(json.loads(riga[0])))
        return eventi

    def da_inviare(self, solo_urgenti: bool) -> list:
        eventi = []
        for evento in self.leggi("WHERE stato = 'da_inviare'"):
            if solo_urgenti and evento.tipo not in TIPI_URGENTI:
                continue
            eventi.append(evento)
        return eventi

    def tutti(self) -> list:
        return self.leggi("")

    def rifiutati(self) -> list:
        domanda = "SELECT dati, errore FROM eventi WHERE stato = 'rifiutato' ORDER BY inizio_utc"
        righe = self.connessione.execute(domanda)
        rifiutati = []
        for riga in righe.fetchall():
            evento = leggi_evento(json.loads(riga[0]))
            rifiutati.append(EventoRifiutato(evento, riga[1]))
        return rifiutati

    def segna_inviati(self, eventi: list) -> None:
        for evento in eventi:
            self.connessione.execute("UPDATE eventi SET stato = 'inviato' WHERE id = ?", (evento.id,))
        self.connessione.commit()

    def segna_rifiutato(self, evento: EventoBase, errore: str) -> None:
        self.connessione.execute("UPDATE eventi SET stato = 'rifiutato', errore = ? WHERE id = ?", (errore, evento.id))
        self.connessione.commit()

    def chiudi(self) -> None:
        self.connessione.close()
