// Logo di SAGE: pallina gonfia con un cuore caldo e il nome.
import { Link } from "react-router";
import Icona from "./Icona";

export default function Logo({ verso }: { verso: string }) {
  return (
    <Link to={verso} className="logo" aria-label="SAGE home">
      <span className="logo-pallina">
        <Icona nome="cuore" dimensione={24} />
      </span>
      <span className="logo-nome">SAGE</span>
    </Link>
  );
}
