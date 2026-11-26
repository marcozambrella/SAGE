// Modulo veloce "Log a meal": ora, cibi (facoltativi) e quanto ha mangiato. "Nothing" vuol dire pasto saltato.
import { useId, useState } from "react";
import { testoQuantoMangiato } from "../descrizioni";
import type { PastoAMano, QuantoMangiatoAMano } from "../inserimenti";
import { nuovoId } from "../salvataggio";
import BarraPasto from "./BarraPasto";
import Campo from "./Campo";
import Icona from "./Icona";
import Pulsante from "./Pulsante";

type Proprieta = {
  giorno: string;
  oraIniziale: string;
  onSalva: (pasto: PastoAMano) => void;
  onAnnulla: () => void;
};

const SCELTE: QuantoMangiatoAMano[] = ["niente", "meno_di_meta", "meta", "tutto"];

export default function ModuloPasto({ giorno, oraIniziale, onSalva, onAnnulla }: Proprieta) {
  const idTitolo = useId();
  const [ora, setOra] = useState(oraIniziale);
  const [cibi, setCibi] = useState("");
  // Nessuna scelta all'inizio: quanto ha mangiato lo dice il familiare, non lo si indovina.
  const [quanto, setQuanto] = useState<QuantoMangiatoAMano | null>(null);
  const valido = ora !== "" && quanto !== null;

  function salva() {
    if (quanto === null) {
      return;
    }
    onSalva({ id: nuovoId("pasto"), tipo: "pasto", giorno: giorno, ora: ora, cibi: cibi.trim(), quanto: quanto });
  }

  const pulsanti = [];
  for (const scelta of SCELTE) {
    let testo = testoQuantoMangiato(scelta);
    if (scelta === "niente") {
      testo = "Nothing, skipped it";
    }
    pulsanti.push(
      <button
        key={scelta}
        type="button"
        className="scelta"
        aria-pressed={quanto === scelta}
        onClick={() => setQuanto(scelta)}
      >
        <BarraPasto quanto={scelta} verticale={false} />
        <span>{testo}</span>
      </button>,
    );
  }

  return (
    <section className="scheda pila-larga entrata-singola" aria-labelledby={idTitolo}>
      <h2 id={idTitolo}>Log a meal</h2>
      <Campo etichetta="Time" tipo="time" valore={ora} onCambia={setOra} />
      <Campo
        etichetta="What was on the plate (optional)"
        valore={cibi}
        onCambia={setCibi}
        segnaposto="e.g. pasta, salad"
      />
      <div className="pila">
        <p className="campo-etichetta">How much did they eat?</p>
        <div className="scelte" role="group" aria-label="How much did they eat?">
          {pulsanti}
        </div>
      </div>
      <div className="due-colonne">
        <Pulsante variante="secondario" onClick={onAnnulla}>
          Cancel
        </Pulsante>
        <Pulsante disattivato={!valido} onClick={salva}>
          <Icona nome="spunta" /> Save meal
        </Pulsante>
      </div>
    </section>
  );
}
