// Stato di una dose: icona + parola + colore (mai il colore da solo).
import type { DoseFarmaco } from "../contratti";
import { oraDellaCasa } from "../formato";
import Icona from "./Icona";

export default function EtichettaDose({ dose, fusoOrario }: { dose: DoseFarmaco; fusoOrario: string }) {
  if (dose.stato === "in_orario") {
    let testo = "On time";
    if (dose.ora_presa !== null) {
      testo = "On time · " + oraDellaCasa(dose.ora_presa, fusoOrario);
    }
    return (
      <span className="stato stato-buono">
        <Icona nome="spunta" dimensione={18} /> {testo}
      </span>
    );
  }
  if (dose.stato === "in_ritardo") {
    return (
      <span className="stato stato-attenzione">
        <Icona nome="orologio" dimensione={18} /> {dose.minuti_ritardo} min late
      </span>
    );
  }
  if (dose.stato === "saltata") {
    return (
      <span className="stato stato-critico">
        <Icona nome="chiudi" dimensione={18} /> Missed
      </span>
    );
  }
  return (
    <span className="stato stato-neutro">
      <Icona nome="orologio" dimensione={18} /> Not yet
    </span>
  );
}
