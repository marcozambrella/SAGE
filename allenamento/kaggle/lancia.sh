#!/usr/bin/env bash
# Lancia un kernel Kaggle di questa cartella (come training/lancia.sh di ARGO): mette il nome utente dell'account al
# posto di KAGGLE_UTENTE in kernel-metadata.json e fa il push.
# Uso:  allenamento/kaggle/lancia.sh esplora_cadute            account di Marco (~/.kaggle/credentials.json)
#       allenamento/kaggle/lancia.sh esplora_cadute secondo    secondo account (token in ~/.kaggle/token_secondo)
# Poi:  allenamento/kaggle/segui.sh esplora_cadute [secondo]   log su file e uscita in runs/kaggle/<nome>/
# I kernel con "enable_gpu": true consumano la quota GPU (30 h/settimana per account): partono solo con
# GPU_APPROVATA=si davanti al comando, dopo che Marco ha approvato il piano delle ore.
set -euo pipefail
nome="$1"
account="${2:-marco}"
cartella_kernel="$(cd "$(dirname "$0")" && pwd)/$nome"
if grep -q '"enable_gpu": true' "$cartella_kernel/kernel-metadata.json" && [ "${GPU_APPROVATA:-no}" != "si" ]; then
    echo "$nome usa la GPU: serve GPU_APPROVATA=si (piano delle ore approvato da Marco)" >&2
    exit 1
fi
if [ "$account" = "secondo" ]; then
    # il percorso del file, non il contenuto: il token non passa mai da questo script
    export KAGGLE_API_TOKEN="$HOME/.kaggle/token_secondo"
fi
utente="$(kaggle config view 2>/dev/null | sed -n 's/^- username: //p')"
if [ -z "$utente" ]; then
    echo "nome utente Kaggle sconosciuto: login scaduto? (kaggle auth login, solo Marco)" >&2
    exit 1
fi
copia="$(mktemp -d)"
cp "$cartella_kernel"/*.py "$cartella_kernel"/kernel-metadata.json "$copia"/
sed -i "s/KAGGLE_UTENTE/$utente/g" "$copia"/kernel-metadata.json
kaggle kernels push -p "$copia"
