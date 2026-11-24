"""Scarica in locale dataset di Roboflow Universe in formato YOLO (yolov8: box o poligoni), ultima versione.

Uso:  python allenamento/scarica_roboflow.py <file della chiave> <cartella di uscita> utente/progetto [utente/progetto ...]
La chiave si legge dal file e non si stampa mai (neanche negli errori: gli indirizzi che la contengono non escono).
Poi la cartella si carica su Kaggle come dataset privato (vedi PIANO.md): i kernel non vedono mai la chiave.
"""
import json
import sys
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

API = "https://api.roboflow.com"


def chiedi_json(indirizzo: str) -> dict:
    """GET di un indirizzo dell'API; in caso di errore solo il codice HTTP, mai l'indirizzo (contiene la chiave)."""
    try:
        with urllib.request.urlopen(indirizzo, timeout=120) as risposta:
            return json.loads(risposta.read())
    except urllib.error.HTTPError as errore:
        return {"errore_http": errore.code}
    except (urllib.error.URLError, TimeoutError, ValueError):
        return {"errore_http": "rete"}


def scarica(chiave: str, progetto: str, cartella_uscita: Path) -> str:
    utente, nome = progetto.split("/")
    informazioni = chiedi_json(f"{API}/{utente}/{nome}?api_key={chiave}")
    if "errore_http" in informazioni:
        return f"progetto non trovato ({informazioni['errore_http']})"
    versioni = informazioni.get("versions", [])
    if not versioni:
        return "nessuna versione pubblicata"
    ultima = versioni[0]["id"].split("/")[-1]
    for versione in versioni:
        numero = versione["id"].split("/")[-1]
        if int(numero) > int(ultima):
            ultima = numero
    licenza = informazioni.get("project", {}).get("license", "?")
    tipo = informazioni.get("project", {}).get("type", "?")
    # l'esportazione può non essere pronta: Roboflow la prepara e si richiede finché c'è il link
    collegamento = None
    for tentativo in range(30):
        esportazione = chiedi_json(f"{API}/{utente}/{nome}/{ultima}/yolov8?api_key={chiave}")
        collegamento = esportazione.get("export", {}).get("link")
        if collegamento:
            break
        time.sleep(10)
    if not collegamento:
        return "esportazione non pronta dopo 5 minuti"
    destinazione = cartella_uscita / f"{utente}__{nome}"
    destinazione.mkdir(parents=True, exist_ok=True)
    archivio = destinazione / "dataset.zip"
    try:
        urllib.request.urlretrieve(collegamento, archivio)
    except (urllib.error.URLError, TimeoutError):
        return "download non riuscito"
    with zipfile.ZipFile(archivio) as file_zip:
        file_zip.extractall(destinazione)
    archivio.unlink()
    (destinazione / "fonte_roboflow.json").write_text(json.dumps(
        {"progetto": progetto, "versione": ultima, "licenza": licenza, "tipo": tipo}, indent=1))
    immagini = 0
    for percorso in destinazione.rglob("*"):
        if percorso.suffix.lower() in [".jpg", ".jpeg", ".png"]:
            immagini += 1
    return f"versione {ultima}, {tipo}, licenza {licenza}, {immagini} immagini"


chiave = Path(sys.argv[1]).read_text().strip()
cartella = Path(sys.argv[2])
for progetto in sys.argv[3:]:
    print(progetto, "→", scarica(chiave, progetto, cartella), flush=True)
