// Containers: bicchieri, bottiglie e tazze con la capienza, e come si calcolano i ml bevuti (D9).
import { useEffect, useState } from "react";
import { Link } from "react-router";
import type { Contenitore, Evento, Personalizzazione, TipoContenitore } from "../contratti";
import { GIORNO_DEMO, leggiEventiDemo, leggiPersonalizzazioneDemo } from "../api";
import { NOMI_CONTENITORI } from "../descrizioni";
import { giornoLungo, maiuscola, millilitri } from "../formato";
import Caricamento from "../componenti/Caricamento";
import Icona from "../componenti/Icona";
import InAttesaTelecamere from "../componenti/InAttesaTelecamere";
import Scheda from "../componenti/Scheda";
import TitoloPagina from "../componenti/TitoloPagina";

type Proprieta = {
  demo: boolean;
  personalizzazione: Personalizzazione | null;
};

export default function Contenitori({ demo, personalizzazione }: Proprieta) {
  if (demo || personalizzazione === null) {
    return <ContenitoriCasaDemo />;
  }
  return (
    <div className="pila-larga entrata">
      <TitoloPagina titolo="Containers" sotto="What they drink from, and how much it holds." />
      <Scheda titolo="Containers" icona="bicchiere">
        <ElencoContenitori contenitori={personalizzazione.contenitori} />
        <div className="riga" style={{ marginTop: 20 }}>
          <Link to="/settings" className="pulsante pulsante-secondario">
            <Icona nome="cursori" /> Edit containers
          </Link>
        </div>
      </Scheda>
      <ComeSiMisura />
      <InAttesaTelecamere
        testo="Each drink, with how many ml, will be listed here once the cameras are connected."
        paginaDemo="/demo/containers"
        piccola
      />
    </div>
  );
}

function ElencoContenitori({ contenitori }: { contenitori: Contenitore[] }) {
  if (contenitori.length === 0) {
    return <p className="testo-secondario">No containers yet.</p>;
  }
  return (
    <ul className="lista-semplice">
      {contenitori.map((contenitore) => (
        <li key={contenitore.id} className="riga-spaziata riga-lista">
          <div>
            <strong>{contenitore.nome}</strong>
            <p className="testo-secondario testo-piccolo">{maiuscola(NOMI_CONTENITORI[contenitore.tipo])}</p>
          </div>
          <span className="stato stato-neutro">{millilitri(contenitore.capienza_ml)}</span>
        </li>
      ))}
    </ul>
  );
}

// Spiegazione del calcolo dei ml dalla percentuale di altezza (D9), con l'esempio della bottiglia.
function ComeSiMisura() {
  return (
    <Scheda titolo="How SAGE measures a drink" icona="goccia">
      <div className="come-si-misura">
        <div className="bottiglia-disegno" aria-hidden="true">
          <span className="bottiglia-acqua" />
          <span className="bottiglia-sceso" />
        </div>
        <p className="testo-secondario">
          The camera sees how far the level drops while they drink. If it drops by 30% of the height of a
          1,000 ml bottle, that is <strong>300 ml</strong>. It is an estimate: it works best with straight-sided
          glasses and bottles.
        </p>
      </div>
    </Scheda>
  );
}

function ContenitoriCasaDemo() {
  const [personalizzazione, setPersonalizzazione] = useState<Personalizzazione | null>(null);
  const [bevute, setBevute] = useState<Evento[] | null>(null);
  const [errore, setErrore] = useState("");

  useEffect(() => {
    async function carica() {
      try {
        setPersonalizzazione(await leggiPersonalizzazioneDemo());
        setBevute(await leggiEventiDemo(GIORNO_DEMO, GIORNO_DEMO, "bevuta"));
      } catch (problema) {
        setErrore(String(problema));
      }
    }
    carica();
  }, []);

  if (personalizzazione === null || bevute === null) {
    return <Caricamento errore={errore} />;
  }

  // Quanto si è bevuto da ogni tipo di contenitore nel giorno della casa demo.
  const mlPerTipo: Record<TipoContenitore, number> = { bicchiere: 0, bottiglia: 0, tazza: 0 };
  const voltePerTipo: Record<TipoContenitore, number> = { bicchiere: 0, bottiglia: 0, tazza: 0 };
  for (const evento of bevute) {
    if (evento.tipo === "bevuta") {
      mlPerTipo[evento.valori.contenitore] = mlPerTipo[evento.valori.contenitore] + evento.valori.ml;
      voltePerTipo[evento.valori.contenitore] = voltePerTipo[evento.valori.contenitore] + 1;
    }
  }

  return (
    <div className="pila-larga entrata">
      <TitoloPagina titolo="Containers" sotto="What they drink from, and how much it holds." />
      <Scheda titolo={"Drinks on " + giornoLungo(GIORNO_DEMO)} icona="goccia">
        <ul className="lista-semplice">
          {personalizzazione.contenitori.map((contenitore) => (
            <li key={contenitore.id} className="riga-spaziata riga-lista">
              <div>
                <strong>{contenitore.nome}</strong>
                <p className="testo-secondario testo-piccolo">
                  {maiuscola(NOMI_CONTENITORI[contenitore.tipo])} · holds {millilitri(contenitore.capienza_ml)}
                </p>
              </div>
              <span className="stato stato-buono">
                <Icona nome="goccia" dimensione={18} /> {millilitri(mlPerTipo[contenitore.tipo])} ·{" "}
                {voltePerTipo[contenitore.tipo]}×
              </span>
            </li>
          ))}
        </ul>
      </Scheda>
      <ComeSiMisura />
    </div>
  );
}
