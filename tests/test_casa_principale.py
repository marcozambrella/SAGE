"""Test d'insieme del programma di casa: video sintetici → percezione finta → analizzatori → registro →
backend finto. La percezione è finta (persone scritte a mano) così il test non dipende dai pesi."""

import datetime
import json
from zoneinfo import ZoneInfo

import cv2
import numpy as np
import pytest

from contratti.configurazione import ConfigurazioneCasa
from contratti.eventi import leggi_evento

from casa.invio import Backend
from casa.percezione import Osservazione, Persona
from casa.principale import elabora, leggi_backend, ora_di_inizio, prepara_telecamere
from casa.registro import RegistroLocale
from test_casa_invio import BackendFinto, indirizzo_backend  # noqa: F401 (fixture del backend finto)
from test_casa_sorgenti import scrivi_video

ROMA = ZoneInfo("Europe/Rome")
INIZIO = datetime.datetime(2026, 12, 2, 2, 0, tzinfo=ROMA)


def persona(x_piedi: float) -> Persona:
    """Persona nel fotogramma 64×48 con i piedi in (x_piedi, 45)."""
    box = np.array([x_piedi - 3, 10, x_piedi + 3, 45], np.float32)
    return Persona(1, box, 0.9, np.zeros((17, 3), np.float32))


class PercezioneFinta:
    """Camera da letto: a letto fino a 12 s, in piedi accanto al letto fino a 15 s, poi via, di nuovo a letto da 45 s.
    Ingresso: nella stanza da 15 a 18 s, nella zona porta da 18 a 20 s mentre apre la porta, poi esce."""

    def nuovo_tracker(self):
        return None

    def osserva(self, immagine, tracker, con_oggetti, telecamera_id, stanza, ora) -> Osservazione:
        secondi = (ora - INIZIO).total_seconds()
        persone = []
        if telecamera_id == "camera-letto":
            if secondi < 12 or secondi >= 45:
                persone.append(persona(50))   # zona letto: metà destra
            elif secondi < 15:
                persone.append(persona(20))   # in piedi, fuori dal letto
        elif 15 <= secondi < 18:
            persone.append(persona(50))
        elif 18 <= secondi < 20:
            persone.append(persona(8))        # zona porta: quarto sinistro
        return Osservazione(telecamera_id, stanza, ora, immagine, persone, [])


def scrivi_video_ingresso(percorso) -> None:
    """40 s a 5 fotogrammi al secondo: stanza grigia, porta nel quarto sinistro che si apre tra 18 e 21 s."""
    scrittore = cv2.VideoWriter(str(percorso), cv2.VideoWriter_fourcc(*"mp4v"), 5, (64, 48))
    for indice in range(40 * 5):
        secondi = indice / 5
        immagine = np.full((48, 64, 3), 80, np.uint8)
        immagine[:, 0:16] = 100
        if 18 <= secondi < 21:
            immagine[:, 0:16] = 200
        scrittore.write(immagine)
    scrittore.release()


def configurazione(cartella) -> ConfigurazioneCasa:
    scrivi_video(cartella / "camera.mp4", 60 * 5, 5)
    scrivi_video_ingresso(cartella / "ingresso.mp4")
    return ConfigurazioneCasa.model_validate({
        "telecamere": [
            {"id": "camera-letto", "nome": "Bedroom", "stanza": "bedroom", "sorgente": str(cartella / "camera.mp4"),
             "analizzatori": ["alzata_notturna", "caduta"],
             "zone": [{"id": "letto", "tipo": "letto", "punti": [[0.5, 0], [1, 0], [1, 1], [0.5, 1]]}]},
            {"id": "ingresso", "nome": "Front door", "stanza": "hall", "sorgente": str(cartella / "ingresso.mp4"),
             "analizzatori": ["uscita"],
             "zone": [{"id": "porta-ingresso", "tipo": "porta", "punti": [[0, 0], [0.25, 0], [0.25, 1], [0, 1]]}]},
        ],
        "personalizzazione": {"anziano": {"nome": "Anna"}},
        "cartella_foto_farmaci": "data/foto_farmaci",
    })


def test_dal_video_al_backend(tmp_path, indirizzo_backend):  # noqa: F811
    telecamere = prepara_telecamere(configurazione(tmp_path), 5)
    # camera da letto: alzata notturna e caduta (le persone finte sono sempre in piedi: nessuna caduta)
    assert len(telecamere[0].analizzatori) == 2
    assert not telecamere[0].usa_oggetti
    registro = RegistroLocale(str(tmp_path / "registro.sqlite3"))
    backend = Backend(indirizzo_backend, "token-finto")
    elabora(telecamere, PercezioneFinta(), registro, backend, INIZIO)

    eventi = registro.tutti()
    tipi = []
    for evento in eventi:
        tipi.append(evento.tipo)
    assert tipi == ["alzata_notturna", "uscita"]
    alzata = eventi[0]
    assert alzata.inizio == INIZIO + datetime.timedelta(seconds=12)
    assert alzata.fine == INIZIO + datetime.timedelta(seconds=45)
    assert alzata.valori.stanze == ["bedroom"]
    uscita = eventi[1]
    assert uscita.inizio == INIZIO + datetime.timedelta(seconds=19.8)
    assert uscita.valori.zona_id == "porta-ingresso"
    assert registro.da_inviare(False) == []

    # l'uscita (urgente) parte da sola appena vista, l'alzata nel lotto finale
    richieste = BackendFinto.richieste
    assert len(richieste) == 2
    assert leggi_evento(richieste[0]["corpo"][0]).tipo == "uscita"
    assert len(richieste[0]["corpo"]) == 1
    assert leggi_evento(richieste[1]["corpo"][0]).tipo == "alzata_notturna"


def test_ora_di_inizio_nel_fuso_della_casa():
    assert ora_di_inizio("2026-12-01T08:00:00+01:00", ROMA) == datetime.datetime(2026, 12, 1, 8, 0, tzinfo=ROMA)
    # senza fuso: quello della casa
    assert ora_di_inizio("2026-12-01T08:00", ROMA).utcoffset() == datetime.timedelta(hours=1)
    # in UTC: riportata all'ora di Roma (serve per gli orari di notte)
    assert ora_di_inizio("2026-12-01T07:00:00+00:00", ROMA).hour == 8


def test_backend_dal_file_env(tmp_path, monkeypatch):
    # setenv + delenv: pytest ricorda che le variabili non c'erano e le toglie a fine test
    monkeypatch.setenv("TOKEN_CASA", "x")
    monkeypatch.delenv("TOKEN_CASA")
    monkeypatch.setenv("INDIRIZZO_BACKEND", "x")
    monkeypatch.delenv("INDIRIZZO_BACKEND")
    vuoto = tmp_path / "vuoto.env"
    vuoto.write_text("")
    assert leggi_backend(str(vuoto)) is None
    finto = tmp_path / "finto.env"
    finto.write_text("INDIRIZZO_BACKEND=http://127.0.0.1:8000/\nTOKEN_CASA=token-finto\n")
    backend = leggi_backend(str(finto))
    assert backend.indirizzo == "http://127.0.0.1:8000"
    assert backend.token == "token-finto"


def test_evento_nel_registro_e_json_dei_contratti(tmp_path, indirizzo_backend):  # noqa: F811
    # il corpo del POST è una lista JSON che il backend legge con i contratti
    telecamere = prepara_telecamere(configurazione(tmp_path), 5)
    registro = RegistroLocale(str(tmp_path / "registro.sqlite3"))
    elabora(telecamere, PercezioneFinta(), registro, None, INIZIO)
    assert BackendFinto.richieste == []  # senza backend niente rete
    assert len(registro.da_inviare(False)) == 2
    for evento in registro.tutti():
        testo = evento.model_dump_json()
        assert leggi_evento(json.loads(testo)) == evento


@pytest.mark.parametrize("fps", [2, 10])
def test_ore_dei_fotogrammi_seguono_il_video(tmp_path, fps):
    telecamere = prepara_telecamere(configurazione(tmp_path), fps)
    secondi = []
    while True:
        fotogramma = telecamere[1].sorgente.leggi()
        if fotogramma is None:
            break
        secondi.append(fotogramma.secondi)
    # il video dell'ingresso è a 5 fotogrammi al secondo: con fps più alti si prendono tutti
    if fps == 2:
        assert len(secondi) == 80
    else:
        assert len(secondi) == 200
