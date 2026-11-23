"""Unione (D3): toglie i doppioni (lo stesso fatto visto da più telecamere o analizzatori), unisce le fonti e combina
le stime pesandole con la confidenza. Gli eventi urgenti (caduta, uscita) escono subito alla prima fonte, perché
l'allarme Telegram non deve aspettare; i doppioni che arrivano dopo vengono assorbiti.

Regole PROVVISORIE (da far scegliere a Marco): due eventi sono lo stesso fatto se hanno lo stesso tipo, vengono da
fonti diverse (telecamera o analizzatore) e i loro intervalli distano al massimo FINESTRA_SECONDI; un gruppo si
chiude quando per FINESTRA_SECONDI non arriva niente di nuovo; la confidenza dell'evento unito è la più alta.

L'unione tiene anche le presenze (in quali stanze si è vista una persona e quando): servono a riempire le stanze
attraversate durante un'alzata notturna.
"""

from dataclasses import dataclass
import datetime

from contratti.eventi import TIPI_URGENTI, EventoBase, leggi_evento

FINESTRA_SECONDI = 10.0
# due avvistamenti nella stessa stanza a meno di tanto fanno parte della stessa presenza
PAUSA_PRESENZA_SECONDI = 5.0


@dataclass
class Gruppo:
    eventi: list                       # eventi grezzi dello stesso fatto
    ultimo_arrivo: datetime.datetime   # ora (del video) in cui è arrivato l'ultimo
    uscito: bool                       # già dato al registro (gli urgenti escono alla prima fonte)


@dataclass
class Intervallo:
    inizio: datetime.datetime
    fine: datetime.datetime


def fine_o_inizio(evento: EventoBase) -> datetime.datetime:
    if evento.fine is None:
        return evento.inizio
    return evento.fine


def distanza_secondi(inizio_a, fine_a, inizio_b, fine_b) -> float:
    """Secondi tra due intervalli di tempo (0 se si sovrappongono)."""
    if fine_a < inizio_b:
        return (inizio_b - fine_a).total_seconds()
    if fine_b < inizio_a:
        return (inizio_a - fine_b).total_seconds()
    return 0.0


def media_pesata(valori: list, pesi: list) -> float:
    somma_pesi = sum(pesi)
    if somma_pesi == 0:
        return sum(valori) / len(valori)
    totale = 0.0
    for indice in range(len(valori)):
        totale = totale + valori[indice] * pesi[indice]
    return totale / somma_pesi


def aggiungi_senza_ripetere(elenco: list, nuovi: list) -> None:
    for elemento in nuovi:
        if elemento not in elenco:
            elenco.append(elemento)


class Unione:
    def __init__(self):
        self.gruppi = []
        self.presenze = {}  # stanza → lista di Intervallo

    # ---------- doppioni ----------

    def aggiungi(self, evento: EventoBase, ora: datetime.datetime) -> list:
        """Aggiunge un evento grezzo. Restituisce gli eventi da registrare subito (un urgente nuovo), o []."""
        gruppo = self.gruppo_dello_stesso_fatto(evento)
        if gruppo is not None:
            gruppo.eventi.append(evento)
            gruppo.ultimo_arrivo = ora
            return []
        urgente = evento.tipo in TIPI_URGENTI
        self.gruppi.append(Gruppo([evento], ora, urgente))
        if urgente:
            return [evento]
        return []

    def gruppo_dello_stesso_fatto(self, evento: EventoBase) -> Gruppo | None:
        fonte = evento.fonti[0]
        for gruppo in self.gruppi:
            if gruppo.eventi[0].tipo != evento.tipo:
                continue
            stessa_fonte = False
            inizio_gruppo = gruppo.eventi[0].inizio
            fine_gruppo = fine_o_inizio(gruppo.eventi[0])
            for altro in gruppo.eventi:
                for altra_fonte in altro.fonti:
                    stessa_telecamera = altra_fonte.telecamera_id == fonte.telecamera_id
                    stesso_analizzatore = altra_fonte.analizzatore == fonte.analizzatore
                    if stessa_telecamera and stesso_analizzatore:
                        stessa_fonte = True
                inizio_gruppo = min(inizio_gruppo, altro.inizio)
                fine_gruppo = max(fine_gruppo, fine_o_inizio(altro))
            # la stessa telecamera con lo stesso analizzatore non vede due volte lo stesso fatto: sono due fatti
            if stessa_fonte:
                continue
            distanza = distanza_secondi(inizio_gruppo, fine_gruppo, evento.inizio, fine_o_inizio(evento))
            if distanza <= FINESTRA_SECONDI:
                return gruppo
        return None

    def pronti(self, ora: datetime.datetime) -> list:
        """Eventi uniti dei gruppi in cui non arriva più niente da FINESTRA_SECONDI."""
        eventi = []
        aperti = []
        for gruppo in self.gruppi:
            if (ora - gruppo.ultimo_arrivo).total_seconds() > FINESTRA_SECONDI:
                if not gruppo.uscito:
                    eventi.append(self.unisci(gruppo.eventi))
            else:
                aperti.append(gruppo)
        self.gruppi = aperti
        return eventi

    def chiudi_tutti(self) -> list:
        """A fine elaborazione: tutti i gruppi ancora aperti."""
        eventi = []
        for gruppo in self.gruppi:
            if not gruppo.uscito:
                eventi.append(self.unisci(gruppo.eventi))
        self.gruppi = []
        return eventi

    def unisci(self, eventi: list) -> EventoBase:
        """Un solo evento dal gruppo: fonti di tutti, tempi dal primo inizio all'ultima fine, stime pesate."""
        migliore = eventi[0]
        for evento in eventi:
            if evento.confidenza > migliore.confidenza:
                migliore = evento
        inizio = migliore.inizio
        fine = migliore.fine
        fonti = []
        pesi = []
        foto = migliore.foto_prova
        for evento in eventi:
            inizio = min(inizio, evento.inizio)
            if evento.fine is not None:
                if fine is None:
                    fine = evento.fine
                fine = max(fine, evento.fine)
            for fonte in evento.fonti:
                fonti.append(fonte.model_dump())
            pesi.append(evento.confidenza)
            if foto is None:
                foto = evento.foto_prova

        dati = migliore.model_dump()
        dati["inizio"] = inizio
        dati["fine"] = fine
        dati["fonti"] = fonti
        dati["foto_prova"] = foto
        dati["valori"] = self.valori_uniti(eventi, pesi, migliore, inizio, fine)
        return leggi_evento(dati)

    def valori_uniti(self, eventi: list, pesi: list, migliore: EventoBase, inizio, fine) -> dict:
        """Le stime numeriche si pesano con la confidenza; il resto viene dall'evento più sicuro."""
        valori = migliore.valori.model_dump()
        tipo = migliore.tipo
        if tipo == "caduta":
            secondi = []
            pesi_secondi = []
            for indice in range(len(eventi)):
                if eventi[indice].valori.secondi_a_terra is not None:
                    secondi.append(eventi[indice].valori.secondi_a_terra)
                    pesi_secondi.append(pesi[indice])
            if len(secondi) > 0:
                valori["secondi_a_terra"] = media_pesata(secondi, pesi_secondi)
        elif tipo == "bevuta":
            # percentuale pesata, poi ml e pixel ricalcolati con la formula di D9 sul contenitore più sicuro
            percentuali = []
            for evento in eventi:
                percentuali.append(evento.valori.percentuale)
            percentuale = media_pesata(percentuali, pesi)
            valori["percentuale"] = percentuale
            valori["livello_sceso_px"] = percentuale / 100 * valori["altezza_contenitore_px"]
            valori["ml"] = percentuale / 100 * valori["capienza_ml"]
        elif tipo == "pasto":
            cibi = []
            percentuali = []
            for evento in eventi:
                aggiungi_senza_ripetere(cibi, evento.valori.cibi)
                percentuali.append(evento.valori.percentuale_mangiata)
            valori["cibi"] = cibi
            valori["percentuale_mangiata"] = media_pesata(percentuali, pesi)
        elif tipo == "alzata_notturna":
            stanze = list(migliore.valori.stanze)
            for evento in eventi:
                aggiungi_senza_ripetere(stanze, evento.valori.stanze)
            aggiungi_senza_ripetere(stanze, self.stanze_attraversate(inizio, fine))
            valori["stanze"] = stanze
        return valori

    # ---------- presenze ----------

    def registra_presenza(self, stanza: str, ora: datetime.datetime) -> None:
        """Una persona vista in questa stanza a quest'ora."""
        if stanza not in self.presenze:
            self.presenze[stanza] = []
        intervalli = self.presenze[stanza]
        if len(intervalli) > 0 and (ora - intervalli[-1].fine).total_seconds() <= PAUSA_PRESENZA_SECONDI:
            intervalli[-1].fine = ora
        else:
            intervalli.append(Intervallo(ora, ora))

    def stanze_attraversate(self, inizio: datetime.datetime, fine: datetime.datetime | None) -> list:
        """Stanze in cui si è vista una persona tra inizio e fine (fine None: fino a ora), in ordine di arrivo."""
        trovate = []  # (prima ora nell'intervallo, stanza)
        for stanza in self.presenze:
            for intervallo in self.presenze[stanza]:
                dopo_inizio = intervallo.fine >= inizio
                prima_della_fine = fine is None or intervallo.inizio <= fine
                if dopo_inizio and prima_della_fine:
                    trovate.append((max(intervallo.inizio, inizio), stanza))
                    break
        trovate.sort()
        stanze = []
        for prima_ora, stanza in trovate:
            stanze.append(stanza)
        return stanze
