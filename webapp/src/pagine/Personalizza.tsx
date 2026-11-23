// Personalizzazione guidata (D21, D28): cinque passi, poi si salva nel browser (D29) e si va a "Coming soon".
import { useState } from "react";
import { useNavigate } from "react-router";
import type { Personalizzazione } from "../contratti";
import Icona from "../componenti/Icona";
import Pulsante from "../componenti/Pulsante";
import ModuloAnziano from "../personalizzazione/ModuloAnziano";
import ModuloContenitori from "../personalizzazione/ModuloContenitori";
import ModuloFarmaci from "../personalizzazione/ModuloFarmaci";
import ModuloRegole from "../personalizzazione/ModuloRegole";
import ModuloTelecamere from "../personalizzazione/ModuloTelecamere";
import { personalizzazioneVuota } from "../salvataggio";

const PASSI = [
  { titolo: "Who are you looking after?", sotto: "A few details so SAGE can speak about them by name." },
  { titolo: "Medications", sotto: "SAGE checks each dose is taken, and on time." },
  { titolo: "Cups, glasses and bottles", sotto: "The containers they usually drink from." },
  { titolo: "Cameras", sotto: "Which rooms the cameras will watch." },
  { titolo: "Alerts and night hours", sotto: "When going out is a worry, and when night starts." },
];

type Proprieta = {
  onSalva: (personalizzazione: Personalizzazione) => void;
};

export default function Personalizza({ onSalva }: Proprieta) {
  const [passo, setPasso] = useState(0);
  const [bozza, setBozza] = useState<Personalizzazione>(personalizzazioneVuota());
  const vai = useNavigate();

  const ultimoPasso = passo === PASSI.length - 1;
  const nomeMancante = bozza.anziano.nome.trim() === "";
  let nome = "them";
  if (!nomeMancante) {
    nome = bozza.anziano.nome.trim();
  }

  // Un pallino per passo: pieno se fatto, gonfio e colorato se è quello attuale.
  const pallini = [];
  for (let indice = 0; indice < PASSI.length; indice++) {
    let classe = "passo";
    if (indice < passo) {
      classe = "passo passo-fatto";
    }
    if (indice === passo) {
      classe = "passo passo-attuale";
    }
    pallini.push(<span key={indice} className={classe} />);
  }

  function avanti() {
    if (ultimoPasso) {
      onSalva(bozza);
      vai("/coming-soon");
      return;
    }
    setPasso(passo + 1);
    window.scrollTo(0, 0);
  }

  function indietro() {
    if (passo === 0) {
      vai("/");
      return;
    }
    setPasso(passo - 1);
    window.scrollTo(0, 0);
  }

  return (
    <div className="pagina-sola pila-larga">
      <div className="passi" aria-hidden="true">
        {pallini}
      </div>

      <div className="titolo-pagina" key={"titolo-" + passo}>
        <p className="testo-secondario testo-piccolo">
          Step {passo + 1} of {PASSI.length}
        </p>
        <h1>{PASSI[passo].titolo}</h1>
        <p className="testo-secondario">{PASSI[passo].sotto}</p>
      </div>

      <section className="scheda entrata-singola" key={"passo-" + passo}>
        {passo === 0 && (
          <ModuloAnziano valore={bozza.anziano} onCambia={(anziano) => setBozza({ ...bozza, anziano: anziano })} />
        )}
        {passo === 1 && (
          <ModuloFarmaci valore={bozza.farmaci} onCambia={(farmaci) => setBozza({ ...bozza, farmaci: farmaci })} />
        )}
        {passo === 2 && (
          <ModuloContenitori
            valore={bozza.contenitori}
            onCambia={(contenitori) => setBozza({ ...bozza, contenitori: contenitori })}
          />
        )}
        {passo === 3 && (
          <ModuloTelecamere
            valore={bozza.telecamere}
            onCambia={(telecamere) => setBozza({ ...bozza, telecamere: telecamere })}
          />
        )}
        {passo === 4 && (
          <ModuloRegole
            valore={bozza.regole}
            nomeAnziano={nome}
            onCambia={(regole) => setBozza({ ...bozza, regole: regole })}
          />
        )}
      </section>

      <div className="barra-azioni">
        <div className="barra-azioni-interno">
          <Pulsante variante="secondario" onClick={indietro}>
            <Icona nome="indietro" /> Back
          </Pulsante>
          <Pulsante disattivato={nomeMancante} onClick={avanti}>
            {ultimoPasso ? "Save my home" : "Next"} <Icona nome={ultimoPasso ? "spunta" : "freccia"} />
          </Pulsante>
        </div>
      </div>
    </div>
  );
}
