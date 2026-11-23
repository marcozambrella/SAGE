// History: giorno per giorno, la linea del tempo degli eventi con le foto di prova.
import { useEffect, useState } from "react";
import type { Evento, Personalizzazione } from "../contratti";
import { GIORNO_DEMO, leggiEventiDemo, leggiPersonalizzazioneDemo } from "../api";
import { giornoLungo, giornoSettimana, spostaGiorno } from "../formato";
import Caricamento from "../componenti/Caricamento";
import InAttesaTelecamere from "../componenti/InAttesaTelecamere";
import RigaEvento from "../componenti/RigaEvento";
import TitoloPagina from "../componenti/TitoloPagina";

type Proprieta = {
  demo: boolean;
  personalizzazione: Personalizzazione | null;
};

// Quanti giorni si possono scegliere nella striscia in alto.
const GIORNI_NELLA_STRISCIA = 14;

export default function Storico({ demo, personalizzazione }: Proprieta) {
  if (demo || personalizzazione === null) {
    return <StoricoCasaDemo />;
  }
  return (
    <div className="pila-larga entrata">
      <TitoloPagina titolo="History" sotto="Day by day, everything SAGE noticed." />
      <InAttesaTelecamere
        testo={
          "A timeline of " +
          personalizzazione.anziano.nome +
          "'s days, with a photo for each important moment, will appear here once the cameras are connected."
        }
        paginaDemo="/demo/history"
      />
    </div>
  );
}

function StoricoCasaDemo() {
  const [giorno, setGiorno] = useState(GIORNO_DEMO);
  const [personalizzazione, setPersonalizzazione] = useState<Personalizzazione | null>(null);
  const [eventi, setEventi] = useState<Evento[] | null>(null);
  const [errore, setErrore] = useState("");

  useEffect(() => {
    async function carica() {
      setEventi(null);
      setErrore("");
      try {
        setPersonalizzazione(await leggiPersonalizzazioneDemo());
        setEventi(await leggiEventiDemo(giorno, giorno, null));
      } catch (problema) {
        setErrore(String(problema));
      }
    }
    carica();
  }, [giorno]);

  // Gli ultimi giorni della casa demo, dal più recente.
  const giorni: string[] = [];
  for (let i = 0; i < GIORNI_NELLA_STRISCIA; i++) {
    giorni.push(spostaGiorno(GIORNO_DEMO, -i));
  }

  let contenuto = <Caricamento errore={errore} />;
  if (personalizzazione !== null && eventi !== null) {
    if (eventi.length === 0) {
      contenuto = <p className="scheda testo-secondario">Nothing was recorded on this day.</p>;
    } else {
      contenuto = (
        <section className="scheda">
          <ol className="linea-tempo">
            {eventi.map((evento) => (
              <RigaEvento key={evento.id} evento={evento} personalizzazione={personalizzazione} />
            ))}
          </ol>
        </section>
      );
    }
  }

  return (
    <div className="pila-larga entrata">
      <TitoloPagina titolo="History" sotto={giornoLungo(giorno)} />
      <div className="striscia-giorni" role="group" aria-label="Choose a day">
        {giorni.map((voce) => (
          <button
            key={voce}
            type="button"
            className="giorno-pallina"
            aria-pressed={voce === giorno}
            onClick={() => setGiorno(voce)}
          >
            <span className="testo-piccolo">{giornoSettimana(voce)}</span>
            <strong>{Number(voce.slice(8, 10))}</strong>
          </button>
        ))}
      </div>
      {contenuto}
    </div>
  );
}
