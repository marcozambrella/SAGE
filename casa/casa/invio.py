"""Invio al backend secondo contratti/API.md, con l'header `Authorization: Bearer <token casa>`:
- PUT /programma-casa/personalizzazione: la Personalizzazione del file locale (senza sorgenti né zone, D21);
- POST /programma-casa/eventi: lista di eventi → {ricevuti, nuovi}.
Gli urgenti partono subito, gli altri a lotti ogni SECONDI_TRA_LOTTI. Se il backend non risponde (rete, tempo
scaduto, errore 5xx) gli eventi restano nel registro locale e si rimandano al giro dopo. Se li rifiuta perché
l'evento è sbagliato (400, 422) rimandarli uguali non serve: diventano "rifiutati" nel registro, con il messaggio,
ed escono dalla coda. Gli altri 4xx (token sbagliato, indirizzo sbagliato, troppe richieste) non sono colpa
dell'evento: si ritentano, scrivendolo nel log (Marco, 24/11).
Il token sta nel file .env, mai nel repo.
"""

from dataclasses import dataclass
import json
import urllib.error
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
# il messaggio d'errore del backend si tiene nel registro, accorciato
LUNGHEZZA_MASSIMA_ERRORE = 1000
# errori per cui l'evento stesso è sbagliato: inutile rimandarlo
CODICI_EVENTO_SBAGLIATO = (400, 422)


@dataclass
class Risposta:
    esito: str                      # "ok", "rifiutata" (400, 422) o "da_ritentare" (rete, altri errori)
    dati: dict | list | None = None
    errore: str = ""


class Backend:
    def __init__(self, indirizzo: str, token: str):
        self.indirizzo = indirizzo.rstrip("/")
        self.token = token

    def richiesta(self, metodo: str, percorso: str, corpo: bytes) -> Risposta:
        intestazioni = {"Authorization": "Bearer " + self.token, "Content-Type": "application/json"}
        richiesta = urllib.request.Request(self.indirizzo + percorso, data=corpo, headers=intestazioni,
                                           method=metodo)
        try:
            with urllib.request.urlopen(richiesta, timeout=SECONDI_ATTESA_RISPOSTA) as risposta:
                return Risposta("ok", json.loads(risposta.read()))
        except urllib.error.HTTPError as errore:
            # il backend ha risposto con un errore: si tiene il codice e il suo messaggio
            testo = errore.read().decode("utf-8", errors="replace")
            messaggio = str(errore.code) + " " + testo
            messaggio = messaggio[:LUNGHEZZA_MASSIMA_ERRORE]
            print("backend: " + metodo + " " + percorso + " → " + messaggio)
            if errore.code in CODICI_EVENTO_SBAGLIATO:
                return Risposta("rifiutata", None, messaggio)
            if 400 <= errore.code < 500:
                print("backend: errore " + str(errore.code) + " non dovuto agli eventi (token? indirizzo?): si ritenta")
            return Risposta("da_ritentare", None, messaggio)
        except (OSError, ValueError) as errore:
            # OSError: rete assente o tempo scaduto; ValueError: risposta che non è JSON
            print("backend: " + metodo + " " + percorso + " non riuscito: " + str(errore))
            return Risposta("da_ritentare", None, str(errore))

    def invia_personalizzazione(self, personalizzazione: Personalizzazione) -> bool:
        corpo = personalizzazione.model_dump_json().encode("utf-8")
        risposta = self.richiesta("PUT", "/programma-casa/personalizzazione", corpo)
        return risposta.esito == "ok"

    def invia_eventi(self, eventi: list) -> Risposta:
        corpo = LETTORE_LISTA_EVENTI.dump_json(eventi)
        return self.richiesta("POST", "/programma-casa/eventi", corpo)


def invia_in_sospeso(registro: RegistroLocale, backend: Backend, solo_urgenti: bool) -> int:
    """Manda gli eventi del registro non ancora inviati. Restituisce quanti sono arrivati al backend."""
    eventi = registro.da_inviare(solo_urgenti)
    inviati = 0
    for primo in range(0, len(eventi), EVENTI_PER_RICHIESTA):
        lotto = eventi[primo:primo + EVENTI_PER_RICHIESTA]
        risposta = backend.invia_eventi(lotto)
        if risposta.esito == "da_ritentare":
            break  # backend non raggiungibile: il resto aspetta il prossimo giro
        if risposta.esito == "ok":
            registro.segna_inviati(lotto)
            inviati = inviati + len(lotto)
            continue
        # lotto rifiutato: può bastare un solo evento sbagliato (il backend controlla la lista intera), quindi si
        # rimandano uno alla volta e diventano "rifiutati" solo quelli che il backend rifiuta anche da soli
        raggiungibile = True
        for evento in lotto:
            singola = risposta
            if len(lotto) > 1:
                singola = backend.invia_eventi([evento])
            if singola.esito == "da_ritentare":
                raggiungibile = False
                break
            if singola.esito == "ok":
                registro.segna_inviati([evento])
                inviati = inviati + 1
            else:
                registro.segna_rifiutato(evento, singola.errore)
                print("evento " + evento.id + " (" + evento.tipo + ") rifiutato dal backend: tolto dalla coda")
        if not raggiungibile:
            break
    return inviati
