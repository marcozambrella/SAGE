"""Riconoscimento del farmaco dalle foto di scatola/blister caricate nell'app (D15), senza allenare un modello per ogni
farmaco: embedding CLIP congelati (ViT-B/16 "openai", gli stessi delle teste CLIP di ARGO) del ritaglio e delle
foto, e somiglianza del coseno. Si usa solo la parte visiva di CLIP: si confrontano immagini con immagini.
"""

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from contratti.configurazione import Personalizzazione

MODELLO_CLIP = "ViT-B-16"
PESI_CLIP = "openai"
# Due foto dello stesso oggetto stanno di solito sopra, oggetti diversi sotto (prove con immagini pubbliche, 24/11).
# Se serve, la tara l'agente di allenamento sui dati pubblici (Marco, 25/11: le sue riprese sono solo per la demo).
SOGLIA_SOMIGLIANZA = 0.75


@dataclass
class Riconoscimento:
    farmaco_id: str
    somiglianza: float  # 0-1


class IncorporatoreClip:
    """Immagini → vettori CLIP normalizzati."""

    def __init__(self):
        import open_clip  # carica torch: solo se c'è davvero un farmaco da riconoscere

        modello, _, self.preprocesso = open_clip.create_model_and_transforms(MODELLO_CLIP, pretrained=PESI_CLIP)
        self.visivo = modello.visual.eval()
        del modello  # la parte del testo non serve: libera memoria (il PC di Marco ne ha poca)

    def incorpora(self, immagini_bgr: list) -> np.ndarray:
        import torch
        from PIL import Image

        ingressi = []
        for immagine in immagini_bgr:
            rgb = cv2.cvtColor(immagine, cv2.COLOR_BGR2RGB)
            ingressi.append(self.preprocesso(Image.fromarray(rgb)))
        with torch.no_grad():
            vettori = self.visivo(torch.stack(ingressi)).numpy()
        return vettori / np.linalg.norm(vettori, axis=1, keepdims=True)


class RiconoscitoreFarmaci:
    def __deepcopy__(self, memo: dict) -> "RiconoscitoreFarmaci":
        # il modello non è stato: le copie per tornare indietro di un secondo (principale.py) lo condividono
        return self

    def __init__(self, incorporatore, personalizzazione: Personalizzazione, cartella_foto: str):
        """incorporatore: qualunque oggetto con incorpora(immagini) → vettori normalizzati (CLIP, o uno finto nei
        test). Le foto sono i file <foto_id>.jpg nella cartella delle foto dei farmaci."""
        self.incorporatore = incorporatore
        self.farmaco_della_foto = []
        immagini = []
        for farmaco in personalizzazione.farmaci:
            for foto_id in farmaco.foto_ids:
                percorso = Path(cartella_foto) / (foto_id + ".jpg")
                immagine = cv2.imread(str(percorso))
                if immagine is None:
                    print("foto del farmaco " + farmaco.id + " non trovata: " + str(percorso))
                    continue
                immagini.append(immagine)
                self.farmaco_della_foto.append(farmaco.id)
        self.vettori_foto = None
        if len(immagini) > 0:
            self.vettori_foto = incorporatore.incorpora(immagini)

    def riconosci(self, ritagli: list) -> Riconoscimento | None:
        """Il farmaco più somigliante a uno dei ritagli, se supera la soglia; altrimenti None (non riconosciuto)."""
        if self.vettori_foto is None or len(ritagli) == 0:
            return None
        vettori_ritagli = self.incorporatore.incorpora(ritagli)
        # somiglianza del coseno di ogni ritaglio con ogni foto: (ritagli, foto)
        somiglianze = vettori_ritagli @ self.vettori_foto.T
        indice_foto = int(np.argmax(somiglianze.max(axis=0)))
        somiglianza = float(somiglianze.max())
        if somiglianza < SOGLIA_SOMIGLIANZA:
            return None
        return Riconoscimento(self.farmaco_della_foto[indice_foto], min(somiglianza, 1.0))


def crea_riconoscitore(personalizzazione: Personalizzazione, cartella_foto: str) -> RiconoscitoreFarmaci | None:
    """Il riconoscitore con CLIP, o None se non ci sono foto o CLIP non si carica: allora i farmaci restano "non
    riconosciuti" (farmaco_id None) e il resto del programma va avanti."""
    ci_sono_foto = False
    for farmaco in personalizzazione.farmaci:
        if len(farmaco.foto_ids) > 0:
            ci_sono_foto = True
    if not ci_sono_foto:
        return None
    try:
        incorporatore = IncorporatoreClip()
    except Exception as errore:  # pesi non scaricabili, rete assente: il riconoscimento è facoltativo
        print("CLIP non disponibile, farmaci non riconosciuti dalle foto: " + str(errore))
        return None
    return RiconoscitoreFarmaci(incorporatore, personalizzazione, cartella_foto)
