// Tipi dei dati scambiati con il backend: copia a mano di contratti/contratti/*.py (eventi, configurazione, report).
// Più avanti questo file si genererà dall'OpenAPI del backend (D31): finché è scritto a mano va tenuto uguale ai .py.
// Date e ore: stringhe ISO 8601 con fuso orario ("2026-12-14T08:05:00+01:00"); giorni: "AAAA-MM-GG".

// ---------- eventi.py ----------

export type TipoContenitore = "bicchiere" | "bottiglia" | "tazza";

export type TipoEvento = "caduta" | "uscita" | "bevuta" | "farmaco" | "pasto" | "alzata_notturna";

// Questi tipi fanno partire subito l'allarme Telegram (D10, D16).
export const TIPI_URGENTI: TipoEvento[] = ["caduta", "uscita"];

export interface Fonte {
  telecamera_id: string;
  analizzatore: string;
  confidenza: number;
}

export interface EventoBase {
  id: string;
  inizio: string;
  // null se l'evento è istantaneo o ancora in corso.
  fine: string | null;
  stanza: string;
  confidenza: number;
  fonti: Fonte[];
  // JPEG piccolo in base64; nelle risposte /demo/eventi è sempre null (la foto si chiede a parte).
  foto_prova: string | null;
  // True solo per lo storico simulato della casa demo (D22): va segnalato nell'interfaccia.
  simulato: boolean;
}

export interface ValoriCaduta {
  secondi_a_terra: number | null;
}

export interface ValoriUscita {
  zona_id: string;
}

export interface ValoriBevuta {
  contenitore: TipoContenitore;
  capienza_ml: number;
  altezza_contenitore_px: number;
  livello_sceso_px: number;
  percentuale: number;
  ml: number;
}

export interface ValoriFarmaco {
  // null se il farmaco non è stato riconosciuto dalle foto di scatola/blister.
  farmaco_id: string | null;
  somiglianza: number | null;
  portapillole_aperto: boolean;
  mano_alla_bocca: boolean;
}

export interface ValoriPasto {
  cibi: string[];
  percentuale_mangiata: number;
}

export interface ValoriAlzataNotturna {
  stanze: string[];
}

export interface EventoCaduta extends EventoBase {
  tipo: "caduta";
  valori: ValoriCaduta;
}

export interface EventoUscita extends EventoBase {
  tipo: "uscita";
  valori: ValoriUscita;
}

export interface EventoBevuta extends EventoBase {
  tipo: "bevuta";
  valori: ValoriBevuta;
}

export interface EventoFarmaco extends EventoBase {
  tipo: "farmaco";
  valori: ValoriFarmaco;
}

export interface EventoPasto extends EventoBase {
  tipo: "pasto";
  valori: ValoriPasto;
}

export interface EventoAlzataNotturna extends EventoBase {
  tipo: "alzata_notturna";
  valori: ValoriAlzataNotturna;
}

// Il campo "tipo" dice quale evento è (e quindi che "valori" aspettarsi).
export type Evento =
  | EventoCaduta
  | EventoUscita
  | EventoBevuta
  | EventoFarmaco
  | EventoPasto
  | EventoAlzataNotturna;

// ---------- configurazione.py (solo la parte che vede la web app) ----------

export interface FasciaOraria {
  // Ore locali "HH:MM". Se alle < dalle la fascia passa la mezzanotte (es. 22:00 → 07:00).
  dalle: string;
  alle: string;
}

export interface Anziano {
  nome: string;
  anno_nascita: number | null;
  obiettivo_acqua_ml: number;
  note: string;
}

export interface Farmaco {
  id: string;
  nome: string;
  // Testo libero, es. "1 tablet".
  dose: string;
  // Orari previsti "HH:MM".
  orari: string[];
  tolleranza_minuti: number;
  foto_ids: string[];
}

export interface Contenitore {
  id: string;
  nome: string;
  tipo: TipoContenitore;
  capienza_ml: number;
}

export interface TelecameraPrevista {
  id: string;
  nome: string;
  stanza: string;
}

export interface RegoleAllarmi {
  orari_uscita_vietati: FasciaOraria[];
  orari_notte: FasciaOraria;
  allarme_uscita_attivo: boolean;
  // Pausa dell'allarme uscita: fino a quando (ISO con fuso), null se non è in pausa.
  pausa_fino_a: string | null;
}

export interface Personalizzazione {
  anziano: Anziano;
  farmaci: Farmaco[];
  contenitori: Contenitore[];
  telecamere: TelecameraPrevista[];
  regole: RegoleAllarmi;
  fuso_orario: string;
}

// ---------- report.py ----------

export type StatoDose = "in_orario" | "in_ritardo" | "saltata" | "in_attesa";

export interface DoseFarmaco {
  farmaco_id: string;
  nome: string;
  orario_previsto: string;
  stato: StatoDose;
  ora_presa: string | null;
  minuti_ritardo: number | null;
  // false: gesto visto ma farmaco non riconosciuto dalle foto. null: dose non presa.
  farmaco_riconosciuto: boolean | null;
}

export interface PastoDelGiorno {
  ora: string;
  cibi: string[];
  percentuale_mangiata: number;
}

export interface ReportGiornaliero {
  data: string;
  acqua_ml: number;
  obiettivo_acqua_ml: number;
  bevute: number;
  dosi: DoseFarmaco[];
  pasti: PastoDelGiorno[];
  alzate_notturne: number;
  minuti_fuori_letto_notte: number;
  cadute: number;
  uscite: number;
  uscite_in_orario_vietato: number;
  simulato: boolean;
}

export interface RiassuntoGiorno {
  data: string;
  acqua_ml: number;
  dosi_previste: number;
  dosi_in_orario: number;
  dosi_in_ritardo: number;
  dosi_saltate: number;
  // null se quel giorno non si è visto nessun pasto.
  percentuale_mangiata_media: number | null;
  alzate_notturne: number;
  cadute: number;
  uscite_in_orario_vietato: number;
  simulato: boolean;
}

export interface ReportPeriodo {
  tipo: "settimanale" | "mensile";
  dal: string;
  al: string;
  giorni: RiassuntoGiorno[];
  acqua_media_ml: number;
  // Dosi in orario + in ritardo sulle dosi previste, da 0 a 100.
  aderenza_farmaci_percentuale: number;
  cadute: number;
  uscite_in_orario_vietato: number;
  alzate_notturne_medie: number;
}
