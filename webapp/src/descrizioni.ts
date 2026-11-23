// Come si racconta un evento a una famiglia: icona, titolo, dettaglio e gravità (per il colore e l'etichetta).
import type { NomeIcona } from "./componenti/Icona";
import type { Evento, FasciaOraria, Personalizzazione, TipoContenitore } from "./contratti";
import { durata, maiuscola, oraDellaCasa } from "./formato";

export type Gravita = "critico" | "attenzione" | "buono" | "neutro";

export type Descrizione = {
  icona: NomeIcona;
  titolo: string;
  dettaglio: string;
  gravita: Gravita;
};

export const NOMI_CONTENITORI: Record<TipoContenitore, string> = {
  bicchiere: "glass",
  bottiglia: "bottle",
  tazza: "cup",
};

// "HH:MM" → minuti dalla mezzanotte.
function minutiDelGiorno(hhmm: string): number {
  return Number(hhmm.slice(0, 2)) * 60 + Number(hhmm.slice(3, 5));
}

// True se l'ora (nel fuso della casa) cade nella fascia; se alle < dalle la fascia passa la mezzanotte.
// Nota: lo decide anche il backend (API.md); qui serve solo a scrivere "during no-exit hours" accanto all'uscita.
export function dentroFascia(iso: string, fascia: FasciaOraria, fusoOrario: string): boolean {
  const minuti = minutiDelGiorno(oraDellaCasa(iso, fusoOrario));
  const dalle = minutiDelGiorno(fascia.dalle);
  const alle = minutiDelGiorno(fascia.alle);
  if (dalle <= alle) {
    return minuti >= dalle && minuti < alle;
  }
  return minuti >= dalle || minuti < alle;
}

export function uscitaVietata(evento: Evento, personalizzazione: Personalizzazione): boolean {
  for (const fascia of personalizzazione.regole.orari_uscita_vietati) {
    if (dentroFascia(evento.inizio, fascia, personalizzazione.fuso_orario)) {
      return true;
    }
  }
  return false;
}

function nomeFarmaco(farmacoId: string, personalizzazione: Personalizzazione): string {
  for (const farmaco of personalizzazione.farmaci) {
    if (farmaco.id === farmacoId) {
      return farmaco.nome;
    }
  }
  return "a medication";
}

// Minuti tra inizio e fine dell'evento (0 se non c'è la fine).
function minutiTra(inizio: string, fine: string | null): number {
  if (fine === null) {
    return 0;
  }
  return (new Date(fine).getTime() - new Date(inizio).getTime()) / 60000;
}

export function descriviEvento(evento: Evento, personalizzazione: Personalizzazione): Descrizione {
  if (evento.tipo === "caduta") {
    let dettaglio = "Still on the floor when the video ended";
    if (evento.valori.secondi_a_terra !== null) {
      dettaglio = "On the floor for " + Math.round(evento.valori.secondi_a_terra) + " seconds";
    }
    return { icona: "avviso", titolo: "Fall in the " + evento.stanza.toLowerCase(), dettaglio: dettaglio, gravita: "critico" };
  }
  if (evento.tipo === "uscita") {
    if (uscitaVietata(evento, personalizzazione)) {
      return { icona: "porta", titolo: "Went out", dettaglio: "During no-exit hours", gravita: "critico" };
    }
    return { icona: "porta", titolo: "Went out", dettaglio: "Outside no-exit hours", gravita: "neutro" };
  }
  if (evento.tipo === "bevuta") {
    const valori = evento.valori;
    const contenitore = NOMI_CONTENITORI[valori.contenitore];
    const dettaglio =
      "Level dropped " + Math.round(valori.percentuale) + "% in a " + Math.round(valori.capienza_ml) + " ml " + contenitore;
    return { icona: "goccia", titolo: "Drank " + Math.round(valori.ml) + " ml", dettaglio: dettaglio, gravita: "buono" };
  }
  if (evento.tipo === "farmaco") {
    if (evento.valori.farmaco_id === null) {
      return {
        icona: "pillola",
        titolo: "Took a pill",
        dettaglio: "Gesture seen, but the medication was not recognised",
        gravita: "attenzione",
      };
    }
    const nome = nomeFarmaco(evento.valori.farmaco_id, personalizzazione);
    return { icona: "pillola", titolo: "Took " + nome, dettaglio: "Pill box opened, hand to mouth", gravita: "buono" };
  }
  if (evento.tipo === "pasto") {
    const cibi = maiuscola(evento.valori.cibi.join(", "));
    const dettaglio = "Ate about " + Math.round(evento.valori.percentuale_mangiata) + "% of the plate";
    return { icona: "pasto", titolo: cibi, dettaglio: dettaglio, gravita: "neutro" };
  }
  // alzata_notturna
  const minuti = minutiTra(evento.inizio, evento.fine);
  const dettaglio = durata(minuti) + " out of bed · " + evento.valori.stanze.join(", ");
  return { icona: "luna", titolo: "Got up at night", dettaglio: dettaglio, gravita: "attenzione" };
}
