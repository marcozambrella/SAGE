// Quanto ha mangiato, come barra di completamento (Marco, 25/11): meno di metà un terzo arancione, metà gialla,
// tutto piena verde, non misurato vuota e tratteggiata. Chi la usa mette anche le parole: mai il colore da solo.
import type { CSSProperties } from "react";
import type { QuantoMangiato } from "../contratti";

type Proprieta = {
  quanto: QuantoMangiato | null;
  // In piedi nel grafico dei Trends, sdraiata nelle liste dei pasti.
  verticale: boolean;
};

export default function BarraPasto({ quanto, verticale }: Proprieta) {
  let classe = "barra-pasto";
  if (verticale) {
    classe = classe + " barra-pasto-verticale";
  }
  if (quanto === null) {
    return <span className={classe + " barra-pasto-non-misurato"} aria-hidden="true" />;
  }

  let pieno = 100;
  let colore = "pasto-tutto";
  if (quanto === "meno_di_meta") {
    pieno = 33;
    colore = "pasto-poco";
  }
  if (quanto === "meta") {
    pieno = 50;
    colore = "pasto-meta";
  }
  let misura: CSSProperties = { width: pieno + "%" };
  if (verticale) {
    misura = { height: pieno + "%" };
  }
  return (
    <span className={classe} aria-hidden="true">
      <span className={"barra-pasto-pieno " + colore} style={misura} />
    </span>
  );
}
