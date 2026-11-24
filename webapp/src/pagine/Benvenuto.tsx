// Apertura (D28): cosa fa SAGE e il pulsante per iniziare la personalizzazione.
import { Link } from "react-router";
import Icona, { type NomeIcona } from "../componenti/Icona";

const PUNTI: { icona: NomeIcona; titolo: string; testo: string }[] = [
  {
    icona: "pillola",
    titolo: "Medication, water, meals",
    testo: "Which pills were taken and when, how much they drank, what they ate.",
  },
  { icona: "scudo", titolo: "Falls and wandering", testo: "Urgent alerts on Telegram for falls and night-time exits." },
  {
    icona: "documento",
    titolo: "Calm reports",
    testo: "Daily, weekly and monthly summaries to share with the doctor.",
  },
];

export default function Benvenuto() {
  return (
    <div className="pagina-sola benvenuto entrata">
      <div className="benvenuto-eroe">
        <div className="benvenuto-nuvola" aria-hidden="true">
          <span className="benvenuto-cuore">
            <Icona nome="cuore" dimensione={56} />
          </span>
        </div>
        <p className="logo-nome">SAGE</p>
        <h1>A gentle eye on the people you love</h1>
        <p className="testo-secondario benvenuto-sotto">
          SAGE watches over an older relative living with Alzheimer's through the cameras at home, and tells the family
          what matters.
        </p>
      </div>

      <div className="pila">
        {PUNTI.map((punto) => (
          <div key={punto.titolo} className="scheda benvenuto-punto">
            <span className="bolla-icona">
              <Icona nome={punto.icona} />
            </span>
            <div>
              <h3>{punto.titolo}</h3>
              <p className="testo-secondario">{punto.testo}</p>
            </div>
          </div>
        ))}
      </div>

      <div className="pila benvenuto-azioni">
        <Link to="/setup" className="pulsante pulsante-principale pulsante-largo">
          Set up your home <Icona nome="freccia" />
        </Link>
        {/* Scorciatoia per chi vuole prima vedere i dati (per esempio i giudici), senza la personalizzazione */}
        <Link to="/demo/today" className="pulsante pulsante-secondario pulsante-largo">
          <Icona nome="casa" /> Explore the demo home
        </Link>
        <p className="testo-secondario testo-piccolo benvenuto-nota">
          No account needed: your setup stays in this browser. This is a demo, so cameras can't be connected yet, but
          you can explore a demo home with real results.
        </p>
      </div>
    </div>
  );
}
