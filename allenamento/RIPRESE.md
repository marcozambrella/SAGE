# Riprese a casa di Marco (BOZZA da approvare)

Pochi video (D8, D35): servono per la demo, per un piccolo test e per tarare le regole dove mancano i dataset.
I video restano in locale (mai nel repo, D17); i fotogrammi di prova della casa demo però diventano pubblici
(API.md): niente documenti, volti di altri o indirizzi nell'inquadratura.

## Regole per tutte le riprese
- **Telecamere**: la telecamera IP (RTSP, ha l'infrarosso) per tutte le scene di notte; il telefono come telecamera IP
  solo di giorno o con la luce accesa. 1080p o 720p, almeno 15 fotogrammi al secondo, telecamera ferma.
- **Posizione**: in alto in un angolo (circa 2,2-2,5 m), inclinata verso il basso, come nella casa vera.
  Eccezione: la scena del tavolo (bere, farmaci, pasto) con la telecamera che inquadra bene il tavolo da 1,5-2,5 m,
  perché il livello dell'acqua deve essere grande abbastanza: un bicchiere alto almeno 80-100 pixel nel fotogramma.
- **Luce**: dove indicato tre versioni: giorno (luce naturale), sera (luce accesa), notte (luce spenta, infrarosso).
- **Ogni clip**: 5-10 secondi di scena ferma prima e dopo l'azione (servono come "prima" e "dopo").
- **Registro delle riprese**: un file `riprese.csv` (fuori dal repo, accanto ai video) con una riga per clip:
  `file, telecamera, stanza, scena, luce, inizio_azione (mm:ss), fine_azione (mm:ss), verita, note`;
  in `verita` il valore vero: ml bevuti, farmaco preso, percentuale mangiata, tipo di caduta.
- **Strumenti**: misurino o meglio bilancia da cucina (1 g di acqua = 1 ml: si pesa il contenitore prima e dopo
  ogni sorso), un materasso per le cadute, il portapillole vero, 2-3 scatole/blister veri (o integratori).

## Scene

| # | Scena | Inquadratura | Luce | Clip × durata | Cosa fare | Verità da segnare |
|---|---|---|---|---|---|---|
| 1 | Bere dal bicchiere | tavolo della cucina, 1,5-2,5 m | giorno, sera (1-2 di notte) | 6 × 30-40 s | bicchiere trasparente pieno fino a un livello noto sul tavolo; prenderlo, bere, rimetterlo **nello stesso punto**; sorsi diversi (circa 50, 100, 150 ml) | ml bevuti (bilancia), capienza del bicchiere |
| 2 | Bere dalla bottiglia | come 1 | come 1 | 6 × 30-40 s | bottiglia trasparente (0,5 o 1,5 L), etichetta che non copra tutto il livello; bere a canna o versare nel bicchiere (anche 2 clip "versa e beve") | ml bevuti, capienza |
| 3 | Bere dalla tazza | come 1 | giorno, sera | 4 × 30 s | tazza opaca: il livello non si vede da fuori; serve per riconoscere il gesto e il contenitore | ml bevuti (per misurare l'errore) |
| 4 | Riempimento lento | come 1 | giorno, sera | 1 × 60 s per contenitore | versare piano l'acqua dal vuoto al pieno con il contenitore fermo sul tavolo: dà tutti i livelli in un video (fotogrammi per la segmentazione) | capienza e livello finale |
| 5 | Farmaci dal portapillole | tavolo (come 1) | giorno, sera, notte (dose della sera) | 8 × 20-30 s | aprire lo scomparto del giorno, prendere la pillola, chiudere, mano alla bocca, bere | farmaco, ora |
| 6 | Farmaco da scatola/blister | tavolo | giorno, sera | 6 × 20-30 s | prendere la scatola, estrarre il blister, staccare una pillola, mano alla bocca, bere; 2-3 farmaci diversi | quale farmaco |
| 7 | Falsi farmaci | tavolo | giorno, sera | 5 × 20 s | toccare il portapillole senza prendere nulla, grattarsi il viso, mangiare un biscotto, bere senza pillola | "nessun farmaco" |
| 8 | Foto dei farmaci per l'app | telefono, da vicino | luce buona | 3-5 foto per farmaco | scatola davanti e dietro, blister davanti e dietro (sono le foto da caricare nella personalizzazione) | nome del farmaco |
| 9 | Foto del portapillole | dalla telecamera del tavolo | giorno, sera, notte | 1 video × 60 s | aprire e chiudere gli scomparti uno alla volta, spostarlo un po' sul tavolo | — |
| 10 | Pasto | tavolo (come 1) | giorno, sera | 4-6 pasti × 2-5 min (si può tagliare) | piatto pieno fermo 10 s, mangiare, piatto finale fermo 10 s; cibi diversi (pasta, insalata, minestra, frutta), quantità diverse (tutto, metà, poco) | cibi, piatto pesato prima e dopo (o stima a occhio) |
| 11 | Caduta | angolo alto del soggiorno o della camera | giorno, sera, notte (IR) | 8-10 × 30-60 s | 10 s di camminata, caduta controllata sul materasso (in avanti, indietro, di lato, dalla sedia, scivolando dal letto), 10-20 s a terra, rialzarsi | tipo di caduta, secondi a terra |
| 12 | Non cadute (falsi allarmi) | come 11 | giorno, notte | 6-8 × 30 s | sedersi di colpo sul divano, sdraiarsi sul letto, raccogliere un oggetto, allacciarsi le scarpe, sedersi per terra con calma | "nessuna caduta" |
| 13 | Alzata notturna | camera da letto, angolo alto | notte (IR, luce spenta) | 3-4 × 2-4 min | a letto 30 s, sedersi, alzarsi, uscire dalla camera (bagno o cucina), tornare dopo 1-2 min, sdraiarsi; se possibile una seconda telecamera nel corridoio o in cucina | ora di uscita e di ritorno, stanze |
| 14 | Non alzate | come 13 | notte | 2 × 1-2 min | girarsi nel letto, sedersi e tornare sdraiato senza alzarsi | "nessuna alzata" |
| 15 | Uscita di casa | porta d'ingresso vista dall'interno | giorno, sera, notte | 4-6 × 30-60 s | andare alla porta, aprire, uscire, chiudere; rientrare dopo 30 s | ora di uscita |
| 16 | Non uscite | come 15 | giorno, sera | 3 × 30 s | passare davanti alla porta, aprire a qualcuno e restare dentro | "nessuna uscita" |
| 17 | Vita normale | cucina e soggiorno (2 telecamere insieme) | giorno, sera | 2 × 10-15 min | attività normali senza eventi o con eventi segnati: serve a contare i falsi allarmi all'ora | eventi veri con l'ora |

Totale circa 80 clip, quasi tutte brevi: circa 1,5-2 ore di riprese con le prove.

## Scelte da fare con Marco
- **Persona che recita**: solo Marco o anche un'altra persona (più varietà per la caduta e la posa)?
- **Bilancia o misurino** per i ml bevuti: la bilancia è più precisa (consigliata se c'è).
- **Tazza**: con la telecamera in alto il livello in una tazza opaca non si vede (D9 funziona solo se si vede il
  liquido). Proposta: per la tazza solo "bevuta riconosciuta" e ml stimati con un sorso medio impostato nell'app,
  oppure la telecamera del tavolo che guarda dentro la tazza dall'alto. Da decidere.
- **Quando**: le scene 1-4 e 9 servono prima delle altre (fine-tuning della segmentazione del liquido e del
  rilevatore del portapillole: settimana 2 del piano); cadute, notte e uscita servono per la taratura e la demo.
