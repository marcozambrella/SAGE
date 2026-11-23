// Pulsante gonfio. Per i collegamenti tra pagine si usa <Link> con le stesse classi CSS ("pulsante pulsante-...").
import type { ReactNode } from "react";

type Proprieta = {
  variante?: "principale" | "secondario" | "pericolo";
  tipo?: "button" | "submit";
  disattivato?: boolean;
  largo?: boolean;
  onClick?: () => void;
  children: ReactNode;
};

export default function Pulsante({
  variante = "principale",
  tipo = "button",
  disattivato = false,
  largo = false,
  onClick,
  children,
}: Proprieta) {
  let classe = "pulsante pulsante-" + variante;
  if (largo) {
    classe = classe + " pulsante-largo";
  }
  return (
    <button type={tipo} className={classe} disabled={disattivato} onClick={onClick}>
      {children}
    </button>
  );
}
