// Farmaci: nome, dose, orari, tolleranza e foto di scatola/blister (D15).
import type { Farmaco } from "../contratti";
import Campo from "../componenti/Campo";
import Icona from "../componenti/Icona";
import Pulsante from "../componenti/Pulsante";
import { nuovoId } from "../salvataggio";

type Proprieta = {
  valore: Farmaco[];
  onCambia: (nuovi: Farmaco[]) => void;
};

export default function ModuloFarmaci({ valore, onCambia }: Proprieta) {
  function cambiaFarmaco(indice: number, nuovo: Farmaco) {
    const copia = valore.slice();
    copia[indice] = nuovo;
    onCambia(copia);
  }

  function togliFarmaco(indice: number) {
    const copia = valore.slice();
    copia.splice(indice, 1);
    onCambia(copia);
  }

  function aggiungiFarmaco() {
    const nuovo: Farmaco = {
      id: nuovoId("farmaco"),
      nome: "",
      dose: "1 tablet",
      orari: ["08:00"],
      tolleranza_minuti: 30,
      foto_ids: [],
    };
    onCambia(valore.concat([nuovo]));
  }

  function cambiaOrario(indice: number, indiceOrario: number, orario: string) {
    const farmaco = valore[indice];
    const orari = farmaco.orari.slice();
    orari[indiceOrario] = orario;
    cambiaFarmaco(indice, { ...farmaco, orari: orari });
  }

  function togliOrario(indice: number, indiceOrario: number) {
    const farmaco = valore[indice];
    const orari = farmaco.orari.slice();
    orari.splice(indiceOrario, 1);
    cambiaFarmaco(indice, { ...farmaco, orari: orari });
  }

  function aggiungiOrario(indice: number) {
    const farmaco = valore[indice];
    cambiaFarmaco(indice, { ...farmaco, orari: farmaco.orari.concat(["20:00"]) });
  }

  return (
    <div className="pila-larga">
      {valore.length === 0 && (
        <p className="testo-secondario">No medications yet. Add each one they take, with the times of the day.</p>
      )}

      {valore.map((farmaco, indice) => (
        <div key={farmaco.id} className="riquadro pila">
          <div className="riga-spaziata">
            <h3>
              {farmaco.nome === "" && "New medication"}
              {farmaco.nome}
            </h3>
            <button
              type="button"
              className="pulsante pulsante-pericolo pulsante-icona"
              aria-label={"Remove " + farmaco.nome}
              onClick={() => togliFarmaco(indice)}
            >
              <Icona nome="cestino" />
            </button>
          </div>
          <div className="due-colonne">
            <Campo
              etichetta="Name"
              valore={farmaco.nome}
              onCambia={(testo) => cambiaFarmaco(indice, { ...farmaco, nome: testo })}
              segnaposto="e.g. Donepezil"
            />
            <Campo
              etichetta="Dose"
              valore={farmaco.dose}
              onCambia={(testo) => cambiaFarmaco(indice, { ...farmaco, dose: testo })}
              segnaposto="e.g. 1 tablet"
            />
          </div>

          <div className="campo">
            <span className="campo-etichetta">Times of day</span>
            <div className="riga">
              {farmaco.orari.map((orario, indiceOrario) => (
                <div key={indiceOrario} className="orario-con-x">
                  <div className="campo-pozzetto">
                    <input
                      type="time"
                      aria-label={"Time " + (indiceOrario + 1)}
                      value={orario}
                      onChange={(evento) => cambiaOrario(indice, indiceOrario, evento.target.value)}
                    />
                  </div>
                  {farmaco.orari.length > 1 && (
                    <button
                      type="button"
                      className="pulsante pulsante-secondario pulsante-icona"
                      aria-label={"Remove time " + orario}
                      onClick={() => togliOrario(indice, indiceOrario)}
                    >
                      <Icona nome="chiudi" />
                    </button>
                  )}
                </div>
              ))}
              <Pulsante variante="secondario" onClick={() => aggiungiOrario(indice)}>
                <Icona nome="piu" /> Time
              </Pulsante>
            </div>
          </div>

          <Campo
            etichetta="On-time window"
            tipo="number"
            unita="min"
            valore={String(farmaco.tolleranza_minuti)}
            onCambia={(testo) => cambiaFarmaco(indice, { ...farmaco, tolleranza_minuti: Number(testo) })}
            aiuto="A dose taken within this window counts as on time; later it counts as late."
          />

          {/* Il modo di salvare le foto (localStorage o IndexedDB) è ancora da decidere: per ora solo il riquadro. */}
          <div className="foto-farmaco">
            <Icona nome="foto" dimensione={28} />
            <div>
              <strong>Box and blister photos</strong>
              <p className="campo-aiuto">They help SAGE recognise this medication. Photo upload arrives in the next build.</p>
            </div>
          </div>
        </div>
      ))}

      <Pulsante variante="secondario" largo onClick={aggiungiFarmaco}>
        <Icona nome="piu" /> Add a medication
      </Pulsante>
    </div>
  );
}
