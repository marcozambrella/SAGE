// Medications: il piano dei farmaci e, nella casa demo, come sono andate le dosi del giorno.
import { useEffect, useState } from "react";
import { Link } from "react-router";
import type { Farmaco, Personalizzazione, ReportGiornaliero, ReportPeriodo } from "../contratti";
import { leggiPeriodoDemo, leggiPersonalizzazioneDemo, leggiReportGiornaliero, leggiReportSettimanale } from "../api";
import { giornoLungo, percentuale, spostaGiorno } from "../formato";
import Caricamento from "../componenti/Caricamento";
import { orariDose } from "../descrizioni";
import EtichettaDose from "../componenti/EtichettaDose";
import Icona from "../componenti/Icona";
import InAttesaTelecamere from "../componenti/InAttesaTelecamere";
import Scheda from "../componenti/Scheda";
import TitoloPagina from "../componenti/TitoloPagina";
import { leggiFoto } from "../salvataggio";

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
          <MiniatureFoto fotoIds={farmaco.foto_ids} nomeFarmaco={farmaco.nome} />
        </li>
      ))}
    </ul>
  );
}

// Le foto di scatola e blister salvate nel browser (la casa demo non ne ha: lì non si vede niente).
function MiniatureFoto({ fotoIds, nomeFarmaco }: { fotoIds: string[]; nomeFarmaco: string }) {
  const immagini: string[] = [];
  for (const id of fotoIds) {
    const immagine = leggiFoto(id);
    if (immagine !== null) {
      immagini.push(immagine);
    }
  }
  if (immagini.length === 0) {
    return null;
  }
  return (
    <div className="riga miniature" style={{ gap: 8, flexBasis: "100%" }}>
      {immagini.map((immagine, indice) => (
        <img key={indice} src={immagine} alt={nomeFarmaco + ", photo " + (indice + 1)} />
      ))}
    </div>
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
        const giorno = (await leggiPeriodoDemo()).al;
        setPersonalizzazione(await leggiPersonalizzazioneDemo());
        setOggi(await leggiReportGiornaliero(giorno));
        setSettimana(await leggiReportSettimanale(spostaGiorno(giorno, -6)));
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
              <li key={dose.farmaco_id + dose.orario_previsto} className="riga-dose riga-lista">
                <strong>{dose.nome}</strong>
                <EtichettaDose dose={dose} />
                <p className="testo-secondario testo-piccolo riga-dose-testo">{orariDose(dose, personalizzazione.fuso_orario)}</p>
              </li>
            ))}
          </ul>
        </Scheda>
        <Scheda titolo="Last 7 days" icona="andamento">
          <p>
            <span className="numero-grande">{percentuale(settimana.aderenza_farmaci_percentuale)}</span>
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
