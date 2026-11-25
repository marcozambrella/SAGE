"""Formato unico degli eventi di SAGE (registro unico, D3).

Gli analizzatori del programma di casa producono eventi in questo formato, l'unione toglie i doppioni tra telecamere,
il backend li riceve e da qui calcola report e allarmi. Ogni tipo di evento ha i suoi "valori".
"""

from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, Field, TypeAdapter

TipoContenitore = Literal["bicchiere", "bottiglia", "tazza"]

# Quanto del piatto è stato mangiato, in tre categorie: la percentuale dal modello del piatto non è abbastanza precisa
# per un numero (Marco, 25/11). La arrotonda il programma di casa.
QuantoMangiato = Literal["meno_di_meta", "meta", "tutto"]

# Questi tipi fanno partire subito l'allarme Telegram (D10, D16); gli altri vanno solo nel registro e nei report.
TIPI_URGENTI = ["caduta", "uscita"]


class Fonte(BaseModel):
    """Un evento grezzo da cui viene l'evento unito: quale telecamera e quale analizzatore l'ha visto."""

    telecamera_id: str
    analizzatore: str
    confidenza: float = Field(ge=0, le=1)


class EventoBase(BaseModel):
    """Campi comuni a tutti gli eventi."""

    # Scelto dal programma di casa (uuid): se un evento viene rimandato, il backend non lo duplica.
    id: str
    # Sempre con il fuso orario (es. 2026-12-01T08:05:00+01:00).
    inizio: AwareDatetime
    # None se l'evento è istantaneo o ancora in corso.
    fine: AwareDatetime | None = None
    stanza: str
    confidenza: float = Field(ge=0, le=1)
    # Le telecamere e gli analizzatori che hanno visto l'evento: più di una se l'unione ha fuso dei doppioni.
    fonti: list[Fonte]
    # Fotogramma di prova, JPEG piccolo in base64 (allarmi Telegram e storico).
    foto_prova: str | None = None
    # Lo mette il backend: True se l'evento ha una foto di prova (nelle liste foto_prova è sempre None).
    ha_foto: bool = False
    # True solo per lo storico simulato della casa demo (D22): la web app lo segnala come simulato.
    simulato: bool = False


class ValoriCaduta(BaseModel):
    # Secondi passati a terra, se si sa (None se non si è ancora rialzato).
    secondi_a_terra: float | None = None


class ValoriUscita(BaseModel):
    # La zona "porta" dove la persona apre il portone ed esce (Marco, 24/11).
    zona_id: str
    # Lo mette il backend con le regole degli allarmi (D16): None finché non l'ha valutato.
    in_orario_vietato: bool | None = None


class ValoriBevuta(BaseModel):
    """Calcolo dei ml dalla percentuale di altezza (D9): ml = livello_sceso_px / altezza_contenitore_px × capienza."""

    contenitore: TipoContenitore
    # Il contenitore della personalizzazione, se il programma di casa l'ha riconosciuto: il backend ricalcola i ml
    # con la sua capienza (Marco, 24/11).
    contenitore_id: str | None = None
    capienza_ml: float
    altezza_contenitore_px: float
    livello_sceso_px: float
    # livello_sceso_px / altezza_contenitore_px × 100
    percentuale: float
    # percentuale / 100 × capienza_ml
    ml: float
    # False se il livello non si vedeva (tazza opaca, poco contrasto): ml = 0 vuol dire "non misurato", non
    # "non ha bevuto" (24/11).
    livello_visibile: bool = True


class ValoriFarmaco(BaseModel):
    """Presa di un farmaco (D15). Se è in orario lo decide il backend confrontando con il piano dell'app."""

    # None se il farmaco non è stato riconosciuto dalle foto di scatola/blister caricate nell'app.
    farmaco_id: str | None
    # Somiglianza con le foto del farmaco riconosciuto (0-1).
    somiglianza: float | None = None
    portapillole_aperto: bool
    mano_alla_bocca: bool


class ValoriPasto(BaseModel):
    # Cosa c'era nel piatto (dal modello visione+linguaggio, una foto a pasto, D14).
    cibi: list[str]
    # Confrontando il piatto prima e dopo. None se non si è potuto misurare (piatto coperto, poco cibo all'inizio).
    quanto_mangiato: QuantoMangiato | None


class ValoriAlzataNotturna(BaseModel):
    """Alzata dal letto negli orari di notte: inizio = esce dalla zona letto, fine = ci torna."""

    # Stanze attraversate prima di tornare a letto (dall'unione tra telecamere).
    stanze: list[str]


class ValoriSonno(BaseModel):
    """Sonno a letto (Marco, 25/11): inizio = si addormenta (sdraiato nella zona letto e quasi fermo), fine = si sveglia
    (si siede, si alza o si muove a lungo). Una notte può avere più pezzi: le ore di sonno le somma il backend."""

    # La zona "letto" dove dorme.
    zona_id: str


class EventoCaduta(EventoBase):
    tipo: Literal["caduta"]
    valori: ValoriCaduta


class EventoUscita(EventoBase):
    tipo: Literal["uscita"]
    valori: ValoriUscita


class EventoBevuta(EventoBase):
    tipo: Literal["bevuta"]
    valori: ValoriBevuta


class EventoFarmaco(EventoBase):
    tipo: Literal["farmaco"]
    valori: ValoriFarmaco


class EventoPasto(EventoBase):
    tipo: Literal["pasto"]
    valori: ValoriPasto


class EventoAlzataNotturna(EventoBase):
    tipo: Literal["alzata_notturna"]
    valori: ValoriAlzataNotturna


class EventoSonno(EventoBase):
    tipo: Literal["sonno"]
    valori: ValoriSonno


# Un evento è uno di questi tipi: il campo "tipo" dice quale (e quindi che "valori" aspettarsi).
Evento = Annotated[
    EventoCaduta | EventoUscita | EventoBevuta | EventoFarmaco | EventoPasto | EventoAlzataNotturna | EventoSonno,
    Field(discriminator="tipo"),
]

LETTORE_EVENTO = TypeAdapter(Evento)


def leggi_evento(dati: dict) -> EventoBase:
    """Trasforma un dizionario (per esempio letto da JSON) nell'evento del tipo giusto, controllando i campi."""
    return LETTORE_EVENTO.validate_python(dati)
