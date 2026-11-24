"""Coordinamento degli eventi (contratti/API.md, "Coordinamento degli eventi", Marco 24/11).

Il programma di casa manda eventi grezzi: una telecamera e un analizzatore ciascuno. Lo stesso fatto può arrivare
più volte: da telecamere diverse, dalla stessa telecamera in pezzi vicini, o rimandato dopo un errore di rete.
L'archivio salva ogni grezzo così com'è (niente si perde); qui i grezzi dello stesso fatto diventano un solo evento
coordinato, l'unico che vedono web app, report e Telegram.

Logica pura, rifatta a ogni lettura dai grezzi salvati: non c'è niente da tenere allineato nel database e un
grezzo arrivato in ritardo trova sempre il suo gruppo.

Stesso fatto: stesso tipo e intervalli di tempo che si sovrappongono o distano al massimo FINESTRA_SECONDI (la
finestra dell'unione del programma di casa, casa/unione.py), da qualunque telecamera. In più, per buon senso:
- due prese di farmaci riconosciuti diversi sono due fatti (due pillole prese una dopo l'altra);
- un evento simulato e uno vero non sono mai lo stesso fatto.
"""

import datetime
from dataclasses import dataclass

from contratti.eventi import EventoBase

FINESTRA_SECONDI = 10.0


@dataclass
class Coordinato:
    # l'evento coordinato: foto_prova sempre None, ha_foto True se uno dei grezzi ha la foto
    evento: EventoBase
    # il grezzo da cui prendere la foto di prova (None se nessuno ce l'ha)
    id_foto: str | None
    # gli id dei grezzi che lo compongono
    grezzi: list[str]


def fine_o_inizio(evento: EventoBase) -> datetime.datetime:
    if evento.fine is None:
        return evento.inizio
    return evento.fine


def inizio_e_id(evento: EventoBase) -> tuple[datetime.datetime, str]:
    """Chiave per l'ordine dei grezzi: per inizio e, a parità, per id (così l'ordine è sempre lo stesso)."""
    return (evento.inizio, evento.id)


def distanza_secondi(
    inizio_a: datetime.datetime, fine_a: datetime.datetime, inizio_b: datetime.datetime, fine_b: datetime.datetime
) -> float:
    """Secondi tra due intervalli di tempo (0 se si sovrappongono)."""
    if fine_a < inizio_b:
        return (inizio_b - fine_a).total_seconds()
    if fine_b < inizio_a:
        return (inizio_a - fine_b).total_seconds()
    return 0.0


def intervallo(gruppo: list[EventoBase]) -> tuple[datetime.datetime, datetime.datetime]:
    """Dal primo inizio all'ultima fine dei grezzi del gruppo."""
    inizio = gruppo[0].inizio
    fine = fine_o_inizio(gruppo[0])
    for grezzo in gruppo:
        inizio = min(inizio, grezzo.inizio)
        fine = max(fine, fine_o_inizio(grezzo))
    return inizio, fine


def compatibile(gruppo: list[EventoBase], grezzo: EventoBase) -> bool:
    """Se il grezzo può essere lo stesso fatto del gruppo (senza guardare il tempo)."""
    primo = gruppo[0]
    if primo.tipo != grezzo.tipo:
        return False
    if primo.simulato != grezzo.simulato:
        return False
    if grezzo.tipo == "farmaco" and grezzo.valori.farmaco_id is not None:
        for altro in gruppo:
            altro_id = altro.valori.farmaco_id
            if altro_id is not None and altro_id != grezzo.valori.farmaco_id:
                return False
    return True


def raggruppa(grezzi: list[EventoBase]) -> list[list[EventoBase]]:
    """I grezzi divisi per fatto, in ordine di inizio. Ogni grezzo va nel gruppo compatibile più vicino entro
    FINESTRA_SECONDI; se non ce n'è uno, apre un gruppo nuovo."""
    in_ordine = sorted(grezzi, key=inizio_e_id)
    gruppi = []
    # i gruppi che possono ancora crescere
    aperti = []
    for grezzo in in_ordine:
        # i grezzi arrivano in ordine di inizio: un gruppo finito più di FINESTRA_SECONDI fa non cresce più
        ancora_aperti = []
        for gruppo in aperti:
            fine_gruppo = intervallo(gruppo)[1]
            if (grezzo.inizio - fine_gruppo).total_seconds() <= FINESTRA_SECONDI:
                ancora_aperti.append(gruppo)
        aperti = ancora_aperti

        # il più vicino: con due pillole prese di fila, la presa non riconosciuta va con quella accanto
        scelto = None
        distanza_scelto = 0.0
        for gruppo in aperti:
            if not compatibile(gruppo, grezzo):
                continue
            inizio_gruppo, fine_gruppo = intervallo(gruppo)
            distanza = distanza_secondi(inizio_gruppo, fine_gruppo, grezzo.inizio, fine_o_inizio(grezzo))
            if distanza > FINESTRA_SECONDI:
                continue
            if scelto is None or distanza < distanza_scelto:
                scelto = gruppo
                distanza_scelto = distanza

        if scelto is None:
            nuovo = [grezzo]
            gruppi.append(nuovo)
            aperti.append(nuovo)
        else:
            scelto.append(grezzo)
    return gruppi


def ha_misurato(grezzo: EventoBase) -> bool:
    """False se la telecamera ha visto il fatto ma non ha potuto misurarlo: livello dell'acqua non visibile, piatto
    non misurato. Allora i valori si prendono da un'altra telecamera che ha misurato, se c'è."""
    if grezzo.tipo == "bevuta":
        return grezzo.valori.livello_visibile
    if grezzo.tipo == "pasto":
        return grezzo.valori.quanto_mangiato is not None
    return True


def aggiungi_senza_ripetere(elenco: list, nuovi: list) -> None:
    for elemento in nuovi:
        if elemento not in elenco:
            elenco.append(elemento)


def unisci(gruppo: list[EventoBase]) -> Coordinato:
    """L'evento coordinato di un gruppo (API.md): id del primo grezzo, inizio il più presto, fine la più tardi,
    tutte le fonti, confidenza la più alta, valori e foto dal grezzo più sicuro, stanze dell'alzata unite.
    I ml di una bevuta vista da due telecamere non si sommano: valgono quelli del grezzo più sicuro.
    Per i valori conta il più sicuro tra quelli che hanno misurato (ha_misurato), se ce n'è almeno uno."""
    migliore = gruppo[0]
    for grezzo in gruppo:
        if grezzo.confidenza > migliore.confidenza:
            migliore = grezzo
    # il grezzo da cui vengono valori, stanza e il resto: il più sicuro tra quelli che hanno misurato
    per_i_valori = None
    for grezzo in gruppo:
        if ha_misurato(grezzo) and (per_i_valori is None or grezzo.confidenza > per_i_valori.confidenza):
            per_i_valori = grezzo
    if per_i_valori is None:
        per_i_valori = migliore

    # la foto dal grezzo più sicuro che ne ha una
    con_foto = None
    for grezzo in gruppo:
        if grezzo.ha_foto and (con_foto is None or grezzo.confidenza > con_foto.confidenza):
            con_foto = grezzo
    id_foto = None
    if con_foto is not None:
        id_foto = con_foto.id

    inizio = intervallo(gruppo)[0]
    # fine None solo se nessun grezzo ha una fine (evento istantaneo)
    fine = None
    fonti = []
    ids = []
    for grezzo in gruppo:
        ids.append(grezzo.id)
        aggiungi_senza_ripetere(fonti, grezzo.fonti)
        if grezzo.fine is not None and (fine is None or grezzo.fine > fine):
            fine = grezzo.fine

    valori = per_i_valori.valori
    if per_i_valori.tipo == "alzata_notturna":
        stanze = list(per_i_valori.valori.stanze)
        for grezzo in gruppo:
            aggiungi_senza_ripetere(stanze, grezzo.valori.stanze)
        valori = per_i_valori.valori.model_copy(update={"stanze": stanze})

    modifiche = {
        "id": gruppo[0].id,
        "inizio": inizio,
        "fine": fine,
        "fonti": fonti,
        "confidenza": migliore.confidenza,
        "valori": valori,
        "foto_prova": None,
        "ha_foto": con_foto is not None,
    }
    return Coordinato(evento=per_i_valori.model_copy(update=modifiche), id_foto=id_foto, grezzi=ids)


def coordina(grezzi: list[EventoBase]) -> list[Coordinato]:
    """Gli eventi coordinati dei grezzi, in ordine di inizio."""
    coordinati = []
    for gruppo in raggruppa(grezzi):
        coordinati.append(unisci(gruppo))
    return coordinati
