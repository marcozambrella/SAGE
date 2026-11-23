# API del backend SAGE

Contratto tra backend, web app e programma di casa. I modelli dei dati sono in `contratti/contratti/`
(`eventi.py`, `configurazione.py`, `report.py`); FastAPI li usa direttamente e pubblica la documentazione su `/docs`.
Tutto in JSON, date e ore con fuso orario (ISO 8601). I giorni dei report si contano nel `fuso_orario` della casa.

## Chi chiama cosa
- **Web app** (famiglie): header `Authorization: Bearer <token familiare>` ricevuto da login.
- **Programma di casa**: header `Authorization: Bearer <token casa>`, un token per casa (creato dal backend,
  messo nel file `.env` del programma di casa, mai nel repo).
- La web app non elabora video e non si collega alle telecamere (D21, D23).

## Account e casa (D26)
| Metodo | Percorso | Corpo → risposta |
|---|---|---|
| POST | `/auth/registrati` | `{nome, email, password}` → `{token}`; crea anche una casa nuova |
| POST | `/auth/entra` | `{email, password}` → `{token}` |
| POST | `/auth/unisciti` | `{nome, email, password, codice_invito}` → `{token}`; entra in una casa esistente |
| GET | `/casa` | → `{codice_invito, familiari: [{nome, email, telegram_collegato}]}` |
| POST | `/casa/nuovo-codice-invito` | → `{codice_invito}` |

## Personalizzazione (onboarding e impostazioni)
| Metodo | Percorso | Corpo → risposta |
|---|---|---|
| GET | `/personalizzazione` | → `Personalizzazione`; **404** se non è ancora stata fatta (la web app apre l'onboarding) |
| PUT | `/personalizzazione` | `Personalizzazione` intera → `Personalizzazione` |
| POST | `/foto-farmaci` | file immagine (multipart) → `{foto_id}` |
| GET | `/foto-farmaci/{foto_id}` | → immagine |

## Allarme uscita (D16) — le stesse azioni ci sono nei pulsanti di Telegram
| Metodo | Percorso | Corpo → risposta |
|---|---|---|
| POST | `/allarme-uscita/pausa` | `{ore}` → `RegoleAllarmi` |
| POST | `/allarme-uscita/spegni` | → `RegoleAllarmi` |
| POST | `/allarme-uscita/riattiva` | → `RegoleAllarmi` (toglie anche la pausa) |

## Telegram (D10, D24)
| Metodo | Percorso | Corpo → risposta |
|---|---|---|
| POST | `/telegram/collega` | → `{link}`: link `t.me/<bot>?start=<codice monouso>` per collegare il familiare |

Il bot manda a tutti i familiari collegati della casa:
- **caduta**: sempre, subito, con la foto di prova;
- **uscita**: se è in un orario vietato, l'allarme è attivo e non in pausa; con la foto;
- **promemoria farmaco**: quando finisce la finestra di una dose senza presa.

Pulsanti nei messaggi di uscita: pausa 1 h, pausa 3 h, spegni. Comando `/riattiva`.

## Dati: `{casa}` è `mia` oppure `demo` (D22)
`demo` è la casa demo, in sola lettura per ogni utente con login: risultati veri dei modelli sui video registrati
più lo storico simulato (`simulato: true`).

| Metodo | Percorso | Risposta |
|---|---|---|
| GET | `/dati/{casa}/stato` | `{primo_evento}`: `null` finché non è arrivato nessun evento → la web app mostra "Waiting for camera setup" |
| GET | `/dati/{casa}/personalizzazione` | `Personalizzazione` (per la casa demo: farmaci, contenitori, telecamere della demo) |
| GET | `/dati/{casa}/eventi?dal=&al=&tipo=` | `list[Evento]` in ordine di `inizio`; `foto_prova` sempre `null` qui |
| GET | `/dati/{casa}/eventi/{id}/foto` | JPEG della foto di prova (404 se non c'è) |
| GET | `/dati/{casa}/report/giornaliero?data=AAAA-MM-GG` | `ReportGiornaliero` |
| GET | `/dati/{casa}/report/settimanale?dal=AAAA-MM-GG` | `ReportPeriodo` dei 7 giorni da `dal` |
| GET | `/dati/{casa}/report/mensile?mese=AAAA-MM` | `ReportPeriodo` del mese |

I trend si disegnano con `ReportPeriodo.giorni` (una riga per giorno).

## Programma di casa
| Metodo | Percorso | Corpo → risposta |
|---|---|---|
| POST | `/programma-casa/eventi` | `list[Evento]` → `{ricevuti, nuovi}`; un `id` già visto viene ignorato; gli urgenti fanno partire Telegram |
| GET | `/programma-casa/personalizzazione` | → `Personalizzazione` (farmaci, contenitori, regole) |
| GET | `/programma-casa/foto-farmaci/{foto_id}` | → immagine (per il riconoscimento dei farmaci) |

## Regole che calcola il backend (non il programma di casa)
- **Stato delle dosi**: per ogni farmaco e orario previsto, la prima presa con quel `farmaco_id` (o non riconosciuta)
  vicino all'orario: entro `tolleranza_minuti` → `in_orario`; dopo → `in_ritardo` con `minuti_ritardo`; finita la
  finestra senza presa → `saltata`; finestra non ancora finita → `in_attesa`. La finestra esatta la propone
  l'agente backend e la decide Marco.
- **Uscita in orario vietato**: `inizio` dell'uscita dentro una fascia di `orari_uscita_vietati`.
- **Notte**: le alzate contano negli `orari_notte`.
