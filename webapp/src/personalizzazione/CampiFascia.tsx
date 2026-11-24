// Due orari "dalle" e "alle" affiancati (una FasciaOraria).
import type { FasciaOraria } from "../contratti";
import Campo from "../componenti/Campo";

type Proprieta = {
  valore: FasciaOraria;
  onCambia: (nuova: FasciaOraria) => void;
};

export default function CampiFascia({ valore, onCambia }: Proprieta) {
  return (
    <div className="due-colonne">
      <Campo
        etichetta="From"
        tipo="time"
        valore={valore.dalle}
        onCambia={(testo) => onCambia({ ...valore, dalle: testo })}
      />
      <Campo
        etichetta="To"
        tipo="time"
        valore={valore.alle}
        onCambia={(testo) => onCambia({ ...valore, alle: testo })}
      />
    </div>
  );
}
