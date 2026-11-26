// ==========================================================================================================
//  DATI FINTI DI SVILUPPO — NON sono risultati dei modelli né dati della casa demo vera.
//  Servono solo finché il backend non è pronto: api.ts li usa quando VITE_API_URL non è impostato.
//  Rispettano esattamente i tipi di contratti.ts (copia di contratti/contratti/*.py).
//  Il "giorno vero" (GIORNO_DEMO) imita i risultati dei video registrati; gli altri giorni imitano lo storico
//  simulato (simulato: true), con una piccola storia: nell'ultima settimana si beve meno, ci si alza più di notte
//  e si dorme meno.
// ==========================================================================================================
import type {
  CambiamentoRoutine,
  DoseFarmaco,
  QuantoMangiato,
  Evento,
  EventoBase,
  PastoDelGiorno,
  PeriodoDemo,
  Personalizzazione,
  ReportGiornaliero,
  ReportPeriodo,
  RiassuntoGiorno,
  StatoDose,
  TipoContenitore,
  TipoEvento,
} from "./contratti";
import { spostaGiorno } from "./formato";

// Il giorno dei video registrati (finto) e il primo giorno dello storico simulato.
export const GIORNO_VERO = "2026-12-14";
export const PRIMO_GIORNO = "2026-11-01";

// In novembre e dicembre Roma è a +01:00.
function ora(giorno: string, hhmm: string): string {
  return giorno + "T" + hhmm + ":00+01:00";
}

export const PERSONALIZZAZIONE_DEMO: Personalizzazione = {
  anziano: { nome: "Rosa", anno_nascita: 1942, obiettivo_acqua_ml: 1500, note: "" },
  farmaci: [
    {
      id: "f-memantina",
      nome: "Memantine",
      dose: "1 tablet",
      orari: ["08:00", "20:00"],
      tolleranza_minuti: 30,
      foto_ids: [],
    },
    { id: "f-ramipril", nome: "Ramipril", dose: "1 tablet", orari: ["08:00"], tolleranza_minuti: 45, foto_ids: [] },
    { id: "f-donepezil", nome: "Donepezil", dose: "1 tablet", orari: ["20:00"], tolleranza_minuti: 30, foto_ids: [] },
  ],
  contenitori: [
    { id: "c-bicchiere", nome: "Blue glass", tipo: "bicchiere", capienza_ml: 250 },
    { id: "c-bottiglia", nome: "Water bottle", tipo: "bottiglia", capienza_ml: 1000 },
    { id: "c-tazza", nome: "Tea cup", tipo: "tazza", capienza_ml: 200 },
  ],
  telecamere: [
    { id: "t-cucina", nome: "Kitchen camera", stanza: "Kitchen" },
    { id: "t-soggiorno", nome: "Living room camera", stanza: "Living room" },
    { id: "t-ingresso", nome: "Hallway camera", stanza: "Hallway" },
    { id: "t-camera", nome: "Bedroom camera", stanza: "Bedroom" },
  ],
  regole: {
    orari_uscita_vietati: [{ dalle: "20:00", alle: "07:00" }],
    orari_notte: { dalle: "22:00", alle: "07:00" },
    allarme_uscita_attivo: true,
    pausa_fino_a: null,
    portone_zona_id: null,
    ore_inattivita: 3,
    // Nella casa demo le visite al bagno sono accese, così la sezione si vede.
    visite_bagno_attive: true,
    promemoria_acqua_attivo: true,
  },
  fuso_orario: "Europe/Rome",
};

// Campi comuni di un evento visto da una sola telecamera.
function base(
  id: string,
  inizio: string,
  fine: string | null,
  stanza: string,
  telecameraId: string,
  analizzatore: string,
  confidenza: number,
  simulato: boolean,
): EventoBase {
  return {
    id: id,
    inizio: inizio,
    fine: fine,
    stanza: stanza,
    confidenza: confidenza,
    fonti: [{ telecamera_id: telecameraId, analizzatore: analizzatore, confidenza: confidenza }],
    foto_prova: null,
    ha_foto: false,
    simulato: simulato,
  };
}

// ---------- Sonno (API.md, Marco 25/11) ----------
// Una notte è fatta di pezzi di sonno: il primo inizia quando si addormenta la sera, l'ultimo finisce quando si
// sveglia al mattino, i buchi in mezzo sono le alzate notturne. La notte conta nel giorno in cui finisce.

type PezzoDiSonno = {
  inizio: string;
  fine: string;
};

// Minuti in tutto di una lista di pezzi con inizio e fine (sonno, episodi di agitazione...).
function minutiDeiPezzi(pezzi: PezzoDiSonno[]): number {
  let minuti = 0;
  for (const pezzo of pezzi) {
    minuti = minuti + (new Date(pezzo.fine).getTime() - new Date(pezzo.inizio).getTime()) / 60000;
  }
  return minuti;
}

function eventiSonno(pezzi: PezzoDiSonno[], prefissoId: string, simulato: boolean): Evento[] {
  const eventi: Evento[] = [];
  for (let i = 0; i < pezzi.length; i++) {
    eventi.push({
      ...base(
        prefissoId + "-sonno-" + i,
        pezzi[i].inizio,
        pezzi[i].fine,
        "Bedroom",
        "t-camera",
        "sonno",
        0.9,
        simulato,
      ),
      tipo: "sonno",
      valori: { zona_id: "z-letto" },
    });
  }
  return eventi;
}

// Bevuta calcolata come in D9: ml = livello sceso / altezza del contenitore × capienza.
function bevuta(
  id: string,
  inizio: string,
  stanza: string,
  telecameraId: string,
  contenitore: TipoContenitore,
  contenitoreId: string,
  capienza: number,
  altezzaPx: number,
  scesoPx: number,
  simulato: boolean,
): Evento {
  const percentuale = (scesoPx / altezzaPx) * 100;
  const ml = (percentuale / 100) * capienza;
  return {
    ...base(id, inizio, null, stanza, telecameraId, "bevuta", 0.86, simulato),
    tipo: "bevuta",
    valori: {
      contenitore: contenitore,
      contenitore_id: contenitoreId,
      capienza_ml: capienza,
      altezza_contenitore_px: altezzaPx,
      livello_sceso_px: scesoPx,
      percentuale: percentuale,
      ml: ml,
      livello_visibile: true,
    },
  };
}

// Bevuta vista (contenitore alla bocca) ma con il livello non visibile, per esempio in una tazza opaca: 0 ml
// vuol dire "non misurato". Non entra nei ml del report.
function bevutaNonMisurata(
  id: string,
  inizio: string,
  stanza: string,
  telecameraId: string,
  contenitore: TipoContenitore,
  contenitoreId: string,
  capienza: number,
  simulato: boolean,
): Evento {
  return {
    ...base(id, inizio, null, stanza, telecameraId, "bevuta", 0.78, simulato),
    tipo: "bevuta",
    valori: {
      contenitore: contenitore,
      contenitore_id: contenitoreId,
      capienza_ml: capienza,
      altezza_contenitore_px: 90,
      livello_sceso_px: 0,
      percentuale: 0,
      ml: 0,
      livello_visibile: false,
    },
  };
}

// ---------- Agitazione, inattività, visite al bagno (Marco, 25/11) ----------

// Numero da usare come seme di caso(): sempre uguale per lo stesso giorno.
function semeDelGiorno(giorno: string): number {
  return Number(giorno.slice(5, 7)) * 31 + Number(giorno.slice(8, 10));
}

type Episodio = {
  inizio: string;
  fine: string;
  inversioni: number;
};

// Episodi di agitazione (cammina avanti e indietro): nel tardo pomeriggio e la sera (sundowning), più spesso
// nell'ultima settimana. Ogni tanto anche uno breve nel primo pomeriggio.
function episodiAgitazione(giorno: string): Episodio[] {
  if (giorno === GIORNO_VERO) {
    return [
      { inizio: ora(giorno, "17:05"), fine: ora(giorno, "17:32"), inversioni: 18 },
      { inizio: ora(giorno, "18:45"), fine: ora(giorno, "19:02"), inversioni: 11 },
    ];
  }
  const seme = semeDelGiorno(giorno);
  let probabilita = 0.35;
  if (giorno >= spostaGiorno(GIORNO_VERO, -7)) {
    probabilita = 0.8;
  }
  const episodi: Episodio[] = [];
  if (caso(seme, 11) < probabilita / 3) {
    const minuti = 8 + Math.round(caso(seme, 12) * 10);
    episodi.push({ inizio: ora(giorno, "14:20"), fine: ora(giorno, aggiungiMinuti("14:20", minuti)), inversioni: 6 });
  }
  if (caso(seme, 8) < probabilita) {
    const minuti = 10 + Math.round(caso(seme, 9) * 25);
    const inizio = aggiungiMinuti("16:30", Math.round(caso(seme, 10) * 150));
    const fine = aggiungiMinuti(inizio, minuti);
    episodi.push({ inizio: ora(giorno, inizio), fine: ora(giorno, fine), inversioni: Math.round(minuti * 0.6) });
  }
  return episodi;
}

// Un pomeriggio in cui nessuno si è visto per più di 3 ore: allarme urgente di inattività (una volta sola).
const INATTIVITA = { giorno: "2026-12-06", ultimaVolta: "13:20", ricompare: "16:45" };

// Durante l'inattività nessuna telecamera ha visto nessuno: in quelle ore restano solo l'evento di inattività
// e niente altro (bevute, visite al bagno, agitazione...).
function senzaEventiDuranteInattivita(eventi: Evento[]): Evento[] {
  const rimasti: Evento[] = [];
  for (const evento of eventi) {
    const hhmm = evento.inizio.slice(11, 16);
    const durante = hhmm >= INATTIVITA.ultimaVolta && hhmm < INATTIVITA.ricompare;
    if (evento.tipo === "inattivita" || !durante) {
      rimasti.push(evento);
    }
  }
  return rimasti;
}

function allarmiInattivita(giorno: string): number {
  if (giorno === INATTIVITA.giorno) {
    return 1;
  }
  return 0;
}

// Visite al bagno: cinque di giorno e una per ogni alzata notturna (si alza per andare in bagno), 4 minuti l'una.
const ORE_BAGNO_GIORNO = ["07:20", "10:45", "13:35", "16:55", "21:25"];

function visiteBagno(giorno: string, oreAlzate: string[]): PezzoDiSonno[] {
  const visite: PezzoDiSonno[] = [];
  for (const alzata of oreAlzate) {
    const inizio = aggiungiMinuti(alzata, 2);
    visite.push({ inizio: ora(giorno, inizio), fine: ora(giorno, aggiungiMinuti(inizio, 4)) });
  }
  for (const inizio of ORE_BAGNO_GIORNO) {
    visite.push({ inizio: ora(giorno, inizio), fine: ora(giorno, aggiungiMinuti(inizio, 4)) });
  }
  return visite;
}

function eventiRicercaAlzheimer(giorno: string, oreAlzate: string[], simulato: boolean): Evento[] {
  const eventi: Evento[] = [];
  const prefisso = "dev-" + giorno;
  const episodi = episodiAgitazione(giorno);
  for (let i = 0; i < episodi.length; i++) {
    const episodio = episodi[i];
    eventi.push({
      ...base(
        prefisso + "-agitazione-" + i,
        episodio.inizio,
        episodio.fine,
        "Living room",
        "t-soggiorno",
        "agitazione",
        0.82,
        simulato,
      ),
      tipo: "agitazione",
      valori: { inversioni: episodio.inversioni },
    });
  }
  const visite = visiteBagno(giorno, oreAlzate);
  for (let i = 0; i < visite.length; i++) {
    eventi.push({
      ...base(
        prefisso + "-bagno-" + i,
        visite[i].inizio,
        visite[i].fine,
        "Hallway",
        "t-ingresso",
        "bagno",
        0.88,
        simulato,
      ),
      tipo: "visita_bagno",
      valori: { zona_id: "z-bagno" },
    });
  }
  if (allarmiInattivita(giorno) > 0) {
    const inizio = ora(giorno, INATTIVITA.ultimaVolta);
    const fine = ora(giorno, INATTIVITA.ricompare);
    eventi.push({
      ...base(prefisso + "-inattivita", inizio, fine, "Living room", "t-soggiorno", "inattivita", 0.95, simulato),
      tipo: "inattivita",
      valori: { ultima_telecamera_id: "t-soggiorno" },
    });
  }
  return eventi;
}

// Cambi di routine rispetto alle 4 settimane prima. Nei dati finti solo i periodi che toccano l'ultima settimana,
// quella della piccola storia; negli altri non è cambiato niente ("No big changes").
const CAMBIAMENTI_ULTIMA_SETTIMANA: CambiamentoRoutine[] = [
  { cosa: "sonno", testo: "Sleeps about 1 hour less than usual" },
  { cosa: "sveglia", testo: "Wakes up about 20 minutes earlier than usual" },
  { cosa: "acqua", testo: "Drinks about 200 ml less water a day than usual" },
  { cosa: "pasti", testo: "More meals with less than half eaten" },
  { cosa: "agitazione", testo: "More restless pacing in the late afternoon and evening" },
  { cosa: "bagno", testo: "Goes to the bathroom more often at night" },
];

// ---------- Il giorno "vero" (imita i risultati dei modelli sui video registrati) ----------

const G = GIORNO_VERO;

function eventiGiornoVero(): Evento[] {
  const eventi: Evento[] = [];
  eventi.push({
    ...base("ev-0214", ora(G, "02:14"), ora(G, "02:26"), "Bedroom", "t-camera", "alzata_notturna", 0.93, false),
    tipo: "alzata_notturna",
    valori: { stanze: ["Bedroom", "Hallway"] },
  });
  eventi.push({
    ...base("ev-0540", ora(G, "05:40"), ora(G, "05:46"), "Bedroom", "t-camera", "alzata_notturna", 0.9, false),
    tipo: "alzata_notturna",
    valori: { stanze: ["Bedroom"] },
  });
  eventi.push(bevuta("ev-0750", ora(G, "07:50"), "Kitchen", "t-cucina", "tazza", "c-tazza", 200, 90, 90, false));
  eventi.push({
    ...base("ev-0807", ora(G, "08:07"), null, "Kitchen", "t-cucina", "farmaco", 0.88, false),
    tipo: "farmaco",
    valori: { farmaco_id: "f-memantina", somiglianza: 0.91, portapillole_aperto: true, mano_alla_bocca: true },
  });
  eventi.push({
    ...base("ev-0815", ora(G, "08:15"), ora(G, "08:38"), "Kitchen", "t-cucina", "pasto", 0.84, false),
    tipo: "pasto",
    valori: { cibi: ["bread", "milk", "biscuits"], quanto_mangiato: "tutto" },
  });
  eventi.push({
    ...base("ev-0852", ora(G, "08:52"), null, "Kitchen", "t-cucina", "farmaco", 0.85, false),
    tipo: "farmaco",
    valori: { farmaco_id: "f-ramipril", somiglianza: 0.87, portapillole_aperto: true, mano_alla_bocca: true },
  });
  eventi.push(
    bevuta("ev-1030", ora(G, "10:30"), "Living room", "t-soggiorno", "bicchiere", "c-bicchiere", 250, 120, 96, false),
  );
  eventi.push({
    ...base("ev-1240", ora(G, "12:40"), ora(G, "13:05"), "Kitchen", "t-cucina", "pasto", 0.82, false),
    tipo: "pasto",
    valori: { cibi: ["pasta with tomato sauce", "green salad"], quanto_mangiato: "meta" },
  });
  eventi.push(
    bevuta("ev-1245", ora(G, "12:45"), "Kitchen", "t-cucina", "bicchiere", "c-bicchiere", 250, 120, 72, false),
  );
  eventi.push(
    bevuta("ev-1500", ora(G, "15:00"), "Living room", "t-soggiorno", "bottiglia", "c-bottiglia", 1000, 260, 78, false),
  );
  // La caduta l'hanno vista due telecamere: il backend ha coordinato i due eventi grezzi in uno.
  eventi.push({
    ...base("ev-1520", ora(G, "15:20"), ora(G, "15:21"), "Living room", "t-soggiorno", "caduta", 0.94, false),
    ha_foto: true,
    fonti: [
      { telecamera_id: "t-soggiorno", analizzatore: "caduta", confidenza: 0.94 },
      { telecamera_id: "t-ingresso", analizzatore: "caduta", confidenza: 0.71 },
    ],
    tipo: "caduta",
    valori: { secondi_a_terra: 48 },
  });
  // Tè nella tazza opaca: la bevuta si vede, il livello no.
  eventi.push(
    bevutaNonMisurata("ev-1610", ora(G, "16:10"), "Living room", "t-soggiorno", "tazza", "c-tazza", 200, false),
  );
  eventi.push(
    bevuta("ev-1730", ora(G, "17:30"), "Living room", "t-soggiorno", "bicchiere", "c-bicchiere", 250, 120, 96, false),
  );
  eventi.push({
    ...base("ev-1930", ora(G, "19:30"), ora(G, "19:52"), "Kitchen", "t-cucina", "pasto", 0.8, false),
    tipo: "pasto",
    valori: { cibi: ["vegetable soup", "cheese"], quanto_mangiato: "meno_di_meta" },
  });
  eventi.push(
    bevuta("ev-1940", ora(G, "19:40"), "Kitchen", "t-cucina", "bicchiere", "c-bicchiere", 250, 120, 48, false),
  );
  eventi.push({
    ...base("ev-2012", ora(G, "20:12"), null, "Kitchen", "t-cucina", "farmaco", 0.86, false),
    tipo: "farmaco",
    valori: { farmaco_id: "f-memantina", somiglianza: 0.89, portapillole_aperto: true, mano_alla_bocca: true },
  });
  eventi.push({
    ...base("ev-2110", ora(G, "21:10"), null, "Hallway", "t-ingresso", "uscita", 0.91, false),
    ha_foto: true,
    tipo: "uscita",
    valori: { zona_id: "porta-ingresso", in_orario_vietato: true },
  });
  for (const evento of eventiSonno(NOTTE_GIORNO_VERO, "ev", false)) {
    eventi.push(evento);
  }
  for (const evento of eventiRicercaAlzheimer(G, ORE_ALZATE_GIORNO_VERO, false)) {
    eventi.push(evento);
  }
  eventi.sort(confrontaInizio);
  return eventi;
}

// Le due alzate della notte vera: ogni volta anche una visita al bagno.
const ORE_ALZATE_GIORNO_VERO = ["02:14", "05:40"];

// La notte tra il 13 e il 14: a letto alle 22:40, due alzate (02:14 e 05:40), sveglia alle 06:55.
const NOTTE_GIORNO_VERO: PezzoDiSonno[] = [
  { inizio: ora("2026-12-13", "22:40"), fine: ora(G, "02:14") },
  { inizio: ora(G, "02:26"), fine: ora(G, "05:40") },
  { inizio: ora(G, "05:46"), fine: ora(G, "06:55") },
];

const REPORT_GIORNO_VERO: ReportGiornaliero = {
  data: G,
  acqua_ml: 1150,
  obiettivo_acqua_ml: 1500,
  bevute: 6,
  dosi: [
    {
      farmaco_id: "f-memantina",
      nome: "Memantine",
      orario_previsto: "08:00",
      stato: "in_orario",
      ora_presa: ora(G, "08:07"),
      minuti_ritardo: null,
      farmaco_riconosciuto: true,
    },
    {
      farmaco_id: "f-ramipril",
      nome: "Ramipril",
      orario_previsto: "08:00",
      stato: "in_ritardo",
      ora_presa: ora(G, "08:52"),
      minuti_ritardo: 52,
      farmaco_riconosciuto: true,
    },
    {
      farmaco_id: "f-memantina",
      nome: "Memantine",
      orario_previsto: "20:00",
      stato: "in_orario",
      ora_presa: ora(G, "20:12"),
      minuti_ritardo: null,
      farmaco_riconosciuto: true,
    },
    {
      farmaco_id: "f-donepezil",
      nome: "Donepezil",
      orario_previsto: "20:00",
      stato: "saltata",
      ora_presa: null,
      minuti_ritardo: null,
      farmaco_riconosciuto: null,
    },
  ],
  pasti: [
    { ora: ora(G, "08:15"), cibi: ["bread", "milk", "biscuits"], quanto_mangiato: "tutto" },
    { ora: ora(G, "12:40"), cibi: ["pasta with tomato sauce", "green salad"], quanto_mangiato: "meta" },
    { ora: ora(G, "19:30"), cibi: ["vegetable soup", "cheese"], quanto_mangiato: "meno_di_meta" },
  ],
  alzate_notturne: 2,
  minuti_fuori_letto_notte: 18,
  sonno_minuti: minutiDeiPezzi(NOTTE_GIORNO_VERO),
  addormentato_alle: NOTTE_GIORNO_VERO[0].inizio,
  sveglio_alle: NOTTE_GIORNO_VERO[2].fine,
  agitazione_minuti: minutiDeiPezzi(episodiAgitazione(G)),
  allarmi_inattivita: 0,
  visite_bagno: visiteBagno(G, ORE_ALZATE_GIORNO_VERO).length,
  visite_bagno_notte: ORE_ALZATE_GIORNO_VERO.length,
  cadute: 1,
  uscite: 1,
  uscite_in_orario_vietato: 1,
  simulato: false,
};

// ---------- Storico simulato: un riassunto per giorno, e da quello report ed eventi ----------

// Numero "a caso" ma sempre uguale per lo stesso giorno, tra 0 e 1.
function caso(indice: number, seme: number): number {
  const x = Math.sin(indice * 12.9898 + seme * 78.233) * 43758.5453;
  return x - Math.floor(x);
}

// Giorni con un evento particolare nello storico simulato.
const GIORNI_CON_CADUTA = ["2026-11-27"];
const GIORNI_CON_USCITA_VIETATA = ["2026-12-03", "2026-12-11"];
// Una notte in cui la telecamera della camera da letto era spenta: sonno non visto (null).
const NOTTI_NON_VISTE = ["2026-11-19"];
// Le alzate notturne simulate: le prime N di queste ore, 9 minuti l'una.
const ORE_ALZATE = ["02:30", "04:45", "05:50"];

// La notte che finisce la mattina di "giorno", con le sue alzate. null se quella notte non si è vista.
function notteSimulata(giorno: string, alzate: number): PezzoDiSonno[] | null {
  if (NOTTI_NON_VISTE.includes(giorno)) {
    return null;
  }
  const seme = semeDelGiorno(giorno);
  // A letto tra le 22:20 e le 23:00, sveglia tra le 06:30 e le 07:10.
  let minutiDopoLe22 = 20 + Math.round(caso(seme, 6) * 40);
  let minutiDopoLe6 = 30 + Math.round(caso(seme, 7) * 40);
  // Nell'ultima settimana va a letto più tardi e si sveglia prima.
  if (giorno >= spostaGiorno(G, -7)) {
    minutiDopoLe22 = minutiDopoLe22 + 30;
    minutiDopoLe6 = minutiDopoLe6 - 20;
  }
  const pezzi: PezzoDiSonno[] = [];
  let inizio = ora(spostaGiorno(giorno, -1), aggiungiMinuti("22:00", minutiDopoLe22));
  for (let i = 0; i < alzate; i++) {
    pezzi.push({ inizio: inizio, fine: ora(giorno, ORE_ALZATE[i]) });
    inizio = ora(giorno, aggiungiMinuti(ORE_ALZATE[i], 9));
  }
  pezzi.push({ inizio: inizio, fine: ora(giorno, aggiungiMinuti("06:00", minutiDopoLe6)) });
  return pezzi;
}

function sonnoDellaNotte(notte: PezzoDiSonno[] | null): number | null {
  if (notte === null) {
    return null;
  }
  return minutiDeiPezzi(notte);
}

function riassuntoSimulato(giorno: string, indice: number): RiassuntoGiorno {
  // indice = quanti giorni prima del giorno vero.
  const ultimaSettimana = indice <= 7;
  let acqua = 1250 + caso(indice, 1) * 400;
  let alzate = Math.floor(caso(indice, 2) * 2);
  if (ultimaSettimana) {
    acqua = acqua - 200;
    alzate = 1 + Math.floor(caso(indice, 2) * 3);
  }
  let saltate = 0;
  if (caso(indice, 3) < 0.18) {
    saltate = 1;
  }
  let inRitardo = 0;
  if (caso(indice, 4) < 0.3) {
    inRitardo = 1;
  }
  // Pasti con meno di metà mangiato: più spesso nell'ultima settimana (fa parte della piccola storia).
  let pastiMenoDiMeta = 0;
  let probabilitaPocoCibo = 0.2;
  if (ultimaSettimana) {
    probabilitaPocoCibo = 0.5;
  }
  if (caso(indice, 5) < probabilitaPocoCibo) {
    pastiMenoDiMeta = 1;
  }
  let cadute = 0;
  if (GIORNI_CON_CADUTA.includes(giorno)) {
    cadute = 1;
  }
  let usciteVietate = 0;
  if (GIORNI_CON_USCITA_VIETATA.includes(giorno)) {
    usciteVietate = 1;
  }
  return {
    data: giorno,
    acqua_ml: Math.round(acqua / 10) * 10,
    dosi_previste: 4,
    dosi_in_orario: 4 - saltate - inRitardo,
    dosi_in_ritardo: inRitardo,
    dosi_saltate: saltate,
    pasti: 3,
    pasti_meno_di_meta: pastiMenoDiMeta,
    alzate_notturne: alzate,
    sonno_minuti: sonnoDellaNotte(notteSimulata(giorno, alzate)),
    agitazione_minuti: minutiDeiPezzi(episodiAgitazione(giorno)),
    visite_bagno: visiteBagno(giorno, ORE_ALZATE.slice(0, alzate)).length,
    cadute: cadute,
    uscite_in_orario_vietato: usciteVietate,
    simulato: true,
  };
}

function riassuntoGiornoVero(): RiassuntoGiorno {
  return {
    data: G,
    acqua_ml: 1150,
    dosi_previste: 4,
    dosi_in_orario: 2,
    dosi_in_ritardo: 1,
    dosi_saltate: 1,
    pasti: 3,
    pasti_meno_di_meta: 1,
    alzate_notturne: 2,
    sonno_minuti: minutiDeiPezzi(NOTTE_GIORNO_VERO),
    agitazione_minuti: REPORT_GIORNO_VERO.agitazione_minuti,
    visite_bagno: REPORT_GIORNO_VERO.visite_bagno,
    cadute: 1,
    uscite_in_orario_vietato: 1,
    simulato: false,
  };
}

// null se il giorno è fuori dallo storico della casa demo.
function riassuntoDelGiorno(giorno: string): RiassuntoGiorno | null {
  if (giorno === G) {
    return riassuntoGiornoVero();
  }
  if (giorno < PRIMO_GIORNO || giorno > G) {
    return null;
  }
  let indice = 0;
  let cursore = giorno;
  while (cursore < G) {
    cursore = spostaGiorno(cursore, 1);
    indice = indice + 1;
  }
  return riassuntoSimulato(giorno, indice);
}

const MENU = [
  ["porridge", "banana"],
  ["risotto", "peas"],
  ["minestrone", "bread"],
  ["toast", "jam", "tea"],
  ["baked fish", "potatoes"],
  ["omelette", "spinach"],
];

// Le quattro dosi previste ogni giorno, nell'ordine in cui si mostrano.
const DOSI_PREVISTE = [
  { farmaco_id: "f-memantina", nome: "Memantine", orario: "08:00" },
  { farmaco_id: "f-ramipril", nome: "Ramipril", orario: "08:00" },
  { farmaco_id: "f-memantina", nome: "Memantine", orario: "20:00" },
  { farmaco_id: "f-donepezil", nome: "Donepezil", orario: "20:00" },
];

function aggiungiMinuti(hhmm: string, minuti: number): string {
  const totale = Number(hhmm.slice(0, 2)) * 60 + Number(hhmm.slice(3, 5)) + minuti;
  const ore = Math.floor(totale / 60);
  const resto = totale % 60;
  return String(ore).padStart(2, "0") + ":" + String(resto).padStart(2, "0");
}

function reportSimulato(riassunto: RiassuntoGiorno): ReportGiornaliero {
  const giorno = riassunto.data;
  // Stati assegnati in ordine: prima le dosi in orario, poi quelle in ritardo, poi le saltate (di sera).
  const stati: StatoDose[] = [];
  for (let i = 0; i < riassunto.dosi_in_orario; i++) {
    stati.push("in_orario");
  }
  for (let i = 0; i < riassunto.dosi_in_ritardo; i++) {
    stati.push("in_ritardo");
  }
  for (let i = 0; i < riassunto.dosi_saltate; i++) {
    stati.push("saltata");
  }
  const dosi: DoseFarmaco[] = [];
  for (let i = 0; i < DOSI_PREVISTE.length; i++) {
    const prevista = DOSI_PREVISTE[i];
    const stato = stati[i];
    let oraPresa: string | null = null;
    let minutiRitardo: number | null = null;
    let riconosciuto: boolean | null = null;
    if (stato === "in_orario") {
      oraPresa = ora(giorno, aggiungiMinuti(prevista.orario, 6));
      riconosciuto = true;
    }
    if (stato === "in_ritardo") {
      oraPresa = ora(giorno, aggiungiMinuti(prevista.orario, 50));
      minutiRitardo = 50;
      riconosciuto = true;
    }
    dosi.push({
      farmaco_id: prevista.farmaco_id,
      nome: prevista.nome,
      orario_previsto: prevista.orario,
      stato: stato,
      ora_presa: oraPresa,
      minuti_ritardo: minutiRitardo,
      farmaco_riconosciuto: riconosciuto,
    });
  }
  // Colazione tutta; pranzo a metà, oppure non misurato un giorno su cinque; cena con meno di metà nei giorni
  // in cui il riassunto lo dice, altrimenti tutta.
  const numeroGiorno = Number(giorno.slice(8, 10));
  let pranzo: QuantoMangiato | null = "meta";
  if (numeroGiorno % 5 === 0) {
    pranzo = null;
  }
  let cena: QuantoMangiato = "tutto";
  if (riassunto.pasti_meno_di_meta > 0) {
    cena = "meno_di_meta";
  }
  // A che ora si è addormentato e svegliato: inizio del primo pezzo di sonno e fine dell'ultimo.
  const notte = notteSimulata(giorno, riassunto.alzate_notturne);
  let addormentato: string | null = null;
  let sveglio: string | null = null;
  if (notte !== null) {
    addormentato = notte[0].inizio;
    sveglio = notte[notte.length - 1].fine;
  }
  const pasti: PastoDelGiorno[] = [
    { ora: ora(giorno, "08:20"), cibi: MENU[numeroGiorno % 6], quanto_mangiato: "tutto" },
    { ora: ora(giorno, "12:45"), cibi: MENU[(numeroGiorno + 1) % 6], quanto_mangiato: pranzo },
    { ora: ora(giorno, "19:15"), cibi: MENU[(numeroGiorno + 2) % 6], quanto_mangiato: cena },
  ];
  return {
    data: giorno,
    acqua_ml: riassunto.acqua_ml,
    obiettivo_acqua_ml: 1500,
    bevute: 5,
    dosi: dosi,
    pasti: pasti,
    alzate_notturne: riassunto.alzate_notturne,
    minuti_fuori_letto_notte: riassunto.alzate_notturne * 9,
    sonno_minuti: riassunto.sonno_minuti,
    addormentato_alle: addormentato,
    sveglio_alle: sveglio,
    agitazione_minuti: riassunto.agitazione_minuti,
    allarmi_inattivita: allarmiInattivita(giorno),
    visite_bagno: riassunto.visite_bagno,
    visite_bagno_notte: riassunto.alzate_notturne,
    cadute: riassunto.cadute,
    uscite: riassunto.uscite_in_orario_vietato,
    uscite_in_orario_vietato: riassunto.uscite_in_orario_vietato,
    simulato: true,
  };
}

function eventiSimulati(report: ReportGiornaliero): Evento[] {
  const giorno = report.data;
  const eventi: Evento[] = [];
  for (let i = 0; i < report.alzate_notturne; i++) {
    const inizio = ORE_ALZATE[i];
    eventi.push({
      ...base(
        "sim-" + giorno + "-alzata-" + i,
        ora(giorno, inizio),
        ora(giorno, aggiungiMinuti(inizio, 9)),
        "Bedroom",
        "t-camera",
        "alzata_notturna",
        0.9,
        true,
      ),
      tipo: "alzata_notturna",
      valori: { stanze: ["Bedroom"] },
    });
  }
  // Cinque bevute da un bicchiere da 250 ml: il livello sceso dà i ml del giorno divisi in parti uguali.
  const oreBevute = ["08:00", "10:30", "13:00", "16:00", "18:30"];
  const mlPerBevuta = report.acqua_ml / 5;
  for (let i = 0; i < oreBevute.length; i++) {
    const scesoPx = (mlPerBevuta / 250) * 120;
    eventi.push(
      bevuta(
        "sim-" + giorno + "-bevuta-" + i,
        ora(giorno, oreBevute[i]),
        "Kitchen",
        "t-cucina",
        "bicchiere",
        "c-bicchiere",
        250,
        120,
        scesoPx,
        true,
      ),
    );
  }
  // Un giorno su tre, anche un tè nella tazza opaca, non misurato.
  if (Number(giorno.slice(8, 10)) % 3 === 0) {
    eventi.push(
      bevutaNonMisurata(
        "sim-" + giorno + "-tazza",
        ora(giorno, "16:30"),
        "Living room",
        "t-soggiorno",
        "tazza",
        "c-tazza",
        200,
        true,
      ),
    );
  }
  for (let i = 0; i < report.dosi.length; i++) {
    const dose = report.dosi[i];
    if (dose.ora_presa === null) {
      continue;
    }
    eventi.push({
      ...base("sim-" + giorno + "-farmaco-" + i, dose.ora_presa, null, "Kitchen", "t-cucina", "farmaco", 0.85, true),
      tipo: "farmaco",
      valori: { farmaco_id: dose.farmaco_id, somiglianza: 0.88, portapillole_aperto: true, mano_alla_bocca: true },
    });
  }
  for (let i = 0; i < report.pasti.length; i++) {
    const pasto = report.pasti[i];
    eventi.push({
      ...base("sim-" + giorno + "-pasto-" + i, pasto.ora, null, "Kitchen", "t-cucina", "pasto", 0.8, true),
      tipo: "pasto",
      valori: { cibi: pasto.cibi, quanto_mangiato: pasto.quanto_mangiato },
    });
  }
  if (report.cadute > 0) {
    eventi.push({
      ...base(
        "sim-" + giorno + "-caduta",
        ora(giorno, "16:40"),
        ora(giorno, "16:41"),
        "Living room",
        "t-soggiorno",
        "caduta",
        0.9,
        true,
      ),
      ha_foto: true,
      tipo: "caduta",
      valori: { secondi_a_terra: 35 },
    });
  }
  if (report.uscite > 0) {
    eventi.push({
      ...base("sim-" + giorno + "-uscita", ora(giorno, "21:30"), null, "Hallway", "t-ingresso", "uscita", 0.9, true),
      ha_foto: true,
      tipo: "uscita",
      valori: { zona_id: "porta-ingresso", in_orario_vietato: true },
    });
  }
  const notte = notteSimulata(giorno, report.alzate_notturne);
  if (notte !== null) {
    for (const evento of eventiSonno(notte, "sim-" + giorno, true)) {
      eventi.push(evento);
    }
  }
  for (const evento of eventiRicercaAlzheimer(giorno, ORE_ALZATE.slice(0, report.alzate_notturne), true)) {
    eventi.push(evento);
  }
  // In ordine di inizio, come risponde il backend.
  eventi.sort(confrontaInizio);
  return eventi;
}

function confrontaInizio(a: Evento, b: Evento): number {
  if (a.inizio < b.inizio) {
    return -1;
  }
  if (a.inizio > b.inizio) {
    return 1;
  }
  return 0;
}

// ---------- Le risposte finte delle chiamate /demo/* ----------

export function periodoSviluppo(): PeriodoDemo {
  return { dal: PRIMO_GIORNO, al: G };
}

export function reportGiornalieroSviluppo(giorno: string): ReportGiornaliero | null {
  if (giorno === G) {
    return REPORT_GIORNO_VERO;
  }
  const riassunto = riassuntoDelGiorno(giorno);
  if (riassunto === null) {
    return null;
  }
  return reportSimulato(riassunto);
}

export function eventiSviluppo(dal: string, al: string, tipo: TipoEvento | null): Evento[] {
  const eventi: Evento[] = [];
  // Si guarda anche il giorno dopo "al": la sua notte inizia la sera di "al". Poi si tengono solo gli eventi
  // che iniziano tra "dal" e "al", come fa il backend.
  const dopo = spostaGiorno(al, 1);
  let giorno = dal;
  while (giorno <= dopo) {
    let delGiorno: Evento[] = [];
    if (giorno === G) {
      delGiorno = eventiGiornoVero();
    } else {
      const report = reportGiornalieroSviluppo(giorno);
      if (report !== null) {
        delGiorno = eventiSimulati(report);
      }
    }
    if (giorno === INATTIVITA.giorno) {
      delGiorno = senzaEventiDuranteInattivita(delGiorno);
    }
    for (const evento of delGiorno) {
      const giornoEvento = evento.inizio.slice(0, 10);
      const nelPeriodo = giornoEvento >= dal && giornoEvento <= al;
      if (nelPeriodo && (tipo === null || evento.tipo === tipo)) {
        eventi.push(evento);
      }
    }
    giorno = spostaGiorno(giorno, 1);
  }
  return eventi;
}

function reportPeriodo(tipo: "settimanale" | "mensile", dal: string, al: string): ReportPeriodo {
  const giorni: RiassuntoGiorno[] = [];
  let giorno = dal;
  while (giorno <= al) {
    const riassunto = riassuntoDelGiorno(giorno);
    if (riassunto !== null) {
      giorni.push(riassunto);
    }
    giorno = spostaGiorno(giorno, 1);
  }
  let acqua = 0;
  let previste = 0;
  let prese = 0;
  let cadute = 0;
  let usciteVietate = 0;
  let alzate = 0;
  let minutiSonno = 0;
  let nottiConSonno = 0;
  for (const riga of giorni) {
    acqua = acqua + riga.acqua_ml;
    previste = previste + riga.dosi_previste;
    prese = prese + riga.dosi_in_orario + riga.dosi_in_ritardo;
    cadute = cadute + riga.cadute;
    usciteVietate = usciteVietate + riga.uscite_in_orario_vietato;
    alzate = alzate + riga.alzate_notturne;
    if (riga.sonno_minuti !== null) {
      minutiSonno = minutiSonno + riga.sonno_minuti;
      nottiConSonno = nottiConSonno + 1;
    }
  }
  let cambiamenti: CambiamentoRoutine[] = [];
  if (al >= spostaGiorno(G, -6) && dal <= G) {
    cambiamenti = CAMBIAMENTI_ULTIMA_SETTIMANA;
  }
  // Media sulle notti in cui si è visto dormire (API.md).
  let sonnoMedio: number | null = null;
  if (nottiConSonno > 0) {
    sonnoMedio = minutiSonno / nottiConSonno;
  }
  const numeroGiorni = Math.max(1, giorni.length);
  // Senza dosi valutate l'aderenza è null (API.md): la web app scrive "No data".
  let aderenza: number | null = null;
  if (previste > 0) {
    aderenza = (prese / previste) * 100;
  }
  return {
    tipo: tipo,
    dal: dal,
    al: al,
    giorni: giorni,
    acqua_media_ml: acqua / numeroGiorni,
    aderenza_farmaci_percentuale: aderenza,
    cadute: cadute,
    uscite_in_orario_vietato: usciteVietate,
    alzate_notturne_medie: alzate / numeroGiorni,
    sonno_medio_minuti: sonnoMedio,
    cambiamenti: cambiamenti,
  };
}

export function reportSettimanaleSviluppo(dal: string): ReportPeriodo {
  return reportPeriodo("settimanale", dal, spostaGiorno(dal, 6));
}

export function reportMensileSviluppo(mese: string): ReportPeriodo {
  // L'ultimo giorno del mese: il giorno prima del primo del mese dopo.
  const primo = mese + "-01";
  let ultimo = primo;
  while (spostaGiorno(ultimo, 1).slice(0, 7) === mese) {
    ultimo = spostaGiorno(ultimo, 1);
  }
  return reportPeriodo("mensile", primo, ultimo);
}
