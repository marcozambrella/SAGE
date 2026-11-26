// Inserimenti a mano dei familiari (API.md, Marco 25/11): se e quanto ha mangiato e bevuto, segnati da un parente.
// Restano nel browser come la personalizzazione (D29) e non vanno al backend. Chiavi separate per la casa propria
// e per la casa demo, dove si sommano agli eventi delle telecamere senza toccare il backend.
import { useState } from "react";
import type { Contenitore, QuantoMangiato, ReportPeriodo, RiassuntoGiorno } from "./contratti";
import { quanti } from "./formato";

// "niente" vuol dire che il pasto è stato saltato.
export type QuantoMangiatoAMano = "niente" | QuantoMangiato;

export interface BevutaAMano {
  id: string;
  tipo: "bevuta";
  // Giorno "AAAA-MM-GG" e ora "HH:MM" nel fuso della casa.
  giorno: string;
  ora: string;
  ml: number;
  // Se è stata segnata a bicchieri: quanti e di quale contenitore (null = bicchiere normale da 200 ml).
  bicchieri: number | null;
  contenitore_id: string | null;
}

export interface PastoAMano {
  id: string;
  tipo: "pasto";
  giorno: string;
  ora: string;
  // Testo libero, può restare vuoto.
  cibi: string;
  quanto: QuantoMangiatoAMano;
}

export type InserimentoAMano = BevutaAMano | PastoAMano;

// Un bicchiere quando nella personalizzazione non c'è nessun contenitore (API.md).
export const ML_BICCHIERE_NORMALE = 200;

function chiave(demo: boolean): string {
  if (demo) {
    return "sage.inserimenti.demo";
  }
  return "sage.inserimenti.casa";
}

// Lista vuota se non c'è niente, se il testo salvato è rovinato o se lo spazio locale non è disponibile.
export function leggiInserimenti(demo: boolean): InserimentoAMano[] {
  let testo: string | null = null;
  try {
    testo = localStorage.getItem(chiave(demo));
  } catch {
    return [];
  }
  if (testo === null) {
    return [];
  }
  try {
    return JSON.parse(testo) as InserimentoAMano[];
  } catch {
    return [];
  }
}

// false se il browser non ha permesso di salvare.
export function salvaInserimenti(demo: boolean, inserimenti: InserimentoAMano[]): boolean {
  try {
    localStorage.setItem(chiave(demo), JSON.stringify(inserimenti));
    return true;
  } catch {
    return false;
  }
}

export function cancellaInserimenti(demo: boolean) {
  try {
    localStorage.removeItem(chiave(demo));
  } catch {
    // Niente da cancellare se lo spazio locale non è disponibile.
  }
}

function confrontaOra(a: InserimentoAMano, b: InserimentoAMano): number {
  if (a.ora < b.ora) {
    return -1;
  }
  if (a.ora > b.ora) {
    return 1;
  }
  return 0;
}

export function bevuteAMano(inserimenti: InserimentoAMano[], giorno: string): BevutaAMano[] {
  const bevute: BevutaAMano[] = [];
  for (const inserimento of inserimenti) {
    if (inserimento.tipo === "bevuta" && inserimento.giorno === giorno) {
      bevute.push(inserimento);
    }
  }
  bevute.sort(confrontaOra);
  return bevute;
}

export function pastiAMano(inserimenti: InserimentoAMano[], giorno: string): PastoAMano[] {
  const pasti: PastoAMano[] = [];
  for (const inserimento of inserimenti) {
    if (inserimento.tipo === "pasto" && inserimento.giorno === giorno) {
      pasti.push(inserimento);
    }
  }
  pasti.sort(confrontaOra);
  return pasti;
}

export function delGiorno(inserimenti: InserimentoAMano[], giorno: string): InserimentoAMano[] {
  const delGiorno: InserimentoAMano[] = [];
  for (const inserimento of inserimenti) {
    if (inserimento.giorno === giorno) {
      delGiorno.push(inserimento);
    }
  }
  delGiorno.sort(confrontaOra);
  return delGiorno;
}

export function sommaMl(bevute: BevutaAMano[]): number {
  let ml = 0;
  for (const bevuta of bevute) {
    ml = ml + bevuta.ml;
  }
  return ml;
}

// I giorni del periodo con dentro anche gli inserimenti a mano: nei Trends e nei report i dati vengono dal
// backend, che non li conosce. Un pasto saltato conta tra quelli con meno di metà mangiato.
export function aggiungiAiGiorni(giorni: RiassuntoGiorno[], inserimenti: InserimentoAMano[]): RiassuntoGiorno[] {
  const nuovi: RiassuntoGiorno[] = [];
  for (const riga of giorni) {
    const pasti = pastiAMano(inserimenti, riga.data);
    let menoDiMeta = 0;
    for (const pasto of pasti) {
      if (pasto.quanto === "niente" || pasto.quanto === "meno_di_meta") {
        menoDiMeta = menoDiMeta + 1;
      }
    }
    const nuova: RiassuntoGiorno = { ...riga };
    nuova.acqua_ml = riga.acqua_ml + sommaMl(bevuteAMano(inserimenti, riga.data));
    nuova.pasti = riga.pasti + pasti.length;
    nuova.pasti_meno_di_meta = riga.pasti_meno_di_meta + menoDiMeta;
    nuovi.push(nuova);
  }
  return nuovi;
}

export function aggiungiAlPeriodo(report: ReportPeriodo, inserimenti: InserimentoAMano[]): ReportPeriodo {
  const giorni = aggiungiAiGiorni(report.giorni, inserimenti);
  let acqua = 0;
  for (const riga of giorni) {
    acqua = acqua + riga.acqua_ml;
  }
  const nuovo: ReportPeriodo = { ...report };
  nuovo.giorni = giorni;
  if (giorni.length > 0) {
    nuovo.acqua_media_ml = acqua / giorni.length;
  }
  return nuovo;
}

// "1 glass · Blue glass", "2 glasses of 200 ml", oppure "" se è stata segnata in ml.
export function testoBicchieri(bevuta: BevutaAMano, contenitori: Contenitore[]): string {
  if (bevuta.bicchieri === null) {
    return "";
  }
  const numero = quanti(bevuta.bicchieri, "glass", "glasses");
  for (const contenitore of contenitori) {
    if (contenitore.id === bevuta.contenitore_id) {
      return numero + " · " + contenitore.nome;
    }
  }
  // Contenitore normale o tolto dalla personalizzazione: si scrive la capienza usata.
  return numero + " of " + Math.round(bevuta.ml / bevuta.bicchieri) + " ml";
}

// Gli inserimenti a mano di una casa, con le due azioni che li cambiano: ogni modifica si salva subito nel browser.
export function useInserimenti(demo: boolean) {
  const [inserimenti, setInserimenti] = useState<InserimentoAMano[]>(leggiInserimenti(demo));

  function aggiungi(nuovo: InserimentoAMano) {
    const nuovi = inserimenti.concat([nuovo]);
    salvaInserimenti(demo, nuovi);
    setInserimenti(nuovi);
  }

  function cancella(id: string) {
    if (!window.confirm("Delete this entry logged by family?")) {
      return;
    }
    const rimasti: InserimentoAMano[] = [];
    for (const inserimento of inserimenti) {
      if (inserimento.id !== id) {
        rimasti.push(inserimento);
      }
    }
    salvaInserimenti(demo, rimasti);
    setInserimenti(rimasti);
  }

  return { inserimenti: inserimenti, aggiungi: aggiungi, cancella: cancella };
}
