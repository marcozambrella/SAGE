// Tabella con una riga per giorno: tutti i numeri dei grafici, leggibili anche senza passare il dito sui grafici.
import type { RiassuntoGiorno } from "../contratti";
import { giornoBreve, millilitri, percentuale } from "../formato";

export default function TabellaGiorni({ giorni }: { giorni: RiassuntoGiorno[] }) {
  let giorniSimulati = 0;
  for (const riga of giorni) {
    if (riga.simulato) {
      giorniSimulati = giorniSimulati + 1;
    }
  }
  return (
    <div className="pila" style={{ gap: 8 }}>
      <div className="tabella-contenitore">
        <table className="tabella">
          <thead>
            <tr>
              <th scope="col">Day</th>
              <th scope="col">Water</th>
              <th scope="col">Doses</th>
              <th scope="col">Eaten</th>
              <th scope="col">Night</th>
              <th scope="col">Falls</th>
              <th scope="col">Exits</th>
            </tr>
          </thead>
          <tbody>
            {giorni.map((riga) => (
              <tr key={riga.data}>
                <th scope="row">
                  {giornoBreve(riga.data)}{" "}
                  {riga.simulato && (
                    <span className="asterisco" title="Simulated">
                      *
                    </span>
                  )}
                </th>
                <td>{millilitri(riga.acqua_ml)}</td>
                <td>
                  {riga.dosi_in_orario} · {riga.dosi_in_ritardo} · {riga.dosi_saltate}
                </td>
                <td>{percentuale(riga.percentuale_mangiata_media)}</td>
                <td>{riga.alzate_notturne}</td>
                <td>{riga.cadute}</td>
                <td>{riga.uscite_in_orario_vietato}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="testo-secondario testo-piccolo">
        Doses: on time · late · missed. Night: times out of bed. Exits: during no-exit hours.
        {giorniSimulati > 0 && <> * Simulated day.</>}
      </p>
    </div>
  );
}
