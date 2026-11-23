// Prova temporanea del design system: le pagine vere arrivano nel prossimo passo.
import { useState } from "react";
import Scheda from "./componenti/Scheda";
import Pulsante from "./componenti/Pulsante";
import Campo from "./componenti/Campo";
import Interruttore from "./componenti/Interruttore";
import Icona from "./componenti/Icona";

export default function App() {
  const [nome, setNome] = useState("Rosa");
  const [acceso, setAcceso] = useState(true);
  return (
    <main className="pila-larga entrata" style={{ padding: 16, maxWidth: 720, margin: "0 auto" }}>
      <h1>Design system</h1>
      <Scheda titolo="Hydration" icona="goccia">
        <div className="pila">
          <p className="numero-grande">1,150 ml</p>
          <div className="misuratore"><div className="misuratore-pieno" style={{ width: "76%" }} /></div>
          <p className="testo-secondario">of 1,500 ml goal · 6 drinks</p>
        </div>
      </Scheda>
      <Scheda titolo="Buttons" icona="scintilla">
        <div className="riga">
          <Pulsante>Open demo home</Pulsante>
          <Pulsante variante="secondario">Back</Pulsante>
          <Pulsante variante="pericolo"><Icona nome="cestino" /> Remove</Pulsante>
          <Pulsante disattivato>Connect</Pulsante>
        </div>
      </Scheda>
      <Scheda titolo="Fields" icona="cursori">
        <div className="pila">
          <Campo etichetta="Name" valore={nome} onCambia={setNome} />
          <Campo etichetta="Daily water goal" valore="1500" onCambia={() => {}} tipo="number" unita="ml" aiuto="Most adults need 1.5 to 2 litres a day." />
          <Interruttore etichetta="Exit alarm" descrizione="Alert me if the front door opens at night" acceso={acceso} onCambia={setAcceso} />
          <div className="riga">
            <span className="stato stato-buono"><Icona nome="spunta" dimensione={18} /> On time</span>
            <span className="stato stato-attenzione"><Icona nome="orologio" dimensione={18} /> 52 min late</span>
            <span className="stato stato-critico"><Icona nome="chiudi" dimensione={18} /> Missed</span>
            <span className="stato stato-neutro"><Icona nome="pausa" dimensione={18} /> Pending</span>
            <span className="simulato">Simulated</span>
          </div>
          <div className="segmenti"><button className="segmento" aria-pressed="true">Daily</button><button className="segmento" aria-pressed="false">Weekly</button><button className="segmento" aria-pressed="false">Monthly</button></div>
        </div>
      </Scheda>
    </main>
  );
}
