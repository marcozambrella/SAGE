// Foto di scatola e blister di un farmaco: si scelgono dal telefono (o si scattano), si rimpiccioliscono e si
// salvano subito nel browser; nel farmaco restano solo gli id (foto_ids).
import { useId, useState, type ChangeEvent } from "react";
import Icona from "../componenti/Icona";
import { rimpicciolisciFoto } from "../foto";
import { leggiFoto, nuovoId, salvaFoto } from "../salvataggio";

// Bastano poche foto per farmaco (scatola, fronte e retro del blister), e così lo spazio del browser basta.
const MASSIMO_FOTO = 3;

type Proprieta = {
  fotoIds: string[];
  nomeFarmaco: string;
  onCambia: (nuoviIds: string[]) => void;
};

export default function FotoFarmaco({ fotoIds, nomeFarmaco, onCambia }: Proprieta) {
  const [problema, setProblema] = useState("");
  const [inCorso, setInCorso] = useState(false);
  const idCampo = useId();

  async function aggiungiFoto(evento: ChangeEvent<HTMLInputElement>) {
    const elenco = evento.target.files;
    if (elenco === null || elenco.length === 0) {
      return;
    }
    const file = elenco[0];
    // Si svuota il campo, così si può scegliere di nuovo lo stesso file.
    evento.target.value = "";
    setProblema("");
    setInCorso(true);
    try {
      const immagine = await rimpicciolisciFoto(file);
      const id = nuovoId("foto");
      if (salvaFoto(id, immagine)) {
        onCambia(fotoIds.concat([id]));
      } else {
        setProblema("This browser has no space left for more photos. Remove some first.");
      }
    } catch {
      setProblema("This file doesn't look like a photo. Try another one.");
    }
    setInCorso(false);
  }

  function togliFoto(indice: number) {
    const copia = fotoIds.slice();
    copia.splice(indice, 1);
    onCambia(copia);
  }

  let nome = "this medication";
  if (nomeFarmaco.trim() !== "") {
    nome = nomeFarmaco.trim();
  }

  return (
    <div className="foto-farmaco">
      <div>
        <strong>Box and blister photos</strong>
        <p className="campo-aiuto">They help SAGE recognise {nome}. Saved only in this browser.</p>
      </div>
      <div className="foto-elenco">
        {fotoIds.map((id, indice) => (
          <FotoPiccola key={id} id={id} numero={indice + 1} onTogli={() => togliFoto(indice)} />
        ))}
        {/* Il campo vero è nascosto: si vede (e riceve il fuoco da tastiera) l'etichetta gonfia subito dopo */}
        <input
          id={idCampo}
          className="solo-lettore-schermo"
          type="file"
          accept="image/*"
          disabled={inCorso || fotoIds.length >= MASSIMO_FOTO}
          onChange={aggiungiFoto}
        />
        {fotoIds.length < MASSIMO_FOTO && (
          <label htmlFor={idCampo} className="foto-aggiungi" aria-disabled={inCorso}>
            <Icona nome="foto" dimensione={26} />
            <span>{inCorso ? "Adding…" : "Add photo"}</span>
          </label>
        )}
      </div>
      {problema !== "" && (
        <p className="campo-aiuto" role="alert" style={{ color: "var(--critico-testo)" }}>
          {problema}
        </p>
      )}
    </div>
  );
}

type ProprietaFotoPiccola = {
  id: string;
  numero: number;
  onTogli: () => void;
};

function FotoPiccola({ id, numero, onTogli }: ProprietaFotoPiccola) {
  const immagine = leggiFoto(id);
  return (
    <div className="foto-piccola">
      {immagine !== null && <img src={immagine} alt={"Photo " + numero} />}
      <button type="button" className="foto-togli" aria-label={"Remove photo " + numero} onClick={onTogli}>
        <Icona nome="chiudi" dimensione={18} />
      </button>
    </div>
  );
}
