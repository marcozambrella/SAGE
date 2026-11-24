// Interruttore acceso/spento: binario scavato e pallina in rilievo.
type Proprieta = {
  etichetta: string;
  descrizione?: string;
  acceso: boolean;
  onCambia: (acceso: boolean) => void;
};

export default function Interruttore({ etichetta, descrizione, acceso, onCambia }: Proprieta) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={acceso}
      className="interruttore"
      onClick={() => onCambia(!acceso)}
    >
      <span className="interruttore-testi">
        <span className="campo-etichetta">{etichetta}</span>
        {descrizione && <span className="campo-aiuto">{descrizione}</span>}
      </span>
      <span className="interruttore-binario">
        <span className="interruttore-pallina" />
      </span>
    </button>
  );
}
