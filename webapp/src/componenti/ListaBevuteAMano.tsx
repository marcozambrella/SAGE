// Le bevute segnate a mano in un giorno, con l'etichetta "Logged by family" e, dove si può, il pulsante per toglierle.
import type { Contenitore } from "../contratti";
import { millilitri } from "../formato";
import { testoBicchieri, type BevutaAMano } from "../inserimenti";
import EtichettaAMano from "./EtichettaAMano";
import Icona from "./Icona";

type Proprieta = {
  bevute: BevutaAMano[];
  contenitori: Contenitore[];
  // null nei report, che si leggono soltanto.
  onCancella: ((id: string) => void) | null;
};

export default function ListaBevuteAMano({ bevute, contenitori, onCancella }: Proprieta) {
  if (bevute.length === 0) {
    return null;
  }
  return (
    <ul className="lista-semplice">
      {bevute.map((bevuta) => (
        <li key={bevuta.id} className="riga-a-mano riga-lista">
          <div className="pila" style={{ gap: 4 }}>
            <p>
              <strong>{millilitri(bevuta.ml)}</strong> <span className="testo-secondario">at {bevuta.ora}</span>
            </p>
            {bevuta.bicchieri !== null && (
              <p className="testo-secondario testo-piccolo">{testoBicchieri(bevuta, contenitori)}</p>
            )}
            <div>
              <EtichettaAMano />
            </div>
          </div>
          {onCancella !== null && (
            <button
              type="button"
              className="pulsante pulsante-pericolo pulsante-icona"
              aria-label={"Delete the drink logged at " + bevuta.ora}
              onClick={() => onCancella(bevuta.id)}
            >
              <Icona nome="cestino" />
            </button>
          )}
        </li>
      ))}
    </ul>
  );
}
