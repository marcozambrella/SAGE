// Grafici dei trend e dei report di periodo, con Recharts. Una riga per giorno (ReportPeriodo.giorni, API.md).
// Regole di stile: barre sottili con la punta arrotondata, linee da 2 px, griglia leggera, il testo mai del colore
// dei dati, i valori esatti nel suggerimento al passaggio del dito e nella tabella dei giorni.
import type { ReactNode } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { RiassuntoGiorno } from "../contratti";
import { giornoBreve, giornoDelMese, giornoLungo, millilitri } from "../formato";

// Gli stessi colori di stile/variabili.css: gli attributi dei disegni SVG non leggono le variabili CSS.
const ACCENTO = "#c0512f";
const SUPERFICIE = "#f8f5f0";
const GRIGLIA = "#e6dfd6";
const TESTO = "#2f2a27";
const TESTO_SECONDARIO = "#675e57";
// Dosi: in orario è il caso normale e resta in grigio; in ritardo e saltate sono i colori di stato.
const DOSE_IN_ORARIO = "#d4cbc1";
const DOSE_IN_RITARDO = "#d99a1c";
const DOSE_SALTATA = "#b23a2b";

const ALTEZZA = 220;
const TESTO_ASSI = { fill: TESTO_SECONDARIO, fontSize: 13, fontFamily: "Nunito" };
const STILE_SUGGERIMENTO = {
  borderRadius: 18,
  border: "none",
  background: "#fffefc",
  boxShadow: "6px 8px 18px rgba(118, 90, 68, 0.2)",
  fontFamily: "Nunito",
  fontWeight: 700,
  color: TESTO,
};
const CURSORE_BARRE = { fill: "rgba(192, 81, 47, 0.08)" };

// Una settimana si legge "Mon 8"; un mese, con 30 barre, solo "8". Se le etichette non ci stanno lo stesso,
// l'asse (interval="preserveStartEnd") ne salta qualcuna tenendo la prima e l'ultima.
function formatoAsse(giorni: RiassuntoGiorno[]): (giorno: string) => string {
  if (giorni.length > 7) {
    return giornoDelMese;
  }
  return giornoBreve;
}

function titoloSuggerimento(etichetta: ReactNode): string {
  return giornoLungo(String(etichetta));
}

function testoLegenda(valore: string): ReactNode {
  return <span style={{ color: TESTO, fontWeight: 700 }}>{valore}</span>;
}

function formattaMl(valore: unknown): string {
  return millilitri(Number(valore));
}

function formattaMigliaia(valore: number): string {
  return valore.toLocaleString("en-GB");
}

type ProprietaAcqua = {
  giorni: RiassuntoGiorno[];
  obiettivoMl: number;
};

// Acqua bevuta ogni giorno, con la linea dell'obiettivo.
export function GraficoAcqua({ giorni, obiettivoMl }: ProprietaAcqua) {
  // L'asse arriva sempre sopra l'obiettivo, a un numero tondo (multiplo di 500 ml), così la linea si vede.
  let massimo = obiettivoMl;
  for (const riga of giorni) {
    massimo = Math.max(massimo, riga.acqua_ml);
  }
  const cima = Math.ceil((massimo * 1.05) / 500) * 500;
  return (
    <figure className="grafico" aria-label="Water drunk each day, against the daily goal">
      <ResponsiveContainer width="100%" height={ALTEZZA}>
        <BarChart data={giorni} margin={{ top: 16, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid vertical={false} stroke={GRIGLIA} />
          <XAxis
            dataKey="data"
            tickFormatter={formatoAsse(giorni)}
            tick={TESTO_ASSI}
            tickLine={false}
            axisLine={false}
            interval="preserveStartEnd"
            minTickGap={10}
          />
          <YAxis
            domain={[0, cima]}
            tickCount={cima / 500 + 1}
            tickFormatter={formattaMigliaia}
            tick={TESTO_ASSI}
            tickLine={false}
            axisLine={false}
            width={48}
          />
          <Tooltip
            cursor={CURSORE_BARRE}
            contentStyle={STILE_SUGGERIMENTO}
            labelFormatter={titoloSuggerimento}
            formatter={formattaMl}
          />
          <ReferenceLine
            y={obiettivoMl}
            stroke={TESTO_SECONDARIO}
            strokeWidth={2}
            label={{ value: "Goal", position: "insideTopRight", fill: TESTO_SECONDARIO, fontSize: 13 }}
          />
          <Bar
            dataKey="acqua_ml"
            name="Water"
            fill={ACCENTO}
            radius={[4, 4, 0, 0]}
            maxBarSize={24}
            isAnimationActive={false}
          />
        </BarChart>
      </ResponsiveContainer>
    </figure>
  );
}

// Dosi di ogni giorno, una sopra l'altra: in orario, in ritardo, saltate.
export function GraficoDosi({ giorni }: { giorni: RiassuntoGiorno[] }) {
  return (
    <figure className="grafico" aria-label="Doses each day: on time, late and missed">
      <ResponsiveContainer width="100%" height={ALTEZZA}>
        <BarChart data={giorni} margin={{ top: 16, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid vertical={false} stroke={GRIGLIA} />
          <XAxis
            dataKey="data"
            tickFormatter={formatoAsse(giorni)}
            tick={TESTO_ASSI}
            tickLine={false}
            axisLine={false}
            interval="preserveStartEnd"
            minTickGap={10}
          />
          <YAxis allowDecimals={false} tick={TESTO_ASSI} tickLine={false} axisLine={false} width={48} />
          <Tooltip
            cursor={CURSORE_BARRE}
            contentStyle={STILE_SUGGERIMENTO}
            labelFormatter={titoloSuggerimento}
            itemSorter="dataKey"
          />
          {/* In ordine di dataKey: in orario, in ritardo, saltate */}
          <Legend iconType="circle" formatter={testoLegenda} itemSorter="dataKey" />
          {/* Il bordo del colore della scheda fa da spazio di 2 px tra un pezzo e l'altro */}
          <Bar
            dataKey="dosi_in_orario"
            name="On time"
            stackId="dosi"
            fill={DOSE_IN_ORARIO}
            stroke={SUPERFICIE}
            strokeWidth={2}
            radius={[4, 4, 0, 0]}
            maxBarSize={24}
            isAnimationActive={false}
          />
          <Bar
            dataKey="dosi_in_ritardo"
            name="Late"
            stackId="dosi"
            fill={DOSE_IN_RITARDO}
            stroke={SUPERFICIE}
            strokeWidth={2}
            radius={[4, 4, 0, 0]}
            maxBarSize={24}
            isAnimationActive={false}
          />
          <Bar
            dataKey="dosi_saltate"
            name="Missed"
            stackId="dosi"
            fill={DOSE_SALTATA}
            stroke={SUPERFICIE}
            strokeWidth={2}
            radius={[4, 4, 0, 0]}
            maxBarSize={24}
            isAnimationActive={false}
          />
        </BarChart>
      </ResponsiveContainer>
    </figure>
  );
}

// Quante volte si è alzato dal letto ogni notte.
export function GraficoNotti({ giorni }: { giorni: RiassuntoGiorno[] }) {
  return (
    <figure className="grafico" aria-label="Night-time rises each night">
      <ResponsiveContainer width="100%" height={ALTEZZA}>
        <BarChart data={giorni} margin={{ top: 16, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid vertical={false} stroke={GRIGLIA} />
          <XAxis
            dataKey="data"
            tickFormatter={formatoAsse(giorni)}
            tick={TESTO_ASSI}
            tickLine={false}
            axisLine={false}
            interval="preserveStartEnd"
            minTickGap={10}
          />
          <YAxis allowDecimals={false} tick={TESTO_ASSI} tickLine={false} axisLine={false} width={48} />
          <Tooltip cursor={CURSORE_BARRE} contentStyle={STILE_SUGGERIMENTO} labelFormatter={titoloSuggerimento} />
          <Bar
            dataKey="alzate_notturne"
            name="Rises"
            fill={ACCENTO}
            radius={[4, 4, 0, 0]}
            maxBarSize={24}
            isAnimationActive={false}
          />
        </BarChart>
      </ResponsiveContainer>
    </figure>
  );
}
