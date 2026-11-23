"""Invio al backend secondo contratti/API.md, con l'header `Authorization: Bearer <token casa>`:
- PUT /programma-casa/personalizzazione: la Personalizzazione del file locale (senza sorgenti né zone, D21);
- POST /programma-casa/eventi: lista di eventi → {ricevuti, nuovi}.
Gli urgenti partono subito, gli altri a lotti ogni SECONDI_TRA_LOTTI. Se il backend non risponde gli eventi restano
nel registro locale e si rimandano al giro dopo. Il token sta nel file .env, mai nel repo.
"""

import json
import urllib.request

from pydantic import TypeAdapter

from contratti.configurazione import Personalizzazione
from contratti.eventi import Evento

from casa.registro import RegistroLocale

LETTORE_LISTA_EVENTI = TypeAdapter(list[Evento])
SECONDI_TRA_LOTTI = 60
# con le foto di prova (decine di KB l'una) una richiesta resta di pochi MB
EVENTI_PER_RICHIESTA = 50
SECONDI_ATTESA_RISPOSTA = 15


class Backend:
    def __init__(self, indirizzo: str, token: str):
        self.indirizzo = indirizzo.rstrip("/")
        self.token = token

    def richiesta(self, metodo: str, percorso: str, corpo: bytes) -> dict | list | None:
        """La risposta JSON, o None se il backend non è raggiungibile o risponde con un errore."""
        intestazioni = {"Authorization": "Bearer " + self.token, "Content-Type": "application/json"}
        richiesta = urllib.request.Request(self.indirizzo + percorso, data=corpo, headers=intestazioni,
                                           method=metodo)
        try:
            with urllib.request.urlopen(richiesta, timeout=SECONDI_ATTESA_RISPOSTA) as risposta:
                return json.loads(risposta.read())
        except (OSError, ValueError) as errore:
            # OSError comprende rete assente, tempo scaduto e risposte HTTP di errore; ValueError il JSON rotto
            print("backend: " + metodo + " " + percorso + " non riuscito: " + str(errore))
            return None

    def invia_personalizzazione(self, personalizzazione: Personalizzazione) -> bool:
        corpo = personalizzazione.model_dump_json().encode("utf-8")
        return self.richiesta("PUT", "/programma-casa/personalizzazione", corpo) is not None

    def invia_eventi(self, eventi: list) -> dict | None:
        corpo = LETTORE_LISTA_EVENTI.dump_json(eventi)
        return self.richiesta("POST", "/programma-casa/eventi", corpo)


def invia_in_sospeso(registro: RegistroLocale, backend: Backend, solo_urgenti: bool) -> int:
    """Manda gli eventi del registro non ancora inviati. Restituisce quanti sono arrivati al backend."""
    eventi = registro.da_inviare(solo_urgenti)
    inviati = 0
    for primo in range(0, len(eventi), EVENTI_PER_RICHIESTA):
        lotto = eventi[primo:primo + EVENTI_PER_RICHIESTA]
        if backend.invia_eventi(lotto) is None:
            break  # backend non raggiungibile: il resto aspetta il prossimo giro
        registro.segna_inviati(lotto)
        inviati = inviati + len(lotto)
    return inviati
