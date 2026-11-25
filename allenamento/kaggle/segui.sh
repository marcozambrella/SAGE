#!/usr/bin/env bash
# Segue un kernel lanciato con lancia.sh fino alla fine e ne scarica l'uscita in runs/kaggle/<nome>/.
# Cose non ovvie di Kaggle (da ARGO): subito dopo il push lo stato risponde spesso con un errore 500 (si riprova);
# "kernels logs" senza -f è vuoto mentre il kernel gira, con -f riparte ogni volta dall'inizio; il log va su file
# perché le pipe bufferizzano.
# Uso:  allenamento/kaggle/segui.sh esplora_cadute [secondo]
set -euo pipefail
nome="$1"
account="${2:-marco}"
radice="$(cd "$(dirname "$0")/../.." && pwd)"
if [ "$account" = "secondo" ]; then
    export KAGGLE_API_TOKEN="$HOME/.kaggle/token_secondo"
fi
utente="$(kaggle config view 2>/dev/null | sed -n 's/^- username: //p')"
metadati="$radice/allenamento/kaggle/$nome/kernel-metadata.json"
slug="$(sed -n 's#.*"id": "KAGGLE_UTENTE/\(.*\)".*#\1#p' "$metadati")"
kernel="$utente/$slug"
uscita="$radice/runs/kaggle/$nome"
mkdir -p "$uscita"
while true; do
    stato="$(kaggle kernels status "$kernel" 2>&1 || true)"
    echo "$(date '+%F %T') $stato" >> "$uscita/stato.txt"
    case "$stato" in
        *COMPLETE*|*ERROR*|*CANCEL*) break ;;
        *RUNNING*) kaggle kernels logs -f "$kernel" > "$uscita/log_diretta.txt" 2>&1 || true ;;
    esac
    sleep 30
done
# il log finale completo (JSON con i campi "data") e i file di uscita
kaggle kernels logs "$kernel" > "$uscita/log.txt" 2>&1 || true
kaggle kernels output "$kernel" -p "$uscita" -o
echo "$stato"
