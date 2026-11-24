// Reports: giornaliero, settimanale e mensile. Casa dell'utente: in attesa. Casa demo: /demo/report/*.
import { useEffect, useState } from "react";
import type { Personalizzazione, ReportGiornaliero, ReportPeriodo } from "../contratti";
import {
  leggiPeriodoDemo,
  leggiPersonalizzazioneDemo,
  leggiReportGiornaliero,
  leggiReportMensile,
  leggiReportSettimanale,
  messaggioErrore,
  type GiorniDemo,
} from "../api";
import {
  durata,
  giornoEMese,
  giornoLungo,
  maiuscola,
  meseLungo,
  millilitri,
  oraDellaCasa,
  percentuale,
  spostaGiorno,
} from "../formato";
import Caricamento from "../componenti/Caricamento";
import { orariDose } from "../descrizioni";
import EtichettaDose from "../componenti/EtichettaDose";
import EtichettaSimulato from "../componenti/EtichettaSimulato";
import Icona from "../componenti/Icona";
import InAttesaTelecamere from "../componenti/InAttesaTelecamere";
import Misuratore from "../componenti/Misuratore";
import TabellaGiorni from "../componenti/TabellaGiorni";
import TitoloPagina from "../componenti/TitoloPagina";
import { GraficoAcqua, GraficoDosi } from "../componenti/Grafici";

type Proprieta = {
  demo: boolean;
  personalizzazione: Personalizzazione | null;
};

type TipoReport = "giornaliero" | "settimanale" | "mensile";

export default function Report({ demo, personalizzazione }: Proprieta) {
  if (demo || personalizzazione === null) {
    return <ReportCasaDemo />;
  }
  return (
    <div className="pila-larga entrata">
      <TitoloPagina titolo="Reports" sotto="Calm summaries to read, keep, or bring to the doctor." />
      <InAttesaTelecamere
        testo={
          "Daily, weekly and monthly reports about " +
          personalizzazione.anziano.nome +
          " will be written here once the cameras are connected."
        }
        paginaDemo="/demo/reports"
      />
    </div>
  );
}

function ReportCasaDemo() {
  const [tipo, setTipo] = useState<TipoReport>("giornaliero");
  const [periodo, setPeriodo] = useState<GiorniDemo | null>(null);
  const [personalizzazione, setPersonalizzazione] = useState<Personalizzazione | null>(null);
  const [errore, setErrore] = useState("");

  useEffect(() => {
    async function carica() {
      try {
        setPeriodo(await leggiPeriodoDemo());
        setPersonalizzazione(await leggiPersonalizzazioneDemo());
      } catch (problema) {
        setErrore(messaggioErrore(problema));
      }
    }
    carica();
  }, []);

  let contenuto = <Caricamento errore={errore} />;
  if (periodo !== null && personalizzazione !== null) {
    if (tipo === "giornaliero") {
      contenuto = <ReportDelGiorno periodo={periodo} personalizzazione={personalizzazione} />;
    } else {
      contenuto = (
        <ReportDelPeriodo tipo={tipo} periodo={periodo} personalizzazione={personalizzazione} key={tipo} />
      );
    }
  }

  return (
    <div className="pila-larga entrata">
      <TitoloPagina titolo="Reports" sotto="Calm summaries to read, keep, or bring to the doctor." />
      <div className="segmenti" role="group" aria-label="Report period">
        <button
          type="button"
          className="segmento"
          aria-pressed={tipo === "giornaliero"}
          onClick={() => setTipo("giornaliero")}
        >
          Daily
        </button>
        <button
          type="button"
          className="segmento"
          aria-pressed={tipo === "settimanale"}
          onClick={() => setTipo("settimanale")}
        >
          Weekly
        </button>
        <button type="button" className="segmento" aria-pressed={tipo === "mensile"} onClick={() => setTipo("mensile")}>
          Monthly
        </button>
      </div>
      {contenuto}
    </div>
  );
}

// Frecce "prima" e "dopo" intorno al nome del periodo: si ferma al primo e all'ultimo giorno della casa demo.
type ProprietaScorri = {
  titolo: string;
  onPrima: () => void;
  onDopo: () => void;
  primaDisattivato: boolean;
  dopoDisattivato: boolean;
};

function ScorriPeriodo({ titolo, onPrima, onDopo, primaDisattivato, dopoDisattivato }: ProprietaScorri) {
  return (
    <div className="scorri-periodo">
      <button
        type="button"
        className="pulsante pulsante-secondario pulsante-icona"
        aria-label="Previous"
        disabled={primaDisattivato}
        onClick={onPrima}
      >
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

type ProprietaGiorno = {
  periodo: GiorniDemo;
  personalizzazione: Personalizzazione;
};

function ReportDelGiorno({ periodo, personalizzazione }: ProprietaGiorno) {
  const [giorno, setGiorno] = useState(periodo.al);
  const [report, setReport] = useState<ReportGiornaliero | null>(null);
  const [errore, setErrore] = useState("");

  useEffect(() => {
    async function carica() {
      setReport(null);
      setErrore("");
      try {
        setReport(await leggiReportGiornaliero(giorno));
      } catch (problema) {
        setErrore(messaggioErrore(problema));
      }
    }
    carica();
  }, [giorno]);

  const scorri = (
    <ScorriPeriodo
      titolo={giornoLungo(giorno)}
      onPrima={() => setGiorno(spostaGiorno(giorno, -1))}
      onDopo={() => setGiorno(spostaGiorno(giorno, 1))}
      primaDisattivato={giorno <= periodo.dal}
      dopoDisattivato={giorno >= periodo.al}
    />
  );

  if (report === null) {
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
              <li key={dose.farmaco_id + dose.orario_previsto} className="riga-con-stato riga-lista">
                <strong>{dose.nome}</strong>
                <EtichettaDose dose={dose} />
                <p className="testo-secondario testo-piccolo riga-con-stato-testo">{orariDose(dose, fuso)}</p>
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

type ProprietaPeriodo = {
  tipo: "settimanale" | "mensile";
  periodo: GiorniDemo;
  personalizzazione: Personalizzazione;
};

function ReportDelPeriodo({ tipo, periodo, personalizzazione }: ProprietaPeriodo) {
  // Settimana: i 7 giorni che finiscono con l'ultimo giorno della casa demo. Mese: il mese di quel giorno.
  const [dal, setDal] = useState(spostaGiorno(periodo.al, -6));
  const [mese, setMese] = useState(periodo.al.slice(0, 7));
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
        setErrore(messaggioErrore(problema));
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
      primaDisattivato={dal <= periodo.dal}
      dopoDisattivato={spostaGiorno(dal, 6) >= periodo.al}
    />
  );
  if (tipo === "mensile") {
    scorri = (
      <ScorriPeriodo
        titolo={meseLungo(mese)}
        onPrima={() => cambiaMese(-1)}
        onDopo={() => cambiaMese(1)}
        primaDisattivato={mese <= periodo.dal.slice(0, 7)}
        dopoDisattivato={mese >= periodo.al.slice(0, 7)}
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
            <span className="numero-medio">{percentuale(report.aderenza_farmaci_percentuale)}</span>
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

        <section className="pila">
          <h3 className="titolo-sezione">
            <Icona nome="goccia" /> Water each day
          </h3>
          <GraficoAcqua giorni={report.giorni} obiettivoMl={personalizzazione.anziano.obiettivo_acqua_ml} />
        </section>
        <section className="pila">
          <h3 className="titolo-sezione">
            <Icona nome="pillola" /> Doses each day
          </h3>
          <GraficoDosi giorni={report.giorni} />
        </section>
        <section className="pila">
          <h3 className="titolo-sezione">
            <Icona nome="calendario" /> Day by day
          </h3>
          <TabellaGiorni giorni={report.giorni} />
        </section>
      </article>
    </>
  );
}
