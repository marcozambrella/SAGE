"""Configurazione di SAGE.

- Personalizzazione: quello che la famiglia imposta nella web app (D21), salvato solo nel suo browser (D29).
  Il backend riceve dal programma di casa solo quella della casa demo.
- ConfigurazioneCasa: il file locale del programma di casa, con le sorgenti e le zone delle telecamere.
  Gli indirizzi delle telecamere non passano mai dalla web app né dal server (D21).
"""

from typing import Literal

from pydantic import AwareDatetime, BaseModel

from contratti.eventi import TipoContenitore

TipoZona = Literal["porta", "letto", "tavolo", "portapillole"]
Analizzatore = Literal["caduta", "uscita", "bevuta", "farmaco", "pasto", "alzata_notturna"]


class FasciaOraria(BaseModel):
    # Ore locali della casa, "HH:MM". Se alle < dalle la fascia passa la mezzanotte (es. 22:00 → 07:00).
    dalle: str
    alle: str


class Anziano(BaseModel):
    nome: str
    anno_nascita: int | None = None
    obiettivo_acqua_ml: int = 1500
    note: str = ""


class Farmaco(BaseModel):
    id: str
    nome: str
    # Testo libero mostrato nei report, es. "1 tablet".
    dose: str
    # Orari previsti, "HH:MM".
    orari: list[str]
    # Entro questa finestra la dose è "in orario", dopo "in ritardo"; finita la finestra senza presa è "saltata".
    tolleranza_minuti: int = 30
    # Foto di scatola/blister caricate dall'app: servono a riconoscere il farmaco (D15).
    foto_ids: list[str] = []


class Contenitore(BaseModel):
    id: str
    nome: str
    tipo: TipoContenitore
    capienza_ml: int


class TelecameraPrevista(BaseModel):
    """Telecamera come la vede la web app demo: solo nome e stanza, nessun indirizzo (D21)."""

    id: str
    nome: str
    stanza: str


class RegoleAllarmi(BaseModel):
    orari_uscita_vietati: list[FasciaOraria] = []
    orari_notte: FasciaOraria = FasciaOraria(dalle="22:00", alle="07:00")
    # Spento dalla web app o da Telegram (D16).
    allarme_uscita_attivo: bool = True
    # Pausa dell'allarme uscita per N ore: fino a quando.
    pausa_fino_a: AwareDatetime | None = None


class Personalizzazione(BaseModel):
    anziano: Anziano
    farmaci: list[Farmaco] = []
    contenitori: list[Contenitore] = []
    telecamere: list[TelecameraPrevista] = []
    regole: RegoleAllarmi = RegoleAllarmi()
    # I giorni dei report si contano in questo fuso orario.
    fuso_orario: str = "Europe/Rome"


class Zona(BaseModel):
    id: str
    tipo: TipoZona
    # Poligono con coordinate da 0 a 1 rispetto al fotogramma: [[x, y], [x, y], ...].
    punti: list[list[float]]


class TelecameraLocale(BaseModel):
    """Telecamera nel file del programma di casa."""

    id: str
    nome: str
    stanza: str
    # Indirizzo RTSP, numero della webcam ("0") o percorso di un file video (video registrati della demo, D6).
    sorgente: str
    analizzatori: list[Analizzatore]
    zone: list[Zona] = []


class ConfigurazioneCasa(BaseModel):
    telecamere: list[TelecameraLocale]
    personalizzazione: Personalizzazione
    # Cartella con le foto dei farmaci, un file <foto_id>.jpg per foto.
    cartella_foto_farmaci: str
