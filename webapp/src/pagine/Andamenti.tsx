// Trends: idratazione, aderenza ai farmaci, pasti, notte, cadute nel tempo (da ReportPeriodo.giorni, API.md).
import { useEffect, useState } from "react";
import type { Personalizzazione, ReportPeriodo, RiassuntoGiorno } from "../contratti";
import {
  leggiPeriodoDemo,
  leggiPersonalizzazioneDemo,
  leggiReportMensile,
  leggiReportSettimanale,
  messaggioErrore,
} from "../api";
import { giornoBreve, giornoEMese, millilitri, percentuale, quanti, spostaGiorno } from "../formato";
import Caricamento from "../componenti/Caricamento";
import { GraficoAcqua, GraficoDosi, GraficoNotti, GraficoPasti } from "../componenti/Grafici";
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

// Media della parte di piatto mangiata, solo sui giorni con almeno un pasto; null se non ce ne sono.
function mediaMangiato(giorni: RiassuntoGiorno[]): number | null {
  let somma = 0;
  let quanti = 0;
  for (const riga of giorni) {
    if (riga.percentuale_mangiata_media !== null) {
      somma = somma + riga.percentuale_mangiata_media;
      quanti = quanti + 1;
    }
  }
  if (quanti === 0) {
    return null;
  }
  return somma / quanti;
}

function AndamentiCasaDemo() {
  const [mensile, setMensile] = useState(false);
  const [personalizzazione, setPersonalizzazione] = useState<Personalizzazione | null>(null);
  const [report, setReport] = useState<ReportPeriodo | null>(null);
  const [errore, setErrore] = useState("");

  useEffect(() => {
    async function carica() {
      setReport(null);
      setErrore("");
      try {
        const ultimo = (await leggiPeriodoDemo()).al;
        setPersonalizzazione(await leggiPersonalizzazioneDemo());
        if (mensile) {
          setReport(await leggiReportMensile(ultimo.slice(0, 7)));
        } else {
          setReport(await leggiReportSettimanale(spostaGiorno(ultimo, -6)));
        }
      } catch (problema) {
        setErrore(messaggioErrore(problema));
      }
    }
    carica();
  }, [mensile]);

  let corpo = <Caricamento errore={errore} />;
  if (personalizzazione !== null && report !== null) {
    corpo = <GraficiDelPeriodo report={report} personalizzazione={personalizzazione} />;
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
  personalizzazione: Personalizzazione;
};

function GraficiDelPeriodo({ report, personalizzazione }: ProprietaGrafici) {
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
            <span className="numero-medio">{percentuale(mediaMangiato(report.giorni))}</span>{" "}
            <span className="testo-secondario">of the plate eaten on average</span>
          </p>
          <GraficoPasti giorni={report.giorni} />
        </Scheda>
        <Scheda titolo="Nights" icona="luna">
          <p>
            <span className="numero-medio">{report.alzate_notturne_medie.toFixed(1)}</span>{" "}
            <span className="testo-secondario">rises per night on average</span>
          </p>
          <GraficoNotti giorni={report.giorni} />
        </Scheda>
        <Scheda titolo="Falls and exits" icona="avviso">
          <div className="pila">
            <p className="testo-secondario">
              {quanti(report.cadute, "fall", "falls")} and{" "}
              {quanti(report.uscite_in_orario_vietato, "exit", "exits")} in no-exit hours.
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
