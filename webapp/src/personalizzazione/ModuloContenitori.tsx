// Contenitori da cui beve (bicchiere, bottiglia, tazza) con la capienza: servono a calcolare i ml (D9).
import type { Contenitore, TipoContenitore } from "../contratti";
import Campo from "../componenti/Campo";
import Icona from "../componenti/Icona";
import Pulsante from "../componenti/Pulsante";
import { nuovoId } from "../salvataggio";

type Proprieta = {
  valore: Contenitore[];
  onCambia: (nuovi: Contenitore[]) => void;
};

// Nome e capienza proposti quando si aggiunge un contenitore: si possono cambiare subito dopo.
const PROPOSTE: Record<TipoContenitore, { nome: string; capienza: number }> = {
  bicchiere: { nome: "Glass", capienza: 250 },
  bottiglia: { nome: "Bottle", capienza: 500 },
  tazza: { nome: "Cup", capienza: 200 },
};

export default function ModuloContenitori({ valore, onCambia }: Proprieta) {
  function cambiaContenitore(indice: number, nuovo: Contenitore) {
    const copia = valore.slice();
    copia[indice] = nuovo;
    onCambia(copia);
  }

  function togliContenitore(indice: number) {
    const copia = valore.slice();
    copia.splice(indice, 1);
    onCambia(copia);
  }

  function aggiungi(tipo: TipoContenitore) {
    const proposta = PROPOSTE[tipo];
    const nuovo: Contenitore = { id: nuovoId("contenitore"), nome: proposta.nome, tipo: tipo, capienza_ml: proposta.capienza };
    onCambia(valore.concat([nuovo]));
  }

  return (
    <div className="pila-larga">
      <p className="testo-secondario">
        SAGE measures how far the drink level drops in the container. 30% of a 1,000 ml bottle is 300 ml.
      </p>

      {valore.map((contenitore, indice) => (
        <div key={contenitore.id} className="riquadro pila">
          <div className="riga-spaziata">
            <span className="riga">
              <span className="bolla-icona">
                <Icona nome="bicchiere" />
              </span>
              <h3>{PROPOSTE[contenitore.tipo].nome}</h3>
            </span>
            <button
              type="button"
              className="pulsante pulsante-pericolo pulsante-icona"
              aria-label={"Remove " + contenitore.nome}
              onClick={() => togliContenitore(indice)}
            >
              <Icona nome="cestino" />
            </button>
          </div>
          <div className="due-colonne">
            <Campo
              etichetta="Name"
              valore={contenitore.nome}
              onCambia={(testo) => cambiaContenitore(indice, { ...contenitore, nome: testo })}
              segnaposto="e.g. Blue glass"
            />
            <Campo
              etichetta="Holds"
              tipo="number"
              unita="ml"
              valore={String(contenitore.capienza_ml)}
              onCambia={(testo) => cambiaContenitore(indice, { ...contenitore, capienza_ml: Number(testo) })}
            />
          </div>
        </div>
      ))}

      <div className="tre-colonne">
        <Pulsante variante="secondario" onClick={() => aggiungi("bicchiere")}>
          <Icona nome="piu" /> Glass
        </Pulsante>
        <Pulsante variante="secondario" onClick={() => aggiungi("bottiglia")}>
          <Icona nome="piu" /> Bottle
        </Pulsante>
        <Pulsante variante="secondario" onClick={() => aggiungi("tazza")}>
          <Icona nome="piu" /> Cup
        </Pulsante>
      </div>
    </div>
  );
}
