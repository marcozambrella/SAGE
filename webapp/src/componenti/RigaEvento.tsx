// Un evento nella linea del tempo: ora, icona, cosa è successo e, se c'è, la foto di prova.
import { useState } from "react";
import { TIPI_URGENTI, type Evento, type Personalizzazione } from "../contratti";
import { descriviEvento } from "../descrizioni";
import { oraDellaCasa } from "../formato";
import { indirizzoFotoEvento } from "../api";
import EtichettaSimulato from "./EtichettaSimulato";
import Icona from "./Icona";

type Proprieta = {
  evento: Evento;
  personalizzazione: Personalizzazione;
};

export default function RigaEvento({ evento, personalizzazione }: Proprieta) {
  // La foto si chiede a parte (/demo/eventi/{id}/foto): se non c'è (404) il riquadro sparisce.
  const [fotoMancante, setFotoMancante] = useState(false);
  const descrizione = descriviEvento(evento, personalizzazione);
  const indirizzoFoto = indirizzoFotoEvento(evento.id);
  // Con i dati di sviluppo non ci sono foto: per gli eventi urgenti si mostra dove andrà la foto.
  const segnapostoFoto = indirizzoFoto === null && TIPI_URGENTI.includes(evento.tipo);

  return (
    <li className={"evento evento-" + descrizione.gravita}>
      <span className="evento-ora">{oraDellaCasa(evento.inizio, personalizzazione.fuso_orario)}</span>
      <span className="evento-bolla" aria-hidden="true">
        <Icona nome={descrizione.icona} dimensione={22} />
      </span>
      <div className="evento-testi">
        <div className="riga" style={{ gap: 8 }}>
          <strong>{descrizione.titolo}</strong>
          {evento.simulato && <EtichettaSimulato />}
        </div>
        <p className="testo-secondario testo-piccolo">{descrizione.dettaglio}</p>
        <p className="testo-secondario testo-piccolo">
          {evento.stanza} · {Math.round(evento.confidenza * 100)}% confidence
        </p>
        {indirizzoFoto !== null && !fotoMancante && (
          <img
            className="evento-foto"
            src={indirizzoFoto}
            alt={"Evidence photo: " + descrizione.titolo}
            loading="lazy"
            onError={() => setFotoMancante(true)}
          />
        )}
        {segnapostoFoto && (
          <div className="evento-foto evento-foto-segnaposto">
            <Icona nome="foto" dimensione={28} />
            <span>Evidence photo</span>
          </div>
        )}
      </div>
    </li>
  );
}
