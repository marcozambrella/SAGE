// Barra di riempimento: binario e riempimento della stessa tinta calda. La percentuale oltre 100 resta piena.
type Proprieta = {
  percentuale: number;
  // Cosa misura, per il lettore di schermo (es. "Water goal").
  etichetta: string;
  sottile?: boolean;
};

export default function Misuratore({ percentuale, etichetta, sottile = false }: Proprieta) {
  const larghezza = Math.max(0, Math.min(100, percentuale));
  let classe = "misuratore";
  if (sottile) {
    classe = classe + " misuratore-sottile";
  }
  return (
    <div
      className={classe}
      role="progressbar"
      aria-label={etichetta}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(percentuale)}
    >
      <div className="misuratore-pieno" style={{ width: larghezza + "%" }} />
    </div>
  );
}
