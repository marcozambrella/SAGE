"""Regole che calcola il backend e non il programma di casa (contratti/API.md): fasce orarie, stato delle dosi,
uscite in orario vietato, alzate di notte, ore di sonno.

Logica pura: niente database e niente orologio, l'ora attuale ("adesso") arriva come parametro.
Gli orari della personalizzazione ("HH:MM") sono ore locali della casa, nel suo fuso_orario.
"""

import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from contratti.configurazione import Farmaco, FasciaOraria, Personalizzazione
from contratti.eventi import EventoAlzataNotturna, EventoBase, EventoFarmaco, EventoUscita
from contratti.report import DoseFarmaco

# Lo stesso valore predefinito di Personalizzazione.fuso_orario: serve solo se la casa non è ancora configurata.
FUSO_ORARIO_PREDEFINITO = "Europe/Rome"

# Finestra delle dosi (D38): "in_orario" da un'ora prima fino a tolleranza_minuti dopo l'orario, "in_ritardo" fino
# a 2 ore dopo l'orario, poi "saltata" con promemoria. Contare chi anticipa evita il promemoria sbagliato (e la
# doppia dose).
MINUTI_ANTICIPO_MASSIMO = 60
MINUTI_RITARDO_MASSIMO = 120

# Ore di sonno (API.md, Marco 25/11): contano i pezzi di sonno che iniziano da 2 ore prima dell'inizio degli orari di
# notte fino a 4 ore dopo la fine, per chi va a letto presto o dorme fino a tardi.
ORE_PRIMA_DELLA_NOTTE = 2
ORE_DOPO_LA_NOTTE = 4


def inizio_evento(evento: EventoBase) -> datetime.datetime:
    """Chiave per mettere gli eventi in ordine di inizio."""
    return evento.inizio


def leggi_ora(testo: str) -> datetime.time:
    """Da "HH:MM" all'ora del giorno; ValueError se il testo non è un'ora."""
    return datetime.datetime.strptime(testo, "%H:%M").time()


def ora_locale(momento: datetime.datetime, fuso_orario: str) -> datetime.time:
    """L'ora del giorno di un momento, nel fuso orario della casa."""
    return momento.astimezone(ZoneInfo(fuso_orario)).time()


def giorno_locale(momento: datetime.datetime, fuso_orario: str) -> datetime.date:
    """Il giorno di un momento, nel fuso orario della casa: i giorni dei report si contano così (API.md)."""
    return momento.astimezone(ZoneInfo(fuso_orario)).date()


def ora_nella_fascia(ora: datetime.time, fascia: FasciaOraria) -> bool:
    """True se l'ora locale è nella fascia: "dalle" compresa, "alle" esclusa."""
    dalle = leggi_ora(fascia.dalle)
    alle = leggi_ora(fascia.alle)
    if dalle <= alle:
        return dalle <= ora < alle
    # la fascia passa la mezzanotte (es. 22:00 → 07:00): da "dalle" a mezzanotte oppure da mezzanotte ad "alle"
    return ora >= dalle or ora < alle


def uscita_in_orario_vietato(evento: EventoUscita, personalizzazione: Personalizzazione) -> bool:
    """Conta l'inizio dell'uscita (API.md, D16)."""
    ora = ora_locale(evento.inizio, personalizzazione.fuso_orario)
    for fascia in personalizzazione.regole.orari_uscita_vietati:
        if ora_nella_fascia(ora, fascia):
            return True
    return False


def alzata_di_notte(evento: EventoAlzataNotturna, personalizzazione: Personalizzazione) -> bool:
    """Le alzate contano solo se iniziano negli orari di notte (API.md)."""
    ora = ora_locale(evento.inizio, personalizzazione.fuso_orario)
    return ora_nella_fascia(ora, personalizzazione.regole.orari_notte)


def finestra_del_sonno(
    data: datetime.date, personalizzazione: Personalizzazione
) -> tuple[datetime.datetime, datetime.datetime]:
    """Inizio (compreso) e fine (esclusa) della finestra in cui comincia il sonno della notte che finisce la mattina
    di `data`: quel sonno conta nel report di `data` (API.md, "Ore di sonno")."""
    fuso = ZoneInfo(personalizzazione.fuso_orario)
    dalle = leggi_ora(personalizzazione.regole.orari_notte.dalle)
    alle = leggi_ora(personalizzazione.regole.orari_notte.alle)
    # di solito la notte passa la mezzanotte e comincia il giorno prima (22:00 → 07:00); se no è tutta in `data`
    giorno_di_inizio = data - datetime.timedelta(days=1)
    if dalle < alle:
        giorno_di_inizio = data
    inizio_notte = datetime.datetime.combine(giorno_di_inizio, dalle, tzinfo=fuso)
    fine_notte = datetime.datetime.combine(data, alle, tzinfo=fuso)
    inizio = inizio_notte - datetime.timedelta(hours=ORE_PRIMA_DELLA_NOTTE)
    fine = fine_notte + datetime.timedelta(hours=ORE_DOPO_LA_NOTTE)
    return inizio, fine


def con_regole_del_backend(evento: EventoBase, personalizzazione: Personalizzazione | None) -> EventoBase:
    """I valori che scrive il backend (API.md, "Regole che calcola il backend"):
    - bevuta: se contenitore_id è nella personalizzazione, ml = percentuale / 100 × capienza di quel contenitore
      (la percentuale vale anche se il contenitore è più vicino o più lontano); altrimenti restano i ml mandati;
    - uscita: in_orario_vietato secondo gli orari vietati (D16).
    Senza personalizzazione l'evento resta com'è."""
    if personalizzazione is None:
        return evento
    if evento.tipo == "bevuta":
        for contenitore in personalizzazione.contenitori:
            if contenitore.id == evento.valori.contenitore_id:
                ml = round(evento.valori.percentuale / 100 * contenitore.capienza_ml, 1)
                modifiche = {"capienza_ml": float(contenitore.capienza_ml), "ml": ml}
                valori = evento.valori.model_copy(update=modifiche)
                return evento.model_copy(update={"valori": valori})
        return evento
    if evento.tipo == "uscita":
        vietato = uscita_in_orario_vietato(evento, personalizzazione)
        valori = evento.valori.model_copy(update={"in_orario_vietato": vietato})
        return evento.model_copy(update={"valori": valori})
    return evento


def errore_nella_personalizzazione(personalizzazione: Personalizzazione) -> str | None:
    """Gli orari "HH:MM" li controllano già i contratti; il fuso orario è testo libero: qui si controlla che il
    backend lo sappia leggere, così l'errore arriva subito al programma di casa invece di rompere i report."""
    try:
        ZoneInfo(personalizzazione.fuso_orario)
    except (ZoneInfoNotFoundError, ValueError):
        return "Unknown time zone: " + personalizzazione.fuso_orario
    return None


def orario_della_dose(dose: tuple[str, Farmaco]) -> datetime.time:
    """Chiave per mettere le dosi (orario, farmaco) in ordine di orario."""
    return leggi_ora(dose[0])


def dosi_previste(personalizzazione: Personalizzazione) -> list[tuple[str, Farmaco]]:
    """Tutte le dosi di un giorno come coppie (orario "HH:MM", farmaco), in ordine di orario."""
    dosi = []
    for farmaco in personalizzazione.farmaci:
        for orario in farmaco.orari:
            dosi.append((orario, farmaco))
    dosi.sort(key=orario_della_dose)
    return dosi


def fine_della_finestra(data: datetime.date, orario: str, farmaco: Farmaco, fuso_orario: str) -> datetime.datetime:
    """Dopo questo momento una dose senza presa è "saltata". Se la tolleranza è più lunga di 2 ore vale la tolleranza,
    altrimenti una presa "in orario" non potrebbe mai esserci."""
    previsto = datetime.datetime.combine(data, leggi_ora(orario), tzinfo=ZoneInfo(fuso_orario))
    minuti = max(MINUTI_RITARDO_MASSIMO, farmaco.tolleranza_minuti)
    return previsto + datetime.timedelta(minutes=minuti)


def cerca_presa(
    eventi_farmaco: list[EventoFarmaco],
    farmaco_id: str,
    dal: datetime.datetime,
    al: datetime.datetime,
    prese_usate: set[str],
) -> EventoFarmaco | None:
    """La prima presa non ancora usata con inizio tra dal e al (compresi). Prima si cerca il farmaco riconosciuto;
    se non c'è, va bene una presa con farmaco non riconosciuto (gesto visto, scatola non riconosciuta, D15)."""
    non_riconosciuta = None
    for evento in eventi_farmaco:
        if evento.id in prese_usate:
            continue
        if evento.inizio < dal or evento.inizio > al:
            continue
        if evento.valori.farmaco_id == farmaco_id:
            return evento
        if evento.valori.farmaco_id is None and non_riconosciuta is None:
            non_riconosciuta = evento
    return non_riconosciuta


def stato_delle_dosi(
    data: datetime.date,
    personalizzazione: Personalizzazione,
    eventi_farmaco: list[EventoFarmaco],
    adesso: datetime.datetime,
) -> list[DoseFarmaco]:
    """Lo stato di ogni dose prevista nel giorno `data` (API.md, D15).

    eventi_farmaco in ordine di inizio, anche del giorno prima e dopo: una dose delle 23:30 si può prendere dopo
    mezzanotte. Ogni presa conta per una sola dose; le dosi si guardano in ordine di orario.
    """
    fuso = ZoneInfo(personalizzazione.fuso_orario)
    prese_usate = set()
    dosi = []
    for orario, farmaco in dosi_previste(personalizzazione):
        previsto = datetime.datetime.combine(data, leggi_ora(orario), tzinfo=fuso)
        tolleranza = datetime.timedelta(minutes=farmaco.tolleranza_minuti)
        inizio_finestra = previsto - datetime.timedelta(minutes=MINUTI_ANTICIPO_MASSIMO)
        fine_finestra = fine_della_finestra(data, orario, farmaco, personalizzazione.fuso_orario)
        presa = cerca_presa(eventi_farmaco, farmaco.id, inizio_finestra, fine_finestra, prese_usate)

        if presa is None:
            if adesso > fine_finestra:
                stato = "saltata"
            else:
                stato = "in_attesa"
            dose = DoseFarmaco(farmaco_id=farmaco.id, nome=farmaco.nome, orario_previsto=orario, stato=stato)
            dosi.append(dose)
            continue

        prese_usate.add(presa.id)
        riconosciuto = presa.valori.farmaco_id is not None
        if presa.inizio <= previsto + tolleranza:
            dose = DoseFarmaco(
                farmaco_id=farmaco.id,
                nome=farmaco.nome,
                orario_previsto=orario,
                stato="in_orario",
                ora_presa=presa.inizio,
                farmaco_riconosciuto=riconosciuto,
            )
        else:
            minuti_ritardo = int((presa.inizio - previsto).total_seconds() // 60)
            dose = DoseFarmaco(
                farmaco_id=farmaco.id,
                nome=farmaco.nome,
                orario_previsto=orario,
                stato="in_ritardo",
                ora_presa=presa.inizio,
                minuti_ritardo=minuti_ritardo,
                farmaco_riconosciuto=riconosciuto,
            )
        dosi.append(dose)
    return dosi
