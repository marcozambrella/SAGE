"""Calcolo dei report (modelli in contratti/report.py) dagli eventi della casa e dalla personalizzazione.

Logica pura come regole.py: gli eventi arrivano già letti dal database, l'ora attuale come parametro.
"""

import calendar
import datetime
from typing import Literal
from zoneinfo import ZoneInfo

from contratti.configurazione import Personalizzazione
from contratti.eventi import EventoBase
from contratti.report import PastoDelGiorno, ReportGiornaliero, ReportPeriodo, RiassuntoGiorno

from backend.regole import (
    alzata_di_notte,
    giorno_locale,
    inizio_evento,
    stato_delle_dosi,
    uscita_in_orario_vietato,
)


def calcola_report_giornaliero(
    data: datetime.date,
    eventi: list[EventoBase],
    personalizzazione: Personalizzazione,
    adesso: datetime.datetime,
) -> ReportGiornaliero:
    """Il report del giorno `data`, contato nel fuso orario della casa (API.md).

    `eventi` può contenere anche eventi del giorno prima e dopo: servono alle dosi vicine alla mezzanotte, mentre
    tutto il resto conta solo gli eventi che iniziano nel giorno.
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
    simulato = False
    eventi_farmaco = []

    for evento in eventi_in_ordine:
        if evento.tipo == "farmaco":
            eventi_farmaco.append(evento)
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
                percentuale_mangiata=evento.valori.percentuale_mangiata,
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

    percentuale_mangiata_media = None
    if len(report.pasti) > 0:
        totale = 0.0
        for pasto in report.pasti:
            totale = totale + pasto.percentuale_mangiata
        percentuale_mangiata_media = round(totale / len(report.pasti), 1)

    return RiassuntoGiorno(
        data=report.data,
        acqua_ml=report.acqua_ml,
        dosi_previste=len(report.dosi),
        dosi_in_orario=in_orario,
        dosi_in_ritardo=in_ritardo,
        dosi_saltate=saltate,
        percentuale_mangiata_media=percentuale_mangiata_media,
        alzate_notturne=report.alzate_notturne,
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
    sono sui giorni con una riga, oggi compreso.
    """
    oggi = giorno_locale(adesso, personalizzazione.fuso_orario)
    giorni = []
    data = dal
    while data <= al and data <= oggi:
        report = calcola_report_giornaliero(data, eventi, personalizzazione, adesso)
        giorni.append(riassunto_del_giorno(report))
        data = data + datetime.timedelta(days=1)

    acqua_totale = 0.0
    alzate_totali = 0
    cadute = 0
    uscite_in_orario_vietato = 0
    dosi_prese = 0
    dosi_saltate = 0
    for giorno in giorni:
        acqua_totale = acqua_totale + giorno.acqua_ml
        alzate_totali = alzate_totali + giorno.alzate_notturne
        cadute = cadute + giorno.cadute
        uscite_in_orario_vietato = uscite_in_orario_vietato + giorno.uscite_in_orario_vietato
        dosi_prese = dosi_prese + giorno.dosi_in_orario + giorno.dosi_in_ritardo
        dosi_saltate = dosi_saltate + giorno.dosi_saltate

    acqua_media_ml = 0.0
    alzate_notturne_medie = 0.0
    if len(giorni) > 0:
        acqua_media_ml = round(acqua_totale / len(giorni), 1)
        alzate_notturne_medie = round(alzate_totali / len(giorni), 2)

    # le dosi ancora in attesa non contano: non sono né prese né saltate
    aderenza = 100.0
    dosi_valutate = dosi_prese + dosi_saltate
    if dosi_valutate > 0:
        aderenza = round(dosi_prese / dosi_valutate * 100, 1)

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
    )


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
