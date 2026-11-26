// Un inserimento a mano nella linea del tempo della History, con "Logged by family" e il pulsante per toglierlo.
import type { Contenitore } from "../contratti";
import { maiuscola, millilitri } from "../formato";
import { testoBicchieri, type InserimentoAMano } from "../inserimenti";
import EtichettaAMano from "./EtichettaAMano";
import EtichettaPasto from "./EtichettaPasto";
import Icona, { type NomeIcona } from "./Icona";

type Proprieta = {
  inserimento: InserimentoAMano;
  contenitori: Contenitore[];
  onCancella: (id: string) => void;
};

export default function RigaInserimento({ inserimento, contenitori, onCancella }: Proprieta) {
  let titolo = "Meal";
  let dettaglio = "";
  let icona: NomeIcona = "pasto";
  let nomeCosa = "meal";
  let classe = "evento evento-neutro";
  if (inserimento.tipo === "bevuta") {
    titolo = "Drank " + millilitri(inserimento.ml);
    dettaglio = testoBicchieri(inserimento, contenitori);
    icona = "goccia";
    nomeCosa = "drink";
  } else {
    if (inserimento.cibi !== "") {
      titolo = maiuscola(inserimento.cibi);
    }
    // Un pasto saltato si vede come le cose che meritano attenzione.
    if (inserimento.quanto === "niente") {
      classe = "evento evento-critico";
    }
  }

  return (
    <li className={classe}>
      <span className="evento-bolla" aria-hidden="true">
        <Icona nome={icona} dimensione={22} />
      </span>
      <div className="evento-testi">
        <div className="riga" style={{ gap: 8 }}>
          <span className="evento-ora">{inserimento.ora}</span>
          <EtichettaAMano />
        </div>
        <strong>{titolo}</strong>
        {inserimento.tipo === "pasto" && (
          <div>
            <EtichettaPasto quanto={inserimento.quanto} />
          </div>
        )}
        {dettaglio !== "" && <p className="testo-secondario testo-piccolo">{dettaglio}</p>}
        <div>
          <button
            type="button"
            className="pulsante pulsante-pericolo"
            aria-label={"Delete the " + nomeCosa + " logged at " + inserimento.ora + " (" + titolo + ")"}
            onClick={() => onCancella(inserimento.id)}
          >
            <Icona nome="cestino" /> Delete
          </button>
        </div>
      </div>
    </li>
  );
}
