// Trends: idratazione, aderenza ai farmaci, pasti, notte, cadute nel tempo (da ReportPeriodo.giorni, API.md).
import { useEffect, useState } from "react";
import type { Evento, Personalizzazione, ReportPeriodo, RiassuntoGiorno } from "../contratti";
import {
  leggiEventiDemo,
  leggiPeriodoDemo,
  leggiPersonalizzazioneDemo,
  leggiReportMensile,
  leggiReportSettimanale,
  messaggioErrore,
} from "../api";
import {
  durata,
  giornoBreve,
  giornoDellaCasa,
  giornoEMese,
  millilitri,
  oraDellaCasa,
  percentuale,
  quanti,
  spostaGiorno,
} from "../formato";
import Caricamento from "../componenti/Caricamento";
import { GraficoAcqua, GraficoDosi, GraficoNotti, GraficoSonno } from "../componenti/Grafici";
import GraficoPasti, { type PastiDelGiorno } from "../componenti/GraficoPasti";
import { aggiungiAlPeriodo, leggiInserimenti, pastiAMano, type QuantoMangiatoAMano } from "../inserimenti";
import Icona from "../componenti/Icona";
import InAttesaTelecamere from "../componenti/InAttesaTelecamere";
import Scheda from "../componenti/Scheda";
import TabellaGiorni from "../componenti/TabellaGiorni";
import TitoloPagina from "../componenti/TitoloPagina";

type Proprieta = {
  demo: boolean;
  personalizzazione: Personalizzazione | null;
};

export default function Andamenti({ demo, personalizzazione }: Proprieta) {
  if (demo || personalizzazione === null) {
    return <AndamentiCasaDemo />;
  }
  return (
    <div className="pila-larga entrata">
      <TitoloPagina titolo="Trends" sotto="How things change over weeks and months." />
      <InAttesaTelecamere
        testo={
          "Trends for hydration, medication, meals, nights and falls need a few days of data from " +
          personalizzazione.anziano.nome +
          "'s cameras."
        }
        paginaDemo="/demo/trends"
      />
    </div>
  );
}

// Quanti pasti in tutto e quanti con meno di metà del piatto mangiato, nel periodo.
function contaPasti(giorni: RiassuntoGiorno[]): { pasti: number; menoDiMeta: number } {
  let pasti = 0;
  let menoDiMeta = 0;
  for (const riga of giorni) {
    pasti = pasti + riga.pasti;
    menoDiMeta = menoDiMeta + riga.pasti_meno_di_meta;
  }
  return { pasti: pasti, menoDiMeta: menoDiMeta };
}

// Per il grafico dei pasti serve quanto ha mangiato a ogni pasto: il riassunto del giorno ha solo i conti,
// perciò si prendono gli eventi "pasto" del periodo e si mettono sotto il loro giorno (nel fuso della casa),
// insieme ai pasti segnati a mano, tutti in ordine di ora.
type PastoConOra = {
  ora: string;
  quanto: QuantoMangiatoAMano | null;
};

function confrontaOra(a: PastoConOra, b: PastoConOra): number {
  if (a.ora < b.ora) {
    return -1;
  }
  if (a.ora > b.ora) {
    return 1;
  }
  return 0;
}

function pastiPerGiorno(giorni: RiassuntoGiorno[], eventiPasti: Evento[], fusoOrario: string): PastiDelGiorno[] {
  const inserimenti = leggiInserimenti(true);
  const risultato: PastiDelGiorno[] = [];
  for (const riga of giorni) {
    const conOra: PastoConOra[] = [];
    for (const evento of eventiPasti) {
      if (evento.tipo === "pasto" && giornoDellaCasa(evento.inizio, fusoOrario) === riga.data) {
        conOra.push({ ora: oraDellaCasa(evento.inizio, fusoOrario), quanto: evento.valori.quanto_mangiato });
      }
    }
    for (const pasto of pastiAMano(inserimenti, riga.data)) {
      conOra.push({ ora: pasto.ora, quanto: pasto.quanto });
    }
    conOra.sort(confrontaOra);
    const pastiDelGiorno: PastiDelGiorno = { data: riga.data, pasti: [] };
    for (const pasto of conOra) {
      pastiDelGiorno.pasti.push(pasto.quanto);
    }
    risultato.push(pastiDelGiorno);
  }
  return risultato;
}

function AndamentiCasaDemo() {
  const [mensile, setMensile] = useState(false);
  const [personalizzazione, setPersonalizzazione] = useState<Personalizzazione | null>(null);
  const [report, setReport] = useState<ReportPeriodo | null>(null);
  const [eventiPasti, setEventiPasti] = useState<Evento[] | null>(null);
  const [errore, setErrore] = useState("");

  useEffect(() => {
    async function carica() {
      setReport(null);
      setEventiPasti(null);
      setErrore("");
      try {
        const ultimo = (await leggiPeriodoDemo()).al;
        setPersonalizzazione(await leggiPersonalizzazioneDemo());
        let nuovoReport: ReportPeriodo;
        if (mensile) {
          nuovoReport = await leggiReportMensile(ultimo.slice(0, 7));
        } else {
          nuovoReport = await leggiReportSettimanale(spostaGiorno(ultimo, -6));
        }
        setEventiPasti(await leggiEventiDemo(nuovoReport.dal, nuovoReport.al, "pasto"));
        // Il backend non conosce gli inserimenti a mano: si aggiungono ai giorni qui nel browser.
        setReport(aggiungiAlPeriodo(nuovoReport, leggiInserimenti(true)));
      } catch (problema) {
        setErrore(messaggioErrore(problema));
      }
    }
    carica();
  }, [mensile]);

  let corpo = <Caricamento errore={errore} />;
  if (personalizzazione !== null && report !== null && eventiPasti !== null) {
    corpo = <GraficiDelPeriodo report={report} eventiPasti={eventiPasti} personalizzazione={personalizzazione} />;
  }

  return (
    <div className="pila-larga entrata">
      <TitoloPagina titolo="Trends" sotto="How things change over weeks and months." />
      <div className="segmenti" role="group" aria-label="Trend period">
        <button type="button" className="segmento" aria-pressed={!mensile} onClick={() => setMensile(false)}>
          Last 7 days
        </button>
        <button type="button" className="segmento" aria-pressed={mensile} onClick={() => setMensile(true)}>
          This month
        </button>
      </div>
      {corpo}
    </div>
  );
}

type ProprietaGrafici = {
  report: ReportPeriodo;
  eventiPasti: Evento[];
  personalizzazione: Personalizzazione;
};

function GraficiDelPeriodo({ report, eventiPasti, personalizzazione }: ProprietaGrafici) {
  // Quali giorni vengono dai video registrati: tutti gli altri sono simulati (va sempre detto).
  const giorniVeri: string[] = [];
  let giorniSimulati = 0;
  for (const riga of report.giorni) {
    if (riga.simulato) {
      giorniSimulati = giorniSimulati + 1;
    } else {
      giorniVeri.push(giornoBreve(riga.data));
    }
  }

  const pastiDelPeriodo = contaPasti(report.giorni);
  const pastiDeiGiorni = pastiPerGiorno(report.giorni, eventiPasti, personalizzazione.fuso_orario);

  // Cadute e uscite sono poche: invece di un grafico quasi vuoto, l'elenco dei giorni in cui sono successe.
  const giorniDaRicordare: { data: string; testo: string }[] = [];
  for (const riga of report.giorni) {
    if (riga.cadute > 0) {
      giorniDaRicordare.push({ data: riga.data, testo: quanti(riga.cadute, "fall", "falls") });
    }
    if (riga.uscite_in_orario_vietato > 0) {
      const uscite = quanti(riga.uscite_in_orario_vietato, "exit", "exits");
      giorniDaRicordare.push({ data: riga.data, testo: uscite + " in no-exit hours" });
    }
  }

  return (
    <div className="pila-larga">
      {giorniSimulati > 0 && (
        <p className="nota-simulato">
          <span className="simulato">Simulated</span>
          <span>
            {giorniSimulati} of {report.giorni.length} days are simulated.
            {giorniVeri.length > 0 && <> From the recorded videos: {giorniVeri.join(", ")}.</>}
          </span>
        </p>
      )}

      <div className="griglia">
        <Scheda titolo="Hydration" icona="goccia">
          <p>
            <span className="numero-medio">{millilitri(report.acqua_media_ml)}</span>{" "}
            <span className="testo-secondario">a day on average</span>
          </p>
          <GraficoAcqua giorni={report.giorni} obiettivoMl={personalizzazione.anziano.obiettivo_acqua_ml} />
        </Scheda>
        <Scheda titolo="Medications" icona="pillola">
          <p>
            <span className="numero-medio">{percentuale(report.aderenza_farmaci_percentuale)}</span>{" "}
            <span className="testo-secondario">of doses taken</span>
          </p>
          <GraficoDosi giorni={report.giorni} />
        </Scheda>
        <Scheda titolo="Meals" icona="pasto">
          <p>
            <span className="numero-medio">{pastiDelPeriodo.menoDiMeta}</span>{" "}
            <span className="testo-secondario">
              of {quanti(pastiDelPeriodo.pasti, "meal", "meals")} with less than half eaten
            </span>
          </p>
          <GraficoPasti giorni={pastiDeiGiorni} />
        </Scheda>
        <Scheda titolo="Sleep" icona="letto">
          {report.sonno_medio_minuti === null && (
            <p className="testo-secondario">No sleep has been seen on these days yet.</p>
          )}
          {report.sonno_medio_minuti !== null && (
            <>
              <p>
                <span className="numero-medio">{durata(report.sonno_medio_minuti)}</span>{" "}
                <span className="testo-secondario">of sleep a night on average</span>
              </p>
              <GraficoSonno giorni={report.giorni} mediaMinuti={report.sonno_medio_minuti} />
            </>
          )}
        </Scheda>
        <Scheda titolo="Night rises" icona="luna">
          <p>
            <span className="numero-medio">{report.alzate_notturne_medie.toFixed(1)}</span>{" "}
            <span className="testo-secondario">rises per night on average</span>
          </p>
          <GraficoNotti giorni={report.giorni} />
        </Scheda>
        <Scheda titolo="Falls and exits" icona="avviso">
          <div className="pila">
            <p className="testo-secondario">
              {quanti(report.cadute, "fall", "falls")} and {quanti(report.uscite_in_orario_vietato, "exit", "exits")} in
              no-exit hours.
            </p>
            {giorniDaRicordare.length === 0 && <p className="testo-secondario">None in this period.</p>}
            <ul className="lista-semplice">
              {giorniDaRicordare.map((voce) => (
                <li key={voce.data + voce.testo} className="riga-lista riga">
                  <span className="stato stato-critico">
                    <Icona nome="avviso" dimensione={18} /> {giornoEMese(voce.data)}
                  </span>
                  <span>{voce.testo}</span>
                </li>
              ))}
            </ul>
          </div>
        </Scheda>
      </div>

      <details className="scheda dettagli">
        <summary>See every day as a table</summary>
        <TabellaGiorni giorni={report.giorni} />
      </details>
    </div>
  );
}
