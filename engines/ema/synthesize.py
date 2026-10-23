"""UTF-8 metinden yerel EMA ile WAV üretir; harici yollar için --output kullanın."""
import argparse
import os
from pathlib import Path
import tempfile

ENGINE_DIR = Path(__file__).resolve().parent
VPOOL = ENGINE_DIR.parent / "vpool"


def load_engine():
    """Uygulama başına bir kez çağırın; dönen EMA nesnesini yeniden kullanın."""
    os.environ["HF_HUB_CACHE"] = str(ENGINE_DIR / "models")
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    os.environ["XDG_CACHE_HOME"] = str(ENGINE_DIR / ".cache")
    import torch
    from ema_lightning import EMA

    torch.set_num_threads(min(4, os.cpu_count() or 1))
    return EMA(device="cpu")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("text_file", type=Path)
    parser.add_argument("-o", "--output", type=Path, help="Harici kullanım için açık WAV çıktı yolu")
    parser.add_argument("--force", action="store_true", help="Mevcut WAV dosyasını yeniden üret")
    args = parser.parse_args()
    source = args.text_file.resolve()
    if source.suffix != ".txt" or (args.output is None and source.parent != VPOOL):
        parser.error(f"Metin {VPOOL} içinde bir .txt dosyası olmalı; harici kullanım için --output belirtin")
    try:
        text = source.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError) as exc:
        parser.error(f"Metin okunamadı: {exc}")
    if not text:
        parser.error("Metin boş olamaz")
    # Son bileşeni resolve etmeyin: çıktı sembolik bağlantıları reddedilir.
    target = (args.output if args.output is not None else source.with_suffix(".wav")).absolute()
    if target.suffix != ".wav" or not target.parent.is_dir():
        parser.error("Çıktı mevcut bir dizin içinde .wav dosyası olmalı")
    if target.is_symlink() or (target.exists() and not target.is_file()):
        parser.error("Çıktı sembolik bağlantı veya özel dosya olamaz")
    if target.exists() and source.samefile(target):
        parser.error("Çıktı giriş dosyasının üzerine yazamaz")
    if target.exists() and not args.force:
        parser.error("WAV zaten var; yeniden üretmek için --force kullanın")
    tts = load_engine()
    # Önce aynı dizinde tamamlayın. link(), eşzamanlı oluşturulan bir hedefi de korur.
    with tempfile.NamedTemporaryFile(dir=target.parent, prefix=f".{target.name}.", suffix=".wav", delete=False) as f:
        temporary = Path(f.name)
    try:
        speech = tts.say(text, path=str(temporary), seed=0, sample_rate=48000)
        if args.force:
            os.replace(temporary, target)
        else:
            os.link(temporary, target)
    except OSError as exc:
        parser.error(f"WAV yazılamadı; mevcut hedef korundu: {exc}")
    finally:
        temporary.unlink(missing_ok=True)
    print(f"{target}: {speech.duration:.3f} saniye, {speech.sample_rate} Hz, CPU")


if __name__ == "__main__":
    main()
