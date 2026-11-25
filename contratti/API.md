# API del backend SAGE

Contratto tra backend, web app e programma di casa. I modelli dei dati sono in `contratti/contratti/`
(`eventi.py`, `configurazione.py`, `report.py`); FastAPI li usa direttamente e pubblica la documentazione su `/docs`.
Tutto in JSON, date e ore con fuso orario (ISO 8601). I giorni dei report si contano nel `fuso_orario` della casa.

## Come è fatta la demo (D21-D23, D27-D29)
- **Niente login.** La web app salva la personalizzazione dell'utente solo nel suo browser: il backend non la vede.
  Flusso: apertura → personalizzazione → "Coming soon" (prossime funzioni) → dashboard vuota con
  "Waiting for camera setup" e il pulsante "Open demo home".
- **Il backend gestisce una sola casa: la casa demo.** I dati arrivano dal programma di casa, che elabora sul PC di
  Marco (o su Kaggle) i video registrati; la web app li legge in sola lettura, senza autenticazione.
- La web app non elabora video e non si collega alle telecamere.

## Casa demo (lettura pubblica, per la web app)
Risultati veri dei modelli sui video registrati più lo storico simulato (`simulato: true`).

| Metodo | Percorso | Risposta |
|---|---|---|
| GET | `/demo/personalizzazione` | `Personalizzazione` della casa demo (farmaci, contenitori, telecamere previste, regole) |
| GET | `/demo/periodo` | `{dal, al}`: primo e ultimo giorno (AAAA-MM-GG) con eventi nella casa demo, `null` se non ce ne sono |
| GET | `/demo/eventi?dal=&al=&tipo=` | `list[Evento]` **coordinati** (vedi sotto) in ordine di `inizio`; `dal` e `al` sono date AAAA-MM-GG comprese, nel fuso della casa; `foto_prova` sempre `null` qui, `ha_foto` dice se c'è |
| GET | `/demo/eventi/{id}/foto` | JPEG della foto di prova (404 se non c'è) |
| GET | `/demo/report/giornaliero?data=AAAA-MM-GG` | `ReportGiornaliero` |
| GET | `/demo/report/settimanale?dal=AAAA-MM-GG` | `ReportPeriodo` dei 7 giorni da `dal` |
| GET | `/demo/report/mensile?mese=AAAA-MM` | `ReportPeriodo` del mese |

I trend si disegnano con `ReportPeriodo.giorni` (una riga per giorno). Le foto di prova della casa demo sono
pubbliche: vengono dai video che Marco registra apposta per la demo.

## Programma di casa (header `Authorization: Bearer <token casa>`)
Il token è la variabile `TOKEN_CASA`: sta nel file `.env` del programma di casa e in `backend/.env`, mai nel repo.

| Metodo | Percorso | Corpo → risposta |
|---|---|---|
| PUT | `/programma-casa/personalizzazione` | `Personalizzazione` (dal file locale `ConfigurazioneCasa`, senza sorgenti né zone) → `Personalizzazione`; serve al backend per orari dei farmaci, orari vietati e notte. Pausa e spegnimento dell'allarme restano quelli decisi da Telegram |
| POST | `/programma-casa/eventi` | `list[Evento]` **grezzi** (una telecamera e un analizzatore ciascuno) → `{ricevuti, nuovi}`; un `id` già visto viene ignorato; gli urgenti fanno partire Telegram |

## Coordinamento degli eventi (Marco, 24/11)
Lo stesso fatto può arrivare più volte: da telecamere diverse, dalla stessa telecamera in pezzi vicini, o rimandato
dopo un errore di rete. Il backend non deve né duplicarlo né perderlo:
- **Ogni evento grezzo ricevuto si salva così com'è** (idempotente sull'`id`): niente si perde, e si può sempre
  ricalcolare.
- **Il coordinatore** del backend raggruppa gli eventi grezzi dello stesso `tipo` che si sovrappongono nel tempo o
  sono vicini (stessa finestra dell'unione del programma di casa), da qualunque telecamera, in un **evento
  coordinato**: `id` del primo grezzo, `inizio` il più presto, `fine` la più tardi, `fonti` tutte, `confidenza` la
  più alta, `valori` e foto dal grezzo più sicuro (i ml di una bevuta vista da due telecamere non si sommano),
  `stanze` dell'alzata notturna unite.
- Web app, report e Telegram usano **solo gli eventi coordinati**. Un allarme parte una volta per evento coordinato:
  i doppioni che arrivano dopo lo aggiornano ma non rimandano il messaggio.
- Il programma di casa manda gli eventi grezzi senza fonderli (tiene il suo registro locale per quando manca la rete).

## Telegram (D10, D24)
- Collegamento: si scrive al bot `/start <codice>`; il codice sta nel `.env` del backend. Tutte le chat collegate
  ricevono gli allarmi della casa demo.
- **caduta**: sempre, subito, con la foto di prova;
- **uscita**: se è in un orario vietato, l'allarme è attivo e non in pausa; con la foto;
- **promemoria farmaco**: quando finisce la finestra di una dose senza presa.
- Pulsanti nei messaggi di uscita: pausa 1 h, pausa 3 h, spegni. Comando `/riattiva`. Cambiano `pausa_fino_a` e
  `allarme_uscita_attivo` della casa demo sul backend.

## Regole che calcola il backend (non il programma di casa)
- **Stato delle dosi**: per ogni farmaco e orario previsto, la prima presa con quel `farmaco_id` (o non riconosciuta)
  vicino all'orario (D38): da 1 ora prima fino a `tolleranza_minuti` dopo → `in_orario`; fino a 2 ore dopo →
  `in_ritardo` con `minuti_ritardo`; finita la finestra senza presa → `saltata` (promemoria Telegram); finestra non
  ancora finita → `in_attesa`.
- **Uscita in orario vietato**: `inizio` dell'uscita dentro una fascia di `orari_uscita_vietati`; il backend lo
  scrive in `valori.in_orario_vietato`.
- **ml della bevuta** (Marco, 24/11): la `percentuale` viene dal programma di casa, misurata in ogni fotogramma come
  rapporto tra pixel scesi e altezza del contenitore nello stesso fotogramma, quindi vale anche se il contenitore
  è più lontano o più vicino. Se `contenitore_id` è nella personalizzazione, il backend ricalcola
  `ml = percentuale / 100 × capienza_ml` di quel contenitore; altrimenti tiene i ml del programma di casa.
- **Aderenza ai farmaci**: `null` se nel periodo non c'è ancora nessuna dose valutata.
- **Quanto ha mangiato** (Marco, 25/11): niente percentuale, tre categorie. Il programma di casa arrotonda la
  percentuale del piatto: sotto il 35% `meno_di_meta`, dal 35 al 75% `meta`, oltre il 75% `tutto`; `null` se non
  misurata. Nei riassunti dei giorni: `pasti` visti e `pasti_meno_di_meta`.
- **Notte**: le alzate contano negli `orari_notte`.
- **Ore di sonno** (Marco, 25/11): il programma di casa manda eventi `sonno` (pezzi di sonno nella zona letto); il
  backend somma i pezzi che iniziano tra 2 ore prima di `orari_notte.dalle` e 4 ore dopo `orari_notte.alle`, e li
  conta nel giorno in cui finisce la notte. `addormentato_alle` = inizio del primo pezzo, `sveglio_alle` = fine
  dell'ultimo. Le alzate notturne sono i buchi tra un pezzo e l'altro.

## Inserimenti a mano dei familiari (web app, Marco 25/11)
- Nella web app un familiare può segnare a mano se e quanto ha mangiato e bevuto l'anziano. Come la
  personalizzazione (D29), questi inserimenti restano nel browser e non vanno al backend.
- Bevuta: ora, ml oppure numero di bicchieri (ml = bicchieri × capienza del contenitore scelto, 200 ml se nessuno).
- Pasto: ora, cibi (testo libero, facoltativo), quanto: `niente` | `meno_di_meta` | `meta` | `tutto`.
- La web app li mostra con la scritta "logged by family" e li somma ai dati delle telecamere nei totali del giorno.
