// Medications: il piano dei farmaci e, nella casa demo, come sono andate le dosi del giorno.
import { useEffect, useState } from "react";
import { Link } from "react-router";
import type { Farmaco, Personalizzazione, ReportGiornaliero, ReportPeriodo } from "../contratti";
import { GIORNO_DEMO, leggiPersonalizzazioneDemo, leggiReportGiornaliero, leggiReportSettimanale } from "../api";
import { giornoLungo, numero, spostaGiorno } from "../formato";
import Caricamento from "../componenti/Caricamento";
import EtichettaDose from "../componenti/EtichettaDose";
import Icona from "../componenti/Icona";
import InAttesaTelecamere from "../componenti/InAttesaTelecamere";
import Scheda from "../componenti/Scheda";
import TitoloPagina from "../componenti/TitoloPagina";

type Proprieta = {
  demo: boolean;
  personalizzazione: Personalizzazione | null;
};

export default function Farmaci({ demo, personalizzazione }: Proprieta) {
  if (demo || personalizzazione === null) {
    return <FarmaciCasaDemo />;
  }
  return (
    <div className="pila-larga entrata">
      <TitoloPagina titolo="Medications" sotto={"The plan for " + personalizzazione.anziano.nome + "."} />
      <Scheda titolo="Plan" icona="pillola">
        <PianoFarmaci farmaci={personalizzazione.farmaci} />
        <div className="riga" style={{ marginTop: 20 }}>
          <Link to="/settings" className="pulsante pulsante-secondario">
            <Icona nome="cursori" /> Edit medications
          </Link>
        </div>
      </Scheda>
      <InAttesaTelecamere
        testo="Each dose will be checked here, on time, late or missed, once the cameras are connected."
        paginaDemo="/demo/medications"
        piccola
      />
    </div>
  );
}

function PianoFarmaci({ farmaci }: { farmaci: Farmaco[] }) {
  if (farmaci.length === 0) {
    return <p className="testo-secondario">No medications in the plan.</p>;
  }
  return (
    <ul className="lista-semplice">
      {farmaci.map((farmaco) => (
        <li key={farmaco.id} className="riga-spaziata riga-lista">
          <div>
            <strong>{farmaco.nome}</strong>
            <p className="testo-secondario testo-piccolo">
              {farmaco.dose} · on time within {farmaco.tolleranza_minuti} min
            </p>
          </div>
          <div className="riga" style={{ gap: 6 }}>
            {farmaco.orari.map((orario) => (
              <span key={orario} className="stato stato-neutro">
                <Icona nome="orologio" dimensione={18} /> {orario}
              </span>
            ))}
          </div>
        </li>
      ))}
    </ul>
  );
}

function FarmaciCasaDemo() {
  const [personalizzazione, setPersonalizzazione] = useState<Personalizzazione | null>(null);
  const [oggi, setOggi] = useState<ReportGiornaliero | null>(null);
  const [settimana, setSettimana] = useState<ReportPeriodo | null>(null);
  const [errore, setErrore] = useState("");

  useEffect(() => {
    async function carica() {
      try {
        setPersonalizzazione(await leggiPersonalizzazioneDemo());
        setOggi(await leggiReportGiornaliero(GIORNO_DEMO));
        setSettimana(await leggiReportSettimanale(spostaGiorno(GIORNO_DEMO, -6)));
      } catch (problema) {
        setErrore(String(problema));
      }
    }
    carica();
  }, []);

  if (personalizzazione === null || oggi === null || settimana === null) {
    return <Caricamento errore={errore} />;
  }

  return (
    <div className="pila-larga entrata">
      <TitoloPagina titolo="Medications" sotto={"The plan for " + personalizzazione.anziano.nome + ", and how it went."} />
      <div className="griglia">
        <Scheda titolo={"Doses on " + giornoLungo(oggi.data)} icona="sole">
          <ul className="lista-semplice">
            {oggi.dosi.map((dose) => (
              <li key={dose.farmaco_id + dose.orario_previsto} className="riga-spaziata riga-lista">
                <div>
                  <strong>{dose.nome}</strong>
                  <p className="testo-secondario testo-piccolo">Planned at {dose.orario_previsto}</p>
                </div>
                <EtichettaDose dose={dose} fusoOrario={personalizzazione.fuso_orario} />
              </li>
            ))}
          </ul>
        </Scheda>
        <Scheda titolo="Last 7 days" icona="andamento">
          <p>
            <span className="numero-grande">{numero(settimana.aderenza_farmaci_percentuale)}%</span>
          </p>
          <p className="testo-secondario">of planned doses were taken (on time or late).</p>
        </Scheda>
      </div>
      <Scheda titolo="Plan" icona="pillola">
        <PianoFarmaci farmaci={personalizzazione.farmaci} />
      </Scheda>
    </div>
  );
}
