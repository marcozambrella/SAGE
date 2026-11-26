// Come si racconta un evento a una famiglia: icona, titolo, dettaglio e gravità (per il colore e l'etichetta).
import type { NomeIcona } from "./componenti/Icona";
import type { DoseFarmaco, Evento, Personalizzazione, TipoContenitore } from "./contratti";
import type { QuantoMangiatoAMano } from "./inserimenti";
import { durata, maiuscola, millilitri, oraDellaCasa } from "./formato";

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
// La stanza di una telecamera della personalizzazione; se non c'è, quella scritta nell'evento.
function stanzaDellaTelecamera(telecameraId: string, personalizzazione: Personalizzazione, riserva: string): string {
  for (const telecamera of personalizzazione.telecamere) {
    if (telecamera.id === telecameraId && telecamera.stanza !== "") {
      return telecamera.stanza;
    }
  }
  return riserva;
}

function minutiTra(inizio: string, fine: string | null): number {
  if (fine === null) {
    return 0;
  }
  return (new Date(fine).getTime() - new Date(inizio).getTime()) / 60000;
}

// Quanto ha mangiato, a parole: niente numeri, il modello del piatto non è abbastanza preciso per una percentuale.
export function testoQuantoMangiato(quanto: QuantoMangiatoAMano | null): string {
  // Solo un familiare può segnare un pasto saltato (inserimenti a mano).
  if (quanto === "niente") {
    return "Skipped the meal";
  }
  if (quanto === "meno_di_meta") {
    return "Ate less than half";
  }
  if (quanto === "meta") {
    return "Ate about half";
  }
  if (quanto === "tutto") {
    return "Ate everything";
  }
  return "Amount not measured";
}

export function descriviEvento(evento: Evento, personalizzazione: Personalizzazione): Descrizione {
  if (evento.tipo === "caduta") {
    let dettaglio = "Still on the floor when the video ended";
    if (evento.valori.secondi_a_terra !== null) {
      dettaglio = "On the floor for " + Math.round(evento.valori.secondi_a_terra) + " seconds";
    }
    return {
      icona: "avviso",
      titolo: "Fall in the " + evento.stanza.toLowerCase(),
      dettaglio: dettaglio,
      gravita: "critico",
    };
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
    // Livello non visibile (tazza opaca): ha bevuto, ma quanto non si sa. Non è "0 ml".
    if (!valori.livello_visibile) {
      return {
        icona: "goccia",
        titolo: "Drink — level not visible",
        dettaglio: "Not measured: the level can't be seen in this " + contenitore,
        gravita: "neutro",
      };
    }
    const capienza = millilitri(valori.capienza_ml);
    const dettaglio = "Level dropped " + Math.round(valori.percentuale) + "% in a " + capienza + " " + contenitore;
    return {
      icona: "goccia",
      titolo: "Drank " + Math.round(valori.ml) + " ml",
      dettaglio: dettaglio,
      gravita: "buono",
    };
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
    const quanto = evento.valori.quanto_mangiato;
    return {
      icona: "pasto",
      titolo: cibi,
      dettaglio: testoQuantoMangiato(quanto),
      // Neutro: il colore (arancione, giallo, verde) lo porta la barra del pasto.
      gravita: "neutro",
    };
  }
  if (evento.tipo === "sonno") {
    // Un pezzo di sonno: dall'addormentarsi al risveglio (la notte può averne più d'uno, tra le alzate).
    if (evento.fine === null) {
      return { icona: "letto", titolo: "Fell asleep", dettaglio: "Still asleep", gravita: "neutro" };
    }
    const sveglio = oraDellaCasa(evento.fine, personalizzazione.fuso_orario);
    const dettaglioSonno = "Slept " + durata(minutiTra(evento.inizio, evento.fine)) + " · woke at " + sveglio;
    return { icona: "letto", titolo: "Asleep", dettaglio: dettaglioSonno, gravita: "neutro" };
  }
  if (evento.tipo === "agitazione") {
    let dettaglio = "Walking back and forth";
    if (evento.fine !== null) {
      dettaglio = "Walked back and forth for " + durata(minutiTra(evento.inizio, evento.fine));
    }
    dettaglio = dettaglio + " · turned around " + evento.valori.inversioni + " times";
    return { icona: "passi", titolo: "Restless pacing", dettaglio: dettaglio, gravita: "attenzione" };
  }
  if (evento.tipo === "inattivita") {
    // Urgente come cadute e uscite: l'inizio è l'ultima volta che si è vista una persona.
    const ultimaVolta = oraDellaCasa(evento.inizio, personalizzazione.fuso_orario);
    const stanza = stanzaDellaTelecamera(evento.valori.ultima_telecamera_id, personalizzazione, evento.stanza);
    const dettaglio = "Last seen at " + ultimaVolta + " in the " + stanza.toLowerCase();
    if (evento.fine === null) {
      return {
        icona: "clessidra",
        titolo: "No one seen since " + ultimaVolta,
        dettaglio: dettaglio,
        gravita: "critico",
      };
    }
    const titolo = "No one seen for " + durata(minutiTra(evento.inizio, evento.fine));
    return { icona: "clessidra", titolo: titolo, dettaglio: dettaglio, gravita: "critico" };
  }
  if (evento.tipo === "visita_bagno") {
    let dettaglio = "Went into the bathroom";
    if (evento.fine !== null) {
      dettaglio = "In the bathroom for " + durata(minutiTra(evento.inizio, evento.fine));
    }
    return { icona: "bagno", titolo: "Bathroom visit", dettaglio: dettaglio, gravita: "neutro" };
  }
  // alzata_notturna
  const minuti = minutiTra(evento.inizio, evento.fine);
  const dettaglio = durata(minuti) + " out of bed · " + evento.valori.stanze.join(", ");
  return { icona: "luna", titolo: "Got up at night", dettaglio: dettaglio, gravita: "attenzione" };
}

// L'icona di un cambio di routine, secondo "cosa" è cambiato (contratti: CambiamentoRoutine).
export function iconaCambiamento(cosa: string): NomeIcona {
  if (cosa === "sveglia") {
    return "sole";
  }
  if (cosa === "acqua") {
    return "goccia";
  }
  if (cosa === "pasti") {
    return "pasto";
  }
  if (cosa === "sonno") {
    return "letto";
  }
  if (cosa === "agitazione") {
    return "passi";
  }
  if (cosa === "bagno") {
    return "bagno";
  }
  if (cosa === "uscite") {
    return "porta";
  }
  return "andamento";
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

// Quante bevute hanno il livello non visibile: non sono nei ml del giorno e si contano a parte.
export function bevuteNonMisurate(eventi: Evento[]): number {
  let quante = 0;
  for (const evento of eventi) {
    if (evento.tipo === "bevuta" && !evento.valori.livello_visibile) {
      quante = quante + 1;
    }
  }
  return quante;
}

// "+1 drink not measured", "+2 drinks not measured"; vuoto se non ce ne sono.
export function testoNonMisurate(quante: number): string {
  if (quante === 0) {
    return "";
  }
  if (quante === 1) {
    return "+1 drink not measured";
  }
  return "+" + quante + " drinks not measured";
}
