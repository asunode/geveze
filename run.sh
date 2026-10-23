#!/usr/bin/env bash
# Geveze'yi başlatır. Arayüz için önce setup.sh'ın kurduğu .venv, yoksa sistem PySide6 kullanılır.
# Kullanım: ./run.sh [--vpool DİZİN]   (veya GEVEZE_VPOOL=DİZİN ./run.sh)
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"
if [ -x .venv/bin/python ]; then
    exec .venv/bin/python -B -m geveze "$@"
fi
if ! /usr/bin/python3 -I -c 'import PySide6.QtWidgets, PySide6.QtMultimedia' 2>/dev/null; then
    echo "PySide6 bulunamadı. Önce ./setup.sh çalıştırın." >&2
    exit 1
fi
exec /usr/bin/python3 -B -m geveze "$@"
