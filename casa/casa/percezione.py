"""Percezione condivisa (D1, D14): per ogni fotogramma di una telecamera un solo passaggio con posa (persone +
scheletro), tracking e, se serve, rilevatore di oggetti. Gli analizzatori leggono solo questa uscita.

Idee riprese dall'Estrattore di ARGO (sicurezza_NN/src/sicurezza/visione.py): il tracker si chiama a mano
fotogramma per fotogramma come fa `.track` di Ultralytics, così i modelli si caricano una volta sola e servono
tutte le telecamere (ogni telecamera ha il suo tracker). La compensazione del movimento della telecamera (GMC) è
spenta: le telecamere di casa sono fisse e in ARGO costava ~11 ms a fotogramma.
"""

import base64
from dataclasses import dataclass, field
import datetime

import cv2
import numpy as np

POSA_PREDEFINITA = "pesi/yolo26n-pose.pt"
RILEVATORE_PREDEFINITO = "pesi/yolo26n.pt"
TRACKER_PREDEFINITO = "tracktrack.yaml"  # il default di `.track` in Ultralytics 8.4, come in ARGO

# cibi che il rilevatore pre-allenato (COCO) conosce: i nomi sono già in inglese come vuole la web app (D13)
CIBI_COCO = ("banana", "apple", "sandwich", "orange", "broccoli", "carrot", "hot dog", "pizza", "donut", "cake")
# Oggetti del rilevatore pre-allenato (COCO) che servono a bevuta, farmaco e pasto; gli altri si scartano.
CLASSI_OGGETTI = ("bottle", "wine glass", "cup", "bowl", "dining table") + CIBI_COCO

# 0,1 come il default di `.track` (ARGO, D3): il tracker usa anche le persone poco sicure nel secondo passaggio.
CONFIDENZA_MINIMA_PERSONE = 0.1
CONFIDENZA_MINIMA_OGGETTI = 0.25
# Contenitori anche poco sicuri, solo per cercarli vicino alla testa intorno al gesto della bevuta: alla bocca la mano
# li copre e il rilevatore li vede con confidenza 0,05-0,16 (agente di allenamento su Charades, 25/11)
CLASSI_CONTENITORI = ("bottle", "wine glass", "cup")
CONFIDENZA_MINIMA_CONTENITORI = 0.05

# Foto di prova degli eventi: JPEG piccolo (va nel JSON dell'evento e su Telegram).
LATO_MASSIMO_FOTO = 640
QUALITA_FOTO = 70


@dataclass
class Persona:
    id_traccia: int
    box: np.ndarray        # x1, y1, x2, y2 in pixel
    confidenza: float
    keypoint: np.ndarray   # (17, 3): x, y in pixel e visibilità, ordine COCO


@dataclass
class Oggetto:
    classe: str            # nome COCO, es. "bottle"
    box: np.ndarray        # x1, y1, x2, y2 in pixel
    confidenza: float


@dataclass
class Osservazione:
    """Quello che la percezione ha visto in un fotogramma di una telecamera."""

    telecamera_id: str
    stanza: str
    ora: datetime.datetime  # ora vera della casa, con fuso orario
    immagine: np.ndarray    # BGR: per le foto di prova e per i controlli in pixel (es. livello della bevuta)
    persone: list[Persona]
    oggetti: list[Oggetto]
    # contenitori con confidenza da 0,05 a 0,25 (sotto la soglia di `oggetti`): solo per la regola dei gesti
    contenitori_incerti: list[Oggetto] = field(default_factory=list)


class Percezione:
    """Tiene caricati i modelli. Il rilevatore di oggetti si carica solo se qualche telecamera ne ha bisogno."""

    def __init__(self, percorso_posa: str = POSA_PREDEFINITA, percorso_rilevatore: str | None = None,
                 tracker: str = TRACKER_PREDEFINITO, lato_immagine: int = 640):
        from ultralytics import YOLO  # lento da importare: solo quando serve davvero

        self.posa = YOLO(percorso_posa)
        self.rilevatore = None
        if percorso_rilevatore is not None:
            self.rilevatore = YOLO(percorso_rilevatore)
        self.percorso_tracker = tracker
        self.lato_immagine = lato_immagine

    def nuovo_tracker(self):
        """Un tracker nuovo per ogni telecamera, come `.track` al primo fotogramma di un video."""
        from ultralytics.trackers.track import TRACKER_MAP
        from ultralytics.utils import YAML, IterableSimpleNamespace
        from ultralytics.utils.checks import check_yaml

        impostazioni = IterableSimpleNamespace(**YAML.load(check_yaml(self.percorso_tracker)))
        impostazioni.device = "cpu"
        if hasattr(impostazioni, "gmc_method"):
            impostazioni.gmc_method = "none"  # telecamere fisse
        return TRACKER_MAP[impostazioni.tracker_type](args=impostazioni)

    def persone(self, immagine: np.ndarray, tracker) -> list[Persona]:
        """Posa + tracking: solo le persone con una traccia confermata."""
        risultato = self.posa.predict(immagine, conf=CONFIDENZA_MINIMA_PERSONE, imgsz=self.lato_immagine,
                                      device="cpu", verbose=False)[0]
        # stessa logica di ultralytics.trackers.track.on_predict_postprocess_end
        tracce = tracker.update(risultato.boxes.cpu().numpy(), risultato.orig_img)
        persone = []
        if len(tracce) == 0:
            return persone
        # ultima colonna: indice della persona nel risultato della posa; prime 4: box del tracker
        indici = tracce[:, -1].astype(int)
        keypoint = risultato.keypoints.data.cpu().numpy()
        # il box previsto dal tracker può uscire dall'immagine: si ritaglia come fa `.track` (Results.update)
        altezza = immagine.shape[0]
        larghezza = immagine.shape[1]
        box = tracce[:, 0:4].astype(np.float32)
        box[:, [0, 2]] = np.clip(box[:, [0, 2]], 0, larghezza)
        box[:, [1, 3]] = np.clip(box[:, [1, 3]], 0, altezza)
        for riga in range(len(tracce)):
            indice = indici[riga]
            persona = Persona(
                id_traccia=int(tracce[riga, 4]),
                box=box[riga],
                confidenza=float(tracce[riga, 5]),
                keypoint=keypoint[indice],
            )
            persone.append(persona)
        return persone

    def oggetti(self, immagine: np.ndarray) -> list[Oggetto]:
        """Contenitori, ciotole e tavoli del rilevatore pre-allenato (D14): da 0,25 in su, i contenitori da 0,05."""
        risultato = self.rilevatore.predict(immagine, conf=CONFIDENZA_MINIMA_CONTENITORI, imgsz=self.lato_immagine,
                                            device="cpu", verbose=False)[0]
        box = risultato.boxes.xyxy.cpu().numpy()
        classi = risultato.boxes.cls.int().cpu().numpy()
        confidenze = risultato.boxes.conf.cpu().numpy()
        oggetti = []
        for indice in range(len(box)):
            nome = risultato.names[int(classi[indice])]
            confidenza = float(confidenze[indice])
            sicuro = nome in CLASSI_OGGETTI and confidenza >= CONFIDENZA_MINIMA_OGGETTI
            if sicuro or nome in CLASSI_CONTENITORI:
                oggetti.append(Oggetto(nome, box[indice], confidenza))
        return oggetti

    def osserva(self, immagine: np.ndarray, tracker, con_oggetti: bool, telecamera_id: str, stanza: str,
                ora: datetime.datetime) -> Osservazione:
        persone = self.persone(immagine, tracker)
        oggetti = []
        contenitori_incerti = []
        if con_oggetti:
            for oggetto in self.oggetti(immagine):
                if oggetto.confidenza >= CONFIDENZA_MINIMA_OGGETTI:
                    oggetti.append(oggetto)
                else:
                    contenitori_incerti.append(oggetto)
        return Osservazione(telecamera_id, stanza, ora, immagine, persone, oggetti, contenitori_incerti)


def foto_prova(immagine: np.ndarray) -> str:
    """JPEG piccolo in base64 per il campo foto_prova degli eventi."""
    altezza = immagine.shape[0]
    larghezza = immagine.shape[1]
    lato = max(altezza, larghezza)
    if lato > LATO_MASSIMO_FOTO:
        scala = LATO_MASSIMO_FOTO / lato
        nuova_dimensione = (round(larghezza * scala), round(altezza * scala))
        immagine = cv2.resize(immagine, nuova_dimensione, interpolation=cv2.INTER_AREA)
    riuscito, dati_jpeg = cv2.imencode(".jpg", immagine, [cv2.IMWRITE_JPEG_QUALITY, QUALITA_FOTO])
    if not riuscito:
        raise RuntimeError("foto di prova non codificabile in JPEG")
    return base64.b64encode(dati_jpeg.tobytes()).decode("ascii")
