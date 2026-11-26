"""Report che il backend calcola dal registro unico e che la web app mostra (oggi, storico, trend, report)."""

import datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel

from contratti.eventi import QuantoMangiato

# in_attesa: la finestra della dose non è ancora finita e la presa non si è vista.
StatoDose = Literal["in_orario", "in_ritardo", "saltata", "in_attesa"]


class DoseFarmaco(BaseModel):
    farmaco_id: str
    nome: str
    orario_previsto: str
    stato: StatoDose
    ora_presa: AwareDatetime | None = None
    minuti_ritardo: int | None = None
    # False: gesto visto ma farmaco non riconosciuto dalle foto. None: dose non presa.
    farmaco_riconosciuto: bool | None = None


class PastoDelGiorno(BaseModel):
    ora: AwareDatetime
    cibi: list[str]
    quanto_mangiato: QuantoMangiato | None


class CambiamentoRoutine(BaseModel):
    """Cosa è cambiato nel periodo rispetto al solito (le 4 settimane prima), per il report (Marco, 25/11)."""

    # Che cosa: "sveglia", "acqua", "pasti", "sonno", "agitazione", "bagno", "uscite".
    cosa: str
    # Frase in inglese per la web app, es. "Wakes up about 1 hour later than usual".
    testo: str


class ReportGiornaliero(BaseModel):
    data: datetime.date
    acqua_ml: float
    obiettivo_acqua_ml: int
    bevute: int
    dosi: list[DoseFarmaco]
    pasti: list[PastoDelGiorno]
    alzate_notturne: int
    minuti_fuori_letto_notte: float
    # Sonno della notte che finisce la mattina di questo giorno (Marco, 25/11). None se non si è visto dormire.
    sonno_minuti: float | None = None
    addormentato_alle: AwareDatetime | None = None
    sveglio_alle: AwareDatetime | None = None
    # Funzioni dalla ricerca su Alzheimer e demenza (Marco, 25/11).
    agitazione_minuti: float = 0
    allarmi_inattivita: int = 0
    visite_bagno: int = 0
    visite_bagno_notte: int = 0
    cadute: int
    uscite: int
    uscite_in_orario_vietato: int
    simulato: bool = False


class RiassuntoGiorno(BaseModel):
    """Una riga per giorno nei report settimanali e mensili: serve anche ai grafici dei trend."""

    data: datetime.date
    acqua_ml: float
    dosi_previste: int
    dosi_in_orario: int
    dosi_in_ritardo: int
    dosi_saltate: int
    pasti: int
    # Pasti con meno di metà del piatto mangiato: il segnale che conta per la famiglia (Marco, 25/11).
    pasti_meno_di_meta: int
    alzate_notturne: int
    # Come nel report giornaliero: None se quella notte non si è visto dormire.
    sonno_minuti: float | None = None
    agitazione_minuti: float = 0
    visite_bagno: int = 0
    cadute: int
    uscite_in_orario_vietato: int
    simulato: bool = False


class ReportPeriodo(BaseModel):
    tipo: Literal["settimanale", "mensile"]
    dal: datetime.date
    al: datetime.date
    giorni: list[RiassuntoGiorno]
    acqua_media_ml: float
    # Dosi in orario + in ritardo sulle dosi già valutate (quelle "in_attesa" non contano), da 0 a 100.
    # None se nel periodo non c'è ancora nessuna dose valutata (la web app scrive "nessun dato").
    aderenza_farmaci_percentuale: float | None
    cadute: int
    uscite_in_orario_vietato: int
    alzate_notturne_medie: float
    # Media sulle notti in cui si è visto dormire; None se nessuna.
    sonno_medio_minuti: float | None = None
    cambiamenti: list[CambiamentoRoutine] = []
