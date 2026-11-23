// Regole degli allarmi: orari di uscita vietati, orari di notte, allarme uscita acceso o spento (D16).
// La pausa per N ore sta nella pagina Alerts, dove serve davvero.
import type { FasciaOraria, RegoleAllarmi } from "../contratti";
import CampiFascia from "./CampiFascia";
import Icona from "../componenti/Icona";
import Interruttore from "../componenti/Interruttore";
import Pulsante from "../componenti/Pulsante";

type Proprieta = {
  valore: RegoleAllarmi;
  onCambia: (nuove: RegoleAllarmi) => void;
  nomeAnziano: string;
};

export default function ModuloRegole({ valore, onCambia, nomeAnziano }: Proprieta) {
  function cambiaFascia(indice: number, nuova: FasciaOraria) {
    const copia = valore.orari_uscita_vietati.slice();
    copia[indice] = nuova;
    onCambia({ ...valore, orari_uscita_vietati: copia });
  }

  function togliFascia(indice: number) {
    const copia = valore.orari_uscita_vietati.slice();
    copia.splice(indice, 1);
    onCambia({ ...valore, orari_uscita_vietati: copia });
  }

  function aggiungiFascia() {
    const nuova: FasciaOraria = { dalle: "21:00", alle: "07:00" };
    onCambia({ ...valore, orari_uscita_vietati: valore.orari_uscita_vietati.concat([nuova]) });
  }

  return (
    <div className="pila-larga">
      <Interruttore
        etichetta="Exit alarm"
        descrizione={"Alert the family if " + nomeAnziano + " goes out during the hours below."}
        acceso={valore.allarme_uscita_attivo}
        onCambia={(acceso) => onCambia({ ...valore, allarme_uscita_attivo: acceso })}
      />

      <div className="pila">
        <h3>No-exit hours</h3>
        {valore.orari_uscita_vietati.length === 0 && (
          <p className="testo-secondario">No hours set: going out never raises an alarm.</p>
        )}
        {valore.orari_uscita_vietati.map((fascia, indice) => (
          <div key={indice} className="riquadro fascia-con-x">
            <CampiFascia valore={fascia} onCambia={(nuova) => cambiaFascia(indice, nuova)} />
            <button
              type="button"
              className="pulsante pulsante-pericolo pulsante-icona"
              aria-label="Remove these hours"
              onClick={() => togliFascia(indice)}
            >
              <Icona nome="cestino" />
            </button>
          </div>
        ))}
        <Pulsante variante="secondario" largo onClick={aggiungiFascia}>
          <Icona nome="piu" /> Add no-exit hours
        </Pulsante>
      </div>

      <div className="pila">
        <h3>Night hours</h3>
        <p className="testo-secondario">Getting out of bed during these hours counts as a night-time rise.</p>
        <div className="riquadro">
          <CampiFascia valore={valore.orari_notte} onCambia={(nuova) => onCambia({ ...valore, orari_notte: nuova })} />
        </div>
      </div>
    </div>
  );
}
