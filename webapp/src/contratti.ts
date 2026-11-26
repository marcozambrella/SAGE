// Tipi dei dati scambiati con il backend: copia a mano di contratti/contratti/*.py (eventi, configurazione, report).
// Più avanti questo file si genererà dall'OpenAPI del backend (D31): finché è scritto a mano va tenuto uguale ai .py.
// Date e ore: stringhe ISO 8601 con fuso orario ("2026-12-14T08:05:00+01:00"); giorni: "AAAA-MM-GG".

// ---------- eventi.py ----------

export type TipoContenitore = "bicchiere" | "bottiglia" | "tazza";

// Quanto del piatto è stato mangiato, in tre categorie (niente percentuale: non è abbastanza precisa).
export type QuantoMangiato = "meno_di_meta" | "meta" | "tutto";

export type TipoEvento =
  | "caduta"
  | "uscita"
  | "bevuta"
  | "farmaco"
  | "pasto"
  | "alzata_notturna"
  | "sonno"
  | "agitazione"
  | "inattivita"
  | "visita_bagno";

// Questi tipi fanno partire subito l'allarme Telegram (D10, D16, inattività: Marco 25/11).
export const TIPI_URGENTI: TipoEvento[] = ["caduta", "uscita", "inattivita"];

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
  // Lo mette il backend: true se l'evento ha una foto di prova (/demo/eventi/{id}/foto).
  ha_foto: boolean;
  // True solo per lo storico simulato della casa demo (D22): va segnalato nell'interfaccia.
  simulato: boolean;
}

export interface ValoriCaduta {
  secondi_a_terra: number | null;
}

export interface ValoriUscita {
  zona_id: string;
  // Lo mette il backend con le regole degli allarmi: null finché non l'ha valutato.
  in_orario_vietato: boolean | null;
}

export interface ValoriBevuta {
  contenitore: TipoContenitore;
  // Il contenitore della personalizzazione, se riconosciuto: il backend ricalcola i ml con la sua capienza.
  contenitore_id: string | null;
  capienza_ml: number;
  altezza_contenitore_px: number;
  livello_sceso_px: number;
  percentuale: number;
  ml: number;
  // false se il livello non si vedeva (tazza opaca, poco contrasto): ml = 0 vuol dire "non misurato",
  // non "non ha bevuto". Queste bevute non si sommano ai ml: si contano a parte.
  livello_visibile: boolean;
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
  // null se non si è potuto misurare (piatto coperto, poco cibo all'inizio).
  quanto_mangiato: QuantoMangiato | null;
}

export interface ValoriAlzataNotturna {
  stanze: string[];
}

// Un pezzo di sonno a letto: inizio = si addormenta, fine = si sveglia. Una notte può averne più d'uno.
export interface ValoriSonno {
  // La zona "letto" dove dorme.
  zona_id: string;
}

// Agitazione: cammina avanti e indietro a lungo senza meta, spesso nel tardo pomeriggio e la sera (sundowning).
// inizio e fine sono quelli dell'episodio.
export interface ValoriAgitazione {
  // Quante volte ha invertito la direzione durante l'episodio.
  inversioni: number;
}

// Inattività (urgente): di giorno nessuno visto per troppe ore. inizio = l'ultima volta che si è vista una persona,
// fine = quando ricompare (null finché non ricompare).
export interface ValoriInattivita {
  // La telecamera dove la persona si è vista l'ultima volta.
  ultima_telecamera_id: string;
}

// Visita al bagno (si accende dall'app): entra dalla porta del bagno e poi esce. Nessuna telecamera nel bagno.
export interface ValoriVisitaBagno {
  // La zona "bagno" (la porta del bagno vista da fuori).
  zona_id: string;
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

export interface EventoSonno extends EventoBase {
  tipo: "sonno";
  valori: ValoriSonno;
}

export interface EventoAgitazione extends EventoBase {
  tipo: "agitazione";
  valori: ValoriAgitazione;
}

export interface EventoInattivita extends EventoBase {
  tipo: "inattivita";
  valori: ValoriInattivita;
}

export interface EventoVisitaBagno extends EventoBase {
  tipo: "visita_bagno";
  valori: ValoriVisitaBagno;
}

// Il campo "tipo" dice quale evento è (e quindi che "valori" aspettarsi).
export type Evento =
  | EventoCaduta
  | EventoUscita
  | EventoBevuta
  | EventoFarmaco
  | EventoPasto
  | EventoAlzataNotturna
  | EventoSonno
  | EventoAgitazione
  | EventoInattivita
  | EventoVisitaBagno;

// ---------- configurazione.py (solo la parte che vede la web app) ----------

export interface FasciaOraria {
  // Ore locali "HH:MM" (00:00 - 23:59, il backend rifiuta gli orari scritti male).
  // Se alle < dalle la fascia passa la mezzanotte (es. 22:00 → 07:00).
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
  // Id della zona "porta" che è il portone di casa: l'uscita si conta solo lì. null: valgono tutte le zone porta.
  // Si sceglierà nell'app quando le telecamere si potranno collegare: per ora la web app non lo imposta.
  portone_zona_id: string | null;
  // Ore di giorno (fuori da orari_notte) senza vedere nessuno prima dell'allarme di inattività. Di base 3.
  ore_inattivita: number;
  // Visite al bagno: spente finché la famiglia non le accende dall'app.
  visite_bagno_attive: boolean;
  // Al massimo un promemoria Telegram al giorno, tra le 16:00 e le 17:00, se ha bevuto meno di metà dell'obiettivo.
  promemoria_acqua_attivo: boolean;
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

// Cosa è cambiato nel periodo rispetto al solito (le 4 settimane prima), per il report.
export interface CambiamentoRoutine {
  // Che cosa: "sveglia", "acqua", "pasti", "sonno", "agitazione", "bagno", "uscite".
  cosa: string;
  // Frase in inglese pronta per la web app, es. "Wakes up about 1 hour later than usual".
  testo: string;
}

export interface PastoDelGiorno {
  ora: string;
  cibi: string[];
  quanto_mangiato: QuantoMangiato | null;
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
  // Sonno della notte che finisce la mattina di questo giorno. null se non si è visto dormire.
  sonno_minuti: number | null;
  // Inizio del primo pezzo di sonno e fine dell'ultimo (ISO con fuso).
  addormentato_alle: string | null;
  sveglio_alle: string | null;
  agitazione_minuti: number;
  allarmi_inattivita: number;
  // Contate solo se regole.visite_bagno_attive: la web app le mostra solo allora.
  visite_bagno: number;
  visite_bagno_notte: number;
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
  pasti: number;
  // Pasti con meno di metà del piatto mangiato: il segnale che conta per la famiglia.
  pasti_meno_di_meta: number;
  alzate_notturne: number;
  // Come nel report giornaliero: null se quella notte non si è visto dormire.
  sonno_minuti: number | null;
  agitazione_minuti: number;
  visite_bagno: number;
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
  // Dosi in orario + in ritardo sulle dosi già valutate (le "in_attesa" non contano), da 0 a 100.
  // null se nel periodo non c'è ancora nessuna dose valutata: la web app scrive "No data".
  aderenza_farmaci_percentuale: number | null;
  cadute: number;
  uscite_in_orario_vietato: number;
  alzate_notturne_medie: number;
  // Media sulle notti in cui si è visto dormire; null se nessuna.
  sonno_medio_minuti: number | null;
  // Solo quello che è cambiato davvero: lista vuota = "No big changes".
  cambiamenti: CambiamentoRoutine[];
}

// ---------- API.md: GET /demo/periodo ----------

// Primo e ultimo giorno (AAAA-MM-GG) con eventi nella casa demo; null se non ce ne sono.
export interface PeriodoDemo {
  dal: string | null;
  al: string | null;
}
