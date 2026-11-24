import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { HashRouter } from "react-router";
import "./stile/variabili.css";
import "./stile/base.css";
import "./stile/componenti.css";
import "./stile/struttura.css";
import "./stile/pagine.css";
import App from "./App.tsx";

const radice = document.getElementById("root");
if (radice === null) {
  throw new Error("Manca l'elemento #root in index.html");
}

// Indirizzi con "#" (es. .../#/demo/today): funzionano su qualunque hosting statico, alla radice o in una
// sottocartella, e un link a una pagina interna non dà mai "pagina non trovata".
createRoot(radice).render(
  <StrictMode>
    <HashRouter>
      <App />
    </HashRouter>
  </StrictMode>,
);
