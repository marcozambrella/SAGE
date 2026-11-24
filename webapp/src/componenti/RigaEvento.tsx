// Un evento nella linea del tempo: ora, icona, cosa è successo e, se c'è, la foto di prova.
import { useState } from "react";
import type { Evento, Personalizzazione } from "../contratti";
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
  // La foto si chiede a parte (/demo/eventi/{id}/foto), solo se ha_foto: se poi non arriva il riquadro sparisce.
  const [fotoMancante, setFotoMancante] = useState(false);
  const descrizione = descriviEvento(evento, personalizzazione);
  const indirizzoFoto = indirizzoFotoEvento(evento);
  // Con i dati di sviluppo non ci sono immagini: si mostra solo dove andrà la foto.
  const segnapostoFoto = evento.ha_foto && indirizzoFoto === null;

  return (
    <li className={"evento evento-" + descrizione.gravita}>
      <span className="evento-bolla" aria-hidden="true">
        <Icona nome={descrizione.icona} dimensione={22} />
      </span>
      <div className="evento-testi">
        <div className="riga" style={{ gap: 8 }}>
          <span className="evento-ora">{oraDellaCasa(evento.inizio, personalizzazione.fuso_orario)}</span>
          {evento.simulato && <EtichettaSimulato />}
        </div>
        <strong>{descrizione.titolo}</strong>
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
