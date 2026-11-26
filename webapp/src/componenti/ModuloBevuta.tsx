// Modulo veloce "Log a drink": ora (adesso, si può cambiare) e quanto, a bicchieri oppure in ml.
// A bicchieri: ml = bicchieri × capienza del contenitore scelto, 200 ml se nella personalizzazione non ce n'è (API.md).
import { useId, useState } from "react";
import type { Contenitore } from "../contratti";
import { millilitri } from "../formato";
import { ML_BICCHIERE_NORMALE, type BevutaAMano } from "../inserimenti";
import { nuovoId } from "../salvataggio";
import Campo from "./Campo";
import Icona from "./Icona";
import Pulsante from "./Pulsante";

type Proprieta = {
  contenitori: Contenitore[];
  giorno: string;
  oraIniziale: string;
  onSalva: (bevuta: BevutaAMano) => void;
  onAnnulla: () => void;
};

// Il contenitore proposto: il primo bicchiere, altrimenti il primo contenitore, altrimenti nessuno ("").
function contenitoreIniziale(contenitori: Contenitore[]): string {
  for (const contenitore of contenitori) {
    if (contenitore.tipo === "bicchiere") {
      return contenitore.id;
    }
  }
  if (contenitori.length > 0) {
    return contenitori[0].id;
  }
  return "";
}

export default function ModuloBevuta({ contenitori, giorno, oraIniziale, onSalva, onAnnulla }: Proprieta) {
  const idScelta = useId();
  const [ora, setOra] = useState(oraIniziale);
  const [aBicchieri, setABicchieri] = useState(true);
  const [bicchieri, setBicchieri] = useState(1);
  const [contenitoreId, setContenitoreId] = useState(contenitoreIniziale(contenitori));
  const [testoMl, setTestoMl] = useState("");

  let capienza = ML_BICCHIERE_NORMALE;
  for (const contenitore of contenitori) {
    if (contenitore.id === contenitoreId) {
      capienza = contenitore.capienza_ml;
    }
  }
  let ml = Number(testoMl);
  if (aBicchieri) {
    ml = bicchieri * capienza;
  }
  const valido = ora !== "" && ml > 0 && ml <= 5000;

  function salva() {
    let numeroBicchieri: number | null = null;
    let idContenitore: string | null = null;
    if (aBicchieri) {
      numeroBicchieri = bicchieri;
      if (contenitoreId !== "") {
        idContenitore = contenitoreId;
      }
    }
    onSalva({
      id: nuovoId("bevuta"),
      tipo: "bevuta",
      giorno: giorno,
      ora: ora,
      ml: ml,
      bicchieri: numeroBicchieri,
      contenitore_id: idContenitore,
    });
  }

  return (
    <section className="scheda pila-larga entrata-singola" aria-labelledby={idScelta + "-titolo"}>
      <h2 id={idScelta + "-titolo"}>Log a drink</h2>
      <Campo etichetta="Time" tipo="time" valore={ora} onCambia={setOra} />

      <div className="segmenti" role="group" aria-label="Amount in">
        <button type="button" className="segmento" aria-pressed={aBicchieri} onClick={() => setABicchieri(true)}>
          Glasses
        </button>
        <button type="button" className="segmento" aria-pressed={!aBicchieri} onClick={() => setABicchieri(false)}>
          Millilitres
        </button>
      </div>

      {aBicchieri && (
        <div className="pila">
          <div className="contatore">
            <button
              type="button"
              className="pulsante pulsante-secondario pulsante-icona"
              aria-label="One glass less"
              disabled={bicchieri <= 1}
              onClick={() => setBicchieri(bicchieri - 1)}
            >
              <Icona nome="meno" />
            </button>
            <p className="contatore-valore" aria-live="polite">
              <span className="numero-medio">{bicchieri}</span> <span>{bicchieri === 1 ? "glass" : "glasses"}</span>
            </p>
            <button
              type="button"
              className="pulsante pulsante-secondario pulsante-icona"
              aria-label="One glass more"
              disabled={bicchieri >= 20}
              onClick={() => setBicchieri(bicchieri + 1)}
            >
              <Icona nome="piu" />
            </button>
          </div>
          {contenitori.length > 0 && (
            <div className="campo">
              <label className="campo-etichetta" htmlFor={idScelta}>
                Which glass or cup?
              </label>
              <div className="campo-pozzetto">
                <select
                  id={idScelta}
                  value={contenitoreId}
                  onChange={(evento) => setContenitoreId(evento.target.value)}
                >
                  {contenitori.map((contenitore) => (
                    <option key={contenitore.id} value={contenitore.id}>
                      {contenitore.nome} ({millilitri(contenitore.capienza_ml)})
                    </option>
                  ))}
                  <option value="">A normal glass ({millilitri(ML_BICCHIERE_NORMALE)})</option>
                </select>
              </div>
            </div>
          )}
          <p className="testo-secondario">That is {millilitri(ml)}.</p>
        </div>
      )}

      {!aBicchieri && (
        <Campo etichetta="How much" tipo="number" valore={testoMl} onCambia={setTestoMl} unita="ml" segnaposto="250" />
      )}

      <div className="due-colonne">
        <Pulsante variante="secondario" onClick={onAnnulla}>
          Cancel
        </Pulsante>
        <Pulsante disattivato={!valido} onClick={salva}>
          <Icona nome="spunta" /> Save drink
        </Pulsante>
      </div>
    </section>
  );
}
