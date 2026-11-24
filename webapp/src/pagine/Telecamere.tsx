// Cameras: le telecamere previste (solo nome e stanza, D21). Il collegamento arriverà in una versione futura.
import { useEffect, useState } from "react";
import { Link } from "react-router";
import type { Evento, Personalizzazione } from "../contratti";
import { leggiEventiDemo, leggiPeriodoDemo, leggiPersonalizzazioneDemo, messaggioErrore } from "../api";
import { giornoLungo } from "../formato";
import Caricamento from "../componenti/Caricamento";
import Icona from "../componenti/Icona";
import Scheda from "../componenti/Scheda";
import TitoloPagina from "../componenti/TitoloPagina";

type Proprieta = {
  demo: boolean;
  personalizzazione: Personalizzazione | null;
};

export default function Telecamere({ demo, personalizzazione }: Proprieta) {
  if (demo || personalizzazione === null) {
    return <TelecamereCasaDemo />;
  }
  return (
    <div className="pila-larga entrata">
      <TitoloPagina titolo="Cameras" sotto="The cameras you planned for each room." />
      {personalizzazione.telecamere.length === 0 && (
        <Scheda>
          <p className="testo-secondario">No cameras planned yet.</p>
        </Scheda>
      )}
      <div className="griglia">
        {personalizzazione.telecamere.map((telecamera) => (
          <Scheda key={telecamera.id}>
            <div className="pila">
              <div className="riga">
                <span className="bolla-icona">
                  <Icona nome="telecamera" />
                </span>
                <div>
                  <h3>{telecamera.nome}</h3>
                  <p className="testo-secondario testo-piccolo">{telecamera.stanza}</p>
                </div>
              </div>
              <button type="button" className="pulsante pulsante-largo" disabled>
                Connect
              </button>
              <p className="testo-secondario testo-piccolo">Coming in a future release.</p>
            </div>
          </Scheda>
        ))}
      </div>
      <div className="riga">
        <Link to="/settings" className="pulsante pulsante-secondario">
          <Icona nome="cursori" /> Edit cameras
        </Link>
        <Link to="/demo/cameras" className="pulsante pulsante-secondario">
          See the demo cameras <Icona nome="freccia" />
        </Link>
      </div>
    </div>
  );
}

function TelecamereCasaDemo() {
  const [personalizzazione, setPersonalizzazione] = useState<Personalizzazione | null>(null);
  const [giorno, setGiorno] = useState("");
  const [eventi, setEventi] = useState<Evento[] | null>(null);
  const [errore, setErrore] = useState("");

  useEffect(() => {
    async function carica() {
      try {
        const ultimo = (await leggiPeriodoDemo()).al;
        setGiorno(ultimo);
        setPersonalizzazione(await leggiPersonalizzazioneDemo());
        setEventi(await leggiEventiDemo(ultimo, ultimo, null));
      } catch (problema) {
        setErrore(messaggioErrore(problema));
      }
    }
    carica();
  }, []);

  if (personalizzazione === null || eventi === null) {
    return <Caricamento errore={errore} />;
  }

  // Quanti eventi ha visto ogni telecamera nel giorno della casa demo (dalle "fonti" di ogni evento).
  const eventiPerTelecamera: Record<string, number> = {};
  for (const telecamera of personalizzazione.telecamere) {
    eventiPerTelecamera[telecamera.id] = 0;
  }
  for (const evento of eventi) {
    for (const fonte of evento.fonti) {
      if (fonte.telecamera_id in eventiPerTelecamera) {
        eventiPerTelecamera[fonte.telecamera_id] = eventiPerTelecamera[fonte.telecamera_id] + 1;
      }
    }
  }

  return (
    <div className="pila-larga entrata">
      <TitoloPagina
        titolo="Cameras"
        sotto="The demo home's cameras recorded real scenes; SAGE processed the videos offline."
      />
      <div className="griglia">
        {personalizzazione.telecamere.map((telecamera) => (
          <Scheda key={telecamera.id}>
            <div className="riga-spaziata">
              <div className="riga">
                <span className="bolla-icona">
                  <Icona nome="telecamera" />
                </span>
                <div>
                  <h3>{telecamera.nome}</h3>
                  <p className="testo-secondario testo-piccolo">{telecamera.stanza}</p>
                </div>
              </div>
              <span className="stato stato-buono">
                <Icona nome="spunta" dimensione={18} /> Recorded video
              </span>
            </div>
            <p className="testo-secondario" style={{ marginTop: 12 }}>
              {eventiPerTelecamera[telecamera.id]} events seen on {giornoLungo(giorno)}
            </p>
          </Scheda>
        ))}
      </div>
    </div>
  );
}
