// Mentre arrivano i dati della casa demo, oppure se il backend non risponde.
export default function Caricamento({ errore }: { errore: string }) {
  if (errore !== "") {
    return (
      <section className="scheda pila" role="alert">
        <h2>We couldn't open the demo home</h2>
        <p className="testo-secondario">{errore}</p>
        <p className="testo-secondario">Check your connection and reload the page.</p>
      </section>
    );
  }
  return (
    <section className="scheda caricamento" aria-busy="true">
      <span className="caricamento-pallina" aria-hidden="true" />
      <p className="testo-secondario">Opening the demo home…</p>
    </section>
  );
}
