// Quanto ha mangiato in una lista di pasti: la barra colorata e, accanto, le stesse cose a parole.
import { testoQuantoMangiato } from "../descrizioni";
import type { QuantoMangiatoAMano } from "../inserimenti";
import BarraPasto from "./BarraPasto";
import Icona from "./Icona";

export default function EtichettaPasto({ quanto }: { quanto: QuantoMangiatoAMano | null }) {
  // Un pasto saltato si deve vedere subito: etichetta rossa invece della barra vuota.
  if (quanto === "niente") {
    return (
      <span className="stato stato-critico">
        <Icona nome="chiudi" dimensione={18} /> Meal skipped
      </span>
    );
  }
  return (
    <span className="pasto-quanto">
      <BarraPasto quanto={quanto} verticale={false} />
      <span>{testoQuantoMangiato(quanto)}</span>
    </span>
  );
}
