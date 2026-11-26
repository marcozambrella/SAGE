// Agitazione di un giorno (Today e report del giorno): quanto ha camminato avanti e indietro senza meta.
import { durata } from "../formato";

export default function AgitazioneDelGiorno({ minuti }: { minuti: number }) {
  if (minuti === 0) {
    return <p className="testo-secondario">No restless pacing.</p>;
  }
  return (
    <div className="pila">
      <p>
        <span className="numero-medio">{durata(minuti)}</span>{" "}
        <span className="testo-secondario">of restless pacing</span>
      </p>
      <p className="testo-secondario testo-piccolo">
        Walking back and forth with no clear aim. In dementia it often rises in the late afternoon and evening.
      </p>
    </div>
  );
}
