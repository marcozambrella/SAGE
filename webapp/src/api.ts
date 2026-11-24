// Chiamate al backend per la casa demo (D22), vedi contratti/API.md: sola lettura, senza login (D27).
// Se VITE_API_URL non è impostato (file .env.local) si usano i dati finti di dati-sviluppo.ts.
import type { Evento, PeriodoDemo, Personalizzazione, ReportGiornaliero, ReportPeriodo, TipoEvento } from "./contratti";
import {
  PERSONALIZZAZIONE_DEMO,
  eventiSviluppo,
  periodoSviluppo,
  reportGiornalieroSviluppo,
  reportMensileSviluppo,
  reportSettimanaleSviluppo,
} from "./dati-sviluppo";

let indirizzo = "";
if (import.meta.env.VITE_API_URL) {
  indirizzo = import.meta.env.VITE_API_URL;
}
export const INDIRIZZO_API = indirizzo;
export const USA_DATI_SVILUPPO = INDIRIZZO_API === "";

async function leggiJson<T>(percorso: string): Promise<T> {
  const risposta = await fetch(INDIRIZZO_API + percorso);
  if (!risposta.ok) {
    throw new Error("The demo server answered " + risposta.status + " for " + percorso);
  }
  return (await risposta.json()) as T;
}

// Primo e ultimo giorno con dati nella casa demo. Today mostra l'ultimo, gli altri giorni si scorrono fino al primo.
export type GiorniDemo = {
  dal: string;
  al: string;
};

export async function leggiPeriodoDemo(): Promise<GiorniDemo> {
  let periodo: PeriodoDemo | null = null;
  if (USA_DATI_SVILUPPO) {
    periodo = periodoSviluppo();
  } else {
    periodo = await leggiJson<PeriodoDemo | null>("/demo/periodo");
  }
  // Senza giorni la casa demo è vuota: lo si dice come un errore, con la scheda di Caricamento.
  if (periodo === null || periodo.dal === null || periodo.al === null) {
    throw new Error("The demo home has no data yet.");
  }
  return { dal: periodo.dal, al: periodo.al };
}

export async function leggiPersonalizzazioneDemo(): Promise<Personalizzazione> {
  if (USA_DATI_SVILUPPO) {
    return PERSONALIZZAZIONE_DEMO;
  }
  return leggiJson<Personalizzazione>("/demo/personalizzazione");
}

// Eventi dal giorno "dal" al giorno "al" compresi (AAAA-MM-GG), in ordine di inizio.
export async function leggiEventiDemo(dal: string, al: string, tipo: TipoEvento | null): Promise<Evento[]> {
  if (USA_DATI_SVILUPPO) {
    return eventiSviluppo(dal, al, tipo);
  }
  let percorso = "/demo/eventi?dal=" + dal + "&al=" + al;
  if (tipo !== null) {
    percorso = percorso + "&tipo=" + tipo;
  }
  return leggiJson<Evento[]>(percorso);
}

// Indirizzo della foto di prova di un evento con ha_foto; null con i dati di sviluppo (non hanno immagini).
export function indirizzoFotoEvento(evento: Evento): string | null {
  if (USA_DATI_SVILUPPO || !evento.ha_foto) {
    return null;
  }
  return INDIRIZZO_API + "/demo/eventi/" + evento.id + "/foto";
}

export async function leggiReportGiornaliero(giorno: string): Promise<ReportGiornaliero> {
  if (USA_DATI_SVILUPPO) {
    const report = reportGiornalieroSviluppo(giorno);
    if (report === null) {
      throw new Error("No data for " + giorno + " in the demo home");
    }
    return report;
  }
  return leggiJson<ReportGiornaliero>("/demo/report/giornaliero?data=" + giorno);
}

// I 7 giorni da "dal".
export async function leggiReportSettimanale(dal: string): Promise<ReportPeriodo> {
  if (USA_DATI_SVILUPPO) {
    return reportSettimanaleSviluppo(dal);
  }
  return leggiJson<ReportPeriodo>("/demo/report/settimanale?dal=" + dal);
}

// mese = "AAAA-MM"
export async function leggiReportMensile(mese: string): Promise<ReportPeriodo> {
  if (USA_DATI_SVILUPPO) {
    return reportMensileSviluppo(mese);
  }
  return leggiJson<ReportPeriodo>("/demo/report/mensile?mese=" + mese);
}
