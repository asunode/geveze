"""Geveze masaüstü arayüzü (PySide6)."""
import sys

from PySide6.QtCore import QProcess, Qt, QTimer, QUrl
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QApplication, QComboBox, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QPlainTextEdit,
    QPushButton, QSlider, QSplitter, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from . import core


def fmt_time(ms):
    s = max(0, ms) // 1000
    return f"{s // 60}:{s % 60:02d}"


class MainWindow(QMainWindow):
    def __init__(self, vpool):
        super().__init__()
        self.vpool = vpool
        self.process = None
        self.pending = None  # Üretimi süren kaydın (txt, wav, ses) bilgisi
        self.last_log = ""  # Son motor çıktısı (stdout+stderr)
        self.setWindowTitle("Geveze")
        self.resize(900, 640)

        # Metin ve ses seçimi
        self.text_edit = QPlainTextEdit()
        self.text_edit.setPlaceholderText("Seslendirilecek metni buraya yazın…")
        self.language = QComboBox()
        self.language.addItems(core.LANGUAGES)
        self.voice = QComboBox()
        self.language.currentTextChanged.connect(self.update_voices)
        self.generate_button = QPushButton("Ses üret")
        self.generate_button.clicked.connect(self.generate)
        self.cancel_button = QPushButton("İptal")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel)
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        options = QHBoxLayout()
        options.addWidget(QLabel("Dil:"))
        options.addWidget(self.language)
        options.addWidget(QLabel("Ses:"))
        options.addWidget(self.voice, 1)
        options.addWidget(self.generate_button)
        options.addWidget(self.cancel_button)

        # Oynatıcı
        self.audio_output = QAudioOutput()
        self.player = QMediaPlayer()
        self.player.setAudioOutput(self.audio_output)
        self.now_playing = QLabel("Seçili kayıt yok")
        self.play_button = QPushButton("Oynat")
        self.play_button.setEnabled(False)
        self.play_button.clicked.connect(self.toggle_play)
        self.stop_button = QPushButton("Durdur")
        self.stop_button.clicked.connect(self.player.stop)
        self.position = QSlider(Qt.Orientation.Horizontal)
        self.position.sliderMoved.connect(self.player.setPosition)
        self.time_label = QLabel("0:00 / 0:00")
        self.player.durationChanged.connect(self.on_duration)
        self.player.positionChanged.connect(self.on_position)
        self.player.playbackStateChanged.connect(self.on_playback_state)
        self.player.errorOccurred.connect(
            lambda _e, msg: self.show_error(f"Oynatma hatası: {msg}"))

        controls = QHBoxLayout()
        controls.addWidget(self.play_button)
        controls.addWidget(self.stop_button)
        controls.addWidget(self.position, 1)
        controls.addWidget(self.time_label)

        # Arşiv
        self.archive = QTreeWidget()
        self.archive.setHeaderLabels(["Kayıt", "Tarih", "Süre", "Metin"])
        self.archive.setRootIsDecorated(False)
        self.archive.setColumnWidth(0, 150)
        self.archive.setColumnWidth(1, 140)
        self.archive.setColumnWidth(2, 60)
        self.archive.currentItemChanged.connect(self.on_record_selected)
        self.archive.itemDoubleClicked.connect(lambda *_: self.toggle_play())
        refresh = QPushButton("Yenile")
        refresh.clicked.connect(self.refresh_archive)
        archive_header = QHBoxLayout()
        archive_header.addWidget(QLabel(f"VPOOL arşivi: {core.display_path(self.vpool)}"), 1)
        archive_header.addWidget(refresh)

        top = QWidget()
        top_layout = QVBoxLayout(top)
        top_layout.addWidget(self.text_edit)
        top_layout.addLayout(options)
        top_layout.addWidget(self.status)
        bottom = QWidget()
        bottom_layout = QVBoxLayout(bottom)
        bottom_layout.addWidget(self.now_playing)
        bottom_layout.addLayout(controls)
        bottom_layout.addLayout(archive_header)
        bottom_layout.addWidget(self.archive)
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(top)
        splitter.addWidget(bottom)
        self.setCentralWidget(splitter)

        self.timeout = QTimer(self)
        self.timeout.setSingleShot(True)
        self.timeout.timeout.connect(self.on_timeout)

        self.update_voices(self.language.currentText())
        missing = core.check_engines()
        if missing:
            self.show_error("Ses motoru dosyaları bulunamadı:\n" + "\n".join(missing))
            self.generate_button.setEnabled(False)
        elif not self.vpool.is_dir():
            self.show_error(f"VPOOL dizini bulunamadı: {self.vpool}")
            self.generate_button.setEnabled(False)
        else:
            self.set_status("Hazır.")
        self.refresh_archive()

    # --- Durum ---

    def set_status(self, text):
        self.status.setStyleSheet("")
        self.status.setText(text)

    def show_error(self, text):
        self.status.setStyleSheet("color: #c62828;")
        self.status.setText(text)

    def update_voices(self, language):
        self.voice.clear()
        for v in core.LANGUAGES[language]:
            self.voice.addItem(v.label, v)
        self.voice.setEnabled(self.voice.count() > 1)

    # --- Ses üretimi ---

    def generate(self):
        if self.process is not None:
            return
        try:
            txt, wav = core.create_record(self.vpool, self.text_edit.toPlainText())
        except ValueError as exc:
            self.show_error(str(exc))
            return
        except OSError as exc:
            self.show_error(f"Metin kaydedilemedi: {exc}")
            return
        voice = self.voice.currentData()
        program, args = core.synth_command(voice, txt, wav)
        self.pending = (txt, wav, voice)
        self.output = []
        self.process = QProcess(self)
        self.process.setWorkingDirectory(str(self.vpool))
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.process.readyReadStandardOutput.connect(self.on_output)
        self.process.finished.connect(self.on_finished)
        self.process.errorOccurred.connect(self.on_process_error)
        self.generate_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.set_status(f"{wav.stem} üretiliyor ({voice.label})…")
        self.timeout.start(core.SYNTH_TIMEOUT_MS)
        self.process.start(program, args)

    def on_output(self):
        self.output.append(bytes(self.process.readAllStandardOutput()).decode("utf-8", "replace"))

    def on_process_error(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            self.finish(f"Ses motoru başlatılamadı: {self.process.errorString()}")

    def on_timeout(self):
        if self.process is not None:
            self.output.append("\nZaman aşımı: süreç durduruldu.")
            self.process.kill()

    def cancel(self):
        if self.process is not None:
            self.output.append("\nKullanıcı iptal etti.")
            self.process.kill()

    def on_finished(self, code, status):
        if self.process is None:
            return
        self.on_output()
        txt, wav, _ = self.pending
        log = self.last_log = "".join(self.output).strip()
        if status != QProcess.ExitStatus.NormalExit or code != 0:
            self.finish(f"Ses üretilemedi (çıkış kodu {code}).\n{log}")
            return
        try:
            info = core.inspect_wav(wav)
        except (OSError, ValueError) as exc:
            self.finish(f"Motor başarılı döndü ama WAV geçersiz: {exc}\n{log}")
            return
        self.finish(None)
        self.set_status(f"Kaydedildi: {wav.name} ve {txt.name} — {info.duration:.1f} sn, "
                        f"{info.sample_rate} Hz")
        self.refresh_archive(select=wav.stem)
        self.toggle_play()

    def finish(self, error):
        """Süreci kapatır; hata varsa sahipsiz TXT'yi kaldırıp hatayı gösterir."""
        self.timeout.stop()
        if self.process is not None:
            self.process.deleteLater()
        self.process = None
        self.generate_button.setEnabled(not core.check_engines())
        self.cancel_button.setEnabled(False)
        if error:
            core.discard_text(self.pending[0])
            core.discard_partial(self.pending[1])
            self.show_error(error)
            self.refresh_archive()
        self.pending = None

    # --- Arşiv ve oynatma ---

    def refresh_archive(self, select=None):
        current = self.archive.currentItem()
        select = select or (current.data(0, Qt.ItemDataRole.UserRole).stem if current else None)
        self.archive.clear()
        try:
            records = core.list_records(self.vpool)
        except OSError as exc:
            self.show_error(f"VPOOL okunamadı: {exc}")
            return
        for record in records:
            duration = "—"
            if record.wav:
                try:
                    duration = f"{core.inspect_wav(record.wav).duration:.1f} sn"
                except (OSError, ValueError):
                    duration = "geçersiz"
            item = QTreeWidgetItem([record.stem, record.modified.strftime("%Y-%m-%d %H:%M"),
                                    duration, record.preview()])
            item.setData(0, Qt.ItemDataRole.UserRole, record)
            item.setToolTip(3, record.preview(2000))
            self.archive.addTopLevelItem(item)
            if record.stem == select:
                self.archive.setCurrentItem(item)

    def on_record_selected(self, item, _previous=None):
        self.player.stop()
        record = item.data(0, Qt.ItemDataRole.UserRole) if item else None
        if record and record.wav:
            self.player.setSource(QUrl.fromLocalFile(str(record.wav)))
            self.now_playing.setText(f"Seçili: {record.wav.name}")
            self.play_button.setEnabled(True)
        else:
            self.player.setSource(QUrl())
            self.now_playing.setText("Seçili kaydın WAV dosyası yok" if record else "Seçili kayıt yok")
            self.play_button.setEnabled(False)

    def toggle_play(self):
        if self.player.source().isEmpty():
            return
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def on_playback_state(self, state):
        playing = state == QMediaPlayer.PlaybackState.PlayingState
        self.play_button.setText("Duraklat" if playing else "Oynat")

    def on_duration(self, ms):
        self.position.setRange(0, ms)
        self.on_position(self.player.position())

    def on_position(self, ms):
        if not self.position.isSliderDown():
            self.position.setValue(ms)
        self.time_label.setText(f"{fmt_time(ms)} / {fmt_time(self.player.duration())}")

    def closeEvent(self, event):
        if self.process is not None:
            answer = QMessageBox.question(self, "Geveze", "Ses üretimi sürüyor. Çıkılsın mı?")
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self.cancel()
            self.process.waitForFinished(5000)
        self.player.stop()
        event.accept()


def main(argv=None):
    argv = sys.argv if argv is None else argv
    app = QApplication(argv)
    app.setApplicationName("Geveze")
    window = MainWindow(core.resolve_vpool(argv[1:]))
    window.show()
    return app.exec()
