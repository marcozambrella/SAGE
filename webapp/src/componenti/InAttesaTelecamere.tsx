// Stato vuoto delle pagine dati nella casa dell'utente: le telecamere non sono ancora collegate (D7, D28).
import { Link } from "react-router";
import Icona from "./Icona";

type Proprieta = {
  // Cosa comparirà qui quando le telecamere saranno collegate, es. "Rosa's day".
  testo: string;
  // La stessa pagina nella casa demo, es. "/demo/today".
  paginaDemo: string;
  // Versione più bassa, sotto ad altri contenuti della pagina.
  piccola?: boolean;
};

export default function InAttesaTelecamere({ testo, paginaDemo, piccola = false }: Proprieta) {
  let classe = "scheda attesa";
  if (piccola) {
    classe = classe + " attesa-piccola";
  }
  return (
    <section className={classe}>
      <div className="attesa-lente" aria-hidden="true">
        <span className="attesa-onda" />
        <span className="attesa-centro">
          <Icona nome="telecamera" dimensione={piccola ? 28 : 36} />
        </span>
      </div>
      <h2>Waiting for camera setup</h2>
      <p className="testo-secondario">{testo}</p>
      <div className="riga attesa-pulsanti">
        <Link to={paginaDemo} className="pulsante pulsante-principale">
          Open demo home <Icona nome="freccia" />
        </Link>
        {!piccola && (
          <Link to="/coming-soon" className="pulsante pulsante-secondario">
            What's coming
          </Link>
        )}
      </div>
    </section>
  );
}
