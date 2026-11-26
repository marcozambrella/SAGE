// I due pulsanti grandi "Log a drink" e "Log a meal" e, sotto, il modulo veloce aperto (inserimenti a mano).
import { useState } from "react";
import type { Contenitore } from "../contratti";
import { oraDellaCasa } from "../formato";
import type { InserimentoAMano } from "../inserimenti";
import Icona from "./Icona";
import ModuloBevuta from "./ModuloBevuta";
import ModuloPasto from "./ModuloPasto";
import Pulsante from "./Pulsante";

type Proprieta = {
  contenitori: Contenitore[];
  fusoOrario: string;
  // Il giorno a cui va l'inserimento: oggi nella casa propria, il giorno mostrato nella casa demo.
  giorno: string;
  onAggiungi: (nuovo: InserimentoAMano) => void;
};

export default function InserisciAMano({ contenitori, fusoOrario, giorno, onAggiungi }: Proprieta) {
  const [aperto, setAperto] = useState<"" | "bevuta" | "pasto">("");
  const [adesso, setAdesso] = useState("");

  // L'ora proposta è quella del momento in cui si apre il modulo, nel fuso della casa.
  function apri(cosa: "bevuta" | "pasto") {
    setAdesso(oraDellaCasa(new Date().toISOString(), fusoOrario));
    setAperto(cosa);
  }

  function salva(nuovo: InserimentoAMano) {
    onAggiungi(nuovo);
    setAperto("");
  }

  return (
    <div className="pila">
      <div className="due-colonne">
        <Pulsante variante="secondario" largo onClick={() => apri("bevuta")}>
          <Icona nome="piu" /> Log a drink
        </Pulsante>
        <Pulsante variante="secondario" largo onClick={() => apri("pasto")}>
          <Icona nome="piu" /> Log a meal
        </Pulsante>
      </div>
      {aperto === "bevuta" && (
        <ModuloBevuta
          contenitori={contenitori}
          giorno={giorno}
          oraIniziale={adesso}
          onSalva={salva}
          onAnnulla={() => setAperto("")}
        />
      )}
      {aperto === "pasto" && (
        <ModuloPasto giorno={giorno} oraIniziale={adesso} onSalva={salva} onAnnulla={() => setAperto("")} />
      )}
    </div>
  );
}
