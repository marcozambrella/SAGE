// Portone di casa (Marco, 25/11): SAGE conta le uscite solo dalla porta scelta (regole.portone_zona_id).
// La porta si sceglie sull'immagine di una telecamera, e nella web app le telecamere non si collegano ancora:
// per ora il passo spiega la funzione e si salta. Il campo resta null, cioè valgono tutte le porte.
import Icona from "../componenti/Icona";

export default function ModuloPortone({ nomeAnziano }: { nomeAnziano: string }) {
  return (
    <div className="pila">
      <div>
        <span className="stato stato-neutro">
          <Icona nome="orologio" dimensione={18} /> Coming in a future release
        </span>
      </div>
      <p>
        SAGE will count {nomeAnziano} going out only through the front door you choose here. A balcony, garden or cellar
        door won't set off the exit alert.
      </p>
      <p className="testo-secondario">
        You'll pick the door on a camera picture, so this needs the cameras connected. For now there is nothing to set
        here: until a door is chosen, every door the cameras see counts as a way out.
      </p>
    </div>
  );
}
