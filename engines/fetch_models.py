"""Ses modellerini manifestteki sabit Hugging Face revizyonlarından indirir ve doğrular.

Yalnızca standart kütüphane kullanır: /usr/bin/python3 -I -B engines/fetch_models.py
Her dosya aynı dizindeki geçici dosyaya indirilir, boyutu ve SHA-256 özeti manifestle
karşılaştırılır, sonra os.link ile var olan hiçbir dosyanın üzerine yazmadan yayımlanır.
Doğru dosya zaten varsa atlanır; farklı içerikli bir dosya varsa işlem durur.
--check yalnızca yerel dosyaları denetler, ağa çıkmaz.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import urllib.request

ENGINES_DIR = Path(__file__).resolve().parent
CHUNK = 1 << 20
RETRIES = 3


class FetchError(Exception):
    pass


class Conflict(FetchError):
    """Yeniden denenmeyecek hata: hedefte farklı içerikli dosya var."""


def sha256_of(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        while block := f.read(CHUNK):
            digest.update(block)
    return digest.hexdigest()


def matches(path, entry):
    return path.is_file() and not path.is_symlink() and path.stat().st_size == entry["size"] \
        and sha256_of(path) == entry["sha256"]


def safe_target(engine_dir, relative):
    """Göreli hedefin motor dizini içinde kaldığını ve symlink'ten geçmediğini doğrular."""
    rel = Path(relative)
    if rel.is_absolute() or ".." in rel.parts:
        raise FetchError(f"Güvensiz hedef yolu: {relative}")
    target = engine_dir / rel
    for parent in [engine_dir, *reversed(target.parents)]:
        if parent == engine_dir or engine_dir in parent.parents:
            if parent.is_symlink():
                raise FetchError(f"Hedef yolunda sembolik bağlantı var: {parent}")
    return target


def download(url, target, entry):
    """URL'yi hedefin yanındaki geçici dosyaya indirir; doğrulanırsa link ile yayımlar."""
    target.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(1, RETRIES + 1):
        fd, name = tempfile.mkstemp(dir=target.parent, prefix=f".{target.name}.", suffix=".part")
        temporary = Path(name)
        try:
            digest, size = hashlib.sha256(), 0
            request = urllib.request.Request(url, headers={"User-Agent": "geveze-setup"})
            with os.fdopen(fd, "wb") as out, urllib.request.urlopen(request, timeout=60) as response:
                while block := response.read(CHUNK):
                    size += len(block)
                    if size > entry["size"]:
                        raise FetchError(f"Beklenenden büyük yanıt: {url}")
                    digest.update(block)
                    out.write(block)
            if size != entry["size"] or digest.hexdigest() != entry["sha256"]:
                raise FetchError(f"Boyut/SHA-256 eşleşmedi: {url}")
            try:
                os.link(temporary, target)
            except FileExistsError:
                if not matches(target, entry):
                    raise Conflict(f"Hedef bu sırada farklı içerikle oluştu: {target}")
            return
        except Conflict:
            raise
        except (OSError, FetchError) as exc:
            if attempt == RETRIES:
                raise FetchError(f"{url}: {exc}") from exc
            print(f"  yeniden denenecek ({attempt}/{RETRIES}): {exc}", file=sys.stderr)
            time.sleep(2 * attempt)
        finally:
            temporary.unlink(missing_ok=True)


def process_engine(engine_dir, check_only):
    manifest = json.loads((engine_dir / "models/manifest.json").read_text(encoding="utf-8"))
    prefix = f"https://huggingface.co/{manifest['repository']}/resolve/{manifest['revision']}/"
    missing = []
    for entry in manifest["files"]:
        if not entry["source"].startswith(prefix):
            raise FetchError(f"Beklenmeyen kaynak (depo/revizyon dışı): {entry['source']}")
        target = safe_target(engine_dir, entry["path"])
        label = f"{engine_dir.name}/{entry['path']}"
        if target.exists() or target.is_symlink():
            if not matches(target, entry):
                raise FetchError(f"{label} var ama manifestle eşleşmiyor; dosyaya dokunulmadı.")
            print(f"  hazır     {label}")
            continue
        if check_only:
            missing.append(label)
            print(f"  eksik     {label}")
            continue
        print(f"  indiriliyor {label} ({entry['size'] / 1e6:.1f} MB)", flush=True)
        download(entry["source"], target, entry)
    if missing:
        return missing
    if "voices" in manifest:
        check_piper_configs(engine_dir, manifest)
    else:
        write_hf_ref(engine_dir, manifest, check_only)
    return []


def check_piper_configs(engine_dir, manifest):
    """Her sesin ONNX/config/kart üçlüsü ve config değerleri manifestle uyumlu mu?"""
    for voice_id, voice in manifest["voices"].items():
        for key in ("model", "config", "model_card"):
            if not (engine_dir / voice[key]).is_file():
                raise FetchError(f"{voice_id}: {voice[key]} eksik")
        config = json.loads((engine_dir / voice["config"]).read_text(encoding="utf-8"))
        if config["audio"]["sample_rate"] != voice["sample_rate"]:
            raise FetchError(f"{voice_id}: örnekleme hızı manifestle uyuşmuyor")
        if config.get("num_speakers", 1) != voice.get("num_speakers", 1):
            raise FetchError(f"{voice_id}: konuşmacı sayısı manifestle uyuşmuyor")


def write_hf_ref(engine_dir, manifest, check_only):
    """EMA, Hugging Face önbelleğinde snapshot'ın yanında refs/main kaydını bekler."""
    cache = "models--" + manifest["repository"].replace("/", "--")
    ref = safe_target(engine_dir, f"models/{cache}/refs/main")
    if ref.exists():
        if ref.read_text(encoding="utf-8").strip() != manifest["revision"]:
            raise FetchError(f"{ref} farklı bir revizyon gösteriyor; dosyaya dokunulmadı.")
        return
    if check_only:
        raise FetchError(f"{ref} eksik")
    ref.parent.mkdir(parents=True, exist_ok=True)
    with ref.open("x", encoding="utf-8") as f:
        f.write(manifest["revision"])


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="Yalnızca yerel dosyaları denetle")
    args = parser.parse_args()
    missing = []
    try:
        for name in ("ema", "piper"):
            print(f"{name}:")
            missing += process_engine(ENGINES_DIR / name, args.check)
    except FetchError as exc:
        print(f"HATA: {exc}", file=sys.stderr)
        return 1
    if missing:
        print(f"{len(missing)} model dosyası eksik.", file=sys.stderr)
        return 1
    print("Tüm model dosyaları doğrulandı.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
