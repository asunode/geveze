#!/usr/bin/env bash
# Geveze kurulumu: ses motoru ortamları, ses modelleri ve gerekirse arayüz ortamı.
#
# Kullanım: ./setup.sh [--accept-model-licenses] [--gui-venv]
#   --accept-model-licenses  Model lisans özetini onaylanmış say (etkileşimsiz kurulum).
#   --gui-venv               Sistemde PySide6 olsa bile arayüz için .venv ortamı kur.
#
# Her şey bu klasörün içine kurulur (.tools/, engines/*/.venv, engines/*/models, .venv).
# sudo kullanılmaz, sistem Python'u değiştirilmez. Tekrar çalıştırmak güvenlidir: var olan
# ortamlar silinmez, doğru model dosyaları yeniden indirilmez, kullanıcı kayıtlarına dokunulmaz.
set -euo pipefail

ROOT="$(cd "$(dirname "$(readlink -f "$0")")" && pwd -P)"
cd "$ROOT"

UV_VERSION=0.13.1
UV_SHA256=eadd9d27c134ab5ac1ffd4473b97a741407f3ea238288f03121fc4deddf90220
UV_URL="https://github.com/astral-sh/uv/releases/download/$UV_VERSION/uv-x86_64-unknown-linux-gnu.tar.gz"
PYTHON_VERSION=3.12.15
PYPI=https://pypi.org/simple
TORCH_CPU=https://download.pytorch.org/whl/cpu

TOOLS="$ROOT/.tools"
UV="$TOOLS/uv-$UV_VERSION/uv"
export UV_CACHE_DIR="$TOOLS/cache" UV_PYTHON_INSTALL_DIR="$TOOLS/python" UV_PYTHON_PREFERENCE=only-managed UV_NO_CONFIG=1

accept_licenses=0
gui_venv=0
for arg in "$@"; do
    case "$arg" in
        --accept-model-licenses) accept_licenses=1 ;;
        --gui-venv) gui_venv=1 ;;
        -h|--help) sed -n '2,10p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "Bilinmeyen seçenek: $arg" >&2; exit 2 ;;
    esac
done

step() { printf '\n==> %s\n' "$*"; }
die() { printf 'HATA: %s\n' "$*" >&2; exit 1; }

[ "$(uname -sm)" = "Linux x86_64" ] || die "Yalnızca Linux x86_64 destekleniyor (bulunan: $(uname -sm))."
[ -x /usr/bin/python3 ] || die "/usr/bin/python3 bulunamadı (Ubuntu'da varsayılan olarak kuruludur)."

step "Ses modeli lisansları"
cat <<'EOF'
Kaynak: Hugging Face, sabit revizyonlar (canberkkkkkk/ema-lightning, rhasspy/piper-voices).
Toplam yaklaşık 740 MB. Modeller bu depoda dağıtılmaz; kendi lisanslarına tabidir.

  Ticari kullanım KISITLI (veri kümesi CC BY-NC-SA 4.0):
    Ryan (en_US-ryan-high), HFC Female (en_US-hfc_female-medium),
    Hi-Fi Captain kadın/erkek (ja_JP-hi_fi_captain-medium)
  Lisans durumu açıklığa kavuşmamış: Amy (en_US-amy-medium), Kerstin (de_DE-kerstin-low)
  Atıf koşullu: Jenny (Dioco), UPMC Jessica/Pierre (CC BY-SA 4.0), Artur (CC BY 4.0 / 3.0)
  Kod ve ağırlık için Apache-2.0: EMA Lightning;  veri kümesi CC0: Thorsten

Ayrıntılar: docs/third-party-licenses.md
EOF
if [ "$accept_licenses" = 0 ]; then
    [ -t 0 ] || die "Etkileşimsiz kurulumda --accept-model-licenses gerekir."
    read -r -p "Bu koşulları okudum, modeller indirilsin mi? [e/H] " answer
    case "$answer" in e|E|evet|Evet|y|Y|yes) ;; *) die "Model indirmesi iptal edildi." ;; esac
fi

step "uv $UV_VERSION (yalnızca bu klasörde)"
if [ ! -x "$UV" ]; then
    mkdir -p "$TOOLS"
    /usr/bin/python3 -I -B - "$UV_URL" "$UV_SHA256" "$TOOLS" "uv-$UV_VERSION" <<'PY'
import hashlib, io, sys, tarfile, urllib.request
from pathlib import Path
url, expected, tools, name = sys.argv[1], sys.argv[2], Path(sys.argv[3]), sys.argv[4]
data = urllib.request.urlopen(url, timeout=120).read()
if hashlib.sha256(data).hexdigest() != expected:
    sys.exit("uv arşivinin SHA-256 özeti beklenen değerle eşleşmedi; kurulum durduruldu.")
target = tools / name
target.mkdir()
with tarfile.open(fileobj=io.BytesIO(data)) as tar:
    for member in tar.getmembers():
        if member.isfile() and Path(member.name).name in ("uv", "uvx"):
            member.name = Path(member.name).name
            tar.extract(member, target, filter="data")
PY
fi
"$UV" --version

step "Python $PYTHON_VERSION (yalnızca bu klasörde; sistem Python'u değişmez)"
"$UV" python install --no-bin "$PYTHON_VERSION"

make_env() {  # make_env DİZİN: ortam yoksa oluşturur, varsa Python sürümünü doğrular
    local env="$1"
    if [ -e "$env" ] || [ -L "$env" ]; then
        local version
        version="$("$env/bin/python" -I -c 'import platform; print(platform.python_version())' 2>/dev/null)" \
            || die "$env var ama çalışmıyor. Kendiniz silip setup.sh'ı yeniden çalıştırın."
        [ "$version" = "$PYTHON_VERSION" ] \
            || die "$env Python $version kullanıyor ($PYTHON_VERSION bekleniyordu); ortama dokunulmadı."
        echo "Var olan ortam kullanılıyor: ${env#"$ROOT"/}"
    else
        "$UV" venv --quiet --python "$PYTHON_VERSION" "$env"
    fi
}

install_locked() {  # install_locked ORTAM DİZİN_URL KİLİT_DOSYASI
    "$UV" pip install --python "$1/bin/python" --require-hashes --no-deps --only-binary :all: \
        --index-url "$2" -r "$3"
}

step "EMA Lightning ortamı (Türkçe)"
make_env "$ROOT/engines/ema/.venv"
install_locked "$ROOT/engines/ema/.venv" "$TORCH_CPU" engines/ema/torch-cpu.lock
install_locked "$ROOT/engines/ema/.venv" "$PYPI" engines/ema/requirements.lock
"$UV" pip check --python "$ROOT/engines/ema/.venv/bin/python"

step "Piper ortamı (English, Deutsch, 日本語, Français, Slovenščina)"
make_env "$ROOT/engines/piper/.venv"
install_locked "$ROOT/engines/piper/.venv" "$PYPI" engines/piper/requirements.lock
"$UV" pip check --python "$ROOT/engines/piper/.venv/bin/python"

step "Arayüz (PySide6)"
if [ "$gui_venv" = 0 ] && /usr/bin/python3 -I -c 'import PySide6.QtWidgets, PySide6.QtMultimedia' 2>/dev/null; then
    echo "Sistem PySide6 kullanılacak: $(/usr/bin/python3 -I -c 'import PySide6; print(PySide6.__version__)')"
else
    make_env "$ROOT/.venv"
    install_locked "$ROOT/.venv" "$PYPI" requirements-gui.lock
    "$UV" pip check --python "$ROOT/.venv/bin/python"
    "$ROOT/.venv/bin/python" -I -c 'import PySide6.QtWidgets, PySide6.QtMultimedia' \
        || die "PySide6 kuruldu ama QtWidgets/QtMultimedia yüklenemedi (eksik sistem kütüphanesi olabilir)."
fi

step "Ses modelleri"
/usr/bin/python3 -I -B engines/fetch_models.py

step "Kayıt arşivi (VPOOL)"
vpool="$(/usr/bin/python3 -I -B -c 'import sys; sys.path.insert(0, sys.argv[1]); from geveze import core; print(core.resolve_vpool())' "$ROOT")"
echo "Kayıtlar burada tutulacak: $vpool"
echo "(Değiştirmek için: GEVEZE_VPOOL=DİZİN ./run.sh  veya  ./run.sh --vpool DİZİN)"

step "Kurulum tamamlandı. Başlatmak için: ./run.sh"
