// Visite al bagno di un giorno (solo se la famiglia le ha accese): in tutto e di notte.
export default function BagnoDelGiorno({ visite, notte }: { visite: number; notte: number }) {
  return (
    <div className="tessere">
      <div className="tessera">
        <span className="numero-medio">{visite}</span>
        <span className="testo-secondario">bathroom visits</span>
      </div>
      <div className="tessera">
        <span className="numero-medio">{notte}</span>
        <span className="testo-secondario">of them at night</span>
      </div>
    </div>
  );
}
