// Pagine della web app e flusso (D28): apertura → personalizzazione → "Coming soon" → dashboard.
// Ogni pagina dati esiste due volte: nella casa dell'utente ("/today", vuota finché non ci sono telecamere)
// e nella casa demo ("/demo/today", dati del backend, D22).
import { lazy, useState, type ReactNode } from "react";
import { Navigate, Route, Routes } from "react-router";
import type { Personalizzazione } from "./contratti";
import Struttura from "./componenti/Struttura";
import Benvenuto from "./pagine/Benvenuto";
import Personalizza from "./pagine/Personalizza";
import ProssimeFunzioni from "./pagine/ProssimeFunzioni";
import Oggi from "./pagine/Oggi";
import Storico from "./pagine/Storico";
import Farmaci from "./pagine/Farmaci";
import Contenitori from "./pagine/Contenitori";
import Telecamere from "./pagine/Telecamere";
import Allarmi from "./pagine/Allarmi";
import Impostazioni from "./pagine/Impostazioni";
import {
  cancellaFotoNonUsate,
  cancellaPersonalizzazione,
  leggiPersonalizzazione,
  salvaPersonalizzazione,
} from "./salvataggio";

// Le due pagine con i grafici si scaricano solo quando servono: la libreria dei grafici pesa più di tutto il resto,
// e così la prima apertura dal telefono resta veloce. Mentre arrivano, Struttura mostra la scheda di caricamento.
const Andamenti = lazy(() => import("./pagine/Andamenti"));
const Report = lazy(() => import("./pagine/Report"));

export default function App() {
  // La personalizzazione della famiglia, letta dal browser all'avvio (null se non è ancora stata fatta).
  const [personalizzazione, setPersonalizzazione] = useState<Personalizzazione | null>(leggiPersonalizzazione());

  function salva(nuova: Personalizzazione) {
    salvaPersonalizzazione(nuova);
    cancellaFotoNonUsate(nuova);
    setPersonalizzazione(nuova);
  }

  function cancella() {
    cancellaPersonalizzazione();
    setPersonalizzazione(null);
  }

  // Senza personalizzazione le pagine della casa dell'utente non esistono: si torna all'apertura (ultima Route).
  let casaUtente: ReactNode = null;
  if (personalizzazione !== null) {
    const p = personalizzazione;
    casaUtente = (
      <Route element={<Struttura demo={false} nomeAnziano={p.anziano.nome} />}>
        <Route path="/today" element={<Oggi demo={false} personalizzazione={p} />} />
        <Route path="/history" element={<Storico demo={false} personalizzazione={p} />} />
        <Route path="/trends" element={<Andamenti demo={false} personalizzazione={p} />} />
        <Route path="/reports" element={<Report demo={false} personalizzazione={p} />} />
        <Route path="/medications" element={<Farmaci demo={false} personalizzazione={p} />} />
        <Route path="/containers" element={<Contenitori demo={false} personalizzazione={p} />} />
        <Route path="/cameras" element={<Telecamere demo={false} personalizzazione={p} />} />
        <Route path="/alerts" element={<Allarmi demo={false} personalizzazione={p} onSalva={salva} />} />
        <Route
          path="/settings"
          element={<Impostazioni demo={false} personalizzazione={p} onSalva={salva} onCancella={cancella} />}
        />
      </Route>
    );
  }

  // Se la famiglia ha già fatto la personalizzazione, l'apertura porta dritto alla dashboard.
  let apertura = <Benvenuto />;
  if (personalizzazione !== null) {
    apertura = <Navigate to="/today" replace />;
  }

  return (
    <Routes>
      <Route path="/" element={apertura} />
      <Route path="/setup" element={<Personalizza onSalva={salva} />} />
      <Route path="/coming-soon" element={<ProssimeFunzioni />} />

      {/* Casa demo: sempre visibile, anche senza personalizzazione */}
      <Route path="/demo" element={<Struttura demo={true} nomeAnziano="" />}>
        <Route index element={<Navigate to="/demo/today" replace />} />
        <Route path="today" element={<Oggi demo={true} personalizzazione={null} />} />
        <Route path="history" element={<Storico demo={true} personalizzazione={null} />} />
        <Route path="trends" element={<Andamenti demo={true} personalizzazione={null} />} />
        <Route path="reports" element={<Report demo={true} personalizzazione={null} />} />
        <Route path="medications" element={<Farmaci demo={true} personalizzazione={null} />} />
        <Route path="containers" element={<Contenitori demo={true} personalizzazione={null} />} />
        <Route path="cameras" element={<Telecamere demo={true} personalizzazione={null} />} />
        <Route path="alerts" element={<Allarmi demo={true} personalizzazione={null} onSalva={salva} />} />
        <Route
          path="settings"
          element={<Impostazioni demo={true} personalizzazione={null} onSalva={salva} onCancella={cancella} />}
        />
      </Route>

      {casaUtente}

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
