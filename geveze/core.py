"""Geveze çekirdeği: motor tanımları, kayıt adlandırma, VPOOL arşivi ve WAV denetimi.

Qt'ye bağlı değildir; arayüz ve testler aynı kuralları buradan kullanır.
"""
from array import array
from dataclasses import dataclass
from datetime import datetime
import os
from pathlib import Path
import re
import sys
import wave

APP_ROOT = Path(__file__).resolve().parent.parent


def find_engine_root(environ=os.environ):
    """Motor kökü: GEVEZE_ENGINE_ROOT, kurulmuş engines/ dizini veya geliştirici düzenindeki üst dizin.

    Geliştirici düzeninde ema/ ve piper/ uygulama klasörünün kardeşleridir. Ortamları
    kurulu olan ilk aday seçilir; hiçbiri kurulu değilse hata iletileri engines/ dizinini gösterir.
    """
    if environ.get("GEVEZE_ENGINE_ROOT"):
        return Path(environ["GEVEZE_ENGINE_ROOT"]).expanduser().absolute()
    for root in (APP_ROOT / "engines", APP_ROOT.parent):
        if all((root / name / ".venv/bin/python").exists() for name in ("ema", "piper")):
            return root
    return APP_ROOT / "engines"


def default_vpool(engine_root, environ=os.environ):
    """Motor kökünün yanında vpool/ varsa o; yoksa kullanıcı veri dizinindeki geveze/vpool."""
    if (engine_root / "vpool").is_dir():
        return engine_root / "vpool"
    data_home = environ.get("XDG_DATA_HOME") or Path.home() / ".local/share"
    return Path(data_home).absolute() / "geveze" / "vpool"


TTS_ROOT = find_engine_root()
DEFAULT_VPOOL = default_vpool(TTS_ROOT)
PREFIX = "geveze_"
NAME_RE = re.compile(rf"^{PREFIX}(\d+)$")
SYNTH_TIMEOUT_MS = 600_000


@dataclass(frozen=True)
class Engine:
    key: str
    python: Path
    script: Path


EMA = Engine("ema", TTS_ROOT / "ema/.venv/bin/python", TTS_ROOT / "ema/synthesize.py")
PIPER = Engine("piper", TTS_ROOT / "piper/.venv/bin/python", TTS_ROOT / "piper/synthesize.py")


@dataclass(frozen=True)
class Voice:
    label: str
    engine: Engine
    voice_id: str | None  # Yalnızca Piper için --voice değeri
    speaker: int | None = None  # Yalnızca çok konuşmacılı modellerde --speaker değeri


TURKISH_VOICE = Voice("EMA Lightning — Türkçe kadın", EMA, None)
ENGLISH_VOICES = (  # İlk eleman Geveze'nin varsayılanıdır.
    Voice("Jenny Dioco — kadın", PIPER, "en_GB-jenny_dioco-medium"),
    Voice("Ryan — erkek", PIPER, "en_US-ryan-high"),
    Voice("HFC Female — kadın", PIPER, "en_US-hfc_female-medium"),
    Voice("Amy — kadın", PIPER, "en_US-amy-medium"),
)
GERMAN_VOICES = (  # İlk eleman varsayılandır.
    Voice("Thorsten — erkek", PIPER, "de_DE-thorsten-high"),
    Voice("Kerstin — kadın", PIPER, "de_DE-kerstin-low"),
)
JAPANESE_VOICES = (  # Aynı modelin iki konuşmacısı; ilk eleman varsayılandır.
    Voice("Hi-Fi Captain — kadın", PIPER, "ja_JP-hi_fi_captain-medium", 0),
    Voice("Hi-Fi Captain — erkek", PIPER, "ja_JP-hi_fi_captain-medium", 1),
)
FRENCH_VOICES = (  # Aynı modelin iki konuşmacısı; ilk eleman varsayılandır.
    Voice("Jessica — kadın", PIPER, "fr_FR-upmc-medium", 0),
    Voice("Pierre — erkek", PIPER, "fr_FR-upmc-medium", 1),
)
SLOVENIAN_VOICE = Voice("Artur — erkek", PIPER, "sl_SI-artur-medium")  # Tek konuşmacı; --speaker yok
LANGUAGES = {"Türkçe": (TURKISH_VOICE,), "English": ENGLISH_VOICES, "Deutsch": GERMAN_VOICES,
             "日本語": JAPANESE_VOICES, "Français": FRENCH_VOICES, "Slovenščina": (SLOVENIAN_VOICE,)}


def synth_command(voice, text_path, wav_path):
    """Motorun kendi yorumlayıcısıyla çalışacak (program, argümanlar) çiftini döndürür."""
    args = ["-I", "-B", str(voice.engine.script), str(text_path), "--output", str(wav_path)]
    if voice.voice_id:
        args += ["--voice", voice.voice_id]
    if voice.speaker is not None:
        args += ["--speaker", str(voice.speaker)]
    return str(voice.engine.python), args


def check_engines():
    """Eksik yorumlayıcı veya betik yollarını döndürür."""
    return [str(p) for e in (EMA, PIPER) for p in (e.python, e.script) if not p.exists()]


def normalize_text(text):
    text = text.strip()
    if not text:
        raise ValueError("Metin boş olamaz.")
    return text


def create_record(vpool, text):
    """Yeni benzersiz kayıt adı ayırır ve metni yazar; (txt, wav) yollarını döndürür.

    TXT dosyası "x" kipiyle oluşturulur, yani var olan hiçbir dosyanın üzerine yazılmaz.
    Aynı temel isimde WAV varsa o numara atlanır. WAV'ı motor betiği --force olmadan
    atomik link ile yayımlar; bu sırada beliren bir hedef de korunur.
    """
    text = normalize_text(text)
    vpool = Path(vpool)
    if not vpool.is_dir():
        raise FileNotFoundError(f"VPOOL dizini bulunamadı: {vpool}")
    number = max((int(m[1]) for p in vpool.iterdir() if (m := NAME_RE.match(p.stem))), default=0)
    while True:
        number += 1
        base = vpool / f"{PREFIX}{number:03d}"
        txt, wav = base.with_suffix(".txt"), base.with_suffix(".wav")
        if wav.exists() or wav.is_symlink():
            continue
        try:
            with txt.open("x", encoding="utf-8") as f:
                f.write(text + "\n")
        except FileExistsError:
            continue
        return txt, wav


def discard_text(txt):
    """Ses üretilemediğinde Geveze'nin az önce oluşturduğu sahipsiz TXT'yi kaldırır."""
    if not txt.with_suffix(".wav").exists():
        txt.unlink(missing_ok=True)


def discard_partial(wav):
    """Durdurulan motorun yarım bıraktığı geçici WAV'ları kaldırır.

    Motor betikleri hedefin yanında ".<hedef>.<rastgele>.wav" adlı geçici dosya açar ve
    kendileri temizler; süreç kill ile durdurulunca bu temizlik çalışmaz. Ad, Geveze'nin
    ayırdığı kayıt adını içerdiği için yalnızca bu üretimin dosyaları eşleşir.
    """
    for path in wav.parent.glob(f".{wav.name}.*.wav"):
        if path.is_file() and not path.is_symlink():
            path.unlink(missing_ok=True)


@dataclass
class Record:
    stem: str
    txt: Path | None
    wav: Path | None
    modified: datetime

    def preview(self, limit=80):
        if not self.txt:
            return "(metin dosyası yok)"
        try:
            text = " ".join(self.txt.read_text(encoding="utf-8").split())
        except (OSError, UnicodeError) as exc:
            return f"(okunamadı: {exc})"
        return text if len(text) <= limit else text[:limit - 1] + "…"


def list_records(vpool):
    """VPOOL'daki TXT/WAV dosyalarını temel isme göre gruplar; en yenisi önce."""
    groups = {}
    for path in Path(vpool).iterdir():
        if path.name.startswith(".") or path.suffix not in (".txt", ".wav") or not path.is_file():
            continue  # Motorların geçici dosyaları ve arşivler listelenmez.
        groups.setdefault(path.stem, {})[path.suffix] = path
    records = [
        Record(stem, files.get(".txt"), files.get(".wav"),
               datetime.fromtimestamp(max(p.stat().st_mtime for p in files.values())))
        for stem, files in groups.items()
    ]
    return sorted(records, key=lambda r: (r.modified, r.stem), reverse=True)


@dataclass
class WavInfo:
    duration: float
    sample_rate: int
    channels: int
    sample_width: int
    frames: int
    peak: int
    rms: float


def inspect_wav(path):
    """WAV'ı tamamen okur; geçersiz veya sessizse ValueError fırlatır."""
    try:
        with wave.open(str(path), "rb") as w:
            params = w.getparams()
            data = w.readframes(params.nframes)
    except (wave.Error, EOFError) as exc:
        raise ValueError(f"WAV okunamadı: {exc}") from exc
    if params.sampwidth != 2:
        raise ValueError(f"Beklenmeyen örnek genişliği: {params.sampwidth}")
    if params.nframes == 0 or len(data) != params.nframes * params.nchannels * 2:
        raise ValueError("WAV verisi eksik veya boş")
    samples = array("h")
    samples.frombytes(data)
    if sys.byteorder == "big":
        samples.byteswap()
    peak = max(abs(s) for s in samples)
    rms = (sum(s * s for s in samples) / len(samples)) ** 0.5
    if peak == 0:
        raise ValueError("WAV tamamen sessiz")
    return WavInfo(params.nframes / params.framerate, params.framerate, params.nchannels,
                   params.sampwidth, params.nframes, peak, rms)


def resolve_vpool(argv=None, environ=os.environ):
    """--vpool DİZİN argümanı, GEVEZE_VPOOL ortam değişkeni veya varsayılan VPOOL.

    Yalnızca varsayılan VPOOL yoksa oluşturulur; açıkça verilen dizin oluşturulmaz.
    """
    argv = list(argv or [])
    if "--vpool" in argv:
        i = argv.index("--vpool")
        if i + 1 >= len(argv):
            raise SystemExit("--vpool bir dizin bekliyor")
        return Path(argv[i + 1]).absolute()
    if environ.get("GEVEZE_VPOOL"):
        return Path(environ["GEVEZE_VPOOL"]).absolute()
    DEFAULT_VPOOL.mkdir(parents=True, exist_ok=True)
    return DEFAULT_VPOOL


def display_path(path):
    """Ev dizinini ~ ile kısaltır; arayüzde kullanıcı adını göstermemek için."""
    try:
        return "~/" + str(Path(path).relative_to(Path.home()))
    except ValueError:
        return str(path)
