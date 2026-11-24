// Alerts: allarme uscita (acceso, spento, in pausa per N ore, D16) e allarmi urgenti (cadute, uscite vietate).
// Senza login, nella web app acceso/spento/pausa sono solo un'impostazione salvata nel browser (D27).
import { useEffect, useState } from "react";
import { Link } from "react-router";
import type { Evento, Personalizzazione } from "../contratti";
import { leggiEventiDemo, leggiPeriodoDemo, leggiPersonalizzazioneDemo, messaggioErrore } from "../api";
import { giornoDellaCasa, giornoLungo, oraDellaCasa, spostaGiorno } from "../formato";
import Caricamento from "../componenti/Caricamento";
import Campo from "../componenti/Campo";
import Icona from "../componenti/Icona";
import InAttesaTelecamere from "../componenti/InAttesaTelecamere";
import Interruttore from "../componenti/Interruttore";
import Pulsante from "../componenti/Pulsante";
import RigaEvento from "../componenti/RigaEvento";
import Scheda from "../componenti/Scheda";
import TitoloPagina from "../componenti/TitoloPagina";

type Proprieta = {
  demo: boolean;
  personalizzazione: Personalizzazione | null;
  onSalva: (personalizzazione: Personalizzazione) => void;
};

// Quanti giorni indietro si cercano gli allarmi nella casa demo.
const GIORNI_DI_ALLARMI = 30;

export default function Allarmi({ demo, personalizzazione, onSalva }: Proprieta) {
  if (demo || personalizzazione === null) {
    return <AllarmiCasaDemo />;
  }
  return <AllarmiCasaUtente personalizzazione={personalizzazione} onSalva={onSalva} />;
}

// True se l'allarme uscita è in pausa adesso.
function inPausa(pausaFinoA: string | null): boolean {
  if (pausaFinoA === null) {
    return false;
  }
  return new Date(pausaFinoA).getTime() > Date.now();
}

function FasceVietate({ personalizzazione }: { personalizzazione: Personalizzazione }) {
  const fasce = personalizzazione.regole.orari_uscita_vietati;
  if (fasce.length === 0) {
    return <p className="testo-secondario">No no-exit hours set.</p>;
  }
  return (
    <div className="riga">
      {fasce.map((fascia, indice) => (
        <span key={indice} className="stato stato-neutro">
          <Icona nome="porta" dimensione={18} /> {fascia.dalle} – {fascia.alle}
        </span>
      ))}
    </div>
  );
}

type ProprietaCasaUtente = {
  personalizzazione: Personalizzazione;
  onSalva: (personalizzazione: Personalizzazione) => void;
};

function AllarmiCasaUtente({ personalizzazione, onSalva }: ProprietaCasaUtente) {
  const [orePausa, setOrePausa] = useState("1");
  const regole = personalizzazione.regole;
  const nome = personalizzazione.anziano.nome;
  const pausa = inPausa(regole.pausa_fino_a);

  function cambiaAttivo(acceso: boolean) {
    onSalva({ ...personalizzazione, regole: { ...regole, allarme_uscita_attivo: acceso } });
  }

  function mettiInPausa() {
    const ore = Number(orePausa);
    if (!(ore > 0)) {
      return;
    }
    // Ora con fuso orario (ISO in UTC, "Z"): è una data "aware" come vuole il contratto.
    const fine = new Date(Date.now() + ore * 3600 * 1000).toISOString();
    onSalva({ ...personalizzazione, regole: { ...regole, pausa_fino_a: fine } });
  }

  function riattiva() {
    onSalva({ ...personalizzazione, regole: { ...regole, pausa_fino_a: null } });
  }

  let statoPausa = null;
  if (pausa && regole.pausa_fino_a !== null) {
    statoPausa = (
      <div className="riquadro riga-spaziata">
        <span className="stato stato-attenzione">
          <Icona nome="pausa" dimensione={18} /> Paused until{" "}
          {oraDellaCasa(regole.pausa_fino_a, personalizzazione.fuso_orario)}
        </span>
        <Pulsante variante="secondario" onClick={riattiva}>
          Resume now
        </Pulsante>
      </div>
    );
  } else {
    statoPausa = (
      <div className="pausa-riga">
        <Campo etichetta="Pause for" tipo="number" unita="hours" valore={orePausa} onCambia={setOrePausa} />
        <Pulsante variante="secondario" disattivato={!regole.allarme_uscita_attivo} onClick={mettiInPausa}>
          <Icona nome="pausa" /> Pause
        </Pulsante>
      </div>
    );
  }

  return (
    <div className="pila-larga entrata">
      <TitoloPagina titolo="Alerts" sotto="What raises an urgent alert, and when." />
      <div className="griglia">
        <Scheda titolo="Exit alarm" icona="porta">
          <div className="pila">
            <Interruttore
              etichetta={regole.allarme_uscita_attivo ? "On" : "Off"}
              descrizione={"Alert the family if " + nome + " goes out during no-exit hours."}
              acceso={regole.allarme_uscita_attivo}
              onCambia={cambiaAttivo}
            />
            {statoPausa}
            <h3>No-exit hours</h3>
            <FasceVietate personalizzazione={personalizzazione} />
            <Link to="/settings" className="pulsante pulsante-secondario">
              <Icona nome="cursori" /> Change hours
            </Link>
          </div>
        </Scheda>
        <Scheda titolo="Telegram alerts" icona="campanella">
          <p className="testo-secondario">
            Falls, and exits during no-exit hours, are sent at once to the family's Telegram with a photo. Telegram
            alerts start when the cameras are connected.
          </p>
        </Scheda>
      </div>
      <InAttesaTelecamere testo="No alerts yet: nothing is being watched." paginaDemo="/demo/alerts" piccola />
    </div>
  );
}

function AllarmiCasaDemo() {
  const [personalizzazione, setPersonalizzazione] = useState<Personalizzazione | null>(null);
  const [urgenti, setUrgenti] = useState<Evento[] | null>(null);
  const [errore, setErrore] = useState("");

  useEffect(() => {
    async function carica() {
      try {
        const ultimo = (await leggiPeriodoDemo()).al;
        const dal = spostaGiorno(ultimo, -(GIORNI_DI_ALLARMI - 1));
        setPersonalizzazione(await leggiPersonalizzazioneDemo());
        const cadute = await leggiEventiDemo(dal, ultimo, "caduta");
        const uscite = await leggiEventiDemo(dal, ultimo, "uscita");
        setUrgenti(cadute.concat(uscite));
      } catch (problema) {
        setErrore(messaggioErrore(problema));
      }
    }
    carica();
  }, []);

  if (personalizzazione === null || urgenti === null) {
    return <Caricamento errore={errore} />;
  }

  const regole = personalizzazione.regole;
  let statoAllarme = (
    <span className="stato stato-buono">
      <Icona nome="spunta" dimensione={18} /> On
    </span>
  );
  if (!regole.allarme_uscita_attivo) {
    statoAllarme = (
      <span className="stato stato-neutro">
        <Icona nome="chiudi" dimensione={18} /> Off
      </span>
    );
  } else if (inPausa(regole.pausa_fino_a) && regole.pausa_fino_a !== null) {
    statoAllarme = (
      <span className="stato stato-attenzione">
        <Icona nome="pausa" dimensione={18} /> Paused until{" "}
        {oraDellaCasa(regole.pausa_fino_a, personalizzazione.fuso_orario)}
      </span>
    );
  }

  // Allarmi dal più recente, divisi per giorno.
  const ordinati = urgenti.slice();
  ordinati.sort(confrontaDalPiuRecente);
  const giorni: { giorno: string; eventi: Evento[] }[] = [];
  for (const evento of ordinati) {
    const giorno = giornoDellaCasa(evento.inizio, personalizzazione.fuso_orario);
    const ultimo = giorni[giorni.length - 1];
    if (ultimo !== undefined && ultimo.giorno === giorno) {
      ultimo.eventi.push(evento);
    } else {
      giorni.push({ giorno: giorno, eventi: [evento] });
    }
  }

  return (
    <div className="pila-larga entrata">
      <TitoloPagina titolo="Alerts" sotto={"Falls and exits in the last " + GIORNI_DI_ALLARMI + " days."} />
      <Scheda titolo="Exit alarm" icona="porta" accanto={statoAllarme}>
        <div className="pila">
          <FasceVietate personalizzazione={personalizzazione} />
          <p className="testo-secondario testo-piccolo">
            In the demo home the family pauses or switches off this alarm from Telegram.
          </p>
        </div>
      </Scheda>
      {giorni.length === 0 && (
        <Scheda>
          <p className="testo-secondario">No alerts in this period.</p>
        </Scheda>
      )}
      {giorni.map((voce) => (
        <Scheda key={voce.giorno} titolo={giornoLungo(voce.giorno)} icona="campanella">
          <ol className="linea-tempo">
            {voce.eventi.map((evento) => (
              <RigaEvento key={evento.id} evento={evento} personalizzazione={personalizzazione} />
            ))}
          </ol>
        </Scheda>
      ))}
    </div>
  );
}

function confrontaDalPiuRecente(a: Evento, b: Evento): number {
  return new Date(b.inizio).getTime() - new Date(a.inizio).getTime();
}
