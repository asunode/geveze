"""Geveze testleri.

Varsayılan olarak her çalıştırma geveze/test_area/run_<zaman> altında yeni bir VPOOL kullanır.
GEVEZE_REAL_VPOOL=1 verildiğinde gerçek VPOOL testi de çalışır; önceki kayıtların
SHA-256 özetleri öncesi ve sonrası karşılaştırılır.

Çalıştırma: QT_QPA_PLATFORM=offscreen /usr/bin/python3 -B -m unittest -v tests.test_geveze
(Arayüz ortamı setup.sh ile kurulduysa /usr/bin/python3 yerine .venv/bin/python.)
NumPy yalnızca konuşmacı perdesi (F0) ölçümü için kullanılır; yoksa bu ölçüm atlanır.
"""
from datetime import datetime
import hashlib
import os
from pathlib import Path
import time
import unicodedata
import sys
import tempfile
import unittest
import wave

try:
    import numpy as np
except ImportError:
    np = None

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QElapsedTimer, QEventLoop, QTimer
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtWidgets import QApplication

from geveze import core
from geveze.app import MainWindow

GEVEZE_DIR = Path(__file__).resolve().parents[1]
RUN_DIR = GEVEZE_DIR / "test_area" / datetime.now().strftime("run_%Y%m%d_%H%M%S")
TR_TEXT = "Merhaba, ben Geveze. Bu kayıt Türkçe EMA sesiyle üretildi; çalışıyor mu, görelim."
EN_TEXT = "Hello, this is Geveze. This recording was generated locally on the CPU."
DE_TEXT = "Hallo, ich bin Geveze. Dieser Satz enthält Umlaute: schön, Grüße, Mädchen und Straße."
JA_TEXT = "一緒にGoogleマップを見ましょう、ね。"  # Kanji + Hiragana + Latin + Katakana
FR_TEXT = ("Bonjour ! Bienvenue chez ASUNODE. Aujourd'hui, nous testons notre nouvelle voix "
           "française. À bientôt !")
SL_TEXT = ("Pozdravljeni in dobrodošli v ASUNODE! Danes preizkušamo naš sistem za pretvorbo besedila "
           "v govor. Vse deluje lokalno na tem računalniku. Želimo vam lep dan!")
JA_RATE = (2, 20)  # Japonca karakter başına daha uzun konuşur (karakter/sn alt-üst sınırı)

app = QApplication.instance() or QApplication([])


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def snapshot(directory):
    return {p.name: sha256(p) for p in directory.iterdir() if p.is_file()}


def scripts(text):
    """Metindeki yazı sistemlerini Unicode karakter adlarından belirler."""
    found = set()
    for ch in text:
        name = unicodedata.name(ch, "")
        for script in ("CJK UNIFIED IDEOGRAPH", "HIRAGANA", "KATAKANA", "LATIN"):
            if name.startswith(script):
                found.add(script)
    return found


def median_f0(path):
    """Sesli çerçevelerde otokorelasyonla temel frekans (Hz) medyanı."""
    with wave.open(str(path), "rb") as w:
        rate = w.getframerate()
        x = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(np.float64)
    size, hop = 2048, 512
    frames = [x[i:i + size] for i in range(0, len(x) - size, hop)]
    energy = np.array([np.sqrt(np.mean(f * f)) for f in frames])
    lo, hi = int(rate / 400), int(rate / 60)
    f0 = []
    for f, e in zip(frames, energy):
        if e < 0.3 * energy.max():
            continue
        f = f - f.mean()
        ac = np.fft.irfft(np.abs(np.fft.rfft(f, 2 * size)) ** 2)[:size]
        lag = lo + int(np.argmax(ac[lo:hi]))
        if ac[lag] > 0.3 * ac[0]:
            f0.append(rate / lag)
    return float(np.median(f0)), len(f0)


def make_dir(name):
    path = RUN_DIR / name
    path.mkdir(parents=True)
    return path


class CoreTests(unittest.TestCase):
    def test_engines_present(self):
        self.assertEqual(core.check_engines(), [])

    def test_empty_text_rejected(self):
        vpool = make_dir("core_empty")
        for text in ("", "   ", "\n\t \n"):
            with self.assertRaises(ValueError):
                core.create_record(vpool, text)
        self.assertEqual(list(vpool.iterdir()), [])

    def test_unique_names_never_overwrite(self):
        vpool = make_dir("core_collision")
        (vpool / "geveze_001.wav").write_bytes(b"onceki wav")   # Eşi olmayan WAV
        (vpool / "geveze_002.txt").write_text("onceki metin")    # Eşi olmayan TXT
        (vpool / "geveze_007.txt").write_text("ileri numara")
        (vpool / "notlar.txt").write_text("ilgisiz")
        before = snapshot(vpool)
        txt, wav = core.create_record(vpool, "  yeni metin  ")
        self.assertEqual(txt.name, "geveze_008.txt")
        self.assertEqual(wav.name, "geveze_008.wav")
        self.assertFalse(wav.exists())
        self.assertEqual(txt.read_text(encoding="utf-8"), "yeni metin\n")
        self.assertEqual({k: v for k, v in snapshot(vpool).items() if k in before}, before)
        txt2, _ = core.create_record(vpool, "ikinci")
        self.assertEqual(txt2.name, "geveze_009.txt")

    def test_gap_numbers_with_existing_wav_are_skipped(self):
        vpool = make_dir("core_gap")
        # Yalnızca WAV'ı olan bir isim, en büyük numara olsa bile yeniden kullanılmaz.
        (vpool / "geveze_003.wav").write_bytes(b"x")
        txt, _ = core.create_record(vpool, "metin")
        self.assertEqual(txt.name, "geveze_004.txt")

    def test_discard_keeps_completed_pairs(self):
        vpool = make_dir("core_discard")
        txt, wav = core.create_record(vpool, "a")
        wav.write_bytes(b"tamamlanmis")
        core.discard_text(txt)
        self.assertTrue(txt.exists())
        txt2, _ = core.create_record(vpool, "b")
        core.discard_text(txt2)
        self.assertFalse(txt2.exists())

    def test_command_uses_engine_venv_and_voice(self):
        program, args = core.synth_command(core.ENGLISH_VOICES[1], "/a.txt", "/a.wav")
        self.assertEqual(program, str(core.TTS_ROOT / "piper/.venv/bin/python"))
        self.assertEqual(args[-4:], ["--output", "/a.wav", "--voice", "en_US-ryan-high"])
        program, args = core.synth_command(core.TURKISH_VOICE, "/a.txt", "/a.wav")
        self.assertEqual(program, str(core.TTS_ROOT / "ema/.venv/bin/python"))
        self.assertNotIn("--voice", args)
        self.assertEqual(core.ENGLISH_VOICES[0].voice_id, "en_GB-jenny_dioco-medium")
        program, args = core.synth_command(core.GERMAN_VOICES[1], "/a.txt", "/a.wav")
        self.assertEqual(program, str(core.TTS_ROOT / "piper/.venv/bin/python"))
        self.assertEqual(args[-2:], ["--voice", "de_DE-kerstin-low"])

    def test_japanese_speaker_arguments(self):
        for voice, speaker in zip(core.JAPANESE_VOICES, ("0", "1")):
            _, args = core.synth_command(voice, "/a.txt", "/a.wav")
            self.assertEqual(args[-4:], ["--voice", "ja_JP-hi_fi_captain-medium", "--speaker", speaker])
        for voice, speaker in zip(core.FRENCH_VOICES, ("0", "1")):
            _, args = core.synth_command(voice, "/a.txt", "/a.wav")
            self.assertEqual(args[-4:], ["--voice", "fr_FR-upmc-medium", "--speaker", speaker])
        for language, voices in core.LANGUAGES.items():
            if language not in ("日本語", "Français"):
                for voice in voices:
                    self.assertNotIn("--speaker", core.synth_command(voice, "/a.txt", "/a.wav")[1])

    def test_unicode_text_saved_byte_exact(self):
        vpool = make_dir("core_unicode")
        self.assertEqual(scripts(JA_TEXT), {"CJK UNIFIED IDEOGRAPH", "HIRAGANA", "KATAKANA", "LATIN"})
        decomposed = unicodedata.normalize("NFD", "がぎぐ ガギグ")  # Geveze normalleştirme yapmamalı
        for text in (JA_TEXT, FR_TEXT, SL_TEXT, "čšž ČŠŽ žaba", decomposed, "日本語\n第二行　全角スペース含む"):
            txt, _ = core.create_record(vpool, text)
            self.assertEqual(txt.read_bytes(), (text.strip() + "\n").encode("utf-8"))

    def test_engine_root_and_default_vpool(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            env = {"GEVEZE_ENGINE_ROOT": str(tmp / "motor kökü ğüş"), "XDG_DATA_HOME": str(tmp / "veri")}
            root = core.find_engine_root(env)
            self.assertEqual(root, tmp / "motor kökü ğüş")
            # Motorun yanında vpool/ yoksa kayıtlar kullanıcı veri dizinine gider
            self.assertEqual(core.default_vpool(root, env), tmp / "veri" / "geveze" / "vpool")
            (root / "vpool").mkdir(parents=True)
            self.assertEqual(core.default_vpool(root, env), root / "vpool")
            self.assertEqual(core.resolve_vpool(["--vpool", str(tmp / "x")], env), tmp / "x")
            self.assertEqual(core.resolve_vpool([], {"GEVEZE_VPOOL": str(tmp / "y")}), tmp / "y")
            self.assertFalse((tmp / "x").exists() or (tmp / "y").exists())  # Açık dizin oluşturulmaz
        self.assertEqual(core.display_path(Path.home() / "a b" / "vpool"), "~/a b/vpool")
        self.assertEqual(core.display_path("/srv/vpool"), "/srv/vpool")

    def test_languages_and_voices(self):
        self.assertEqual(list(core.LANGUAGES),
                         ["Türkçe", "English", "Deutsch", "日本語", "Français", "Slovenščina"])
        self.assertEqual([len(v) for v in core.LANGUAGES.values()], [1, 4, 2, 2, 2, 1])
        voices = [v for vs in core.LANGUAGES.values() for v in vs]
        self.assertEqual(len(voices), 12)
        program, args = core.synth_command(core.SLOVENIAN_VOICE, "/a.txt", "/a.wav")
        self.assertEqual(program, str(core.TTS_ROOT / "piper/.venv/bin/python"))
        self.assertEqual(args[-4:], ["--output", "/a.wav", "--voice", "sl_SI-artur-medium"])
        self.assertTrue({"č", "š", "Ž"} <= set(SL_TEXT))  # Verilen metinde küçük ž yok
        self.assertEqual([v.speaker for v in core.JAPANESE_VOICES], [0, 1])
        self.assertEqual([v.speaker for v in core.FRENCH_VOICES], [0, 1])
        self.assertEqual([v.voice_id for v in core.GERMAN_VOICES],
                         ["de_DE-thorsten-high", "de_DE-kerstin-low"])
        # Her Piper kimliği motor betiğinin VOICES tablosunda tanımlı olmalı
        piper_source = core.PIPER.script.read_text(encoding="utf-8")
        for v in voices:
            if v.voice_id:
                self.assertIn(f'"{v.voice_id}":', piper_source)


class GuiTestCase(unittest.TestCase):
    vpool = None

    def setUp(self):
        self.window = MainWindow(self.vpool)
        self.window.audio_output.setVolume(0)  # Test sırasında hoparlörden ses çıkmasın
        self.window.show()

    def tearDown(self):
        self.window.player.stop()
        self.window.close()
        self.window.deleteLater()
        app.processEvents()

    def generate(self, language, voice_index, text, timeout=300):
        """Arayüz üzerinden üretir; bu sırada olay döngüsünün tepki süresini ölçer."""
        w = self.window
        w.language.setCurrentText(language)
        w.voice.setCurrentIndex(voice_index)
        w.text_edit.setPlainText(text)
        w.generate_button.click()
        self.assertIsNotNone(w.process, w.status.text())
        self.assertFalse(w.generate_button.isEnabled())
        self.assertIn("üretiliyor", w.status.text())
        ticks, gaps, clock, last = 0, [], QElapsedTimer(), [0]
        clock.start()

        def tick():
            nonlocal ticks
            ticks += 1
            gaps.append(clock.elapsed() - last[0])
            last[0] = clock.elapsed()

        timer = QTimer()
        timer.timeout.connect(tick)
        timer.start(20)
        deadline = time.monotonic() + timeout
        while w.process is not None and time.monotonic() < deadline:
            app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 50)
        timer.stop()
        self.assertIsNone(w.process, "Ses üretimi zaman aşımına uğradı")
        return {"seconds": clock.elapsed() / 1000, "ticks": ticks, "max_gap_ms": max(gaps, default=0)}

    def newest(self):
        return max(core.list_records(self.vpool), key=lambda r: int(r.stem.split("_")[1])
                   if core.NAME_RE.match(r.stem) else -1)

    def assert_record(self, text, sample_rate, voice_id=None, rate=(5, 40), speaker=None):
        record = self.newest()
        self.assertIsNotNone(record.txt)
        self.assertIsNotNone(record.wav)
        self.assertEqual(record.txt.stem, record.wav.stem)
        self.assertEqual(record.txt.read_bytes(), (text + "\n").encode("utf-8"))
        info = core.inspect_wav(record.wav)
        self.assertEqual(info.sample_rate, sample_rate)
        self.assertEqual(info.channels, 1)
        self.assertEqual(info.sample_width, 2)
        # Metin uzunluğuna göre makul süre ve gerçek ses enerjisi
        self.assertGreater(info.duration, len(text) / rate[1])
        self.assertLess(info.duration, len(text) / rate[0])
        self.assertGreater(info.peak, 1000)
        self.assertGreater(info.rms, 100)
        self.assertIn(str(record.wav), self.window.last_log)
        if voice_id:
            self.assertIn(f"voice={voice_id}", self.window.last_log)
        if speaker is not None:
            self.assertIn(f"speaker={speaker}", self.window.last_log)
        self.assertIn(f"Kaydedildi: {record.wav.name}", self.window.status.text())
        current = self.window.archive.currentItem()
        self.assertEqual(current.text(0), record.stem)
        return record, info

    def assert_plays(self):
        """Seçili WAV'ı QMediaPlayer ile oynatır; konumun ilerlediğini doğrular."""
        w = self.window
        self.assertTrue(w.play_button.isEnabled())
        if w.player.playbackState() != QMediaPlayer.PlaybackState.PlayingState:
            w.play_button.click()
        deadline = time.monotonic() + 10
        while w.player.position() < 500 and time.monotonic() < deadline:
            app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 50)
        self.assertEqual(w.player.error(), QMediaPlayer.Error.NoError, w.player.errorString())
        self.assertGreaterEqual(w.player.position(), 500)
        self.assertGreater(w.player.duration(), 0)
        w.player.stop()


class GuiTestAreaTests(GuiTestCase):
    @classmethod
    def setUpClass(cls):
        cls.vpool = make_dir("vpool")
        (cls.vpool / "geveze_001.wav").write_bytes(b"korunacak eski wav")
        (cls.vpool / "geveze_002.txt").write_text("korunacak eski metin", encoding="utf-8")
        cls.protected = snapshot(cls.vpool)
        cls.results = {}

    @classmethod
    def tearDownClass(cls):
        lines = [f"{k}: {v}" for k, v in sorted(cls.results.items())]
        (RUN_DIR / "results.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")

    def test_1_turkish_ema(self):
        stats = self.generate("Türkçe", 0, TR_TEXT)
        record, info = self.assert_record(TR_TEXT, 48000)
        self.assertEqual(record.stem, "geveze_003")  # 001 ve 002 çakışmadan atlandı
        self.results["tr_ema"] = (record.stem, round(info.duration, 3), info.sample_rate, stats)
        self.assert_responsive(stats)
        self.assert_plays()

    def test_2_english_jenny_default(self):
        self.window.language.setCurrentText("English")
        self.assertEqual(self.window.voice.currentText(), "Jenny Dioco — kadın")
        stats = self.generate("English", 0, EN_TEXT)
        record, info = self.assert_record(EN_TEXT, 22050, "en_GB-jenny_dioco-medium")
        self.results["en_jenny"] = (record.stem, round(info.duration, 3), info.sample_rate, stats)
        self.assert_responsive(stats)

    def test_3_english_ryan(self):
        stats = self.generate("English", 1, EN_TEXT)
        record, info = self.assert_record(EN_TEXT, 22050, "en_US-ryan-high")
        self.results["en_ryan"] = (record.stem, round(info.duration, 3), info.sample_rate, stats)
        jenny = [r for r in core.list_records(self.vpool) if r.stem == self.results["en_jenny"][0]][0]
        self.assertNotEqual(sha256(jenny.wav), sha256(record.wav))  # Farklı ses gerçekten seçildi
        self.assert_responsive(stats)
        self.assert_plays()

    def test_3b_german_thorsten(self):
        w = self.window
        w.language.setCurrentText("Deutsch")
        self.assertEqual([w.voice.itemText(i) for i in range(w.voice.count())],
                         ["Thorsten — erkek", "Kerstin — kadın"])
        self.assertEqual(w.voice.currentText(), "Thorsten — erkek")
        self.assertTrue(w.voice.isEnabled())
        stats = self.generate("Deutsch", 0, DE_TEXT)
        record, info = self.assert_record(DE_TEXT, 22050, "de_DE-thorsten-high")
        self.results["de_thorsten"] = (record.stem, round(info.duration, 3), info.sample_rate, stats)
        self.assert_responsive(stats)
        self.assert_plays()

    def test_3c_german_kerstin(self):
        stats = self.generate("Deutsch", 1, DE_TEXT)
        record, info = self.assert_record(DE_TEXT, 16000, "de_DE-kerstin-low")
        self.results["de_kerstin"] = (record.stem, round(info.duration, 3), info.sample_rate, stats)
        self.assertNotIn("Missing phoneme", self.window.last_log)
        self.assert_responsive(stats)
        self.assert_plays()
        # Thorsten kaydı arşivden seçilip yeniden oynatılır
        w = self.window
        items = [w.archive.topLevelItem(i) for i in range(w.archive.topLevelItemCount())]
        w.archive.setCurrentItem(next(i for i in items if i.text(0) == self.results["de_thorsten"][0]))
        self.assert_plays()

    def test_3d_language_switch_keeps_voice_lists(self):
        w = self.window
        w.language.setCurrentText("English")
        self.assertEqual(w.voice.count(), 4)
        self.assertEqual(w.voice.currentText(), "Jenny Dioco — kadın")
        w.language.setCurrentText("Türkçe")
        self.assertEqual(w.voice.count(), 1)
        self.assertFalse(w.voice.isEnabled())
        w.language.setCurrentText("Deutsch")
        self.assertEqual(w.voice.currentText(), "Thorsten — erkek")
        w.language.setCurrentText("日本語")
        self.assertEqual(w.voice.count(), 2)
        self.assertEqual(w.voice.currentText(), "Hi-Fi Captain — kadın")
        w.language.setCurrentText("Français")
        self.assertEqual(w.voice.count(), 2)
        self.assertEqual(w.voice.currentText(), "Jessica — kadın")
        w.language.setCurrentText("Slovenščina")
        self.assertEqual(w.voice.count(), 1)
        self.assertEqual(w.voice.currentText(), "Artur — erkek")
        # Geri dönüşte çok konuşmacılı seçimler aynı kalır
        w.language.setCurrentText("日本語")
        self.assertEqual([w.voice.itemData(i).speaker for i in range(2)], [0, 1])
        w.language.setCurrentText("Français")
        self.assertEqual([w.voice.itemData(i).speaker for i in range(2)], [0, 1])

    def test_3e_japanese_female(self):
        w = self.window
        w.language.setCurrentText("日本語")
        self.assertEqual([w.voice.itemText(i) for i in range(w.voice.count())],
                         ["Hi-Fi Captain — kadın", "Hi-Fi Captain — erkek"])
        self.assertEqual(w.voice.currentData().speaker, 0)
        stats = self.generate("日本語", 0, JA_TEXT)
        self.assertEqual(w.text_edit.toPlainText(), JA_TEXT)  # Giriş alanı metni değiştirmedi
        record, info = self.assert_record(JA_TEXT, 22050, "ja_JP-hi_fi_captain-medium", JA_RATE, 0)
        self.assertEqual(w.archive.currentItem().text(3), JA_TEXT)  # Arşivde aynen görünür
        self.assertNotIn("Missing phoneme", w.last_log)
        self.results["ja_female"] = (record.stem, round(info.duration, 3), info.sample_rate, stats)
        self.assert_responsive(stats)
        self.assert_plays()

    def test_3f_japanese_male(self):
        stats = self.generate("日本語", 1, JA_TEXT)
        record, info = self.assert_record(JA_TEXT, 22050, "ja_JP-hi_fi_captain-medium", JA_RATE, 1)
        self.assertNotIn("Missing phoneme", self.window.last_log)
        self.results["ja_male"] = (record.stem, round(info.duration, 3), info.sample_rate, stats)
        self.assert_responsive(stats)
        self.assert_plays()
        female = self.vpool / f"{self.results['ja_female'][0]}.wav"
        self.assertNotEqual(sha256(female), sha256(record.wav))
        # Konuşmacı farkı fiziksel olarak da ölçülür: erkek sesin perdesi belirgin şekilde düşük
        if np is not None:
            f0_female, n_female = median_f0(female)
            f0_male, n_male = median_f0(record.wav)
            self.results["ja_f0_hz"] = (round(f0_female, 1), round(f0_male, 1), n_female, n_male)
            self.assertGreater(min(n_female, n_male), 10)
            self.assertLess(f0_male, f0_female * 0.8)
        w = self.window
        items = [w.archive.topLevelItem(i) for i in range(w.archive.topLevelItemCount())]
        w.archive.setCurrentItem(next(i for i in items if i.text(0) == self.results["ja_female"][0]))
        self.assert_plays()

    def test_3g_french_jessica(self):
        w = self.window
        w.language.setCurrentText("Français")
        self.assertEqual([w.voice.itemText(i) for i in range(w.voice.count())],
                         ["Jessica — kadın", "Pierre — erkek"])
        self.assertEqual(w.voice.currentData().speaker, 0)
        stats = self.generate("Français", 0, FR_TEXT)
        self.assertEqual(w.text_edit.toPlainText(), FR_TEXT)
        record, info = self.assert_record(FR_TEXT, 22050, "fr_FR-upmc-medium", speaker=0)
        self.assertEqual(w.archive.currentItem().toolTip(3), FR_TEXT)  # Önizleme kesik, ipucu tam
        self.assertNotIn("Missing phoneme", w.last_log)
        self.results["fr_jessica"] = (record.stem, round(info.duration, 3), info.sample_rate, stats)
        self.assert_responsive(stats)
        self.assert_plays()

    def test_3h_french_pierre(self):
        stats = self.generate("Français", 1, FR_TEXT)
        record, info = self.assert_record(FR_TEXT, 22050, "fr_FR-upmc-medium", speaker=1)
        self.assertNotIn("Missing phoneme", self.window.last_log)
        self.results["fr_pierre"] = (record.stem, round(info.duration, 3), info.sample_rate, stats)
        self.assert_responsive(stats)
        self.assert_plays()
        jessica = self.vpool / f"{self.results['fr_jessica'][0]}.wav"
        self.assertNotEqual(sha256(jessica), sha256(record.wav))
        if np is not None:
            f0_jessica, n_jessica = median_f0(jessica)
            f0_pierre, n_pierre = median_f0(record.wav)
            self.results["fr_f0_hz"] = (round(f0_jessica, 1), round(f0_pierre, 1), n_jessica, n_pierre)
            self.assertGreater(min(n_jessica, n_pierre), 10)
            self.assertLess(f0_pierre, f0_jessica * 0.8)
        w = self.window
        items = [w.archive.topLevelItem(i) for i in range(w.archive.topLevelItemCount())]
        w.archive.setCurrentItem(next(i for i in items if i.text(0) == self.results["fr_jessica"][0]))
        self.assert_plays()

    def test_3i_slovenian_artur(self):
        w = self.window
        w.language.setCurrentText("Slovenščina")
        self.assertEqual(w.language.currentText(), "Slovenščina")
        self.assertEqual([w.voice.itemText(i) for i in range(w.voice.count())], ["Artur — erkek"])
        self.assertFalse(w.voice.isEnabled())  # Tek ses: Türkçedeki gibi pasif liste
        self.assertNotIn("--speaker", core.synth_command(w.voice.currentData(), "/a.txt", "/a.wav")[1])
        # Çakışma koruması: sıradaki numaranın WAV'ı önceden var; Geveze onu atlamalı
        numbers = [int(m[1]) for p in self.vpool.iterdir() if (m := core.NAME_RE.match(p.stem))]
        blocked = self.vpool / f"geveze_{max(numbers) + 1:03d}.wav"
        blocked.write_bytes(b"onceden var olan wav")
        stats = self.generate("Slovenščina", 0, SL_TEXT)
        self.assertEqual(w.text_edit.toPlainText(), SL_TEXT)
        record, info = self.assert_record(SL_TEXT, 22050, "sl_SI-artur-medium", speaker=0)
        self.assertEqual(record.stem, f"geveze_{max(numbers) + 2:03d}")
        self.assertEqual(blocked.read_bytes(), b"onceden var olan wav")
        self.assertFalse(blocked.with_suffix(".txt").exists())
        self.assertEqual(w.archive.currentItem().toolTip(3), SL_TEXT)
        self.assertTrue(w.archive.currentItem().text(3).startswith("Pozdravljeni in dobrodošli"))
        self.assertNotIn("Missing phoneme", w.last_log)
        self.results["sl_artur"] = (record.stem, round(info.duration, 3), info.sample_rate, stats)
        self.assert_responsive(stats)
        self.assert_plays()
        # Arşivden yeniden seçip oynatma
        w.archive.setCurrentItem(None)
        items = [w.archive.topLevelItem(i) for i in range(w.archive.topLevelItemCount())]
        w.archive.setCurrentItem(next(i for i in items if i.text(0) == record.stem))
        self.assert_plays()

    def test_4_play_existing_from_archive(self):
        w = self.window
        items = [w.archive.topLevelItem(i) for i in range(w.archive.topLevelItemCount())]
        target = next(i for i in items if i.text(0) == "geveze_003")
        w.archive.setCurrentItem(target)
        self.assertIn("geveze_003.wav", w.now_playing.text())
        self.assert_plays()
        # Eşsiz eski kayıtlar listelenir ama WAV'ı olmayan oynatılamaz
        w.archive.setCurrentItem(next(i for i in items if i.text(0) == "geveze_002"))
        self.assertFalse(w.play_button.isEnabled())
        self.assertEqual(next(i for i in items if i.text(0) == "geveze_001").text(2), "geçersiz")

    def test_5_empty_text(self):
        before = snapshot(self.vpool)
        self.window.text_edit.setPlainText("   \n  ")
        self.window.generate_button.click()
        self.assertIsNone(self.window.process)
        self.assertEqual(self.window.status.text(), "Metin boş olamaz.")
        self.assertEqual(snapshot(self.vpool), before)

    def test_6_engine_failure_is_reported_and_cleaned(self):
        before = snapshot(self.vpool)
        original = core.synth_command
        core.synth_command = lambda v, t, o: (sys.executable, ["-c", "import sys; sys.exit('motor hatası: test')"])
        try:
            self.generate("English", 0, "failure path")
        finally:
            core.synth_command = original
        self.assertIn("Ses üretilemedi (çıkış kodu 1)", self.window.status.text())
        self.assertIn("motor hatası: test", self.window.status.text())
        self.assertEqual(snapshot(self.vpool), before)  # Sahipsiz TXT bırakılmadı
        self.assertTrue(self.window.generate_button.isEnabled())

    def test_7_cancel(self):
        before = snapshot(self.vpool)
        original = core.synth_command
        core.synth_command = lambda v, t, o: ("/usr/bin/sleep", ["30"])
        try:
            QTimer.singleShot(300, self.window.cancel_button.click)
            stats = self.generate("English", 0, "cancel path", timeout=10)
        finally:
            core.synth_command = original
        self.assertLess(stats["seconds"], 5)
        self.assertIn("iptal", self.window.status.text())
        self.assertEqual(snapshot(self.vpool), before)

    def test_7b_cancel_removes_engine_temp_file(self):
        before = snapshot(self.vpool)
        original = core.synth_command
        # Motor gibi davranır: hedefin yanında geçici WAV açar, sonra çalışmaya devam eder
        script = ("import pathlib, sys, time; o = pathlib.Path(sys.argv[1]); "
                  "(o.parent / f'.{o.name}.abc123.wav').write_bytes(b'yarim'); time.sleep(30)")
        core.synth_command = lambda v, t, o: (sys.executable, ["-c", script, str(o)])
        unrelated = self.vpool / ".baska_kayit.wav.xyz.wav"
        unrelated.write_bytes(b"ilgisiz gecici dosya")
        try:
            QTimer.singleShot(800, self.window.cancel_button.click)
            self.generate("English", 0, "cancel with temp file", timeout=10)
        finally:
            core.synth_command = original
        self.assertIn("iptal", self.window.status.text())
        self.assertTrue(unrelated.exists())  # Başka üretimin geçici dosyasına dokunulmaz
        unrelated.unlink()
        self.assertEqual(snapshot(self.vpool), before)
        self.assertEqual([p.name for p in self.vpool.iterdir() if p.name.startswith(".")], [])

    def test_8_protected_files_unchanged(self):
        now = snapshot(self.vpool)
        self.assertEqual({k: now[k] for k in self.protected}, self.protected)

    def assert_responsive(self, stats):
        # 20 ms zamanlayıcı üretim boyunca çalışmaya devam etmeli; en uzun boşluk < 250 ms
        self.assertGreater(stats["ticks"], stats["seconds"] * 1000 / 20 * 0.5)
        self.assertLess(stats["max_gap_ms"], 250)


@unittest.skipUnless(os.environ.get("GEVEZE_REAL_VPOOL") == "1", "GEVEZE_REAL_VPOOL=1 gerekli")
class GuiRealVpoolTests(GuiTestCase):
    vpool = core.DEFAULT_VPOOL

    def test_real_vpool_tr_and_en(self):
        before = snapshot(self.vpool)
        self.generate("Türkçe", 0, TR_TEXT)
        tr, _ = self.assert_record(TR_TEXT, 48000)
        self.assert_plays()
        self.generate("English", 0, EN_TEXT)
        en, _ = self.assert_record(EN_TEXT, 22050, "en_GB-jenny_dioco-medium")
        self.assert_plays()
        now = snapshot(self.vpool)
        self.assertEqual({k: now[k] for k in before}, before)  # Önceki kayıtlar aynen duruyor
        self.assertEqual(set(now) - set(before), {f"{tr.stem}.txt", f"{tr.stem}.wav",
                                                  f"{en.stem}.txt", f"{en.stem}.wav"})
        print(f"\nGerçek VPOOL kayıtları: {tr.stem}, {en.stem}")

    def test_real_vpool_german(self):
        before = snapshot(self.vpool)
        self.generate("Deutsch", 0, DE_TEXT)
        th, _ = self.assert_record(DE_TEXT, 22050, "de_DE-thorsten-high")
        self.assert_plays()
        self.generate("Deutsch", 1, DE_TEXT)
        ke, _ = self.assert_record(DE_TEXT, 16000, "de_DE-kerstin-low")
        self.assert_plays()
        now = snapshot(self.vpool)
        self.assertEqual({k: now[k] for k in before}, before)
        self.assertEqual(set(now) - set(before), {f"{th.stem}.txt", f"{th.stem}.wav",
                                                  f"{ke.stem}.txt", f"{ke.stem}.wav"})
        print(f"\nGerçek VPOOL Almanca kayıtları: {th.stem}, {ke.stem}")

    def test_real_vpool_japanese(self):
        before = snapshot(self.vpool)
        stems = []
        for index in (0, 1):
            self.generate("日本語", index, JA_TEXT)
            record, info = self.assert_record(JA_TEXT, 22050, "ja_JP-hi_fi_captain-medium", JA_RATE, index)
            self.assert_plays()
            stems.append(record.stem)
            print(f"\n{record.stem}: speaker={index}, {info.duration:.3f} sn, {info.sample_rate} Hz, "
                  + (f"F0≈{median_f0(record.wav)[0]:.0f} Hz" if np is not None else "F0 ölçülmedi"))
        now = snapshot(self.vpool)
        self.assertEqual({k: now[k] for k in before}, before)
        self.assertEqual(set(now) - set(before), {f"{s}.{e}" for s in stems for e in ("txt", "wav")})
        w = self.window
        w.refresh_archive()
        shown = {w.archive.topLevelItem(i).text(0): w.archive.topLevelItem(i).text(3)
                 for i in range(w.archive.topLevelItemCount())}
        self.assertEqual([shown[s] for s in stems], [JA_TEXT, JA_TEXT])

    def test_real_vpool_slovenian(self):
        before = snapshot(self.vpool)
        self.generate("Slovenščina", 0, SL_TEXT)
        record, info = self.assert_record(SL_TEXT, 22050, "sl_SI-artur-medium", speaker=0)
        self.assert_plays()
        now = snapshot(self.vpool)
        self.assertEqual({k: now[k] for k in before}, before)
        self.assertEqual(set(now) - set(before), {f"{record.stem}.txt", f"{record.stem}.wav"})
        w = self.window
        w.refresh_archive()
        item = next(w.archive.topLevelItem(i) for i in range(w.archive.topLevelItemCount())
                    if w.archive.topLevelItem(i).text(0) == record.stem)
        self.assertEqual(item.toolTip(3), SL_TEXT)
        w.archive.setCurrentItem(item)
        self.assert_plays()
        print(f"\n{record.stem}: {info.duration:.3f} sn, {info.sample_rate} Hz, tepe {info.peak}, "
              f"RMS {info.rms:.0f}")

    def test_real_vpool_french(self):
        before = snapshot(self.vpool)
        stems = []
        for index in (0, 1):
            self.generate("Français", index, FR_TEXT)
            record, info = self.assert_record(FR_TEXT, 22050, "fr_FR-upmc-medium", speaker=index)
            self.assert_plays()
            stems.append(record.stem)
            print(f"\n{record.stem}: speaker={index}, {info.duration:.3f} sn, {info.sample_rate} Hz, "
                  + (f"F0≈{median_f0(record.wav)[0]:.0f} Hz" if np is not None else "F0 ölçülmedi"))
        now = snapshot(self.vpool)
        self.assertEqual({k: now[k] for k in before}, before)
        self.assertEqual(set(now) - set(before), {f"{s}.{e}" for s in stems for e in ("txt", "wav")})
        w = self.window
        w.refresh_archive()
        tips = {w.archive.topLevelItem(i).text(0): w.archive.topLevelItem(i).toolTip(3)
                for i in range(w.archive.topLevelItemCount())}
        self.assertEqual([tips[s] for s in stems], [FR_TEXT, FR_TEXT])


if __name__ == "__main__":
    unittest.main()
