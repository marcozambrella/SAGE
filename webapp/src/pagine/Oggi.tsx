// Today: la giornata in un colpo d'occhio. Casa dell'utente: in attesa delle telecamere. Casa demo: report del giorno.
import { useEffect, useState } from "react";
import { Link } from "react-router";
import type { Evento, Personalizzazione, ReportGiornaliero } from "../contratti";
import { GIORNO_DEMO, leggiEventiDemo, leggiPersonalizzazioneDemo, leggiReportGiornaliero } from "../api";
import { descriviEvento, orariDose, type Descrizione } from "../descrizioni";
import { durata, giornoLungo, maiuscola, millilitri, oraDellaCasa } from "../formato";
import Caricamento from "../componenti/Caricamento";
import EtichettaDose from "../componenti/EtichettaDose";
import EtichettaSimulato from "../componenti/EtichettaSimulato";
import Icona from "../componenti/Icona";
import InAttesaTelecamere from "../componenti/InAttesaTelecamere";
import Misuratore from "../componenti/Misuratore";
import Scheda from "../componenti/Scheda";
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
  let dosiAlGiorno = 0;
  for (const farmaco of personalizzazione.farmaci) {
    dosiAlGiorno = dosiAlGiorno + farmaco.orari.length;
  }
  return (
    <div className="pila-larga entrata">
      <TitoloPagina titolo={"Hello! Here's " + nome + "'s day"} sotto="Nothing to show yet." />
      <InAttesaTelecamere
        testo={
          "Medication, water, meals and night-time activity will appear here as soon as the cameras at " +
          nome +
          "'s home are connected. Camera connection is coming in a future release."
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
  const [errore, setErrore] = useState("");

  useEffect(() => {
    async function carica() {
      try {
        setPersonalizzazione(await leggiPersonalizzazioneDemo());
        setReport(await leggiReportGiornaliero(GIORNO_DEMO));
        const cadute = await leggiEventiDemo(GIORNO_DEMO, GIORNO_DEMO, "caduta");
        const uscite = await leggiEventiDemo(GIORNO_DEMO, GIORNO_DEMO, "uscita");
        setUrgenti(cadute.concat(uscite));
      } catch (problema) {
        setErrore(String(problema));
      }
    }
    carica();
  }, []);

  if (personalizzazione === null || report === null) {
    return <Caricamento errore={errore} />;
  }

  const fuso = personalizzazione.fuso_orario;
  const nome = personalizzazione.anziano.nome;
  const percentualeAcqua = (report.acqua_ml / report.obiettivo_acqua_ml) * 100;

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
        descrizione: { icona: "pillola", titolo: dose.nome + " missed", dettaglio: "Planned at " + dose.orario_previsto, gravita: "critico" },
      });
    }
  }

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

      <div className="griglia">
        <Scheda titolo="Water" icona="goccia" classe="scheda-acqua">
          <div className="pila">
            <p>
              <span className="numero-grande">{millilitri(report.acqua_ml)}</span>
            </p>
            <Misuratore percentuale={percentualeAcqua} etichetta="Water goal reached" />
            <p className="testo-secondario">
              {Math.round(percentualeAcqua)}% of the {millilitri(report.obiettivo_acqua_ml)} goal · {report.bevute} drinks
            </p>
          </div>
        </Scheda>

        <Scheda titolo="Medications" icona="pillola">
          <ul className="lista-semplice">
            {report.dosi.map((dose) => (
              <li key={dose.farmaco_id + dose.orario_previsto} className="riga-dose riga-lista">
                <strong>{dose.nome}</strong>
                <EtichettaDose dose={dose} />
                <p className="testo-secondario testo-piccolo riga-dose-testo">{orariDose(dose, personalizzazione.fuso_orario)}</p>
              </li>
            ))}
          </ul>
        </Scheda>

        <Scheda titolo="Meals" icona="pasto">
          <ul className="lista-semplice">
            {report.pasti.map((pasto) => (
              <li key={pasto.ora} className="pila riga-lista" style={{ gap: 6 }}>
                <div className="riga-spaziata">
                  <strong>{maiuscola(pasto.cibi.join(", "))}</strong>
                  <span className="testo-secondario testo-piccolo">{oraDellaCasa(pasto.ora, fuso)}</span>
                </div>
                <Misuratore percentuale={pasto.percentuale_mangiata} etichetta="Share of the plate eaten" sottile />
                <span className="testo-secondario testo-piccolo">Ate about {Math.round(pasto.percentuale_mangiata)}%</span>
              </li>
            ))}
          </ul>
        </Scheda>

        <Scheda titolo="Night and safety" icona="luna">
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
