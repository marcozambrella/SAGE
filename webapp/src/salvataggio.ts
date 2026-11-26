// Personalizzazione della famiglia salvata solo nel browser (D29): nessun dato dell'utente va al server.
// Il testo JSON della personalizzazione sta in una chiave; ogni foto di un farmaco in una chiave sua
// ("sage.foto.<id>"), e nella personalizzazione restano solo gli id delle foto (Farmaco.foto_ids).
import type { Personalizzazione } from "./contratti";

const CHIAVE = "sage.personalizzazione";
const PREFISSO_FOTO = "sage.foto.";

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
      portone_zona_id: null,
      ore_inattivita: 3,
      visite_bagno_attive: false,
      promemoria_acqua_attivo: true,
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
  let letta: Personalizzazione;
  try {
    letta = JSON.parse(testo) as Personalizzazione;
  } catch {
    return null;
  }
  // Una personalizzazione salvata prima che arrivasse una regola nuova non ce l'ha: si completa con i valori
  // predefiniti (quelli salvati vincono).
  letta.regole = { ...personalizzazioneVuota().regole, ...letta.regole };
  return letta;
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
  cancellaFotoNonUsate(null);
}

// false se il browser non ha più spazio (o non permette di salvare).
export function salvaFoto(id: string, immagine: string): boolean {
  try {
    localStorage.setItem(PREFISSO_FOTO + id, immagine);
    return true;
  } catch {
    return false;
  }
}

// La foto come testo "data:image/jpeg;...", oppure null se non c'è.
export function leggiFoto(id: string): string | null {
  try {
    return localStorage.getItem(PREFISSO_FOTO + id);
  } catch {
    return null;
  }
}

// Le foto vengono salvate appena scelte, anche se poi la famiglia non salva la personalizzazione: qui si tolgono
// quelle che nessun farmaco usa più. Con null si tolgono tutte.
export function cancellaFotoNonUsate(personalizzazione: Personalizzazione | null) {
  const usate: string[] = [];
  if (personalizzazione !== null) {
    for (const farmaco of personalizzazione.farmaci) {
      for (const id of farmaco.foto_ids) {
        usate.push(PREFISSO_FOTO + id);
      }
    }
  }
  try {
    // Prima si raccolgono le chiavi, poi si cancellano: cancellare mentre si scorre sposterebbe gli indici.
    const daTogliere: string[] = [];
    for (let i = 0; i < localStorage.length; i++) {
      const chiave = localStorage.key(i);
      if (chiave !== null && chiave.startsWith(PREFISSO_FOTO) && !usate.includes(chiave)) {
        daTogliere.push(chiave);
      }
    }
    for (const chiave of daTogliere) {
      localStorage.removeItem(chiave);
    }
  } catch {
    // Spazio locale non disponibile: non c'è niente da pulire.
  }
}

// Identificativo per farmaci, contenitori e telecamere. Non si usa crypto.randomUUID perché sul telefono,
// aprendo la app dalla rete di casa in http, non è disponibile.
export function nuovoId(prefisso: string): string {
  const tempo = Date.now().toString(36);
  const caso = Math.random().toString(36).slice(2, 8);
  return prefisso + "-" + tempo + caso;
}
