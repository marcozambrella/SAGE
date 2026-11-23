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
| GET | `/demo/eventi?dal=&al=&tipo=` | `list[Evento]` in ordine di `inizio`; `dal` e `al` sono date AAAA-MM-GG comprese, nel fuso della casa; `foto_prova` sempre `null` qui |
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
| POST | `/programma-casa/eventi` | `list[Evento]` → `{ricevuti, nuovi}`; un `id` già visto viene ignorato; gli urgenti fanno partire Telegram |

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
- **Uscita in orario vietato**: `inizio` dell'uscita dentro una fascia di `orari_uscita_vietati`.
- **Notte**: le alzate contano negli `orari_notte`.
