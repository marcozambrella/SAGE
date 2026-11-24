// Struttura comune delle pagine: testata, menu e contenuto. La stessa struttura serve la casa dell'utente
// (percorsi "/today", "/history"...) e la casa demo (percorsi "/demo/today", "/demo/history"..., D22).
import { Suspense, useState } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router";
import Icona, { type NomeIcona } from "./Icona";
import Caricamento from "./Caricamento";
import Logo from "./Logo";
import { USA_DATI_SVILUPPO } from "../api";

type Voce = {
  percorso: string;
  titolo: string;
  icona: NomeIcona;
};

// Le prime quattro stanno nella barra in basso del telefono, le altre nel foglio "More".
const VOCI_PRINCIPALI: Voce[] = [
  { percorso: "today", titolo: "Today", icona: "sole" },
  { percorso: "history", titolo: "History", icona: "calendario" },
  { percorso: "trends", titolo: "Trends", icona: "andamento" },
  { percorso: "reports", titolo: "Reports", icona: "documento" },
];

const ALTRE_VOCI: Voce[] = [
  { percorso: "medications", titolo: "Medications", icona: "pillola" },
  { percorso: "containers", titolo: "Containers", icona: "bicchiere" },
  { percorso: "cameras", titolo: "Cameras", icona: "telecamera" },
  { percorso: "alerts", titolo: "Alerts", icona: "campanella" },
  { percorso: "settings", titolo: "Settings", icona: "cursori" },
];

type Proprieta = {
  demo: boolean;
  // Nome dell'anziano della casa dell'utente (nella casa demo non serve).
  nomeAnziano: string;
};

export default function Struttura({ demo, nomeAnziano }: Proprieta) {
  const posizione = useLocation();
  // Il foglio "More" resta aperto solo sulla pagina dove è stato aperto: se si cambia pagina (anche con il tasto
  // "indietro" del telefono) si chiude da solo.
  const [foglioApertoSu, setFoglioApertoSu] = useState("");
  const foglioAperto = foglioApertoSu === posizione.pathname;

  let prefisso = "";
  let titoloCasa = nomeAnziano + "'s home";
  if (demo) {
    prefisso = "/demo";
    titoloCasa = "Demo home";
  }

  // La stessa pagina nell'altra casa: serve per passare dalla casa demo alla propria e viceversa.
  let paginaMia = posizione.pathname;
  if (demo) {
    paginaMia = posizione.pathname.replace("/demo", "");
  }

  const tutteLeVoci = VOCI_PRINCIPALI.concat(ALTRE_VOCI);

  // "More" resta evidenziato quando si è su una delle pagine che contiene.
  let paginaInAltre = false;
  for (const voce of ALTRE_VOCI) {
    if (posizione.pathname === prefisso + "/" + voce.percorso) {
      paginaInAltre = true;
    }
  }

  return (
    <div className="struttura">
      <aside className="menu-laterale">
        <Logo verso={prefisso + "/today"} />
        <nav className="pila" style={{ gap: 6 }} aria-label="Pages">
          {tutteLeVoci.map((voce) => (
            <NavLink key={voce.percorso} to={prefisso + "/" + voce.percorso} className="voce-menu">
              <Icona nome={voce.icona} />
              {voce.titolo}
            </NavLink>
          ))}
          <NavLink to="/coming-soon" className="voce-menu">
            <Icona nome="scintilla" />
            What's coming
          </NavLink>
        </nav>
      </aside>

      <div className="struttura-centro">
        <header className="testata">
          <Logo verso={prefisso + "/today"} />
          <div className="testata-casa">
            <span className="testo-secondario testo-piccolo">{demo ? "Exploring" : "Looking after"}</span>
            <strong>{titoloCasa}</strong>
          </div>
        </header>

        <main className="contenuto">
          {demo && (
            <div className="striscia-demo" role="note">
              <span className="bolla-icona">
                <Icona nome="casa" />
              </span>
              <p>
                <strong>Demo home.</strong> Real model results on videos we recorded, plus a simulated history marked
                “Simulated”.
                {USA_DATI_SVILUPPO && <strong> Showing development sample data (no backend connected).</strong>}
              </p>
              <Link to={paginaMia} className="pulsante pulsante-secondario">
                Back to my home
              </Link>
            </div>
          )}
          <Suspense fallback={<Caricamento errore="" />}>
            <Outlet />
          </Suspense>
        </main>
      </div>

      <nav className="barra-basso" aria-label="Main pages">
        {VOCI_PRINCIPALI.map((voce) => (
          <NavLink key={voce.percorso} to={prefisso + "/" + voce.percorso} className="voce-barra">
            <Icona nome={voce.icona} />
            {voce.titolo}
          </NavLink>
        ))}
        <button
          type="button"
          className={paginaInAltre ? "voce-barra active" : "voce-barra"}
          aria-expanded={foglioAperto}
          onClick={() => setFoglioApertoSu(posizione.pathname)}
        >
          <Icona nome="altro" />
          More
        </button>
      </nav>

      {foglioAperto && (
        <>
          <div className="foglio-sfondo" onClick={() => setFoglioApertoSu("")} />
          <div className="foglio" role="dialog" aria-label="More pages">
            <div className="riga-spaziata">
              <h2>More</h2>
              <button
                type="button"
                className="pulsante pulsante-secondario pulsante-icona"
                aria-label="Close"
                onClick={() => setFoglioApertoSu("")}
              >
                <Icona nome="chiudi" />
              </button>
            </div>
            <div className="foglio-voci">
              {ALTRE_VOCI.map((voce) => (
                <NavLink
                  key={voce.percorso}
                  to={prefisso + "/" + voce.percorso}
                  className="pulsante pulsante-secondario"
                  onClick={() => setFoglioApertoSu("")}
                >
                  <Icona nome={voce.icona} />
                  {voce.titolo}
                </NavLink>
              ))}
              <NavLink to="/coming-soon" className="pulsante pulsante-secondario" onClick={() => setFoglioApertoSu("")}>
                <Icona nome="scintilla" />
                What's coming
              </NavLink>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
