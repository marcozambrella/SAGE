"""Tipo di cibo (D14), kernel solo CPU: confronto di modelli visione+linguaggio piccoli, una foto per pasto.

Per ogni candidato: risposta su FOTO_PER_MODELLO foto di Food-101 (`kmader/food41`, cartelle images/<piatto>/),
metà da piatti italiani; tempo per foto sulla CPU di Kaggle (4 core, come i 4 thread del PC di Marco) e picco di
memoria. Corretta "esatta" se il nome del piatto compare nella risposta, "parziale" se compare almeno una sua
parola lunga. Le risposte restano tutte in risposte.json per leggerle a mano (il nome di Food-101 è uno solo,
la risposta può essere giusta con altre parole). Ogni modello gira in un processo separato (picco di memoria suo).
Pesi in float32: sul PC di Marco (6,7 GB) servirà una versione ridotta (bf16 o int8), da provare dopo la scelta.
"""
import json
import multiprocessing
import os
import random
import resource
import subprocess
import sys
import time
from pathlib import Path

subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-U", "transformers>=4.57", "accelerate",
                "num2words"], check=True)

INGRESSO = Path("/kaggle/input")
USCITA = Path("/kaggle/working")
CANDIDATI = [
    "Qwen/Qwen3-VL-2B-Instruct",                 # Apache 2.0
    "HuggingFaceTB/SmolVLM2-2.2B-Instruct",      # Apache 2.0
    "HuggingFaceTB/SmolVLM2-500M-Video-Instruct",  # Apache 2.0, il più leggero
]
FOTO_PER_MODELLO = 40
LATO_MASSIMO = 512   # foto rimpicciolite: meno token dell'immagine, risposta più veloce
DOMANDA = ("What food is on this plate? Answer only with a short comma-separated list of dish or food names "
           "in English.")
PIATTI_ITALIANI = ["pizza", "lasagna", "spaghetti_bolognese", "spaghetti_carbonara", "risotto", "ravioli",
                   "gnocchi", "bruschetta", "caprese_salad", "tiramisu", "panna_cotta", "cannoli", "beef_carpaccio",
                   "garlic_bread", "minestrone"]


def foto_food101() -> list:
    """(percorso, piatto) di metà foto italiane e metà di altri piatti, sempre le stesse (seme 0)."""
    per_piatto = {}
    for cartella, _, nomi in os.walk(INGRESSO, followlinks=True):
        percorso_cartella = Path(cartella)
        if percorso_cartella.parent.name != "images":
            continue
        for nome in sorted(nomi):
            if nome.lower().endswith(".jpg"):
                if percorso_cartella.name not in per_piatto:
                    per_piatto[percorso_cartella.name] = []
                per_piatto[percorso_cartella.name].append(percorso_cartella / nome)
    generatore = random.Random(0)
    italiani = []
    altri = []
    for piatto in sorted(per_piatto):
        if piatto in PIATTI_ITALIANI:
            italiani.append(piatto)
        else:
            altri.append(piatto)
    scelte = []
    for indice in range(FOTO_PER_MODELLO):
        if indice % 2 == 0 and italiani:
            piatto = italiani[(indice // 2) % len(italiani)]
        else:
            piatto = generatore.choice(altri)
        scelte.append((str(generatore.choice(per_piatto[piatto])), piatto))
    return scelte


def corretta(risposta: str, piatto: str) -> tuple:
    testo = risposta.lower().replace("-", " ")
    nome = piatto.replace("_", " ")
    esatta = nome in testo
    parziale = False
    for parola in nome.split():
        if len(parola) >= 4 and parola in testo:
            parziale = True
    return esatta, parziale


def prova_modello(nome_modello: str, foto: list, percorso_uscita: str) -> None:
    """Un processo: carica il modello, risponde su tutte le foto, scrive il suo json."""
    import torch
    from PIL import Image
    from transformers import AutoModelForImageTextToText, AutoProcessor

    torch.set_num_threads(4)
    inizio = time.perf_counter()
    processore = AutoProcessor.from_pretrained(nome_modello)
    modello = AutoModelForImageTextToText.from_pretrained(nome_modello, torch_dtype=torch.float32)
    modello.eval()
    secondi_caricamento = time.perf_counter() - inizio
    risposte = []
    for percorso, piatto in foto:
        immagine = Image.open(percorso).convert("RGB")
        immagine.thumbnail((LATO_MASSIMO, LATO_MASSIMO))
        messaggi = [{"role": "user", "content": [{"type": "image", "image": immagine},
                                                 {"type": "text", "text": DOMANDA}]}]
        ingressi = processore.apply_chat_template(messaggi, add_generation_prompt=True, tokenize=True,
                                                  return_dict=True, return_tensors="pt")
        inizio = time.perf_counter()
        with torch.no_grad():
            generati = modello.generate(**ingressi, max_new_tokens=40, do_sample=False)
        secondi = time.perf_counter() - inizio
        nuovi = generati[:, ingressi["input_ids"].shape[1]:]
        testo = processore.batch_decode(nuovi, skip_special_tokens=True)[0].strip()
        esatta, parziale = corretta(testo, piatto)
        risposte.append({"foto": percorso, "piatto": piatto, "risposta": testo, "secondi": round(secondi, 2),
                         "esatta": esatta, "parziale": parziale})
        print(f"[{nome_modello}] {piatto}: {testo} ({secondi:.1f} s)", flush=True)
    secondi_per_foto = []
    esatte = 0
    parziali = 0
    for risposta in risposte:
        secondi_per_foto.append(risposta["secondi"])
        if risposta["esatta"]:
            esatte += 1
        if risposta["parziale"]:
            parziali += 1
    secondi_per_foto.sort()
    riassunto = {
        "modello": nome_modello, "foto": len(risposte), "esatte": esatte, "parziali": parziali,
        "secondi_per_foto_mediana": secondi_per_foto[len(secondi_per_foto) // 2],
        "secondi_caricamento": round(secondi_caricamento, 1),
        # ru_maxrss è in KB su Linux
        "picco_memoria_gb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024 / 1024, 2),
        "risposte": risposte,
    }
    Path(percorso_uscita).write_text(json.dumps(riassunto, indent=1, ensure_ascii=False))


foto = foto_food101()
print("foto scelte:", len(foto), flush=True)
contesto = multiprocessing.get_context("fork")
riassunti = []
for numero, nome_modello in enumerate(CANDIDATI):
    percorso_uscita = USCITA / f"risposte_{numero}.json"
    processo = contesto.Process(target=prova_modello, args=(nome_modello, foto, str(percorso_uscita)))
    processo.start()
    processo.join()
    if processo.exitcode != 0 or not percorso_uscita.exists():
        riassunti.append({"modello": nome_modello, "errore": f"codice di uscita {processo.exitcode}"})
        continue
    dati = json.loads(percorso_uscita.read_text())
    riassunto = {}
    for chiave in dati:
        if chiave != "risposte":
            riassunto[chiave] = dati[chiave]
    riassunti.append(riassunto)
    print("RIASSUNTO", riassunto, flush=True)
(USCITA / "riassunto.json").write_text(json.dumps(riassunti, indent=1, ensure_ascii=False))
