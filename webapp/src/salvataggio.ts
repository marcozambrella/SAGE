// Personalizzazione della famiglia salvata solo nel browser (D29): nessun dato dell'utente va al server.
// Qui sta solo il testo JSON della personalizzazione; per le foto dei farmaci il modo di salvarle è ancora da decidere.
import type { Personalizzazione } from "./contratti";

const CHIAVE = "sage.personalizzazione";

export function personalizzazioneVuota(): Personalizzazione {
  // Stessi valori predefiniti di contratti/contratti/configurazione.py.
  return {
    anziano: { nome: "", anno_nascita: null, obiettivo_acqua_ml: 1500, note: "" },
    farmaci: [],
    contenitori: [],
    telecamere: [],
    regole: {
      orari_uscita_vietati: [],
      orari_notte: { dalle: "22:00", alle: "07:00" },
      allarme_uscita_attivo: true,
      pausa_fino_a: null,
    },
    fuso_orario: "Europe/Rome",
  };
}

// null se la famiglia non ha ancora fatto la personalizzazione (o se il testo salvato è rovinato).
export function leggiPersonalizzazione(): Personalizzazione | null {
  let testo: string | null = null;
  try {
    testo = localStorage.getItem(CHIAVE);
  } catch {
    // Spazio locale non disponibile (es. navigazione privata con i dati bloccati).
    return null;
  }
  if (testo === null) {
    return null;
  }
  try {
    return JSON.parse(testo) as Personalizzazione;
  } catch {
    return null;
  }
}

// false se il browser non ha permesso di salvare.
export function salvaPersonalizzazione(personalizzazione: Personalizzazione): boolean {
  try {
    localStorage.setItem(CHIAVE, JSON.stringify(personalizzazione));
    return true;
  } catch {
    return false;
  }
}

export function cancellaPersonalizzazione() {
  try {
    localStorage.removeItem(CHIAVE);
  } catch {
    // Niente da cancellare se lo spazio locale non è disponibile.
  }
}

// Identificativo per farmaci, contenitori e telecamere. Non si usa crypto.randomUUID perché sul telefono,
// aprendo la app dalla rete di casa in http, non è disponibile.
export function nuovoId(prefisso: string): string {
  const tempo = Date.now().toString(36);
  const caso = Math.random().toString(36).slice(2, 8);
  return prefisso + "-" + tempo + caso;
}
