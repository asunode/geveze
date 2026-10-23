"""UTF-8 metinden yerel Piper ile WAV üretir; ses için --voice, harici yollar için --output kullanın."""
import argparse
import json
import os
from pathlib import Path
import tempfile
import wave

ENGINE_DIR = Path(__file__).resolve().parent
VPOOL = ENGINE_DIR.parent / "vpool"
DEFAULT_VOICE = "en_US-amy-medium"
VOICES = {
    "en_GB-jenny_dioco-medium": ENGINE_DIR / "models/en_GB-jenny_dioco-medium/en_GB-jenny_dioco-medium.onnx",
    "en_US-hfc_female-medium": ENGINE_DIR / "models/en_US-hfc_female-medium/en_US-hfc_female-medium.onnx",
    "en_US-amy-medium": ENGINE_DIR / "models/en_US-amy-medium.onnx",
    "en_US-ryan-high": ENGINE_DIR / "models/en_US-ryan-high/en_US-ryan-high.onnx",
    "de_DE-thorsten-high": ENGINE_DIR / "models/de_DE-thorsten-high/de_DE-thorsten-high.onnx",
    "de_DE-kerstin-low": ENGINE_DIR / "models/de_DE-kerstin-low/de_DE-kerstin-low.onnx",
    "ja_JP-hi_fi_captain-medium": ENGINE_DIR / "models/ja_JP-hi_fi_captain-medium/ja_JP-hi_fi_captain-medium.onnx",
    "fr_FR-upmc-medium": ENGINE_DIR / "models/fr_FR-upmc-medium/fr_FR-upmc-medium.onnx",
    "sl_SI-artur-medium": ENGINE_DIR / "models/sl_SI-artur-medium/sl_SI-artur-medium.onnx",
}
MODEL = VOICES[DEFAULT_VOICE]  # Önceki Python çağıranları için Amy yolu korunur.


def load_engine(voice_id=DEFAULT_VOICE):
    """Uygulama başına bir kez çağırın; dönen PiperVoice nesnesini yeniden kullanın."""
    if voice_id not in VOICES:
        raise ValueError(f"Tanımsız ses kimliği: {voice_id}")
    from piper import PiperVoice

    voice = PiperVoice.load(str(VOICES[voice_id]), use_cuda=False)
    if voice_id == "de_DE-kerstin-low":
        # Eski Kerstin tablosu ç bekler; mevcut espeak bunu c + U+0327 üretebilir.
        # Yalnızca yeni ses için kanonik Unicode eşdeğerini kullanın.
        import unicodedata

        phonemize = voice.phonemize

        def normalized_phonemes(text):
            return [list(unicodedata.normalize("NFC", "".join(sentence))) for sentence in phonemize(text)]

        voice.phonemize = normalized_phonemes
    return voice


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("text_file", type=Path)
    parser.add_argument("--voice", choices=tuple(VOICES), default=DEFAULT_VOICE,
                        help="Yerel ses modeli kimliği (varsayılan: en_US-amy-medium)")
    parser.add_argument("--speaker", type=int, help="Model içindeki konuşmacı kimliği (Japonca/Fransızca: 0 kadın, 1 erkek)")
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
    try:
        config = json.loads(Path(str(VOICES[args.voice]) + ".json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        parser.error(f"Model yapılandırması okunamadı: {exc}")
    speaker_count = int(config.get("num_speakers", 1))
    if args.speaker is not None and not 0 <= args.speaker < speaker_count:
        parser.error(f"Geçersiz konuşmacı kimliği {args.speaker}: {args.voice} için geçerli aralık 0..{speaker_count - 1}")
    speaker_id = args.speaker if args.speaker is not None else config.get("default_speaker_id", 0)
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
    voice = load_engine(args.voice)
    syn_config = None
    if args.speaker is not None:
        from piper import SynthesisConfig

        syn_config = SynthesisConfig(speaker_id=args.speaker)
    with tempfile.NamedTemporaryFile(dir=target.parent, prefix=f".{target.name}.", suffix=".wav", delete=False) as f:
        temporary = Path(f.name)
    try:
        with wave.open(str(temporary), "wb") as output:
            voice.synthesize_wav(text, output, syn_config=syn_config)
        if args.force:
            os.replace(temporary, target)
        else:
            os.link(temporary, target)
    except OSError as exc:
        parser.error(f"WAV yazılamadı; mevcut hedef korundu: {exc}")
    finally:
        temporary.unlink(missing_ok=True)
    with wave.open(str(target), "rb") as audio:
        print(f"{target}: {audio.getnframes()/audio.getframerate():.3f} saniye, "
              f"{audio.getframerate()} Hz, CPU ({voice.session.get_providers()}), voice={args.voice}, speaker={speaker_id}")


if __name__ == "__main__":
    main()
