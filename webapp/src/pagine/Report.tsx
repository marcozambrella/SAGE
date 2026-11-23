// Reports: giornaliero, settimanale e mensile. Casa dell'utente: in attesa. Casa demo: /demo/report/*.
import { useEffect, useState } from "react";
import type { Personalizzazione, ReportGiornaliero, ReportPeriodo } from "../contratti";
import {
  GIORNO_DEMO,
  leggiPersonalizzazioneDemo,
  leggiReportGiornaliero,
  leggiReportMensile,
  leggiReportSettimanale,
} from "../api";
import {
  durata,
  giornoBreve,
  giornoEMese,
  giornoLungo,
  maiuscola,
  meseLungo,
  millilitri,
  numero,
  oraDellaCasa,
  spostaGiorno,
} from "../formato";
import Caricamento from "../componenti/Caricamento";
import { orariDose } from "../descrizioni";
import EtichettaDose from "../componenti/EtichettaDose";
import EtichettaSimulato from "../componenti/EtichettaSimulato";
import Icona from "../componenti/Icona";
import InAttesaTelecamere from "../componenti/InAttesaTelecamere";
import Misuratore from "../componenti/Misuratore";
import TitoloPagina from "../componenti/TitoloPagina";

type Proprieta = {
  demo: boolean;
  personalizzazione: Personalizzazione | null;
};

type TipoReport = "giornaliero" | "settimanale" | "mensile";

export default function Report({ demo, personalizzazione }: Proprieta) {
  const [tipo, setTipo] = useState<TipoReport>("giornaliero");

  let contenuto = null;
  if (!demo && personalizzazione !== null) {
    contenuto = (
      <InAttesaTelecamere
        testo={
          "Daily, weekly and monthly reports about " +
          personalizzazione.anziano.nome +
          " will be written here once the cameras are connected."
        }
        paginaDemo="/demo/reports"
      />
    );
  } else if (tipo === "giornaliero") {
    contenuto = <ReportDelGiorno />;
  } else {
    contenuto = <ReportDelPeriodo tipo={tipo} key={tipo} />;
  }

  return (
    <div className="pila-larga entrata">
      <TitoloPagina titolo="Reports" sotto="Calm summaries to read, keep, or bring to the doctor." />
      {demo && (
        <div className="segmenti" role="group" aria-label="Report period">
          <button type="button" className="segmento" aria-pressed={tipo === "giornaliero"} onClick={() => setTipo("giornaliero")}>
            Daily
          </button>
          <button type="button" className="segmento" aria-pressed={tipo === "settimanale"} onClick={() => setTipo("settimanale")}>
            Weekly
          </button>
          <button type="button" className="segmento" aria-pressed={tipo === "mensile"} onClick={() => setTipo("mensile")}>
            Monthly
          </button>
        </div>
      )}
      {contenuto}
    </div>
  );
}

// Frecce "prima" e "dopo" intorno al nome del periodo.
type ProprietaScorri = {
  titolo: string;
  onPrima: () => void;
  onDopo: () => void;
  dopoDisattivato: boolean;
};

function ScorriPeriodo({ titolo, onPrima, onDopo, dopoDisattivato }: ProprietaScorri) {
  return (
    <div className="scorri-periodo">
      <button type="button" className="pulsante pulsante-secondario pulsante-icona" aria-label="Previous" onClick={onPrima}>
        <Icona nome="indietro" />
      </button>
      <h2>{titolo}</h2>
      <button
        type="button"
        className="pulsante pulsante-secondario pulsante-icona"
        aria-label="Next"
        disabled={dopoDisattivato}
        onClick={onDopo}
      >
        <Icona nome="freccia" />
      </button>
    </div>
  );
}

function ReportDelGiorno() {
  const [giorno, setGiorno] = useState(GIORNO_DEMO);
  const [personalizzazione, setPersonalizzazione] = useState<Personalizzazione | null>(null);
  const [report, setReport] = useState<ReportGiornaliero | null>(null);
  const [errore, setErrore] = useState("");

  useEffect(() => {
    async function carica() {
      setReport(null);
      setErrore("");
      try {
        setPersonalizzazione(await leggiPersonalizzazioneDemo());
        setReport(await leggiReportGiornaliero(giorno));
      } catch (problema) {
        setErrore(String(problema));
      }
    }
    carica();
  }, [giorno]);

  const scorri = (
    <ScorriPeriodo
      titolo={giornoLungo(giorno)}
      onPrima={() => setGiorno(spostaGiorno(giorno, -1))}
      onDopo={() => setGiorno(spostaGiorno(giorno, 1))}
      dopoDisattivato={giorno >= GIORNO_DEMO}
    />
  );

  if (personalizzazione === null || report === null) {
    return (
      <>
        {scorri}
        <Caricamento errore={errore} />
      </>
    );
  }

  const fuso = personalizzazione.fuso_orario;
  const percentualeAcqua = (report.acqua_ml / report.obiettivo_acqua_ml) * 100;
  let origine = "from the recorded videos";
  if (report.simulato) {
    origine = "simulated day";
  }

  return (
    <>
      {scorri}
      <article className="scheda foglio-report pila-larga">
        <header className="riga-spaziata">
          <div>
            <h2>Daily report</h2>
            <p className="testo-secondario">
              {personalizzazione.anziano.nome} · {origine}
            </p>
          </div>
          {report.simulato && <EtichettaSimulato />}
        </header>

        <section className="pila">
          <h3 className="titolo-sezione">
            <Icona nome="goccia" /> Water
          </h3>
          <p>
            <span className="numero-medio">{millilitri(report.acqua_ml)}</span>{" "}
            <span className="testo-secondario">
              of {millilitri(report.obiettivo_acqua_ml)} · {report.bevute} drinks
            </span>
          </p>
          <Misuratore percentuale={percentualeAcqua} etichetta="Water goal reached" />
        </section>

        <section className="pila">
          <h3 className="titolo-sezione">
            <Icona nome="pillola" /> Medications
          </h3>
          <ul className="lista-semplice">
            {report.dosi.map((dose) => (
              <li key={dose.farmaco_id + dose.orario_previsto} className="riga-dose riga-lista">
                <strong>{dose.nome}</strong>
                <EtichettaDose dose={dose} />
                <p className="testo-secondario testo-piccolo riga-dose-testo">{orariDose(dose, fuso)}</p>
              </li>
            ))}
          </ul>
        </section>

        <section className="pila">
          <h3 className="titolo-sezione">
            <Icona nome="pasto" /> Meals
          </h3>
          <ul className="lista-semplice">
            {report.pasti.map((pasto) => (
              <li key={pasto.ora} className="riga-spaziata riga-lista">
                <span>
                  <strong>{oraDellaCasa(pasto.ora, fuso)}</strong> {maiuscola(pasto.cibi.join(", "))}
                </span>
                <span className="testo-secondario">ate {Math.round(pasto.percentuale_mangiata)}%</span>
              </li>
            ))}
          </ul>
        </section>

        <section className="pila">
          <h3 className="titolo-sezione">
            <Icona nome="luna" /> Night and safety
          </h3>
          <div className="tessere">
            <div className="tessera">
              <span className="numero-medio">{report.alzate_notturne}</span>
              <span className="testo-secondario">night-time rises</span>
            </div>
            <div className="tessera">
              <span className="numero-medio">{durata(report.minuti_fuori_letto_notte)}</span>
              <span className="testo-secondario">out of bed at night</span>
            </div>
            <div className="tessera">
              <span className="numero-medio">{report.cadute}</span>
              <span className="testo-secondario">falls</span>
            </div>
            <div className="tessera">
              <span className="numero-medio">{report.uscite_in_orario_vietato}</span>
              <span className="testo-secondario">exits in no-exit hours</span>
            </div>
          </div>
        </section>
      </article>
    </>
  );
}

function ReportDelPeriodo({ tipo }: { tipo: "settimanale" | "mensile" }) {
  // Settimana: i 7 giorni che finiscono con l'ultimo giorno della casa demo. Mese: il mese di quel giorno.
  const [dal, setDal] = useState(spostaGiorno(GIORNO_DEMO, -6));
  const [mese, setMese] = useState(GIORNO_DEMO.slice(0, 7));
  const [report, setReport] = useState<ReportPeriodo | null>(null);
  const [errore, setErrore] = useState("");

  useEffect(() => {
    async function carica() {
      setReport(null);
      setErrore("");
      try {
        if (tipo === "settimanale") {
          setReport(await leggiReportSettimanale(dal));
        } else {
          setReport(await leggiReportMensile(mese));
        }
      } catch (problema) {
        setErrore(String(problema));
      }
    }
    carica();
  }, [tipo, dal, mese]);

  // Il mese prima o dopo: si passa dal 15 del mese per non sbagliare con i mesi corti.
  function cambiaMese(direzione: number) {
    const metaMese = spostaGiorno(mese + "-15", direzione * 30);
    setMese(metaMese.slice(0, 7));
  }

  let scorri = (
    <ScorriPeriodo
      titolo={giornoEMese(dal) + " – " + giornoEMese(spostaGiorno(dal, 6))}
      onPrima={() => setDal(spostaGiorno(dal, -7))}
      onDopo={() => setDal(spostaGiorno(dal, 7))}
      dopoDisattivato={spostaGiorno(dal, 6) >= GIORNO_DEMO}
    />
  );
  if (tipo === "mensile") {
    scorri = (
      <ScorriPeriodo
        titolo={meseLungo(mese)}
        onPrima={() => cambiaMese(-1)}
        onDopo={() => cambiaMese(1)}
        dopoDisattivato={mese >= GIORNO_DEMO.slice(0, 7)}
      />
    );
  }

  if (report === null) {
    return (
      <>
        {scorri}
        <Caricamento errore={errore} />
      </>
    );
  }

  let giorniSimulati = 0;
  for (const riga of report.giorni) {
    if (riga.simulato) {
      giorniSimulati = giorniSimulati + 1;
    }
  }

  let titolo = "Weekly report";
  if (tipo === "mensile") {
    titolo = "Monthly report";
  }

  return (
    <>
      {scorri}
      <article className="scheda foglio-report pila-larga">
        <header className="riga-spaziata">
          <div>
            <h2>{titolo}</h2>
            <p className="testo-secondario">
              {report.giorni.length} days with data
              {giorniSimulati > 0 && <>, {giorniSimulati} of them simulated</>}
            </p>
          </div>
          {giorniSimulati > 0 && <EtichettaSimulato />}
        </header>

        <div className="tessere">
          <div className="tessera">
            <span className="numero-medio">{millilitri(report.acqua_media_ml)}</span>
            <span className="testo-secondario">water per day</span>
          </div>
          <div className="tessera">
            <span className="numero-medio">{numero(report.aderenza_farmaci_percentuale)}%</span>
            <span className="testo-secondario">doses taken</span>
          </div>
          <div className="tessera">
            <span className="numero-medio">{report.alzate_notturne_medie.toFixed(1)}</span>
            <span className="testo-secondario">night rises per night</span>
          </div>
          <div className="tessera">
            <span className="numero-medio">{report.cadute}</span>
            <span className="testo-secondario">falls</span>
          </div>
          <div className="tessera">
            <span className="numero-medio">{report.uscite_in_orario_vietato}</span>
            <span className="testo-secondario">exits in no-exit hours</span>
          </div>
        </div>

        <div className="tabella-contenitore">
          <table className="tabella">
            <thead>
              <tr>
                <th scope="col">Day</th>
                <th scope="col">Water</th>
                <th scope="col">Doses</th>
                <th scope="col">Eaten</th>
                <th scope="col">Night</th>
                <th scope="col">Falls</th>
                <th scope="col">Exits</th>
              </tr>
            </thead>
            <tbody>
              {report.giorni.map((riga) => (
                <tr key={riga.data}>
                  <th scope="row">
                    {giornoBreve(riga.data)} {riga.simulato && <span className="asterisco" title="Simulated">*</span>}
                  </th>
                  <td>{millilitri(riga.acqua_ml)}</td>
                  <td>
                    {riga.dosi_in_orario} · {riga.dosi_in_ritardo} · {riga.dosi_saltate}
                  </td>
                  <td>{riga.percentuale_mangiata_media === null ? "–" : Math.round(riga.percentuale_mangiata_media) + "%"}</td>
                  <td>{riga.alzate_notturne}</td>
                  <td>{riga.cadute}</td>
                  <td>{riga.uscite_in_orario_vietato}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="testo-secondario testo-piccolo">
          Doses: on time · late · missed. Night: times out of bed. Exits: during no-exit hours.
          {giorniSimulati > 0 && <> * Simulated day.</>}
        </p>
      </article>
    </>
  );
}
