// Today: la giornata in un colpo d'occhio. Casa dell'utente: in attesa delle telecamere, con acqua e pasti segnati a
// mano dai familiari. Casa demo: report del giorno, più gli inserimenti a mano (solo nel browser).
import { useEffect, useState } from "react";
import { Link } from "react-router";
import type { Evento, Personalizzazione, ReportGiornaliero } from "../contratti";
import {
  leggiEventiDemo,
  leggiPeriodoDemo,
  leggiPersonalizzazioneDemo,
  leggiReportGiornaliero,
  messaggioErrore,
} from "../api";
import { bevuteNonMisurate, descriviEvento, orariDose, testoNonMisurate, type Descrizione } from "../descrizioni";
import { giornoLungo, millilitri, oggiNellaCasa, oraDellaCasa } from "../formato";
import { bevuteAMano, pastiAMano, sommaMl, useInserimenti } from "../inserimenti";
import Caricamento from "../componenti/Caricamento";
import EtichettaDose from "../componenti/EtichettaDose";
import EtichettaSimulato from "../componenti/EtichettaSimulato";
import Icona from "../componenti/Icona";
import InAttesaTelecamere from "../componenti/InAttesaTelecamere";
import InserisciAMano from "../componenti/InserisciAMano";
import ListaBevuteAMano from "../componenti/ListaBevuteAMano";
import ListaPasti from "../componenti/ListaPasti";
import Misuratore from "../componenti/Misuratore";
import Scheda from "../componenti/Scheda";
import SonnoDellaNotte from "../componenti/SonnoDellaNotte";
import TitoloPagina from "../componenti/TitoloPagina";

type Proprieta = {
  demo: boolean;
  personalizzazione: Personalizzazione | null;
};

export default function Oggi({ demo, personalizzazione }: Proprieta) {
  if (demo || personalizzazione === null) {
    return <OggiCasaDemo />;
  }
  return <OggiCasaUtente personalizzazione={personalizzazione} />;
}

function OggiCasaUtente({ personalizzazione }: { personalizzazione: Personalizzazione }) {
  const nome = personalizzazione.anziano.nome;
  const fuso = personalizzazione.fuso_orario;
  const { inserimenti, aggiungi, cancella } = useInserimenti(false);
  let dosiAlGiorno = 0;
  for (const farmaco of personalizzazione.farmaci) {
    dosiAlGiorno = dosiAlGiorno + farmaco.orari.length;
  }
  // Oggi nel fuso della casa: senza telecamere acqua e pasti vengono solo da quello che segna la famiglia.
  const giorno = oggiNellaCasa(fuso);
  const bevute = bevuteAMano(inserimenti, giorno);
  const pasti = pastiAMano(inserimenti, giorno);
  const acqua = sommaMl(bevute);
  const obiettivo = personalizzazione.anziano.obiettivo_acqua_ml;

  return (
    <div className="pila-larga entrata">
      <TitoloPagina titolo={"Hello! Here's " + nome + "'s day"} sotto={giornoLungo(giorno)} />
      <InserisciAMano
        contenitori={personalizzazione.contenitori}
        fusoOrario={fuso}
        giorno={giorno}
        onAggiungi={aggiungi}
      />
      <div className="griglia">
        <Scheda titolo="Water" icona="goccia" classe="scheda-acqua">
          <div className="pila">
            <p>
              <span className="numero-grande">{millilitri(acqua)}</span>
            </p>
            <Misuratore percentuale={(acqua / obiettivo) * 100} etichetta="Water goal reached" />
            <p className="testo-secondario">
              {Math.round((acqua / obiettivo) * 100)}% of the {millilitri(obiettivo)} goal
            </p>
            {bevute.length === 0 && <p className="testo-secondario">No drinks logged yet today.</p>}
            <ListaBevuteAMano bevute={bevute} contenitori={personalizzazione.contenitori} onCancella={cancella} />
          </div>
        </Scheda>
        <Scheda titolo="Meals" icona="pasto">
          {pasti.length === 0 && <p className="testo-secondario">No meals logged yet today.</p>}
          <ListaPasti pasti={[]} pastiAMano={pasti} fusoOrario={fuso} onCancella={cancella} />
        </Scheda>
      </div>
      <InAttesaTelecamere
        testo={
          "Medication, sleep and night-time activity will appear here as soon as the cameras at " +
          nome +
          "'s home are connected. Camera connection is coming in a future release. Until then, you can log " +
          "drinks and meals yourself."
        }
        paginaDemo="/demo/today"
      />
      <Scheda titolo="Your setup" icona="cursori">
        <div className="tessere">
          <div className="tessera">
            <span className="numero-medio">{dosiAlGiorno}</span>
            <span className="testo-secondario">doses a day</span>
          </div>
          <div className="tessera">
            <span className="numero-medio">{millilitri(personalizzazione.anziano.obiettivo_acqua_ml)}</span>
            <span className="testo-secondario">water goal</span>
          </div>
          <div className="tessera">
            <span className="numero-medio">{personalizzazione.contenitori.length}</span>
            <span className="testo-secondario">containers</span>
          </div>
          <div className="tessera">
            <span className="numero-medio">{personalizzazione.telecamere.length}</span>
            <span className="testo-secondario">cameras planned</span>
          </div>
        </div>
        <div className="riga" style={{ marginTop: 20 }}>
          <Link to="/settings" className="pulsante pulsante-secondario">
            <Icona nome="cursori" /> Change setup
          </Link>
        </div>
      </Scheda>
    </div>
  );
}

function OggiCasaDemo() {
  const [personalizzazione, setPersonalizzazione] = useState<Personalizzazione | null>(null);
  const [report, setReport] = useState<ReportGiornaliero | null>(null);
  const [urgenti, setUrgenti] = useState<Evento[]>([]);
  const [nonMisurate, setNonMisurate] = useState(0);
  const [errore, setErrore] = useState("");
  const { inserimenti, aggiungi, cancella } = useInserimenti(true);

  useEffect(() => {
    async function carica() {
      try {
        // "Oggi" nella casa demo è l'ultimo giorno con dati (quello dei video registrati).
        const giorno = (await leggiPeriodoDemo()).al;
        setPersonalizzazione(await leggiPersonalizzazioneDemo());
        setReport(await leggiReportGiornaliero(giorno));
        const cadute = await leggiEventiDemo(giorno, giorno, "caduta");
        const uscite = await leggiEventiDemo(giorno, giorno, "uscita");
        setUrgenti(cadute.concat(uscite));
        setNonMisurate(bevuteNonMisurate(await leggiEventiDemo(giorno, giorno, "bevuta")));
      } catch (problema) {
        setErrore(messaggioErrore(problema));
      }
    }
    carica();
  }, []);

  if (personalizzazione === null || report === null) {
    return <Caricamento errore={errore} />;
  }

  const fuso = personalizzazione.fuso_orario;
  const nome = personalizzazione.anziano.nome;
  // Le bevute e i pasti segnati a mano si sommano a quelli visti dalle telecamere (API.md).
  const bevute = bevuteAMano(inserimenti, report.data);
  const pasti = pastiAMano(inserimenti, report.data);
  const acqua = report.acqua_ml + sommaMl(bevute);
  const percentualeAcqua = (acqua / report.obiettivo_acqua_ml) * 100;

  // Cose che meritano attenzione: cadute, uscite in orario vietato, dosi saltate.
  const attenzioni: { chiave: string; ora: string; descrizione: Descrizione }[] = [];
  for (const evento of urgenti) {
    const descrizione = descriviEvento(evento, personalizzazione);
    if (descrizione.gravita === "critico") {
      attenzioni.push({ chiave: evento.id, ora: oraDellaCasa(evento.inizio, fuso), descrizione: descrizione });
    }
  }
  for (const dose of report.dosi) {
    if (dose.stato === "saltata") {
      attenzioni.push({
        chiave: dose.farmaco_id + dose.orario_previsto,
        ora: dose.orario_previsto,
        descrizione: {
          icona: "pillola",
          titolo: dose.nome + " missed",
          dettaglio: "Planned at " + dose.orario_previsto,
          gravita: "critico",
        },
      });
    }
  }

  // In ordine di ora, come sono successe.
  attenzioni.sort(confrontaOra);

  return (
    <div className="pila-larga entrata">
      <TitoloPagina
        titolo={nome + "'s day"}
        sotto={
          <>
            {giornoLungo(report.data)} · from the recorded videos {report.simulato && <EtichettaSimulato />}
          </>
        }
      />

      {attenzioni.length > 0 && (
        <section className="scheda scheda-attenzione">
          <div className="scheda-intestazione">
            <span className="bolla-icona bolla-critica">
              <Icona nome="avviso" />
            </span>
            <h2>Needs your attention</h2>
          </div>
          <ul className="lista-semplice">
            {attenzioni.map((voce) => (
              <li key={voce.chiave} className="riga-attenzione">
                <span className="stato stato-critico">
                  <Icona nome={voce.descrizione.icona} dimensione={18} /> {voce.ora}
                </span>
                <div>
                  <strong>{voce.descrizione.titolo}</strong>
                  <p className="testo-secondario testo-piccolo">{voce.descrizione.dettaglio}</p>
                </div>
              </li>
            ))}
          </ul>
          <Link to="/demo/history" className="pulsante pulsante-secondario">
            See the timeline <Icona nome="freccia" />
          </Link>
        </section>
      )}

      <InserisciAMano
        contenitori={personalizzazione.contenitori}
        fusoOrario={fuso}
        giorno={report.data}
        onAggiungi={aggiungi}
      />

      <div className="griglia">
        <Scheda titolo="Water" icona="goccia" classe="scheda-acqua">
          <div className="pila">
            <p>
              <span className="numero-grande">{millilitri(acqua)}</span>
            </p>
            <Misuratore percentuale={percentualeAcqua} etichetta="Water goal reached" />
            <p className="testo-secondario">
              {Math.round(percentualeAcqua)}% of the {millilitri(report.obiettivo_acqua_ml)} goal ·{" "}
              {report.bevute + bevute.length} drinks
            </p>
            {nonMisurate > 0 && <p className="testo-secondario testo-piccolo">{testoNonMisurate(nonMisurate)}</p>}
            <ListaBevuteAMano bevute={bevute} contenitori={personalizzazione.contenitori} onCancella={cancella} />
          </div>
        </Scheda>

        <Scheda titolo="Medications" icona="pillola">
          <ul className="lista-semplice">
            {report.dosi.map((dose) => (
              <li key={dose.farmaco_id + dose.orario_previsto} className="riga-con-stato riga-lista">
                <strong>{dose.nome}</strong>
                <EtichettaDose dose={dose} />
                <p className="testo-secondario testo-piccolo riga-con-stato-testo">
                  {orariDose(dose, personalizzazione.fuso_orario)}
                </p>
              </li>
            ))}
          </ul>
        </Scheda>

        <Scheda titolo="Meals" icona="pasto">
          <ListaPasti pasti={report.pasti} pastiAMano={pasti} fusoOrario={fuso} onCancella={cancella} />
        </Scheda>

        <Scheda titolo="Last night" icona="letto">
          <SonnoDellaNotte report={report} fusoOrario={fuso} />
        </Scheda>

        <Scheda titolo="Safety" icona="scudo">
          <div className="tessere">
            <div className="tessera">
              <span className="numero-medio">{report.cadute}</span>
              <span className="testo-secondario">falls</span>
            </div>
            <div className="tessera">
              <span className="numero-medio">
                {report.uscite_in_orario_vietato}
                <span className="numero-di"> / {report.uscite}</span>
              </span>
              <span className="testo-secondario">exits in no-exit hours</span>
            </div>
          </div>
        </Scheda>
      </div>
    </div>
  );
}

// Le ore "HH:MM" si confrontano bene anche come testo.
function confrontaOra(a: { ora: string }, b: { ora: string }): number {
  if (a.ora < b.ora) {
    return -1;
  }
  if (a.ora > b.ora) {
    return 1;
  }
  return 0;
}
