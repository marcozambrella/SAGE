# Modelli di SAGE: ingresso e uscita (per il programma di casa)

Stato (24/11): **nessun modello ancora allenato**; i kernel sono pronti (vedi `PIANO.md`, sez. 6). Ogni YOLO26 si
allena in due grandezze, n e s: Marco sceglie dopo, con la precisione sulla validazione e i millisecondi su CPU.
Le soglie e le scelte segnate "da decidere" le approva Marco; dopo ogni allenamento qui si aggiornano metriche,
file dei pesi e velocità misurata.

Convenzioni per tutti i modelli:
- Fotogrammi BGR `uint8` di forma (altezza, larghezza, 3), come li dà OpenCV.
- Coordinate in pixel del fotogramma intero (non del ritaglio), origine in alto a sinistra, `y` cresce verso il basso.
- Pesi in `pesi/` del programma di casa (mai nel repo): `.pt` (Ultralytics/PyTorch) e, dove serve velocità, `.onnx`
  per ONNX Runtime su CPU (come ARGO v1.2).
- Velocità: millisecondi per chiamata sul PC di Marco (8 core, senza GPU), da misurare con i pesi finali.
  Prima misura (23/11, pesi COCO, fotogramma 1920×1080, `imgsz=640`, PyTorch con 4 thread, mediana di 15):
  posa n 114 ms / s 252 ms; rilevatore n 113 ms / s 251 ms; segmentazione n 113 ms / s 283 ms.

## 1. Passaggio condiviso (D1): persone, posa, oggetti, tracking — nessun allenamento
- **Modelli**: Ultralytics YOLO26 preallenati su COCO, `yolo26?-pose.pt` per persone e scheletro e `yolo26?.pt` per
  gli oggetti; tracking BoT-SORT o ByteTrack di Ultralytics (`model.track(..., persist=True)`). Grandezza n o s: da
  decidere. Licenza dei pesi Ultralytics: AGPL-3.0 (va bene per l'hackathon, pesi non pubblicati, D34).
- **Ingresso**: un fotogramma.
- **Uscita** per ogni persona: `id_traccia`, box `[x1, y1, x2, y2]`, confidenza, 17 punti COCO `(x, y, confidenza)`
  (0 naso, 5-6 spalle, 9-10 polsi, 11-12 anche, 15-16 caviglie); per ogni oggetto: classe COCO
  (`bottle`, `cup`, `wine glass`, `bowl`, `dining table`, `bed`, `chair`, `couch`...), box, confidenza.
- Serve a tutti gli analizzatori; uscita della porta e alzata notturna usano solo questo (zone + tracking + regole).

## 2. Classificatore delle cadute (da allenare, compito 1)
- **Ingresso**: finestra di `T` fotogrammi di una persona tracciata: array `float32` (T, 17, 3) con `x, y` normalizzati
  sulla finestra (centro e scala dello scheletro) e la confidenza del punto; maschera (T,) dei fotogrammi in cui la
  persona c'è. `T` e fotogrammi al secondo da decidere (proposta: 3 s a 10 fps, T = 30, una finestra ogni 0,5 s).
- **Uscita**: probabilità di 3 classi `[normale, caduta, a_terra]` (`a_terra` serve per `secondi_a_terra`).
- **Pesi**: `cadute.pt` + `cadute.onnx`. Velocità attesa: pochi ms per finestra.
- L'analizzatore: evento `caduta` quando `caduta` supera la soglia seguita da `a_terra` per almeno N secondi.
- Scheletri di allenamento (kernel `cadute_scheletri`): un `.npz` per video con `frame` (N,), `traccia` (N,),
  `box` (N, 4) xyxy, `conf` (N,), `punti` (N, 17, 3), `numero_frame`, `fps`, `larghezza`, `altezza`: lo stesso
  formato che il programma di casa può produrre dal passaggio condiviso.

## 3. Contenitore e livello del liquido (da allenare, compito 2, D9)
- **Ingresso**: ritaglio del fotogramma attorno a una `bottle` / `cup` / `wine glass` del passaggio condiviso
  (con margine), solo nei momenti "prima" e "dopo" la bevuta (contenitore fermo sul tavolo): poche chiamate a evento.
- **Uscita**: maschere (o box) di 2 classi, `contenitore` e `liquido`; da qui
  `altezza_contenitore_px` = altezza del contenitore e `y_superficie_px` = riga più alta del liquido, in pixel del
  fotogramma intero. L'analizzatore calcola `livello_sceso_px = y_superficie_dopo - y_superficie_prima` e i ml con la
  formula di D9 (`ValoriBevuta`).
- **Pesi**: `liquido.pt` + `liquido.onnx` (YOLO26-seg, grandezza da decidere).

## 4. Farmaci (da allenare, compito 3, D15)
- **4a Rilevatore** (kernel `farmaci_det`): ingresso il fotogramma o, meglio, un ritaglio attorno alle mani / alla
  zona `portapillole`; uscita box con classi `pillola` (0), `blister` (1), `scatola_farmaco` (2), `portapillole`
  (3), `scomparto` (4). Aperto/chiuso arriverà con le riprese di Marco. Pesi `best.pt` + `.onnx` per n e s.
- **4c Gesto** (proposta di Marco, da scegliere): classificatore su finestre di scheletri come le cadute, classi
  `prende_farmaco`, `beve`, `mangia`, `altro`; ingresso (T, 17, 3) come il modello 2. Scheletri da Charades
  (kernel `gesti_scheletri`, 12 fps).
- **4b Riconoscimento del farmaco** (nessun allenamento): encoder di immagini congelato (CLIP ViT-B/16 come nelle
  teste di ARGO, o DINOv2: da decidere con una prova); ingresso il ritaglio di scatola/blister; uscita un vettore
  normalizzato. Il programma confronta (coseno) con i vettori delle foto `foto_ids` di ogni farmaco: il massimo dà
  `farmaco_id` e `somiglianza`; sotto una soglia `farmaco_id = None`.
- `mano_alla_bocca` viene dalla posa (polso vicino a naso/bocca), non da un modello.

## 5. Cibo (compito 4)
- **5a Segmentazione del cibo** (da allenare): ingresso il ritaglio del piatto / della zona `tavolo` prima e dopo il
  pasto; uscita la maschera `cibo` (e `piatto` se serve). `percentuale_mangiata = 100 × (1 - area_dopo / area_prima)`.
  Pesi `cibo.pt` + `.onnx`.
- **5b Tipo di cibo** (modello visione+linguaggio piccolo, nessun allenamento, D14): ingresso una foto JPEG del
  piatto pieno, una a pasto; uscita la lista `cibi` in inglese (la web app è in inglese, D13). Modello da decidere;
  su CPU sono accettabili decine di secondi perché è una foto a pasto.
