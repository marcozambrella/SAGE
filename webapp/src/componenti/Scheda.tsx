// Scheda: il "cuscino" in rilievo su cui sta ogni blocco di contenuto.
import type { ReactNode } from "react";
import Icona, { type NomeIcona } from "./Icona";

type Proprieta = {
  titolo?: string;
  icona?: NomeIcona;
  // Qualcosa da mostrare a destra del titolo (es. l'etichetta "Simulated").
  accanto?: ReactNode;
  classe?: string;
  children: ReactNode;
};

export default function Scheda({ titolo, icona, accanto, classe = "", children }: Proprieta) {
  return (
    <section className={"scheda " + classe}>
      {titolo && (
        <div className="scheda-intestazione">
          {icona && (
            <span className="bolla-icona">
              <Icona nome={icona} />
            </span>
          )}
          <h2>{titolo}</h2>
          {accanto && <div style={{ marginLeft: "auto" }}>{accanto}</div>}
        </div>
      )}
      {children}
    </section>
  );
}
