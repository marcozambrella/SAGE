// Telecamere previste: solo nome e stanza (D21). Il collegamento vero arriverà in una versione futura.
import type { TelecameraPrevista } from "../contratti";
import Campo from "../componenti/Campo";
import Icona from "../componenti/Icona";
import Pulsante from "../componenti/Pulsante";
import { nuovoId } from "../salvataggio";

type Proprieta = {
  valore: TelecameraPrevista[];
  onCambia: (nuove: TelecameraPrevista[]) => void;
};

export default function ModuloTelecamere({ valore, onCambia }: Proprieta) {
  function cambiaTelecamera(indice: number, nuova: TelecameraPrevista) {
    const copia = valore.slice();
    copia[indice] = nuova;
    onCambia(copia);
  }

  function togliTelecamera(indice: number) {
    const copia = valore.slice();
    copia.splice(indice, 1);
    onCambia(copia);
  }

  function aggiungiTelecamera() {
    const nuova: TelecameraPrevista = { id: nuovoId("telecamera"), nome: "", stanza: "" };
    onCambia(valore.concat([nuova]));
  }

  return (
    <div className="pila-larga">
      <p className="testo-secondario">
        Plan where the cameras will go. You only name them here: connecting them is coming in a future release.
      </p>

      {valore.map((telecamera, indice) => (
        <div key={telecamera.id} className="riquadro pila">
          <div className="riga-spaziata">
            <span className="riga">
              <span className="bolla-icona">
                <Icona nome="telecamera" />
              </span>
              <h3>Camera {indice + 1}</h3>
            </span>
            <button
              type="button"
              className="pulsante pulsante-pericolo pulsante-icona"
              aria-label={"Remove camera " + (indice + 1)}
              onClick={() => togliTelecamera(indice)}
            >
              <Icona nome="cestino" />
            </button>
          </div>
          <div className="due-colonne">
            <Campo
              etichetta="Name"
              valore={telecamera.nome}
              onCambia={(testo) => cambiaTelecamera(indice, { ...telecamera, nome: testo })}
              segnaposto="e.g. Kitchen camera"
            />
            <Campo
              etichetta="Room"
              valore={telecamera.stanza}
              onCambia={(testo) => cambiaTelecamera(indice, { ...telecamera, stanza: testo })}
              segnaposto="e.g. Kitchen"
            />
          </div>
        </div>
      ))}

      <Pulsante variante="secondario" largo onClick={aggiungiTelecamera}>
        <Icona nome="piu" /> Add a camera
      </Pulsante>
    </div>
  );
}
