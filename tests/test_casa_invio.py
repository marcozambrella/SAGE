"""Test di registro locale e invio al backend con un backend finto (server HTTP locale nel test)."""

import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
import uuid
from zoneinfo import ZoneInfo

import pytest

from contratti.configurazione import Personalizzazione
from contratti.eventi import leggi_evento

from casa.invio import EVENTI_PER_RICHIESTA, Backend, invia_in_sospeso
from casa.registro import RegistroLocale

ROMA = ZoneInfo("Europe/Rome")
TOKEN = "token-di-prova"


# un evento con questa stanza il backend finto lo rifiuta (come il backend vero rifiuta un evento fuori contratto)
STANZA_RIFIUTATA = "stanza-che-il-backend-rifiuta"


class BackendFinto(BaseHTTPRequestHandler):
    """Registra le richieste e risponde come il backend vero (API.md). Con `codice_errore` risponde sempre con
    quel codice; se nella lista c'è un evento con STANZA_RIFIUTATA rifiuta tutta la richiesta con 422, come FastAPI
    quando un elemento della lista non va bene."""

    richieste = []
    codice_errore = None

    def rispondi(self) -> None:
        lunghezza = int(self.headers["Content-Length"])
        corpo = json.loads(self.rfile.read(lunghezza))
        BackendFinto.richieste.append({
            "metodo": self.command,
            "percorso": self.path,
            "autorizzazione": self.headers["Authorization"],
            "corpo": corpo,
        })
        codice = 200
        risposta = corpo
        if self.command == "POST":
            risposta = {"ricevuti": len(corpo), "nuovi": len(corpo)}
            for evento in corpo:
                if evento["stanza"] == STANZA_RIFIUTATA:
                    codice = 422
                    risposta = {"detail": "stanza non valida"}
        if BackendFinto.codice_errore is not None:
            codice = BackendFinto.codice_errore
            risposta = {"detail": "errore di prova"}
        testo = json.dumps(risposta).encode("utf-8")
        self.send_response(codice)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(testo)))
        self.end_headers()
        self.wfile.write(testo)

    def do_POST(self) -> None:
        self.rispondi()

    def do_PUT(self) -> None:
        self.rispondi()

    def log_message(self, formato, *argomenti) -> None:
        pass  # niente righe di log nei test


@pytest.fixture
def indirizzo_backend():
    BackendFinto.richieste = []
    BackendFinto.codice_errore = None
    server = ThreadingHTTPServer(("127.0.0.1", 0), BackendFinto)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield "http://127.0.0.1:" + str(server.server_address[1])
    server.shutdown()
    server.server_close()


def evento(tipo: str, minuti: int, stanza: str = "hall"):
    valori = {"zona_id": "porta-ingresso"}
    if tipo == "alzata_notturna":
        valori = {"stanze": ["bedroom"]}
    return leggi_evento({
        "id": str(uuid.uuid4()),
        "tipo": tipo,
        "inizio": datetime.datetime(2026, 12, 1, 10, 0, tzinfo=ROMA) + datetime.timedelta(minutes=minuti),
        "stanza": stanza,
        "confidenza": 0.8,
        "fonti": [{"telecamera_id": "ingresso", "analizzatore": tipo, "confidenza": 0.8}],
        "valori": valori,
    })


def test_registro_salva_e_ricorda_gli_inviati(tmp_path):
    percorso = str(tmp_path / "dati" / "registro.sqlite3")
    registro = RegistroLocale(percorso)
    prima = evento("uscita", 5)
    seconda = evento("alzata_notturna", 1)
    registro.salva(prima)
    registro.salva(seconda)
    registro.salva(prima)  # stesso id: ignorato
    assert registro.tutti() == [seconda, prima]  # in ordine di inizio
    registro.segna_inviati([seconda])
    registro.chiudi()
    # riaperto (programma riavviato): resta da inviare solo il primo
    riaperto = RegistroLocale(percorso)
    assert riaperto.da_inviare(False) == [prima]
    assert len(riaperto.tutti()) == 2


def test_solo_urgenti(tmp_path):
    registro = RegistroLocale(str(tmp_path / "registro.sqlite3"))
    urgente = evento("uscita", 0)
    registro.salva(urgente)
    registro.salva(evento("alzata_notturna", 1))
    assert registro.da_inviare(True) == [urgente]


def test_invio_eventi_e_personalizzazione(tmp_path, indirizzo_backend):
    backend = Backend(indirizzo_backend + "/", TOKEN)
    personalizzazione = Personalizzazione.model_validate({"anziano": {"nome": "Anna"}})
    assert backend.invia_personalizzazione(personalizzazione)
    registro = RegistroLocale(str(tmp_path / "registro.sqlite3"))
    registro.salva(evento("uscita", 0))
    registro.salva(evento("alzata_notturna", 1))
    assert invia_in_sospeso(registro, backend, False) == 2
    assert registro.da_inviare(False) == []

    put = BackendFinto.richieste[0]
    assert put["metodo"] == "PUT"
    assert put["percorso"] == "/programma-casa/personalizzazione"
    assert put["autorizzazione"] == "Bearer " + TOKEN
    assert put["corpo"]["anziano"]["nome"] == "Anna"
    post = BackendFinto.richieste[1]
    assert post["metodo"] == "POST"
    assert post["percorso"] == "/programma-casa/eventi"
    assert post["autorizzazione"] == "Bearer " + TOKEN
    # il backend riceve eventi validi secondo i contratti
    tipi = []
    for dati in post["corpo"]:
        tipi.append(leggi_evento(dati).tipo)
    assert tipi == ["uscita", "alzata_notturna"]


def test_backend_guasto_poi_rimandati(tmp_path, indirizzo_backend):
    backend = Backend(indirizzo_backend, TOKEN)
    registro = RegistroLocale(str(tmp_path / "registro.sqlite3"))
    registro.salva(evento("uscita", 0))
    # errore 5xx: si ritenta, l'evento resta in coda
    BackendFinto.codice_errore = 503
    assert invia_in_sospeso(registro, backend, True) == 0
    assert len(registro.da_inviare(False)) == 1
    assert registro.rifiutati() == []
    BackendFinto.codice_errore = None
    assert invia_in_sospeso(registro, backend, True) == 1
    assert registro.da_inviare(False) == []


def test_lotto_rifiutato_si_scartano_solo_gli_eventi_sbagliati(tmp_path, indirizzo_backend):
    backend = Backend(indirizzo_backend, TOKEN)
    registro = RegistroLocale(str(tmp_path / "registro.sqlite3"))
    buono = evento("alzata_notturna", 0)
    sbagliato = evento("alzata_notturna", 1, STANZA_RIFIUTATA)
    altro_buono = evento("uscita", 2)
    registro.salva(buono)
    registro.salva(sbagliato)
    registro.salva(altro_buono)
    assert invia_in_sospeso(registro, backend, False) == 2
    # il lotto intero rifiutato con 422, poi un evento alla volta
    dimensioni = []
    for richiesta in BackendFinto.richieste:
        dimensioni.append(len(richiesta["corpo"]))
    assert dimensioni == [3, 1, 1, 1]
    # fuori dalla coda, ma ricordato nel registro con il messaggio del backend
    assert registro.da_inviare(False) == []
    rifiutati = registro.rifiutati()
    assert len(rifiutati) == 1
    assert rifiutati[0].evento == sbagliato
    assert rifiutati[0].errore.startswith("422 ")
    assert "stanza non valida" in rifiutati[0].errore
    # al giro dopo non si rimanda niente
    assert invia_in_sospeso(registro, backend, False) == 0
    assert len(BackendFinto.richieste) == 4


@pytest.mark.parametrize("codice", [401, 403, 404, 429])
def test_altri_4xx_si_ritentano(tmp_path, indirizzo_backend, codice):
    # token o indirizzo sbagliati non sono colpa dell'evento: resta in coda, non diventa rifiutato
    backend = Backend(indirizzo_backend, TOKEN)
    registro = RegistroLocale(str(tmp_path / "registro.sqlite3"))
    registro.salva(evento("uscita", 0))
    BackendFinto.codice_errore = codice
    assert invia_in_sospeso(registro, backend, False) == 0
    assert len(registro.da_inviare(False)) == 1
    assert registro.rifiutati() == []
    BackendFinto.codice_errore = None
    assert invia_in_sospeso(registro, backend, False) == 1


def test_evento_singolo_rifiutato_senza_ritentare(tmp_path, indirizzo_backend):
    backend = Backend(indirizzo_backend, TOKEN)
    registro = RegistroLocale(str(tmp_path / "registro.sqlite3"))
    registro.salva(evento("uscita", 0))
    BackendFinto.codice_errore = 400
    assert invia_in_sospeso(registro, backend, True) == 0
    assert len(BackendFinto.richieste) == 1
    assert registro.da_inviare(False) == []
    assert registro.rifiutati()[0].errore.startswith("400 ")


def test_backend_spento(tmp_path):
    # nessuno in ascolto su questa porta: niente eccezioni, l'evento resta da inviare
    backend = Backend("http://127.0.0.1:9", TOKEN)
    registro = RegistroLocale(str(tmp_path / "registro.sqlite3"))
    registro.salva(evento("uscita", 0))
    assert invia_in_sospeso(registro, backend, False) == 0
    assert len(registro.da_inviare(False)) == 1


def test_a_lotti(tmp_path, indirizzo_backend):
    backend = Backend(indirizzo_backend, TOKEN)
    registro = RegistroLocale(str(tmp_path / "registro.sqlite3"))
    numero = EVENTI_PER_RICHIESTA * 2 + 7
    for minuto in range(numero):
        registro.salva(evento("alzata_notturna", minuto))
    assert invia_in_sospeso(registro, backend, False) == numero
    dimensioni = []
    for richiesta in BackendFinto.richieste:
        dimensioni.append(len(richiesta["corpo"]))
    assert dimensioni == [EVENTI_PER_RICHIESTA, EVENTI_PER_RICHIESTA, 7]
