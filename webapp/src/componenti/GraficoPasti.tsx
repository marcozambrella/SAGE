// Pasti nei Trends (Marco, 25/11): per ogni giorno una barra di completamento per pasto, in ordine di ora.
// Niente Recharts qui: sono barre di completamento, non quantità su un asse. I giorni vanno a capo ogni 7,
// così anche un mese intero si legge sul telefono.
import type { QuantoMangiato } from "../contratti";
import { testoQuantoMangiato } from "../descrizioni";
import { giornoBreve, giornoDelMese, giornoSettimana } from "../formato";
import BarraPasto from "./BarraPasto";

export type PastiDelGiorno = {
  data: string;
  pasti: (QuantoMangiato | null)[];
};

export default function GraficoPasti({ giorni }: { giorni: PastiDelGiorno[] }) {
  let classe = "grafico-pasti";
  if (giorni.length > 7) {
    classe = classe + " grafico-pasti-mese";
  }

  const celle = [];
  for (const giorno of giorni) {
    const barre = [];
    const testi: string[] = [];
    for (let indice = 0; indice < giorno.pasti.length; indice++) {
      const quanto = giorno.pasti[indice];
      barre.push(<BarraPasto key={indice} quanto={quanto} verticale />);
      testi.push(testoQuantoMangiato(quanto).toLowerCase());
    }
    // Per il lettore di schermo e per il suggerimento al passaggio del mouse.
    let descrizione = giornoBreve(giorno.data) + ": no meals seen";
    if (testi.length > 0) {
      descrizione = giornoBreve(giorno.data) + ": " + testi.join(", ");
    }
    celle.push(
      <div key={giorno.data} className="pasti-giorno" role="img" aria-label={descrizione} title={descrizione}>
        <div className="pasti-barre">{barre}</div>
        <span className="pasti-data">
          <span>{giornoSettimana(giorno.data)}</span>
          <strong>{giornoDelMese(giorno.data)}</strong>
        </span>
      </div>,
    );
  }

  return (
    <figure className="grafico">
      <div className={classe}>{celle}</div>
      <figcaption className="legenda-pasti">
        <span>
          <span className="legenda-segno pasto-poco" /> Less than half
        </span>
        <span>
          <span className="legenda-segno pasto-meta" /> About half
        </span>
        <span>
          <span className="legenda-segno pasto-tutto" /> Everything
        </span>
        <span>
          <span className="legenda-segno legenda-non-misurato" /> Not measured
        </span>
      </figcaption>
    </figure>
  );
}
