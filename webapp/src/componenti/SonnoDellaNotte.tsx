// La notte passata (Today e report del giorno): ore dormite, a che ora si è addormentato e svegliato, e le
// interruzioni, cioè le alzate notturne (API.md: sono i buchi tra un pezzo di sonno e l'altro).
import type { ReportGiornaliero } from "../contratti";
import { durata, oraDellaCasa } from "../formato";

type Proprieta = {
  report: ReportGiornaliero;
  fusoOrario: string;
};

export default function SonnoDellaNotte({ report, fusoOrario }: Proprieta) {
  let orari = "";
  if (report.addormentato_alle !== null && report.sveglio_alle !== null) {
    const addormentato = oraDellaCasa(report.addormentato_alle, fusoOrario);
    const sveglio = oraDellaCasa(report.sveglio_alle, fusoOrario);
    orari = "Fell asleep at " + addormentato + " · woke up at " + sveglio;
  }
  return (
    <div className="pila">
      {report.sonno_minuti === null && <p className="testo-secondario">Sleep wasn't seen last night.</p>}
      {report.sonno_minuti !== null && (
        <div>
          <p>
            <span className="numero-medio">{durata(report.sonno_minuti)}</span>{" "}
            <span className="testo-secondario">of sleep</span>
          </p>
          {orari !== "" && <p className="testo-secondario">{orari}</p>}
        </div>
      )}
      <div className="tessere">
        <div className="tessera">
          <span className="numero-medio">{report.alzate_notturne}</span>
          <span className="testo-secondario">times up at night</span>
        </div>
        <div className="tessera">
          <span className="numero-medio">{durata(report.minuti_fuori_letto_notte)}</span>
          <span className="testo-secondario">out of bed at night</span>
        </div>
      </div>
    </div>
  );
}
