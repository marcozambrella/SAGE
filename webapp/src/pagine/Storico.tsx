// History: giorno per giorno, la linea del tempo degli eventi con le foto di prova e, mescolati in ordine di ora,
// gli inserimenti a mano dei familiari (che si possono togliere da qui).
import { useEffect, useState } from "react";
import type { Evento, Personalizzazione } from "../contratti";
import {
  leggiEventiDemo,
  leggiPeriodoDemo,
  leggiPersonalizzazioneDemo,
  messaggioErrore,
  type GiorniDemo,
} from "../api";
import { giornoLungo, giornoSettimana, oggiNellaCasa, oraDellaCasa, spostaGiorno } from "../formato";
import { delGiorno, useInserimenti, type InserimentoAMano } from "../inserimenti";
import Caricamento from "../componenti/Caricamento";
import InAttesaTelecamere from "../componenti/InAttesaTelecamere";
import RigaEvento from "../componenti/RigaEvento";
import RigaInserimento from "../componenti/RigaInserimento";
import TitoloPagina from "../componenti/TitoloPagina";

type Proprieta = {
  demo: boolean;
  personalizzazione: Personalizzazione | null;
};

// Quanti giorni si possono scegliere nella striscia in alto.
const GIORNI_NELLA_STRISCIA = 14;

export default function Storico({ demo, personalizzazione }: Proprieta) {
  if (demo || personalizzazione === null) {
    return <StoricoCasaDemo />;
  }
  return <StoricoCasaUtente personalizzazione={personalizzazione} />;
}

// La striscia dei giorni in alto, dal più recente.
type ProprietaStriscia = {
  giorni: string[];
  giorno: string;
  onScegli: (giorno: string) => void;
};

function StrisciaGiorni({ giorni, giorno, onScegli }: ProprietaStriscia) {
  return (
    <div className="striscia-giorni" role="group" aria-label="Choose a day">
      {giorni.map((voce) => (
        <button
          key={voce}
          type="button"
          className="giorno-pallina"
          aria-pressed={voce === giorno}
          onClick={() => onScegli(voce)}
        >
          <span className="testo-piccolo">{giornoSettimana(voce)}</span>
          <strong>{Number(voce.slice(8, 10))}</strong>
        </button>
      ))}
    </div>
  );
}

// Una voce della linea del tempo: un evento delle telecamere oppure un inserimento a mano.
type Voce = {
  ora: string;
  evento: Evento | null;
  inserimento: InserimentoAMano | null;
};

function confrontaOra(a: Voce, b: Voce): number {
  if (a.ora < b.ora) {
    return -1;
  }
  if (a.ora > b.ora) {
    return 1;
  }
  return 0;
}

type ProprietaLinea = {
  eventi: Evento[];
  inserimenti: InserimentoAMano[];
  personalizzazione: Personalizzazione;
  onCancella: (id: string) => void;
};

function LineaDelTempo({ eventi, inserimenti, personalizzazione, onCancella }: ProprietaLinea) {
  const voci: Voce[] = [];
  for (const evento of eventi) {
    voci.push({ ora: oraDellaCasa(evento.inizio, personalizzazione.fuso_orario), evento: evento, inserimento: null });
  }
  for (const inserimento of inserimenti) {
    voci.push({ ora: inserimento.ora, evento: null, inserimento: inserimento });
  }
  voci.sort(confrontaOra);
  const righe = [];
  for (const voce of voci) {
    if (voce.evento !== null) {
      righe.push(<RigaEvento key={voce.evento.id} evento={voce.evento} personalizzazione={personalizzazione} />);
    }
    if (voce.inserimento !== null) {
      righe.push(
        <RigaInserimento
          key={voce.inserimento.id}
          inserimento={voce.inserimento}
          contenitori={personalizzazione.contenitori}
          onCancella={onCancella}
        />,
      );
    }
  }
  return (
    <section className="scheda">
      <ol className="linea-tempo">{righe}</ol>
    </section>
  );
}

// Casa dell'utente: senza telecamere la linea del tempo ha solo quello che ha segnato la famiglia.
function StoricoCasaUtente({ personalizzazione }: { personalizzazione: Personalizzazione }) {
  const oggi = oggiNellaCasa(personalizzazione.fuso_orario);
  const [giorno, setGiorno] = useState(oggi);
  const { inserimenti, cancella } = useInserimenti(false);

  const giorni: string[] = [];
  for (let i = 0; i < GIORNI_NELLA_STRISCIA; i++) {
    giorni.push(spostaGiorno(oggi, -i));
  }
  const delGiornoScelto = delGiorno(inserimenti, giorno);

  return (
    <div className="pila-larga entrata">
      <TitoloPagina titolo="History" sotto={giornoLungo(giorno)} />
      <StrisciaGiorni giorni={giorni} giorno={giorno} onScegli={setGiorno} />
      {delGiornoScelto.length === 0 && (
        <p className="scheda testo-secondario">
          Nothing was logged on this day. You can log drinks and meals on Today.
        </p>
      )}
      {delGiornoScelto.length > 0 && (
        <LineaDelTempo
          eventi={[]}
          inserimenti={delGiornoScelto}
          personalizzazione={personalizzazione}
          onCancella={cancella}
        />
      )}
      <InAttesaTelecamere
        testo={
          "A timeline of " +
          personalizzazione.anziano.nome +
          "'s days, with a photo for each important moment, will appear here once the cameras are connected."
        }
        paginaDemo="/demo/history"
      />
    </div>
  );
}

function StoricoCasaDemo() {
  const [periodo, setPeriodo] = useState<GiorniDemo | null>(null);
  const [personalizzazione, setPersonalizzazione] = useState<Personalizzazione | null>(null);
  const [giorno, setGiorno] = useState("");
  const [eventi, setEventi] = useState<Evento[] | null>(null);
  const [errore, setErrore] = useState("");
  const { inserimenti, cancella } = useInserimenti(true);

  // Prima si chiede quali giorni ha la casa demo: si parte dall'ultimo.
  useEffect(() => {
    async function carica() {
      try {
        const giorniDemo = await leggiPeriodoDemo();
        setPersonalizzazione(await leggiPersonalizzazioneDemo());
        setPeriodo(giorniDemo);
        setGiorno(giorniDemo.al);
      } catch (problema) {
        setErrore(messaggioErrore(problema));
      }
    }
    carica();
  }, []);

  // Poi gli eventi del giorno scelto.
  useEffect(() => {
    async function carica() {
      if (giorno === "") {
        return;
      }
      setEventi(null);
      setErrore("");
      try {
        setEventi(await leggiEventiDemo(giorno, giorno, null));
      } catch (problema) {
        setErrore(messaggioErrore(problema));
      }
    }
    carica();
  }, [giorno]);

  if (periodo === null) {
    return <Caricamento errore={errore} />;
  }

  // Gli ultimi giorni della casa demo, dal più recente, senza andare prima del primo giorno.
  const giorni: string[] = [];
  for (let i = 0; i < GIORNI_NELLA_STRISCIA; i++) {
    const voce = spostaGiorno(periodo.al, -i);
    if (voce >= periodo.dal) {
      giorni.push(voce);
    }
  }

  let contenuto = <Caricamento errore={errore} />;
  if (personalizzazione !== null && eventi !== null) {
    const delGiornoScelto = delGiorno(inserimenti, giorno);
    if (eventi.length === 0 && delGiornoScelto.length === 0) {
      contenuto = <p className="scheda testo-secondario">Nothing was recorded on this day.</p>;
    } else {
      contenuto = (
        <LineaDelTempo
          eventi={eventi}
          inserimenti={delGiornoScelto}
          personalizzazione={personalizzazione}
          onCancella={cancella}
        />
      );
    }
  }

  return (
    <div className="pila-larga entrata">
      <TitoloPagina titolo="History" sotto={giornoLungo(giorno)} />
      <StrisciaGiorni giorni={giorni} giorno={giorno} onScegli={setGiorno} />
      {contenuto}
    </div>
  );
}
