// History: giorno per giorno, la linea del tempo degli eventi con le foto di prova.
import { useEffect, useState } from "react";
import type { Evento, Personalizzazione } from "../contratti";
import { leggiEventiDemo, leggiPeriodoDemo, leggiPersonalizzazioneDemo, type GiorniDemo } from "../api";
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
  const [periodo, setPeriodo] = useState<GiorniDemo | null>(null);
  const [personalizzazione, setPersonalizzazione] = useState<Personalizzazione | null>(null);
  const [giorno, setGiorno] = useState("");
  const [eventi, setEventi] = useState<Evento[] | null>(null);
  const [errore, setErrore] = useState("");

  // Prima si chiede quali giorni ha la casa demo: si parte dall'ultimo.
  useEffect(() => {
    async function carica() {
      try {
        const giorniDemo = await leggiPeriodoDemo();
        setPersonalizzazione(await leggiPersonalizzazioneDemo());
        setPeriodo(giorniDemo);
        setGiorno(giorniDemo.al);
      } catch (problema) {
        setErrore(String(problema));
      }
    }
    carica();
  }, []);

  // Poi gli eventi del giorno scelto.
  useEffect(() => {
    async function carica() {
      if (giorno === "") {
        return;
      }
      setEventi(null);
      setErrore("");
      try {
        setEventi(await leggiEventiDemo(giorno, giorno, null));
      } catch (problema) {
        setErrore(String(problema));
      }
    }
    carica();
  }, [giorno]);

  if (periodo === null) {
    return <Caricamento errore={errore} />;
  }

  // Gli ultimi giorni della casa demo, dal più recente, senza andare prima del primo giorno.
  const giorni: string[] = [];
  for (let i = 0; i < GIORNI_NELLA_STRISCIA; i++) {
    const voce = spostaGiorno(periodo.al, -i);
    if (voce >= periodo.dal) {
      giorni.push(voce);
    }
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
