// Campo di testo, numero o ora, scavato nella superficie (ombra interna).
import { useId } from "react";

type Proprieta = {
  etichetta: string;
  valore: string;
  onCambia: (testo: string) => void;
  tipo?: "text" | "number" | "time";
  segnaposto?: string;
  aiuto?: string;
  // Unità mostrata a destra del valore, es. "ml".
  unita?: string;
  obbligatorio?: boolean;
};

export default function Campo({
  etichetta,
  valore,
  onCambia,
  tipo = "text",
  segnaposto,
  aiuto,
  unita,
  obbligatorio = false,
}: Proprieta) {
  const id = useId();
  let modoTastiera: "numeric" | undefined = undefined;
  if (tipo === "number") {
    modoTastiera = "numeric";
  }
  return (
    <div className="campo">
      <label className="campo-etichetta" htmlFor={id}>
        {etichetta}
      </label>
      <div className="campo-pozzetto">
        <input
          id={id}
          type={tipo}
          inputMode={modoTastiera}
          value={valore}
          placeholder={segnaposto}
          required={obbligatorio}
          onChange={(evento) => onCambia(evento.target.value)}
        />
        {unita && <span className="campo-unita">{unita}</span>}
      </div>
      {aiuto && <p className="campo-aiuto">{aiuto}</p>}
    </div>
  );
}
