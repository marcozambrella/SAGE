// I pasti di un giorno in ordine di ora: quelli visti dalle telecamere e quelli segnati a mano dai familiari.
import type { PastoDelGiorno } from "../contratti";
import { maiuscola, oraDellaCasa } from "../formato";
import type { PastoAMano, QuantoMangiatoAMano } from "../inserimenti";
import EtichettaAMano from "./EtichettaAMano";
import EtichettaPasto from "./EtichettaPasto";
import Icona from "./Icona";

type Proprieta = {
  pasti: PastoDelGiorno[];
  pastiAMano: PastoAMano[];
  fusoOrario: string;
  // null nei report, che si leggono soltanto.
  onCancella: ((id: string) => void) | null;
};

type Voce = {
  chiave: string;
  ora: string;
  titolo: string;
  quanto: QuantoMangiatoAMano | null;
  // L'id dell'inserimento a mano, "" per i pasti visti dalle telecamere.
  idAMano: string;
};

function confrontaOra(a: Voce, b: Voce): number {
  if (a.ora < b.ora) {
    return -1;
  }
  if (a.ora > b.ora) {
    return 1;
  }
  return 0;
}

export default function ListaPasti({ pasti, pastiAMano, fusoOrario, onCancella }: Proprieta) {
  const voci: Voce[] = [];
  for (const pasto of pasti) {
    const ora = oraDellaCasa(pasto.ora, fusoOrario);
    const titolo = maiuscola(pasto.cibi.join(", "));
    voci.push({ chiave: pasto.ora, ora: ora, titolo: titolo, quanto: pasto.quanto_mangiato, idAMano: "" });
  }
  for (const pasto of pastiAMano) {
    let titolo = "Meal";
    if (pasto.cibi !== "") {
      titolo = maiuscola(pasto.cibi);
    }
    voci.push({ chiave: pasto.id, ora: pasto.ora, titolo: titolo, quanto: pasto.quanto, idAMano: pasto.id });
  }
  voci.sort(confrontaOra);

  return (
    <ul className="lista-semplice">
      {voci.map((voce) => (
        <li key={voce.chiave} className="pila riga-lista" style={{ gap: 8 }}>
          <div className="riga-spaziata">
            <strong>{voce.titolo}</strong>
            <span className="testo-secondario testo-piccolo">{voce.ora}</span>
          </div>
          <div className="riga-a-mano">
            <div className="pila" style={{ gap: 8 }}>
              <div>
                <EtichettaPasto quanto={voce.quanto} />
              </div>
              {voce.idAMano !== "" && (
                <div>
                  <EtichettaAMano />
                </div>
              )}
            </div>
            {voce.idAMano !== "" && onCancella !== null && (
              <button
                type="button"
                className="pulsante pulsante-pericolo pulsante-icona"
                aria-label={"Delete the meal logged at " + voce.ora}
                onClick={() => onCancella(voce.idAMano)}
              >
                <Icona nome="cestino" />
              </button>
            )}
          </div>
        </li>
      ))}
    </ul>
  );
}
