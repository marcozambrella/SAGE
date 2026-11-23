// Dati della persona seguita: nome, anno di nascita, obiettivo d'acqua, note.
import type { Anziano } from "../contratti";
import Campo from "../componenti/Campo";

type Proprieta = {
  valore: Anziano;
  onCambia: (nuovo: Anziano) => void;
};

// Testo del campo numerico → numero; un campo vuoto diventa null.
function numeroODiNull(testo: string): number | null {
  if (testo.trim() === "") {
    return null;
  }
  return Number(testo);
}

export default function ModuloAnziano({ valore, onCambia }: Proprieta) {
  let annoNascita = "";
  if (valore.anno_nascita !== null) {
    annoNascita = String(valore.anno_nascita);
  }

  function cambiaObiettivo(testo: string) {
    let obiettivo = numeroODiNull(testo);
    if (obiettivo === null) {
      obiettivo = 0;
    }
    onCambia({ ...valore, obiettivo_acqua_ml: obiettivo });
  }

  return (
    <div className="pila-larga">
      <Campo
        etichetta="Their first name"
        valore={valore.nome}
        onCambia={(testo) => onCambia({ ...valore, nome: testo })}
        segnaposto="e.g. Rosa"
        obbligatorio
      />
      <Campo
        etichetta="Year of birth"
        tipo="number"
        valore={annoNascita}
        onCambia={(testo) => onCambia({ ...valore, anno_nascita: numeroODiNull(testo) })}
        segnaposto="e.g. 1942"
        aiuto="Optional."
      />
      <Campo
        etichetta="Daily water goal"
        tipo="number"
        unita="ml"
        valore={String(valore.obiettivo_acqua_ml)}
        onCambia={cambiaObiettivo}
        aiuto="Ask their doctor. Many older adults need about 1,500 ml a day."
      />
      <Campo
        etichetta="Notes"
        valore={valore.note}
        onCambia={(testo) => onCambia({ ...valore, note: testo })}
        segnaposto="e.g. Prefers tea in the afternoon"
        aiuto="Optional, only for your family."
      />
    </div>
  );
}
