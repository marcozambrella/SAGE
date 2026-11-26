// Tabella con una riga per giorno: tutti i numeri dei grafici, leggibili anche senza passare il dito sui grafici.
import type { RiassuntoGiorno } from "../contratti";
import { durata, giornoBreve, millilitri } from "../formato";

// "—" per le notti in cui non si è visto dormire.
function testoSonno(riga: RiassuntoGiorno): string {
  if (riga.sonno_minuti === null) {
    return "—";
  }
  return durata(riga.sonno_minuti);
}

type Proprieta = {
  giorni: RiassuntoGiorno[];
  // Le visite al bagno si mostrano solo se la famiglia le ha accese.
  mostraBagno: boolean;
};

export default function TabellaGiorni({ giorni, mostraBagno }: Proprieta) {
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
              <th scope="col">Meals</th>
              <th scope="col">Sleep</th>
              <th scope="col">Night</th>
              <th scope="col">Agitation</th>
              {mostraBagno && <th scope="col">Bathroom</th>}
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
                <td>
                  {riga.pasti} · {riga.pasti_meno_di_meta}
                </td>
                <td>{testoSonno(riga)}</td>
                <td>{riga.alzate_notturne}</td>
                <td>{durata(riga.agitazione_minuti)}</td>
                {mostraBagno && <td>{riga.visite_bagno}</td>}
                <td>{riga.cadute}</td>
                <td>{riga.uscite_in_orario_vietato}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="testo-secondario testo-piccolo">
        Doses: on time · late · missed. Meals: seen · less than half eaten. Sleep: the night before. Night: times out of
        bed. Agitation: restless pacing. Exits: during no-exit hours.
        {giorniSimulati > 0 && <> * Simulated day.</>}
      </p>
    </div>
  );
}
