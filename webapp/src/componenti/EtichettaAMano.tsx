// "Logged by family": ogni inserimento a mano di un familiare si riconosce da questa etichetta (API.md).
import Icona from "./Icona";

export default function EtichettaAMano() {
  return (
    <span className="a-mano">
      <Icona nome="famiglia" dimensione={16} /> Logged by family
    </span>
  );
}
