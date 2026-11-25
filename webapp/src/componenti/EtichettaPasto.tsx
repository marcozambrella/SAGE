// Quanto ha mangiato in una lista di pasti: la barra colorata e, accanto, le stesse cose a parole.
import type { QuantoMangiato } from "../contratti";
import { testoQuantoMangiato } from "../descrizioni";
import BarraPasto from "./BarraPasto";

export default function EtichettaPasto({ quanto }: { quanto: QuantoMangiato | null }) {
  return (
    <span className="pasto-quanto">
      <BarraPasto quanto={quanto} verticale={false} />
      <span>{testoQuantoMangiato(quanto)}</span>
    </span>
  );
}
