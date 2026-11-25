// Quanto ha mangiato: icona + parole + colore (mai il colore da solo), come per le dosi.
import type { QuantoMangiato } from "../contratti";
import { gravitaQuantoMangiato, testoQuantoMangiato } from "../descrizioni";
import Icona, { type NomeIcona } from "./Icona";

export default function EtichettaPasto({ quanto }: { quanto: QuantoMangiato | null }) {
  const gravita = gravitaQuantoMangiato(quanto);
  let icona: NomeIcona = "pasto";
  if (gravita === "attenzione") {
    icona = "avviso";
  }
  if (gravita === "buono") {
    icona = "spunta";
  }
  return (
    <span className={"stato stato-" + gravita}>
      <Icona nome={icona} dimensione={18} /> {testoQuantoMangiato(quanto)}
    </span>
  );
}
