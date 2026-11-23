import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router";
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

createRoot(radice).render(
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>,
);
