// Trends: idratazione, aderenza ai farmaci, pasti, notte, cadute nel tempo (da ReportPeriodo.giorni, API.md).
// I grafici aspettano la scelta della libreria: per ora numeri riassuntivi e riquadri segnaposto.
import { useEffect, useState } from "react";
import type { Personalizzazione, ReportPeriodo } from "../contratti";
import { leggiPeriodoDemo, leggiReportMensile, leggiReportSettimanale } from "../api";
import { millilitri, percentuale, spostaGiorno } from "../formato";
import Caricamento from "../componenti/Caricamento";
import EtichettaSimulato from "../componenti/EtichettaSimulato";
import InAttesaTelecamere from "../componenti/InAttesaTelecamere";
import Scheda from "../componenti/Scheda";
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

function AndamentiCasaDemo() {
  const [mensile, setMensile] = useState(false);
  const [report, setReport] = useState<ReportPeriodo | null>(null);
  const [errore, setErrore] = useState("");

  useEffect(() => {
    async function carica() {
      setReport(null);
      setErrore("");
      try {
        const ultimo = (await leggiPeriodoDemo()).al;
        if (mensile) {
          setReport(await leggiReportMensile(ultimo.slice(0, 7)));
        } else {
          setReport(await leggiReportSettimanale(spostaGiorno(ultimo, -6)));
        }
      } catch (problema) {
        setErrore(String(problema));
      }
    }
    carica();
  }, [mensile]);

  let corpo = <Caricamento errore={errore} />;
  if (report !== null) {
    let simulati = false;
    for (const riga of report.giorni) {
      if (riga.simulato) {
        simulati = true;
      }
    }
    let etichetta = null;
    if (simulati) {
      etichetta = <EtichettaSimulato />;
    }
    corpo = (
      <div className="griglia">
        <Scheda titolo="Hydration" icona="goccia" accanto={etichetta}>
          <p>
            <span className="numero-medio">{millilitri(report.acqua_media_ml)}</span>{" "}
            <span className="testo-secondario">a day on average</span>
          </p>
          <div className="segnaposto-grafico">Line chart: water per day against the goal</div>
        </Scheda>
        <Scheda titolo="Medications" icona="pillola" accanto={etichetta}>
          <p>
            <span className="numero-medio">{percentuale(report.aderenza_farmaci_percentuale)}</span>{" "}
            <span className="testo-secondario">of doses taken</span>
          </p>
          <div className="segnaposto-grafico">Stacked bars: on time, late and missed doses per day</div>
        </Scheda>
        <Scheda titolo="Meals" icona="pasto" accanto={etichetta}>
          <p className="testo-secondario">Share of the plate eaten, on average per day.</p>
          <div className="segnaposto-grafico">Line chart: share of the plate eaten per day</div>
        </Scheda>
        <Scheda titolo="Nights" icona="luna" accanto={etichetta}>
          <p>
            <span className="numero-medio">{report.alzate_notturne_medie.toFixed(1)}</span>{" "}
            <span className="testo-secondario">rises per night on average</span>
          </p>
          <div className="segnaposto-grafico">Bars: night-time rises per night</div>
        </Scheda>
        <Scheda titolo="Falls and exits" icona="avviso" accanto={etichetta}>
          <p>
            <span className="numero-medio">{report.cadute}</span> <span className="testo-secondario">falls</span>
            {" · "}
            <span className="numero-medio">{report.uscite_in_orario_vietato}</span>{" "}
            <span className="testo-secondario">exits in no-exit hours</span>
          </p>
          <div className="segnaposto-grafico">Dots on a timeline: each fall and each exit</div>
        </Scheda>
      </div>
    );
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
