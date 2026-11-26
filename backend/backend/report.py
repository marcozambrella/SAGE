"""Calcolo dei report (modelli in contratti/report.py) dagli eventi della casa e dalla personalizzazione.

Logica pura come regole.py: gli eventi arrivano già letti dal database, l'ora attuale come parametro.
"""

import calendar
import datetime
from typing import Literal
from zoneinfo import ZoneInfo

from contratti.configurazione import Personalizzazione
from contratti.eventi import EventoBase
from contratti.report import CambiamentoRoutine, PastoDelGiorno, ReportGiornaliero, ReportPeriodo, RiassuntoGiorno

from backend.regole import (
    alzata_di_notte,
    finestra_del_sonno,
    giorno_locale,
    inizio_evento,
    ora_locale,
    ora_nella_fascia,
    stato_delle_dosi,
    uscita_in_orario_vietato,
)

# Cambi di routine (API.md, Marco 25/11): il periodo si confronta con le 4 settimane prima. Contano solo i giorni già
# finiti e con almeno un evento (un giorno senza eventi è una casa spenta, non un giorno a zero). Per sapere com'è "di
# solito" servono almeno due settimane di giorni prima (con una sola il caso pesa troppo); nel periodo bastano 3 giorni.
SETTIMANE_DI_CONFRONTO = 4
MINIMO_GIORNI_DI_PRIMA = 14
MINIMO_GIORNI_DEL_PERIODO = 3
# Soglie (PROPOSTE da confermare con Marco): una differenza tra le medie più piccola non è un cambiamento vero. Sono
# poco sopra la differenza più grande di 99 settimane normali su 100 nello storico simulato (60 semi): sveglia 52
# minuti, sonno 32 minuti, acqua 333 ml, pasti 0.63, agitazione 9 minuti, bagno 1.7 al giorno e 0.84 a notte,
# uscite 1.1 al giorno.
SOGLIA_SVEGLIA_MINUTI = 60
SOGLIA_SONNO_MINUTI = 40
SOGLIA_ACQUA_ML = 300
SOGLIA_ACQUA_PERCENTUALE = 25
SOGLIA_PASTI_AL_GIORNO = 0.7
SOGLIA_AGITAZIONE_MINUTI = 10
SOGLIA_AGITAZIONE_PERCENTUALE = 50
SOGLIA_BAGNO_AL_GIORNO = 1.75
SOGLIA_BAGNO_DI_NOTTE = 0.9
SOGLIA_USCITE_AL_GIORNO = 1.25


def calcola_report_giornaliero(
    data: datetime.date,
    eventi: list[EventoBase],
    personalizzazione: Personalizzazione,
    adesso: datetime.datetime,
) -> ReportGiornaliero:
    """Il report del giorno `data`, contato nel fuso orario della casa (API.md).

    `eventi` può contenere anche eventi del giorno prima e dopo: servono alle dosi vicine alla mezzanotte e al sonno
    iniziato la sera prima, mentre tutto il resto conta solo gli eventi che iniziano nel giorno.
    """
    eventi_in_ordine = sorted(eventi, key=inizio_evento)
    acqua_ml = 0.0
    bevute = 0
    pasti = []
    alzate_notturne = 0
    minuti_fuori_letto_notte = 0.0
    cadute = 0
    uscite = 0
    uscite_in_orario_vietato = 0
    agitazione_minuti = 0.0
    allarmi_inattivita = 0
    visite_bagno = 0
    visite_bagno_notte = 0
    simulato = False
    eventi_farmaco = []
    pezzi_di_sonno = []
    inizio_finestra_sonno, fine_finestra_sonno = finestra_del_sonno(data, personalizzazione)

    for evento in eventi_in_ordine:
        if evento.tipo == "farmaco":
            eventi_farmaco.append(evento)
        # il sonno conta nel giorno in cui finisce la notte, anche se è iniziato la sera prima (API.md)
        if evento.tipo == "sonno":
            dentro = inizio_finestra_sonno <= evento.inizio < fine_finestra_sonno
            # un pezzo ancora in corso (fine None) non ha ancora una durata: non conta, come i minuti delle alzate
            if dentro and evento.fine is not None:
                pezzi_di_sonno.append(evento)
            continue
        if giorno_locale(evento.inizio, personalizzazione.fuso_orario) != data:
            continue
        # il giorno è segnato come simulato se contiene eventi dello storico simulato (D22)
        if evento.simulato:
            simulato = True

        if evento.tipo == "bevuta":
            acqua_ml = acqua_ml + evento.valori.ml
            bevute = bevute + 1
        elif evento.tipo == "pasto":
            pasto = PastoDelGiorno(
                ora=evento.inizio,
                cibi=evento.valori.cibi,
                quanto_mangiato=evento.valori.quanto_mangiato,
            )
            pasti.append(pasto)
        elif evento.tipo == "alzata_notturna":
            if alzata_di_notte(evento, personalizzazione):
                alzate_notturne = alzate_notturne + 1
                # un'alzata ancora in corso (fine None) non ha ancora una durata
                if evento.fine is not None:
                    minuti = (evento.fine - evento.inizio).total_seconds() / 60
                    minuti_fuori_letto_notte = minuti_fuori_letto_notte + minuti
        elif evento.tipo == "caduta":
            cadute = cadute + 1
        elif evento.tipo == "uscita":
            uscite = uscite + 1
            if uscita_in_orario_vietato(evento, personalizzazione):
                uscite_in_orario_vietato = uscite_in_orario_vietato + 1
        # funzioni dalla ricerca su Alzheimer e demenza (API.md)
        elif evento.tipo == "agitazione":
            # come le alzate: un episodio ancora in corso non ha ancora una durata
            if evento.fine is not None:
                minuti = (evento.fine - evento.inizio).total_seconds() / 60
                agitazione_minuti = agitazione_minuti + minuti
        elif evento.tipo == "inattivita":
            allarmi_inattivita = allarmi_inattivita + 1
        elif evento.tipo == "visita_bagno":
            visite_bagno = visite_bagno + 1
            ora = ora_locale(evento.inizio, personalizzazione.fuso_orario)
            if ora_nella_fascia(ora, personalizzazione.regole.orari_notte):
                visite_bagno_notte = visite_bagno_notte + 1

    # None se non si è visto dormire; le alzate sono i buchi tra un pezzo e l'altro e non si contano nel sonno
    sonno_minuti = None
    addormentato_alle = None
    sveglio_alle = None
    if len(pezzi_di_sonno) > 0:
        sonno_minuti = 0.0
        addormentato_alle = pezzi_di_sonno[0].inizio
        sveglio_alle = pezzi_di_sonno[0].fine
        for pezzo in pezzi_di_sonno:
            minuti = (pezzo.fine - pezzo.inizio).total_seconds() / 60
            sonno_minuti = sonno_minuti + minuti
            sveglio_alle = max(sveglio_alle, pezzo.fine)
            if pezzo.simulato:
                simulato = True
        sonno_minuti = round(sonno_minuti, 1)

    dosi = stato_delle_dosi(data, personalizzazione, eventi_farmaco, adesso)
    return ReportGiornaliero(
        data=data,
        acqua_ml=round(acqua_ml, 1),
        obiettivo_acqua_ml=personalizzazione.anziano.obiettivo_acqua_ml,
        bevute=bevute,
        dosi=dosi,
        pasti=pasti,
        alzate_notturne=alzate_notturne,
        minuti_fuori_letto_notte=round(minuti_fuori_letto_notte, 1),
        sonno_minuti=sonno_minuti,
        addormentato_alle=addormentato_alle,
        sveglio_alle=sveglio_alle,
        agitazione_minuti=round(agitazione_minuti, 1),
        allarmi_inattivita=allarmi_inattivita,
        visite_bagno=visite_bagno,
        visite_bagno_notte=visite_bagno_notte,
        cadute=cadute,
        uscite=uscite,
        uscite_in_orario_vietato=uscite_in_orario_vietato,
        simulato=simulato,
    )


def riassunto_del_giorno(report: ReportGiornaliero) -> RiassuntoGiorno:
    """La riga di un giorno nei report di periodo e nei grafici dei trend."""
    in_orario = 0
    in_ritardo = 0
    saltate = 0
    for dose in report.dosi:
        if dose.stato == "in_orario":
            in_orario = in_orario + 1
        elif dose.stato == "in_ritardo":
            in_ritardo = in_ritardo + 1
        elif dose.stato == "saltata":
            saltate = saltate + 1

    # il segnale che conta per la famiglia: i pasti lasciati quasi interi (API.md, "Quanto ha mangiato")
    pasti_meno_di_meta = 0
    for pasto in report.pasti:
        if pasto.quanto_mangiato == "meno_di_meta":
            pasti_meno_di_meta = pasti_meno_di_meta + 1

    return RiassuntoGiorno(
        data=report.data,
        acqua_ml=report.acqua_ml,
        dosi_previste=len(report.dosi),
        dosi_in_orario=in_orario,
        dosi_in_ritardo=in_ritardo,
        dosi_saltate=saltate,
        pasti=len(report.pasti),
        pasti_meno_di_meta=pasti_meno_di_meta,
        alzate_notturne=report.alzate_notturne,
        sonno_minuti=report.sonno_minuti,
        agitazione_minuti=report.agitazione_minuti,
        visite_bagno=report.visite_bagno,
        cadute=report.cadute,
        uscite_in_orario_vietato=report.uscite_in_orario_vietato,
        simulato=report.simulato,
    )


def calcola_report_periodo(
    tipo: Literal["settimanale", "mensile"],
    dal: datetime.date,
    al: datetime.date,
    eventi: list[EventoBase],
    personalizzazione: Personalizzazione,
    adesso: datetime.datetime,
) -> ReportPeriodo:
    """Il report dei giorni da `dal` ad `al` compresi.

    I giorni che non sono ancora cominciati non hanno una riga (nei trend sembrerebbero giorni a zero); le medie
    sono sui giorni con una riga, oggi compreso. Per i cambi di routine `eventi` deve avere anche le
    SETTIMANE_DI_CONFRONTO settimane prima di `dal`.
    """
    oggi = giorno_locale(adesso, personalizzazione.fuso_orario)
    report_dei_giorni = []
    giorni = []
    data = dal
    while data <= al and data <= oggi:
        report = calcola_report_giornaliero(data, eventi, personalizzazione, adesso)
        report_dei_giorni.append(report)
        giorni.append(riassunto_del_giorno(report))
        data = data + datetime.timedelta(days=1)

    acqua_totale = 0.0
    alzate_totali = 0
    cadute = 0
    uscite_in_orario_vietato = 0
    dosi_prese = 0
    dosi_saltate = 0
    sonno_totale = 0.0
    notti_con_sonno = 0
    for giorno in giorni:
        acqua_totale = acqua_totale + giorno.acqua_ml
        alzate_totali = alzate_totali + giorno.alzate_notturne
        cadute = cadute + giorno.cadute
        uscite_in_orario_vietato = uscite_in_orario_vietato + giorno.uscite_in_orario_vietato
        dosi_prese = dosi_prese + giorno.dosi_in_orario + giorno.dosi_in_ritardo
        dosi_saltate = dosi_saltate + giorno.dosi_saltate
        if giorno.sonno_minuti is not None:
            sonno_totale = sonno_totale + giorno.sonno_minuti
            notti_con_sonno = notti_con_sonno + 1

    acqua_media_ml = 0.0
    alzate_notturne_medie = 0.0
    if len(giorni) > 0:
        acqua_media_ml = round(acqua_totale / len(giorni), 1)
        alzate_notturne_medie = round(alzate_totali / len(giorni), 2)

    # le dosi ancora in attesa non contano: non sono né prese né saltate; None se non c'è niente da valutare
    aderenza = None
    dosi_valutate = dosi_prese + dosi_saltate
    if dosi_valutate > 0:
        aderenza = round(dosi_prese / dosi_valutate * 100, 1)

    # media sulle sole notti in cui si è visto dormire: una notte senza dati non è una notte in bianco
    sonno_medio_minuti = None
    if notti_con_sonno > 0:
        sonno_medio_minuti = round(sonno_totale / notti_con_sonno, 1)

    return ReportPeriodo(
        tipo=tipo,
        dal=dal,
        al=al,
        giorni=giorni,
        acqua_media_ml=acqua_media_ml,
        aderenza_farmaci_percentuale=aderenza,
        cadute=cadute,
        uscite_in_orario_vietato=uscite_in_orario_vietato,
        alzate_notturne_medie=alzate_notturne_medie,
        sonno_medio_minuti=sonno_medio_minuti,
        cambiamenti=cambiamenti_di_routine(dal, report_dei_giorni, eventi, personalizzazione, adesso),
    )


def giorni_da_confrontare(
    report_dei_giorni: list[ReportGiornaliero], eventi: list[EventoBase], fuso_orario: str, oggi: datetime.date
) -> list[ReportGiornaliero]:
    """I giorni già finiti e con almeno un evento: oggi è ancora a metà, un giorno senza eventi è una casa spenta."""
    giorni_con_eventi = set()
    for evento in eventi:
        momento = evento.inizio
        # il sonno è del giorno in cui finisce la notte: la sera prima, da solo, sembrerebbe un giorno senza acqua
        if evento.tipo == "sonno" and evento.fine is not None:
            momento = evento.fine
        giorni_con_eventi.add(giorno_locale(momento, fuso_orario))
    scelti = []
    for report in report_dei_giorni:
        if report.data < oggi and report.data in giorni_con_eventi:
            scelti.append(report)
    return scelti


def media(valori: list[float], minimo: int) -> float | None:
    """None se i valori sono meno di `minimo`: troppo pochi per un confronto."""
    if len(valori) < minimo:
        return None
    return sum(valori) / len(valori)


def cambiato(prima: float | None, dopo: float | None, soglia: float, soglia_percentuale: float) -> bool:
    """True se la media è cambiata almeno della soglia e, quando prima non era zero, della soglia percentuale."""
    if prima is None or dopo is None:
        return False
    differenza = abs(dopo - prima)
    if differenza < soglia:
        return False
    if prima > 0 and differenza / prima * 100 < soglia_percentuale:
        return False
    return True


def un_decimale(valore: float) -> str:
    """1.0 → "1", 0.34 → "0.3": per le frasi dei cambiamenti."""
    arrotondato = round(valore, 1)
    if arrotondato == int(arrotondato):
        return str(int(arrotondato))
    return str(arrotondato)


def quanti(valore: float, singolare: str, plurale: str) -> str:
    """1 → "1 meal", 1.3 → "1.3 meals"."""
    testo = un_decimale(valore)
    if testo == "1":
        return "1 " + singolare
    return testo + " " + plurale


def durata_in_parole(minuti: float) -> str:
    """45 → "45 minutes", 70 → "1 hour", 100 → "1.5 hours"."""
    if minuti < 55:
        return str(round(minuti / 5) * 5) + " minutes"
    ore = round(minuti / 30) / 2
    if ore == 1:
        return "1 hour"
    return un_decimale(ore) + " hours"


def ora_in_parole(minuti_dalla_mezzanotte: float) -> str:
    """405 → "06:45"."""
    minuti = round(minuti_dalla_mezzanotte)
    ora = datetime.time((minuti // 60) % 24, minuti % 60)
    return ora.strftime("%H:%M")


def piu_o_meno(prima: float, dopo: float) -> str:
    if dopo > prima:
        return "more"
    return "less"


def medie_dei_giorni(
    report_dei_giorni: list[ReportGiornaliero], fuso_orario: str, minimo: int
) -> dict[str, float | None]:
    """Le medie al giorno (o a notte) di quello che si confronta; None dove i giorni sono meno di `minimo`."""
    sveglia = []
    sonno = []
    acqua = []
    pasti = []
    agitazione = []
    bagno = []
    bagno_di_notte = []
    uscite = []
    for report in report_dei_giorni:
        # sveglia e sonno solo nelle notti in cui si è visto dormire
        if report.sveglio_alle is not None:
            ora = ora_locale(report.sveglio_alle, fuso_orario)
            sveglia.append(ora.hour * 60 + ora.minute)
        if report.sonno_minuti is not None:
            sonno.append(report.sonno_minuti)
        acqua.append(report.acqua_ml)
        pasti_meno_di_meta = 0
        for pasto in report.pasti:
            if pasto.quanto_mangiato == "meno_di_meta":
                pasti_meno_di_meta = pasti_meno_di_meta + 1
        pasti.append(pasti_meno_di_meta)
        agitazione.append(report.agitazione_minuti)
        bagno.append(report.visite_bagno)
        bagno_di_notte.append(report.visite_bagno_notte)
        uscite.append(report.uscite)
    return {
        "sveglia": media(sveglia, minimo),
        "sonno": media(sonno, minimo),
        "acqua": media(acqua, minimo),
        "pasti": media(pasti, minimo),
        "agitazione": media(agitazione, minimo),
        "bagno": media(bagno, minimo),
        "bagno_di_notte": media(bagno_di_notte, minimo),
        "uscite": media(uscite, minimo),
    }


def cambiamenti_di_routine(
    dal: datetime.date,
    report_del_periodo: list[ReportGiornaliero],
    eventi: list[EventoBase],
    personalizzazione: Personalizzazione,
    adesso: datetime.datetime,
) -> list[CambiamentoRoutine]:
    """Quello che è cambiato davvero nel periodo rispetto alle SETTIMANE_DI_CONFRONTO settimane prima di `dal`, con
    una frase in inglese per la web app (API.md, "Cambi di routine")."""
    fuso_orario = personalizzazione.fuso_orario
    oggi = giorno_locale(adesso, fuso_orario)
    report_di_prima = []
    data = dal - datetime.timedelta(weeks=SETTIMANE_DI_CONFRONTO)
    while data < dal:
        report_di_prima.append(calcola_report_giornaliero(data, eventi, personalizzazione, adesso))
        data = data + datetime.timedelta(days=1)
    giorni_di_prima = giorni_da_confrontare(report_di_prima, eventi, fuso_orario, oggi)
    giorni_di_adesso = giorni_da_confrontare(report_del_periodo, eventi, fuso_orario, oggi)
    prima = medie_dei_giorni(giorni_di_prima, fuso_orario, MINIMO_GIORNI_DI_PRIMA)
    ora = medie_dei_giorni(giorni_di_adesso, fuso_orario, MINIMO_GIORNI_DEL_PERIODO)

    cambiamenti = []
    if cambiato(prima["sveglia"], ora["sveglia"], SOGLIA_SVEGLIA_MINUTI, 0):
        verso = "earlier"
        if ora["sveglia"] > prima["sveglia"]:
            verso = "later"
        durata = durata_in_parole(abs(ora["sveglia"] - prima["sveglia"]))
        testo = ("Wakes up about " + durata + " " + verso + " than usual (" + ora_in_parole(ora["sveglia"])
                 + " instead of " + ora_in_parole(prima["sveglia"]) + ").")
        cambiamenti.append(CambiamentoRoutine(cosa="sveglia", testo=testo))
    if cambiato(prima["sonno"], ora["sonno"], SOGLIA_SONNO_MINUTI, 0):
        durata = durata_in_parole(abs(ora["sonno"] - prima["sonno"]))
        testo = ("Sleeps about " + durata + " " + piu_o_meno(prima["sonno"], ora["sonno"]) + " than usual ("
                 + un_decimale(ora["sonno"] / 60) + " h instead of " + un_decimale(prima["sonno"] / 60)
                 + " h a night).")
        cambiamenti.append(CambiamentoRoutine(cosa="sonno", testo=testo))
    if cambiato(prima["acqua"], ora["acqua"], SOGLIA_ACQUA_ML, SOGLIA_ACQUA_PERCENTUALE):
        percentuale = round(abs(ora["acqua"] - prima["acqua"]) / prima["acqua"] * 100)
        testo = ("Drinks " + str(percentuale) + "% " + piu_o_meno(prima["acqua"], ora["acqua"])
                 + " water than usual (" + str(round(ora["acqua"])) + " ml instead of " + str(round(prima["acqua"]))
                 + " ml a day).")
        cambiamenti.append(CambiamentoRoutine(cosa="acqua", testo=testo))
    if cambiato(prima["pasti"], ora["pasti"], SOGLIA_PASTI_AL_GIORNO, 0):
        testo = ("Leaves more than half of the plate " + piu_o_meno(prima["pasti"], ora["pasti"])
                 + " often than usual (" + quanti(ora["pasti"], "meal", "meals") + " a day instead of "
                 + un_decimale(prima["pasti"]) + ").")
        cambiamenti.append(CambiamentoRoutine(cosa="pasti", testo=testo))
    if cambiato(prima["agitazione"], ora["agitazione"], SOGLIA_AGITAZIONE_MINUTI, SOGLIA_AGITAZIONE_PERCENTUALE):
        testo = ("Agitated (pacing) " + piu_o_meno(prima["agitazione"], ora["agitazione"]) + " than usual ("
                 + quanti(round(ora["agitazione"]), "minute", "minutes") + " a day instead of "
                 + str(round(prima["agitazione"])) + ").")
        cambiamenti.append(CambiamentoRoutine(cosa="agitazione", testo=testo))
    # le visite al bagno solo se la famiglia le ha accese (API.md)
    if personalizzazione.regole.visite_bagno_attive:
        if cambiato(prima["bagno"], ora["bagno"], SOGLIA_BAGNO_AL_GIORNO, 0):
            testo = ("Goes to the bathroom " + piu_o_meno(prima["bagno"], ora["bagno"]) + " often than usual ("
                     + quanti(ora["bagno"], "time", "times") + " a day instead of " + un_decimale(prima["bagno"])
                     + ").")
            cambiamenti.append(CambiamentoRoutine(cosa="bagno", testo=testo))
        if cambiato(prima["bagno_di_notte"], ora["bagno_di_notte"], SOGLIA_BAGNO_DI_NOTTE, 0):
            testo = ("Goes to the bathroom " + piu_o_meno(prima["bagno_di_notte"], ora["bagno_di_notte"])
                     + " often at night (" + quanti(ora["bagno_di_notte"], "time", "times") + " a night instead of "
                     + un_decimale(prima["bagno_di_notte"]) + ").")
            cambiamenti.append(CambiamentoRoutine(cosa="bagno", testo=testo))
    if cambiato(prima["uscite"], ora["uscite"], SOGLIA_USCITE_AL_GIORNO, 0):
        testo = ("Goes out " + piu_o_meno(prima["uscite"], ora["uscite"]) + " often than usual ("
                 + quanti(ora["uscite"], "time", "times") + " a day instead of " + un_decimale(prima["uscite"]) + ").")
        cambiamenti.append(CambiamentoRoutine(cosa="uscite", testo=testo))
    return cambiamenti


def giorni_della_settimana(dal: datetime.date) -> tuple[datetime.date, datetime.date]:
    """Il report settimanale copre i 7 giorni da `dal` (API.md)."""
    al = dal + datetime.timedelta(days=6)
    return dal, al


def giorni_del_mese(anno: int, mese: int) -> tuple[datetime.date, datetime.date]:
    """Primo e ultimo giorno del mese; ValueError se il mese non esiste."""
    primo = datetime.date(anno, mese, 1)
    numero_giorni = calendar.monthrange(anno, mese)[1]
    ultimo = datetime.date(anno, mese, numero_giorni)
    return primo, ultimo


def inizio_del_giorno(data: datetime.date, fuso_orario: str) -> datetime.datetime:
    """La mezzanotte locale della casa all'inizio del giorno `data`."""
    return datetime.datetime.combine(data, datetime.time(0, 0), tzinfo=ZoneInfo(fuso_orario))
