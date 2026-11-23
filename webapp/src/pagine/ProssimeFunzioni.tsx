// "Coming soon" (D28): le prossime funzioni, mostrate dopo la personalizzazione.
import { Link } from "react-router";
import Icona, { type NomeIcona } from "../componenti/Icona";

const FUNZIONI: { icona: NomeIcona; titolo: string; testo: string }[] = [
  {
    icona: "famiglia",
    titolo: "Family accounts and login",
    testo: "Invite the whole family with a code. Everyone gets their own login and their own Telegram alerts.",
  },
  {
    icona: "telecamera",
    titolo: "Live camera connection",
    testo: "Connect the cameras you planned straight from the app, and see the day fill in as it happens.",
  },
  {
    icona: "documento",
    titolo: "Reports for the doctor",
    testo: "Download a monthly PDF with medication, hydration and night activity to bring to appointments.",
  },
  {
    icona: "campanella",
    titolo: "Alerts inside the app",
    testo: "Phone notifications from SAGE itself, for families who don't use Telegram.",
  },
];

export default function ProssimeFunzioni() {
  return (
    <div className="pagina-sola entrata pila-larga">
      <div className="titolo-pagina">
        <span className="bolla-icona" style={{ width: 64, height: 64 }}>
          <Icona nome="scintilla" dimensione={32} />
        </span>
        <h1>Coming soon</h1>
        <p className="testo-secondario">Your home is set up. Here is what we are building next.</p>
      </div>

      {FUNZIONI.map((funzione) => (
        <div key={funzione.titolo} className="scheda benvenuto-punto">
          <span className="bolla-icona">
            <Icona nome={funzione.icona} />
          </span>
          <div className="pila" style={{ gap: 4 }}>
            <h3>{funzione.titolo}</h3>
            <p className="testo-secondario">{funzione.testo}</p>
          </div>
        </div>
      ))}

      <div className="barra-azioni">
        <div className="barra-azioni-interno">
          <Link to="/today" className="pulsante pulsante-principale">
            Go to my dashboard <Icona nome="freccia" />
          </Link>
        </div>
      </div>
    </div>
  );
}
