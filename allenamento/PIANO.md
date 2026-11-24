# Piano di allenamento di SAGE (BOZZA da approvare)

Scritto il 23/11 dall'agente di allenamento. Tutto quello che è segnato **da decidere** lo decide Marco (sezione 7);
le ore GPU non si usano finché Marco non approva la sezione 6. Dataset: `ricerca/dataset.md` (anche la seconda
ricerca, sez. 12). Licenze non commerciali ammesse anche per allenare, pesi mai pubblicati (D34).

## 0. Calendario e quota
La quota GPU Kaggle (30 h a settimana per account) si azzera il sabato alle 00:00 UTC.

| Settimana | Giorni | Cosa |
|---|---|---|
| S0 | lun 23/11 - ven 27/11 | esplorazioni su CPU; estrazione degli scheletri; prime versioni dei modelli con i dati pubblici |
| S1 | sab 28/11 - ven 4/12 | riprese di Marco (prima quelle del tavolo); seconde versioni con i fotogrammi di Marco |
| S2 | sab 5/12 - ven 11/12 | valutazione sui video di Marco, taratura delle soglie, ONNX e tempi sul PC di Marco |
| S3 | sab 12/12 - ven 18/12 | solo correzioni; i modelli finali consegnati all'agente di casa entro il 14/12 |
| S4 | sab 19/12 - dom 20/12 | niente allenamenti (consegna lunedì 21/12) |

## 1. Cadute (compito 1)
- **Dataset** (tutti su Kaggle, si allegano al kernel):

  | Dataset | Slug Kaggle | Licenza | Perché |
  |---|---|---|---|
  | CAUCAFall | `thanhtung09t2/caucafall` | CC BY 4.0 | infrarosso, telecamera in alto in un angolo: il più simile alla casa |
  | GMDCSA-24 | `ambatipallisahasra/gmdcsa24` (copia più recente `nguynthnhquang/gmdcsa`) | CC BY 4.0 | 3 case vere, notte con poca luce, etichette a tempo |
  | UR Fall | `shahliza27/ur-fall-detection-dataset` | CC BY-NC-SA 4.0 | nella copia Kaggle solo la camera 0 (parallela al pavimento), senza etichette per fotogramma |
  | Le2i | `tuyenldvn/falldataset-imvia` | CC BY-NC-SA | 4 ambienti, momento della caduta annotato |
  | da valutare: MUVIM | `hiugip/muvim-yolo-raw` | non verificata (Kaggle dice Apache 2.0) | infrarosso e termico |
  | da valutare: VARISHTA-MM50 | `abhatewari22/varishta-mm50-organized` | CC BY 4.0 | 50 anziani 60-90 anni (camera da smartphone) |

  Le etichette di OmniFall (Hugging Face, CC BY-NC) danno a tutti la stessa tassonomia, compresa la classe
  "a terra dopo la caduta": utile per `secondi_a_terra`.
- **Modello**: scheletri da YOLO26-pose preallenato (nessun allenamento della posa) + classificatore su finestre
  di scheletri a 3 classi `normale / caduta / a_terra` (classificatore: **da decidere**, proposta ST-GCN come ARGO).
- **Divisione**: per soggetto e scena, mai per finestra (lezione di ARGO): test = soggetti mai visti (es. CAUCAFall
  soggetti 9-10, GMDCSA soggetto 4, una stanza di Le2i), validazione separata per scegliere la soglia.
- **Metrica**: su pezzi di durata fissa (es. 5 s), non per video: richiamo delle cadute (una caduta è presa se
  l'allarme arriva entro 3 s dalla fine) e falsi allarmi per ora di video senza cadute; F1 per pezzo.
- **Obiettivo proposto**: richiamo ≥ 0,90 con ≤ 1 falso allarme all'ora sul test pubblico; sui video di Marco tutte
  le 8-10 cadute prese e nessun allarme sulle 6-8 "non cadute".
- **Ore GPU**: 0 se gli scheletri si estraggono con i kernel CPU gratuiti (5 sessioni insieme, vedi esplorazione per
  i fotogrammi totali); altrimenti 1-2 h. Il classificatore è piccolo: si allena su CPU (gratis) o in < 1 h di GPU.

## 2. Bevuta: contenitore e livello del liquido (compito 2, D9)
- Il gesto (contenitore in mano vicino alla bocca) e il tipo di contenitore vengono dal passaggio condiviso
  (COCO `bottle`, `cup`, `wine glass`, posa); il modello nuovo serve per **contenitore e liquido in pixel**.
- **Dataset**: LabPics Chemistry + Medical `sagieppel/labpics-chemistry-labpics-medical` (CC0 su Kaggle, MIT
  l'originale; maschere di recipiente e liquido); Roboflow CC BY 4.0 (serve un account): "SAM2 Liquid
  Sem-Segmentation" (poligoni, origine di `goktani/...`), "waterbottle-level", "water level in cup",
  "Glass Of Water Segmentation", "Fill level"; `goktani/liquid-level-detection-dataset-yolov11` (CC BY 4.0, solo box)
  per una prova a box; poi i fotogrammi delle riprese 1-4 di Marco (indispensabili: nessun dataset è da lontano/IR).
- **Modello**: YOLO26-seg (grandezza **da decidere**) con 2 classi `contenitore`, `liquido`, sui ritagli del
  contenitore. Confronto senza allenamento: SAM2 di Eppel per il livello (Apache 2.0, pesante ma usato 2 volte a
  bevuta) e YOLOE a vocabolario aperto.
- **Metrica**: IoU delle maschere sulla validazione; errore della riga del liquido in % dell'altezza del
  contenitore; sulle bevute misurate di Marco errore in ml.
- **Obiettivo proposto**: errore mediano della riga ≤ 3% dell'altezza; ml entro ±30% (o ±40 ml) per sorso sulle
  bevute di Marco dal bicchiere e dalla bottiglia trasparenti.
- **Ore GPU**: v1 su dati pubblici circa 3 h, v2 con i fotogrammi di Marco circa 2 h, prove 2 h: **~7 h**.

## 3. Farmaci (compito 3, D15)
- **Dataset**: pillole `perfect9015/pillsdetectiondataset` (CC0) e `alexanderyyy/pills-detection-dataset`
  (CC BY-NC-SA); scatole `melikeklahc/yolocilin-medicine-box-detection` (CC BY 4.0); Roboflow CC BY 4.0
  `vishnu-6xlhd/mouth-and-pillbox-detection` (bocca + portapillole), "Pill Organizer", "pill box" (Gary, Andre),
  `yolov11pills/pillbox-nvhsd`; per il portapillole settimanale nessun dataset: riprese 5-9 di Marco.
- **Modello**: YOLO26 rilevatore n e s con classi `pillola`, `blister`, `scatola_farmaco`, `portapillole`,
  `scomparto` (aperto/chiuso non c'è nei dati pubblici: verrà dalle riprese di Marco). Vista dall'alto e ristretta
  (Marco, 24/11): foto ravvicinate di pillole limitate a 3.000, 30% di copie "come la telecamera" (grigio, bassa
  risoluzione, rumore, mano sopra), rotazioni libere e oggetti rimpiccioliti; valutazione anche su ritagli attorno
  alle mani (idea di `ritagli_delle_mani` di ARGO) quando ci saranno le riprese.
- **Gesto** (proposta di Marco): classificatore sulle finestre di scheletri come per le cadute, classi
  `prende_farmaco / beve / mangia / altro`, allenato su Charades (c129, c106, c156/c065); serve anche alla bevuta.
  Kernel `gesti_scheletri` pronto (estrazione); il classificatore si sceglie dopo (sez. 7). Riconoscimento del farmaco senza allenamento:
  encoder congelato (CLIP ViT-B/16 come D15, o DINOv2: **da decidere** con una prova su CPU) e confronto con le foto
  di scatola/blister caricate nell'app.
- **Metrica e obiettivo proposti**: mAP50 ≥ 0,8 sulla validazione; sui video di Marco prese riconosciute ≥ 9 su 10
  con ≤ 1 falso su 5 "falsi farmaci"; farmaco giusto ≥ 90% tra i 2-3 farmaci di Marco.
- **Ore GPU**: v1 pubblico circa 2 h, v2 con i fotogrammi di Marco circa 2 h: **~4-5 h**. L'encoder: 0 (CPU).

## 4. Cibo (compito 4)
- **Percentuale mangiata**: segmentazione `cibo` (tutte le classi di FoodSeg103 unite in una) sul ritaglio del piatto
  prima e dopo: `100 × (1 - area_dopo / area_prima)`. Dataset `ggrill/foodseg103` (Apache 2.0, 4.983 + 2.135
  immagini) e UNIMIB2016 `dangvanthuc0209/unimib2016` (vassoi visti dall'alto; licenza non dichiarata). Modello
  YOLO26-seg (grandezza **da decidere**). Metrica: IoU `cibo` sulla validazione (obiettivo ≥ 0,80); sui pasti di
  Marco errore della percentuale ≤ 15 punti. **Ore GPU ~4-5 h.**
- **Tipo di cibo** (D14, una foto a pasto, nessun allenamento): modello visione+linguaggio piccolo **da decidere**;
  prova su CPU gratis (Kaggle) con 200 foto di FoodSeg103/Food-101: correttezza dei nomi, secondi a foto, RAM.

## 5. Alzata notturna e uscita
Nessun modello da allenare: passaggio condiviso + zone `letto` e `porta` + tracking + regole tarate sulle riprese
13-16. Da misurare: quanto la posa trova la persona in infrarosso (CAUCAFall, sotto) e a letto (SLP,
`awsaf49/ieee-vip-cup-2021-train-val-dataset`, solo se serve).

## 6. Piano delle ore GPU (allargato il 24/11)
Marco (24/11, tramite il coordinatore): modelli prima di tutto, GPU con generosità, fino a ~20 h per account in
S0; ogni YOLO26 in due grandezze, n e s (n sulla GPU 0, s sulla GPU 1 della stessa sessione T4 x2), la scelta
dopo con precisione sulla validazione e millisecondi su CPU.

| Kernel (cartella `allenamento/kaggle/`) | Account | Macchina | Ore stimate | Stato (24/11, 02:30) |
|---|---|---|---|---|
| `esplora_cadute` | Marco | CPU | 0 | fatto (v2): numeri nella sez. 8 |
| `cadute_scheletri_cpu` (posa n, stesso file di `cadute_scheletri`) | Marco | CPU | 0 | fatto: 520 npz, 142.127 fotogrammi in 5,0 h (7,8 fps); persona trovata nel 91-100% dei fotogrammi (mediana per dataset) |
| `vlm_cibo` (Qwen3-VL-2B, SmolVLM2-2.2B, SmolVLM2-500M su 40 foto Food-101) | Marco | CPU | 0 | fatto: risultati sotto |
| `cadute_scheletri` (posa n + s) | Marco | GPU T4 x2 | ~1,5 | pronto, **lancio GPU bloccato** (sez. 9) |
| `liquido_seg` (LabPics + goktani, 4 h di allenamento) | Marco | GPU T4 x2 | ~5 | pronto, bloccato |
| `cibo_seg` (FoodSeg103 + UNIMIB2016 + Food Recognition 2022, 9 h) | Marco | GPU T4 x2 | ~10 | pronto, bloccato |
| `farmaci_det` (pillole, scatole + Roboflow, 6 h) | secondo | GPU T4 x2 | ~7 | pronto, bloccato; meglio dopo i dataset Roboflow |
| `gesti_scheletri` (Charades, 3.611 video, posa n + s a 12 fps) | secondo | GPU T4 x2 | ~6-7 | pronto, bloccato |
| classificatori ST-GCN cadute e gesti | uno dei due | GPU o CPU | ~1-2 | da scrivere quando ci sono gli scheletri |

Totale S0: ~16,5 h sull'account di Marco e ~14 h sul secondo. Ogni kernel GPU salva pesi (`best.pt`, ONNX),
`results.csv`, mAP per classe sulla validazione, ms per immagine sulla CPU di Kaggle e ore di allenamento in
`risultati.json`; le estrazioni salvano `tempi_*.json`.

## 7. Scelte da fare (Marco)
Vedi il rapporto dell'agente: classificatore delle cadute (ST-GCN per primo, come chiesto), fotogrammi al secondo
delle finestre, classi dei gesti, modello per il tipo di cibo (dopo `vlm_cibo`), encoder dei farmaci, soglie e
obiettivi, come i kernel ricevono il codice, dipendenze locali, video di Marco su Kaggle (privati).

## 8. Esplorazione dei dataset di cadute (kernel `esplora_cadute` v2, 24/11)
| Dataset | Video | Durata | Risoluzione, fps | Etichette | Note |
|---|---|---|---|---|---|
| CAUCAFall | 100 avi (10 soggetti × 10 azioni) | 16,6 min, 19.877 fotogrammi | 720×480, 20 fps | un txt YOLO per fotogramma: box della persona, classe 0 = nofall, 1 = fall (caduta + a terra) | angolo alto, grandangolo; **infrarosso: soggetti 6 e 8** (20 video) |
| GMDCSA-24 v2.1 (`nguynthnhquang/gmdcsa`) | 160 mp4 (4 soggetti) | 21,5 min, 34.172 | 1280×720 o 640×480, 30 o 15 fps | csv per soggetto con classi e secondi, es. `Falling[2 to 4]` | altezza occhi, giorno e notte con luce |
| Le2i | 190 avi (4 ambienti) | 51 min, 75.911 | 320×240 25 fps o 320×180 24 fps | 130 txt: fotogramma di inizio e fine caduta + box per fotogramma | avi grezzi con audio: OpenCV va in errore, si leggono con ffmpeg |
| UR Fall (copia Kaggle) | 70 sequenze png | 11.936 fotogrammi | 640×480, 30 fps | nessun csv per fotogramma: solo "fall-NN" / "adl-NN" | **solo camera 0** (parallela al pavimento), niente camera a soffitto |
| VARISHTA-MM50 | 450 mp4 (50 anziani, 9 classi) | 175 min, 316.277 | smartphone, varie | classe = cartella del video | posa ottima (47-48/48) ma camera a mano: per ora non usato |
| MUVIM (`hiugip`) | 12 mila immagini YOLO | — | 672×376 | box, fall/normal | fotogrammi, non video: per ora non usato |

Posa YOLO26 su 48 fotogrammi per dataset (persona trovata; ms su CPU Kaggle): CAUCAFall n 42/48 (IR 19/24),
s 44/48 (IR 21/24); GMDCSA n 45, s 47; Le2i n 43, s 45; UR Fall n 39, s 41. n ~85-105 ms, s ~200-240 ms.

## 9. Cose che deve fare Marco (24/11)
- **Lanciare i kernel GPU**: il sistema dei permessi di Claude Code blocca il lancio di kernel GPU (consumo di
  quota) perché l'approvazione è arrivata tramite il coordinatore e non da Marco. Comandi, dalla cartella del worktree:
  `GPU_APPROVATA=si allenamento/kaggle/lancia.sh cadute_scheletri`, `... liquido_seg`, `... cibo_seg`
  (account di Marco); `GPU_APPROVATA=si allenamento/kaggle/lancia.sh gesti_scheletri secondo` e
  `... farmaci_det secondo` (secondo account). Poi `allenamento/kaggle/segui.sh <nome> [secondo]`.
  In alternativa una regola di permesso che lasci all'agente `lancia.sh` con `GPU_APPROVATA=si`.
- **Scaricare i dataset Roboflow**: bloccato anche l'uso della chiave Roboflow da parte dell'agente. Comando:
  `python3 allenamento/scarica_roboflow.py ~/.config/roboflow/chiave runs/roboflow/farmaci vishnu-6xlhd/mouth-and-pillbox-detection hannas-workspace-zgvp5/pillbox-compartment-detection-w3ayb muhammads-workspace-mdgli/pill-organizer-um6kg gary-ofgwc/pill-box-0nbmp andre-anrfr/pill-box yolov11pills/pillbox-nvhsd medai2/blister-womyq yoloultra/tablet-blister-rhrec`
  (e per il cibo `runs/roboflow/cibo hust-ajpvu/food-srnub miyams-workspace/tray-segmentation-vgevo crab-robot-2025/leftover-foods xuhong0987-gmail-com/hospital-meal georges-workspace/food-tray-detection cv-eu0de/food-detection-erjhm`;
  per il liquido `runs/roboflow/liquidi nonbiodegradable-data-sets/waterbottle-level nunnut1s-workspace/water-level-in-cup mohamed-6qlja/glass-of-water-segmentation`).
  Poi l'agente carica le cartelle come dataset privati sull'account che le usa e le aggiunge ai kernel.

## 10. Tipo di cibo: confronto dei modelli visione+linguaggio (kernel `vlm_cibo`, 24/11)
40 foto di Food-101 (metà piatti italiani), CPU di Kaggle a 4 thread, pesi float32, foto ridotte a 512 px.
"Esatte" = il nome del piatto compare nella risposta; "parziali" = ne compare almeno una parola lunga.

| Modello (licenza Apache 2.0) | Esatte | Parziali | Secondi per foto (mediana) | Picco di memoria |
|---|---|---|---|---|
| Qwen3-VL-2B-Instruct | 20/40 | 28/40 | 16,8 | 12,4 GB |
| SmolVLM2-2.2B-Instruct | 13/40 | 24/40 | 167 | 9,8 GB |
| SmolVLM2-500M-Video-Instruct | 8/40 | 19/40 | 50,7 | 3,0 GB |

Proposta: Qwen3-VL-2B (il più corretto e anche il più veloce). In float32 non sta nei 6,7 GB del PC di Marco:
serve una versione ridotta (bf16 circa 4,5 GB o quantizzata), da provare. Risposte complete in
`runs/kaggle/vlm_cibo/risposte_*.json` (fuori da git).
