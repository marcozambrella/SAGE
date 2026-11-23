// ==========================================================================================================
//  DATI FINTI DI SVILUPPO — NON sono risultati dei modelli né dati della casa demo vera.
//  Servono solo finché il backend non è pronto: api.ts li usa quando VITE_API_URL non è impostato.
//  Rispettano esattamente i tipi di contratti.ts (copia di contratti/contratti/*.py).
//  Il "giorno vero" (GIORNO_DEMO) imita i risultati dei video registrati; gli altri giorni imitano lo storico
//  simulato (simulato: true), con una piccola storia: nell'ultima settimana si beve meno e ci si alza più di notte.
// ==========================================================================================================
import type {
  DoseFarmaco,
  Evento,
  EventoBase,
  PastoDelGiorno,
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
    { id: "f-memantina", nome: "Memantine", dose: "1 tablet", orari: ["08:00", "20:00"], tolleranza_minuti: 30, foto_ids: [] },
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
    simulato: simulato,
  };
}

// Bevuta calcolata come in D9: ml = livello sceso / altezza del contenitore × capienza.
function bevuta(
  id: string,
  inizio: string,
  stanza: string,
  telecameraId: string,
  contenitore: TipoContenitore,
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
      capienza_ml: capienza,
      altezza_contenitore_px: altezzaPx,
      livello_sceso_px: scesoPx,
      percentuale: percentuale,
      ml: ml,
    },
  };
}

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
  eventi.push(bevuta("ev-0750", ora(G, "07:50"), "Kitchen", "t-cucina", "tazza", 200, 90, 90, false));
  eventi.push({
    ...base("ev-0807", ora(G, "08:07"), null, "Kitchen", "t-cucina", "farmaco", 0.88, false),
    tipo: "farmaco",
    valori: { farmaco_id: "f-memantina", somiglianza: 0.91, portapillole_aperto: true, mano_alla_bocca: true },
  });
  eventi.push({
    ...base("ev-0815", ora(G, "08:15"), ora(G, "08:38"), "Kitchen", "t-cucina", "pasto", 0.84, false),
    tipo: "pasto",
    valori: { cibi: ["bread", "milk", "biscuits"], percentuale_mangiata: 90 },
  });
  eventi.push({
    ...base("ev-0852", ora(G, "08:52"), null, "Kitchen", "t-cucina", "farmaco", 0.85, false),
    tipo: "farmaco",
    valori: { farmaco_id: "f-ramipril", somiglianza: 0.87, portapillole_aperto: true, mano_alla_bocca: true },
  });
  eventi.push(bevuta("ev-1030", ora(G, "10:30"), "Living room", "t-soggiorno", "bicchiere", 250, 120, 96, false));
  eventi.push({
    ...base("ev-1240", ora(G, "12:40"), ora(G, "13:05"), "Kitchen", "t-cucina", "pasto", 0.82, false),
    tipo: "pasto",
    valori: { cibi: ["pasta with tomato sauce", "green salad"], percentuale_mangiata: 60 },
  });
  eventi.push(bevuta("ev-1245", ora(G, "12:45"), "Kitchen", "t-cucina", "bicchiere", 250, 120, 72, false));
  eventi.push(bevuta("ev-1500", ora(G, "15:00"), "Living room", "t-soggiorno", "bottiglia", 1000, 260, 78, false));
  // La caduta l'hanno vista due telecamere: l'unione ha fuso i due eventi in uno (D3).
  eventi.push({
    ...base("ev-1520", ora(G, "15:20"), ora(G, "15:21"), "Living room", "t-soggiorno", "caduta", 0.94, false),
    fonti: [
      { telecamera_id: "t-soggiorno", analizzatore: "caduta", confidenza: 0.94 },
      { telecamera_id: "t-ingresso", analizzatore: "caduta", confidenza: 0.71 },
    ],
    tipo: "caduta",
    valori: { secondi_a_terra: 48 },
  });
  eventi.push(bevuta("ev-1730", ora(G, "17:30"), "Living room", "t-soggiorno", "bicchiere", 250, 120, 96, false));
  eventi.push({
    ...base("ev-1930", ora(G, "19:30"), ora(G, "19:52"), "Kitchen", "t-cucina", "pasto", 0.8, false),
    tipo: "pasto",
    valori: { cibi: ["vegetable soup", "cheese"], percentuale_mangiata: 45 },
  });
  eventi.push(bevuta("ev-1940", ora(G, "19:40"), "Kitchen", "t-cucina", "bicchiere", 250, 120, 48, false));
  eventi.push({
    ...base("ev-2012", ora(G, "20:12"), null, "Kitchen", "t-cucina", "farmaco", 0.86, false),
    tipo: "farmaco",
    valori: { farmaco_id: "f-memantina", somiglianza: 0.89, portapillole_aperto: true, mano_alla_bocca: true },
  });
  eventi.push({
    ...base("ev-2110", ora(G, "21:10"), null, "Hallway", "t-ingresso", "uscita", 0.91, false),
    tipo: "uscita",
    valori: { zona_id: "porta-ingresso" },
  });
  return eventi;
}

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
    { ora: ora(G, "08:15"), cibi: ["bread", "milk", "biscuits"], percentuale_mangiata: 90 },
    { ora: ora(G, "12:40"), cibi: ["pasta with tomato sauce", "green salad"], percentuale_mangiata: 60 },
    { ora: ora(G, "19:30"), cibi: ["vegetable soup", "cheese"], percentuale_mangiata: 45 },
  ],
  alzate_notturne: 2,
  minuti_fuori_letto_notte: 18,
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
    percentuale_mangiata_media: Math.round(60 + caso(indice, 5) * 30),
    alzate_notturne: alzate,
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
    percentuale_mangiata_media: 65,
    alzate_notturne: 2,
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
  let media = 70;
  if (riassunto.percentuale_mangiata_media !== null) {
    media = riassunto.percentuale_mangiata_media;
  }
  const numeroGiorno = Number(giorno.slice(8, 10));
  const pasti: PastoDelGiorno[] = [
    { ora: ora(giorno, "08:20"), cibi: MENU[numeroGiorno % 6], percentuale_mangiata: Math.min(100, media + 10) },
    { ora: ora(giorno, "12:45"), cibi: MENU[(numeroGiorno + 1) % 6], percentuale_mangiata: media },
    { ora: ora(giorno, "19:15"), cibi: MENU[(numeroGiorno + 2) % 6], percentuale_mangiata: Math.max(0, media - 10) },
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
    cadute: riassunto.cadute,
    uscite: riassunto.uscite_in_orario_vietato,
    uscite_in_orario_vietato: riassunto.uscite_in_orario_vietato,
    simulato: true,
  };
}

function eventiSimulati(report: ReportGiornaliero): Evento[] {
  const giorno = report.data;
  const eventi: Evento[] = [];
  const oreAlzate = ["02:30", "04:45", "05:50"];
  for (let i = 0; i < report.alzate_notturne; i++) {
    const inizio = oreAlzate[i];
    eventi.push({
      ...base("sim-" + giorno + "-alzata-" + i, ora(giorno, inizio), ora(giorno, aggiungiMinuti(inizio, 9)),
        "Bedroom", "t-camera", "alzata_notturna", 0.9, true),
      tipo: "alzata_notturna",
      valori: { stanze: ["Bedroom"] },
    });
  }
  // Cinque bevute da un bicchiere da 250 ml: il livello sceso dà i ml del giorno divisi in parti uguali.
  const oreBevute = ["08:00", "10:30", "13:00", "16:00", "18:30"];
  const mlPerBevuta = report.acqua_ml / 5;
  for (let i = 0; i < oreBevute.length; i++) {
    const scesoPx = (mlPerBevuta / 250) * 120;
    eventi.push(bevuta("sim-" + giorno + "-bevuta-" + i, ora(giorno, oreBevute[i]), "Kitchen", "t-cucina",
      "bicchiere", 250, 120, scesoPx, true));
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
      valori: { cibi: pasto.cibi, percentuale_mangiata: pasto.percentuale_mangiata },
    });
  }
  if (report.cadute > 0) {
    eventi.push({
      ...base("sim-" + giorno + "-caduta", ora(giorno, "16:40"), ora(giorno, "16:41"), "Living room", "t-soggiorno",
        "caduta", 0.9, true),
      tipo: "caduta",
      valori: { secondi_a_terra: 35 },
    });
  }
  if (report.uscite > 0) {
    eventi.push({
      ...base("sim-" + giorno + "-uscita", ora(giorno, "21:30"), null, "Hallway", "t-ingresso", "uscita", 0.9, true),
      tipo: "uscita",
      valori: { zona_id: "porta-ingresso" },
    });
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
  let giorno = dal;
  while (giorno <= al) {
    let delGiorno: Evento[] = [];
    if (giorno === G) {
      delGiorno = eventiGiornoVero();
    } else {
      const report = reportGiornalieroSviluppo(giorno);
      if (report !== null) {
        delGiorno = eventiSimulati(report);
      }
    }
    for (const evento of delGiorno) {
      if (tipo === null || evento.tipo === tipo) {
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
  for (const riga of giorni) {
    acqua = acqua + riga.acqua_ml;
    previste = previste + riga.dosi_previste;
    prese = prese + riga.dosi_in_orario + riga.dosi_in_ritardo;
    cadute = cadute + riga.cadute;
    usciteVietate = usciteVietate + riga.uscite_in_orario_vietato;
    alzate = alzate + riga.alzate_notturne;
  }
  const numeroGiorni = Math.max(1, giorni.length);
  return {
    tipo: tipo,
    dal: dal,
    al: al,
    giorni: giorni,
    acqua_media_ml: acqua / numeroGiorni,
    aderenza_farmaci_percentuale: (prese / Math.max(1, previste)) * 100,
    cadute: cadute,
    uscite_in_orario_vietato: usciteVietate,
    alzate_notturne_medie: alzate / numeroGiorni,
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
