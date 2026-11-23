// Titolo grande della pagina con una riga di spiegazione sotto.
import type { ReactNode } from "react";

export default function TitoloPagina({ titolo, sotto }: { titolo: string; sotto?: ReactNode }) {
  return (
    <div className="titolo-pagina">
      <h1>{titolo}</h1>
      {sotto && <p className="testo-secondario">{sotto}</p>}
    </div>
  );
}
