// Come si mostrano ore, giorni e quantità. I testi dell'interfaccia sono in inglese (D13).
// Le ore degli eventi si mostrano nel fuso orario della casa, non in quello del telefono di chi guarda.

const LINGUA = "en-GB";

// "08:07" da una data ISO con fuso, nel fuso orario della casa.
export function oraDellaCasa(iso: string, fusoOrario: string): string {
  const formato = new Intl.DateTimeFormat(LINGUA, {
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
    timeZone: fusoOrario,
  });
  return formato.format(new Date(iso));
}

// "AAAA-MM-GG" del giorno in cui è successo l'evento, nel fuso orario della casa.
export function giornoDellaCasa(iso: string, fusoOrario: string): string {
  // Il formato canadese scrive le date proprio come "AAAA-MM-GG".
  const formato = new Intl.DateTimeFormat("en-CA", { year: "numeric", month: "2-digit", day: "2-digit", timeZone: fusoOrario });
  return formato.format(new Date(iso));
}

// I giorni "AAAA-MM-GG" si leggono a mezzogiorno UTC: così nessun fuso orario li sposta al giorno prima o dopo.
function giornoComeData(giorno: string): Date {
  return new Date(giorno + "T12:00:00Z");
}

// "Monday 14 December"
export function giornoLungo(giorno: string): string {
  const formato = new Intl.DateTimeFormat(LINGUA, { weekday: "long", day: "numeric", month: "long", timeZone: "UTC" });
  return formato.format(giornoComeData(giorno));
}

// "Mon 14"
export function giornoBreve(giorno: string): string {
  const formato = new Intl.DateTimeFormat(LINGUA, { weekday: "short", day: "numeric", timeZone: "UTC" });
  return formato.format(giornoComeData(giorno));
}

// "Mon"
export function giornoSettimana(giorno: string): string {
  const formato = new Intl.DateTimeFormat(LINGUA, { weekday: "short", timeZone: "UTC" });
  return formato.format(giornoComeData(giorno));
}

// "14 Dec"
export function giornoEMese(giorno: string): string {
  const formato = new Intl.DateTimeFormat(LINGUA, { day: "numeric", month: "short", timeZone: "UTC" });
  return formato.format(giornoComeData(giorno));
}

// "December 2026" da "2026-12"
export function meseLungo(mese: string): string {
  const formato = new Intl.DateTimeFormat(LINGUA, { month: "long", year: "numeric", timeZone: "UTC" });
  return formato.format(giornoComeData(mese + "-15"));
}

// Giorno "AAAA-MM-GG" spostato di n giorni (n può essere negativo).
export function spostaGiorno(giorno: string, n: number): string {
  const data = giornoComeData(giorno);
  data.setUTCDate(data.getUTCDate() + n);
  return data.toISOString().slice(0, 10);
}

// "1,150"
export function numero(valore: number): string {
  return Math.round(valore).toLocaleString(LINGUA);
}

// "96%", oppure "No data" se il valore non c'è (es. aderenza senza dosi valutate).
export function percentuale(valore: number | null): string {
  if (valore === null) {
    return "No data";
  }
  return Math.round(valore) + "%";
}

// "1,150 ml"
export function millilitri(valore: number): string {
  return numero(valore) + " ml";
}

// "1 h 05 min" oppure "18 min"
export function durata(minuti: number): string {
  const tondi = Math.round(minuti);
  if (tondi < 60) {
    return tondi + " min";
  }
  const ore = Math.floor(tondi / 60);
  const resto = tondi % 60;
  return ore + " h " + String(resto).padStart(2, "0") + " min";
}

// Prima lettera maiuscola: "pasta with tomato sauce" → "Pasta with tomato sauce"
export function maiuscola(testo: string): string {
  if (testo === "") {
    return testo;
  }
  return testo[0].toUpperCase() + testo.slice(1);
}
