// Settings: la stessa personalizzazione della procedura guidata, modificabile dopo (D21). Si salva nel browser (D29).
import { useState } from "react";
import { Link, useNavigate } from "react-router";
import type { Personalizzazione } from "../contratti";
import Icona from "../componenti/Icona";
import Pulsante from "../componenti/Pulsante";
import Scheda from "../componenti/Scheda";
import TitoloPagina from "../componenti/TitoloPagina";
import ModuloAnziano from "../personalizzazione/ModuloAnziano";
import ModuloContenitori from "../personalizzazione/ModuloContenitori";
import ModuloFarmaci from "../personalizzazione/ModuloFarmaci";
import ModuloRegole from "../personalizzazione/ModuloRegole";
import ModuloTelecamere from "../personalizzazione/ModuloTelecamere";

type Proprieta = {
  demo: boolean;
  personalizzazione: Personalizzazione | null;
  onSalva: (personalizzazione: Personalizzazione) => void;
  onCancella: () => void;
};

export default function Impostazioni({ demo, personalizzazione, onSalva, onCancella }: Proprieta) {
  if (demo || personalizzazione === null) {
    return (
      <div className="pila-larga entrata">
        <TitoloPagina titolo="Settings" />
        <Scheda titolo="The demo home can't be changed" icona="casa">
          <div className="pila">
            <p className="testo-secondario">
              Its medications, containers, cameras and alert hours come from the recorded demo. Your own settings
              are saved only in this browser.
            </p>
            <Link to="/settings" className="pulsante pulsante-secondario">
              Open my settings <Icona nome="freccia" />
            </Link>
          </div>
        </Scheda>
      </div>
    );
  }
  return <ImpostazioniCasaUtente personalizzazione={personalizzazione} onSalva={onSalva} onCancella={onCancella} />;
}

type ProprietaCasaUtente = {
  personalizzazione: Personalizzazione;
  onSalva: (personalizzazione: Personalizzazione) => void;
  onCancella: () => void;
};

function ImpostazioniCasaUtente({ personalizzazione, onSalva, onCancella }: ProprietaCasaUtente) {
  // Si modifica una copia: la personalizzazione salvata cambia solo con "Save changes".
  const [bozza, setBozza] = useState<Personalizzazione>(personalizzazione);
  const [salvato, setSalvato] = useState(false);
  const vai = useNavigate();

  const modificata = JSON.stringify(bozza) !== JSON.stringify(personalizzazione);
  const nomeMancante = bozza.anziano.nome.trim() === "";

  function cambia(nuova: Personalizzazione) {
    setBozza(nuova);
    setSalvato(false);
  }

  function salva() {
    onSalva(bozza);
    setSalvato(true);
  }

  function cancellaTutto() {
    const conferma = window.confirm("Delete your setup from this browser? You will start again from the welcome page.");
    if (conferma) {
      onCancella();
      vai("/");
    }
  }

  return (
    <div className="pila-larga entrata">
      <TitoloPagina titolo="Settings" sotto="Saved only in this browser. Nothing is sent to a server." />

      <Scheda titolo="About them" icona="cuore">
        <ModuloAnziano valore={bozza.anziano} onCambia={(anziano) => cambia({ ...bozza, anziano: anziano })} />
      </Scheda>
      <Scheda titolo="Medications" icona="pillola">
        <ModuloFarmaci valore={bozza.farmaci} onCambia={(farmaci) => cambia({ ...bozza, farmaci: farmaci })} />
      </Scheda>
      <Scheda titolo="Containers" icona="bicchiere">
        <ModuloContenitori
          valore={bozza.contenitori}
          onCambia={(contenitori) => cambia({ ...bozza, contenitori: contenitori })}
        />
      </Scheda>
      <Scheda titolo="Cameras" icona="telecamera">
        <ModuloTelecamere
          valore={bozza.telecamere}
          onCambia={(telecamere) => cambia({ ...bozza, telecamere: telecamere })}
        />
      </Scheda>
      <Scheda titolo="Alerts and night hours" icona="campanella">
        <ModuloRegole
          valore={bozza.regole}
          nomeAnziano={bozza.anziano.nome}
          onCambia={(regole) => cambia({ ...bozza, regole: regole })}
        />
      </Scheda>

      <Scheda titolo="Start again" icona="cestino">
        <div className="pila">
          <p className="testo-secondario">Delete everything saved in this browser and go back to the welcome page.</p>
          <Pulsante variante="pericolo" onClick={cancellaTutto}>
            <Icona nome="cestino" /> Delete my setup
          </Pulsante>
        </div>
      </Scheda>

      <div className="barra-salva">
        {salvato && !modificata && (
          <span className="stato stato-buono">
            <Icona nome="spunta" dimensione={18} /> Saved
          </span>
        )}
        <Pulsante disattivato={!modificata || nomeMancante} onClick={salva}>
          Save changes
        </Pulsante>
      </div>
    </div>
  );
}
