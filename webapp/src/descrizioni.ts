// Come si racconta un evento a una famiglia: icona, titolo, dettaglio e gravità (per il colore e l'etichetta).
import type { NomeIcona } from "./componenti/Icona";
import type { DoseFarmaco, Evento, Personalizzazione, TipoContenitore } from "./contratti";
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
    // Se era in un orario vietato lo dice il backend (null: non ancora valutato).
    if (evento.valori.in_orario_vietato === true) {
      return { icona: "porta", titolo: "Went out", dettaglio: "During no-exit hours", gravita: "critico" };
    }
    if (evento.valori.in_orario_vietato === false) {
      return { icona: "porta", titolo: "Went out", dettaglio: "Outside no-exit hours", gravita: "neutro" };
    }
    return { icona: "porta", titolo: "Went out", dettaglio: "Through the front door", gravita: "neutro" };
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

// "Planned 08:00 · taken 08:07": la riga di testo sotto il nome del farmaco.
export function orariDose(dose: DoseFarmaco, fusoOrario: string): string {
  let testo = "Planned " + dose.orario_previsto;
  if (dose.ora_presa !== null) {
    testo = testo + " · taken " + oraDellaCasa(dose.ora_presa, fusoOrario);
  }
  if (dose.farmaco_riconosciuto === false) {
    testo = testo + " · pill not recognised";
  }
  return testo;
}
