"""Dove il backend tiene i dati della casa demo: personalizzazione, eventi, foto di prova.

PROVVISORIO: tutto in memoria, si perde a ogni riavvio del server. La libreria del database (SQLite in sviluppo,
PostgreSQL online, D12) la sceglie Marco; l'archivio sul database avrà gli stessi metodi, così app e regole non
cambiano.
"""

import datetime

from contratti.configurazione import Personalizzazione
from contratti.eventi import EventoBase

from backend.regole import inizio_evento


class ArchivioMemoria:
    def __init__(self) -> None:
        self.personalizzazione: Personalizzazione | None = None
        # eventi per id, salvati senza foto: la lista degli eventi non le restituisce mai (API.md)
        self.eventi: dict[str, EventoBase] = {}
        # foto di prova per id dell'evento, già in JPEG (non più in base64)
        self.foto: dict[str, bytes] = {}

    def leggi_personalizzazione(self) -> Personalizzazione | None:
        return self.personalizzazione

    def salva_personalizzazione(self, nuova: Personalizzazione) -> Personalizzazione:
        """Salva quella mandata dal programma di casa, ma pausa e spegnimento dell'allarme uscita restano quelli già
        decisi da Telegram (API.md, D16, D27). La prima volta si prendono quelli mandati."""
        if self.personalizzazione is not None:
            vecchie_regole = self.personalizzazione.regole
            modifiche = {
                "allarme_uscita_attivo": vecchie_regole.allarme_uscita_attivo,
                "pausa_fino_a": vecchie_regole.pausa_fino_a,
            }
            regole = nuova.regole.model_copy(update=modifiche)
            nuova = nuova.model_copy(update={"regole": regole})
        self.personalizzazione = nuova
        return nuova

    def aggiungi_evento(self, evento: EventoBase, foto: bytes | None) -> bool:
        """Salva un evento nuovo con la sua foto; False se l'id è già stato visto (il programma di casa può rimandare
        gli stessi eventi, API.md)."""
        if evento.id in self.eventi:
            return False
        self.eventi[evento.id] = evento.model_copy(update={"foto_prova": None})
        if foto is not None:
            self.foto[evento.id] = foto
        return True

    def leggi_eventi(
        self,
        dal: datetime.datetime | None,
        al: datetime.datetime | None,
        tipo: str | None,
    ) -> list[EventoBase]:
        """Gli eventi con inizio da `dal` (compreso) ad `al` (escluso), in ordine di inizio. None: nessun limite."""
        scelti = []
        for evento in self.eventi.values():
            if dal is not None and evento.inizio < dal:
                continue
            if al is not None and evento.inizio >= al:
                continue
            if tipo is not None and evento.tipo != tipo:
                continue
            scelti.append(evento)
        scelti.sort(key=inizio_evento)
        return scelti

    def leggi_foto(self, id_evento: str) -> bytes | None:
        return self.foto.get(id_evento)
