<div align="center">

# GEVEZE

### Offline Multilingual Text-to-Speech & Voice Archive

**6 languages · 12 voices · CPU only · no cloud · every recording kept as a TXT + WAV pair**

Part of the **ASUNODE** ecosystem

[Türkçe README](README.tr.md) · [Installation](docs/installation.md) · [Architecture](docs/architecture.md) · [Licenses](docs/third-party-licenses.md)

</div>

![Geveze main window: text editor, language and voice selection, player and the TXT/WAV archive](docs/images/main-window.png)

## What is Geveze?

Geveze is a desktop application that turns text into speech **entirely on your own
computer**. Type a sentence, pick a language and a voice, press **Ses üret** ("generate
audio"): Geveze synthesises the audio on the CPU, plays it, and stores the text and the
audio side by side in a plain-file archive.

Its purpose in ASUNODE is to **prepare ready-made voice messages** — announcements,
confirmations, reminders — that other ASUNODE applications can play later without
generating speech themselves. Each message is a pair of ordinary files
(`geveze_007.txt` + `geveze_007.wav`), so any program can find and reuse it.

> **Status:** Geveze is a working single-user desktop tool. It is not a server, an API,
> or a real-time voice assistant (ASUNODE Local Voice Assistant is a separate project).
> Automatically preparing new messages with a local LLM is a future goal, not a
> current feature.

The interface itself is in Turkish (e.g. *Dil* = language, *Ses* = voice,
*Kayıt* = record, *Süre* = duration, *Metin* = text).

## Features

- **Six languages, twelve voices**, including female/male speakers of the same model for
  Japanese and French.
- **Offline:** after installation no network connection is used; tested with the network
  disabled.
- **CPU only:** no GPU, CUDA, server, database or background service.
- **Archive of TXT/WAV pairs** with date, duration and a text preview; play any record.
- **Never overwrites:** new records always get a new number; existing files are never
  replaced, even under concurrent writes.
- **Unicode-exact:** text is stored byte for byte as typed — Kanji, Kana, accents,
  Slovenian č/š/ž, decomposed forms.
- **Responsive UI:** synthesis runs in a separate process; it can be cancelled and times
  out after 10 minutes.

## Languages and voices

| Language | Voice | Gender | Model | Sample rate |
| --- | --- | --- | --- | --- |
| Türkçe | EMA Lightning | female | `canberkkkkkk/ema-lightning` | 48 kHz |
| English | Jenny (Dioco) — *default* | female | `en_GB-jenny_dioco-medium` | 22.05 kHz |
| English | Ryan ⚠ | male | `en_US-ryan-high` | 22.05 kHz |
| English | HFC Female ⚠ | female | `en_US-hfc_female-medium` | 22.05 kHz |
| English | Amy | female | `en_US-amy-medium` | 22.05 kHz |
| Deutsch | Thorsten — *default* | male | `de_DE-thorsten-high` | 22.05 kHz |
| Deutsch | Kerstin | female | `de_DE-kerstin-low` | 16 kHz |
| 日本語 | Hi-Fi Captain ⚠ — *default* | female | `ja_JP-hi_fi_captain-medium`, speaker 0 | 22.05 kHz |
| 日本語 | Hi-Fi Captain ⚠ | male | `ja_JP-hi_fi_captain-medium`, speaker 1 | 22.05 kHz |
| Français | Jessica — *default* | female | `fr_FR-upmc-medium`, speaker 0 | 22.05 kHz |
| Français | Pierre | male | `fr_FR-upmc-medium`, speaker 1 | 22.05 kHz |
| Slovenščina | Artur | male | `sl_SI-artur-medium` | 22.05 kHz |

⚠ = trained on CC BY-NC-SA 4.0 data: **not for commercial use**. Amy and Kerstin have
unresolved license questions. See [Licenses](#licenses).

![Choosing between the four English voices](docs/images/voice-selection.png)

## Architecture

```text
 Geveze UI (Python 3 + PySide6)
   │  writes geveze_NNN.txt (exclusive create)
   │  starts the engine with QProcess ─────────────┐
   ▼                                               ▼
 Archive (VPOOL)                    EMA Lightning (Turkish)   ─ own Python 3.12 venv, PyTorch CPU
   geveze_NNN.txt  ◄── os.link ──   Piper + ONNX Runtime      ─ own Python 3.12 venv
   geveze_NNN.wav                   (eSpeak NG / OpenJTalk)
```

- The interface never imports an engine; it runs each engine's own interpreter with an
  argument list and reads back the finished WAV.
- Engines write to a temporary file and publish it with `os.link`, which refuses to
  replace an existing file. Geveze validates the WAV before announcing success.
- Model files are pinned to fixed Hugging Face revisions and verified by SHA-256.

Details: [docs/architecture.md](docs/architecture.md).

## Installation

Requirements: Ubuntu on x86_64 (tested on 26.04), `git`, an internet connection during
installation (~1.4 GB download), about 2.8 GB of disk space.

```bash
git clone https://github.com/asunode/geveze.git
cd geveze
./setup.sh
./run.sh
```

`setup.sh` shows the model licenses and asks for confirmation, then installs everything
**inside the cloned folder**: a pinned `uv`, Python 3.12.15, one virtual environment per
engine (all packages hash-verified), the voice models (size- and SHA-256-verified), and
a PySide6 environment only if the system does not already provide PySide6. It does not
use `sudo` and does not modify the system Python. Running it again is safe.

Full guide, options and troubleshooting: [docs/installation.md](docs/installation.md).

## Usage

```bash
./run.sh                          # archive: ~/.local/share/geveze/vpool
./run.sh --vpool ~/Voice/messages # any existing folder
GEVEZE_VPOOL=~/Voice/messages ./run.sh
```

1. Type or paste the text.
2. Choose **Dil** (language) and **Ses** (voice).
3. Press **Ses üret**. The status line shows progress; **İptal** cancels.
4. When finished, the record is selected in the archive and played automatically.
5. Select any record and press **Oynat** (play) or double-click it; **Yenile** reloads
   the archive.

## The TXT/WAV archive

![The archive: every record is a TXT/WAV pair](docs/images/archive.png)

Every generation creates exactly two files in the archive folder (VPOOL):

```text
~/.local/share/geveze/vpool/
├── geveze_001.txt   # the text, UTF-8, exactly as typed
├── geveze_001.wav   # mono 16-bit PCM WAV
├── geveze_002.txt
├── geveze_002.wav
└── …
```

- The next number is one above the highest existing `geveze_NNN`; numbers whose TXT or
  WAV already exist are skipped. Nothing is ever renamed or overwritten.
- If synthesis fails or is cancelled, Geveze removes only the files it just created for
  that record; other files are never touched.
- Other applications can read the folder directly: the `.txt` tells what the `.wav` says.
- The archive lives outside the repository, so updating or deleting the Geveze folder
  does not affect recordings.

## Unicode and Japanese

![Japanese text mixing Kanji, Hiragana, Katakana and Latin letters](docs/images/japanese-unicode.png)

Geveze stores text without any normalisation or transliteration, and the tests verify
the saved bytes for Japanese, French, Slovenian, decomposed (NFD) text and the
ideographic space.

**Byte-exact storage does not by itself prove correct pronunciation.** Pronunciation
comes from each engine's front end:

| Japanese input | Result |
| --- | --- |
| Kanji / Hiragana / Katakana: `一緒にGoogleマップを見ましょう、ね。` | Converted to the correct reading (OpenJTalk: イッショニグーグルマップヲミマショー、ネ) |
| Latin word **in** the dictionary inside a Japanese sentence: `Google` | Read as グーグル |
| Latin word **not** in the dictionary: `Geveze` | Spelled letter by letter (ジーイーブイイーゼットイー) — write ゲヴェゼ instead |
| Japanese written in **Romaji**: `konnichiwa` | **Not read as Japanese** — spelled letter by letter (ケーオーエヌエヌアイ…) |

Geveze does **not** convert Romaji to Japanese script. Write Japanese text in Japanese
characters.

## Offline operation

The network is used only by `setup.sh`. During synthesis the EMA engine runs with
`HF_HUB_OFFLINE=1` and telemetry disabled; Piper loads local ONNX files on the CPU.
In the clean installation test all twelve voices were generated inside a container
started with `--network none`.

## Licenses

| Layer | License |
| --- | --- |
| Geveze source code (this repository) | [MIT](LICENSE) |
| EMA Lightning engine | Apache-2.0 |
| Piper engine (with eSpeak NG) | GPL-3.0-or-later — installed separately from PyPI, run as a separate process |
| PySide6 / Qt | LGPL-3.0 (open-source option) |
| Voice models | Their own licenses — downloaded from the original sources, **not** included here |

Commercial use:

- **Not allowed** (non-commercial training data, CC BY-NC-SA 4.0): Ryan, HFC Female,
  Hi-Fi Captain female and male.
- **Unclear, do not assume**: Amy, Kerstin.
- **Attribution required**: Jenny — credit as *Jenny (Dioco)*; Jessica/Pierre (CC BY-SA
  4.0); Artur (CC BY 4.0 / 3.0).
- **Allowed by the model card**: EMA Lightning (Apache-2.0 for code and weights).

Geveze makes no claim that generated audio is free for any purpose. Full details,
sources and open questions: [docs/third-party-licenses.md](docs/third-party-licenses.md).

## Testing and verification

Clean installation test, 23 October 2026, run in a fresh `ubuntu:26.04` Docker container
(non-root user, no PySide6 preinstalled, install path containing spaces and Turkish
characters). The repository was cloned with `git clone` and installed with
`./setup.sh`, exactly as described above.

| Check | Result |
| --- | --- |
| `setup.sh` without license confirmation in a non-interactive shell | Stops before downloading anything |
| `setup.sh --accept-model-licenses` | Completed; 31 model files verified by size and SHA-256; `uv pip check` clean in all three environments |
| `setup.sh` run again | Existing environments reused, model files unchanged, a pre-existing archive record unchanged (SHA-256) |
| All 12 voices generated through the real window, **network disabled** | 12/12 valid WAVs (48 / 22.05 / 16 kHz as expected), correct `--voice`/`--speaker`, text stored byte-exact |
| Archive location | `~/.local/share/geveze/vpool`, outside the repository |
| Playback (QMediaPlayer) | Position advances (container used a PulseAudio null sink) |
| Engine safety | Existing output refused; invalid speaker ID rejected |
| Automated test suite (`tests/test_geveze.py`) | 32 tests: 27 passed, 5 skipped (the opt-in real-archive tests) |

The test suite also checks unique naming, the no-overwrite guarantee, failure and cancel
clean-up, UI responsiveness during synthesis (no event-loop gap over 250 ms), and that
female and male speakers differ in pitch (F0 measurement, with NumPy).

Not verified: installation on a second physical computer, other distributions or Ubuntu
versions, ARM64, and listening tests for intelligibility. Speech quality was checked
technically (WAV structure, duration, signal level), not by ear in this test.

## Known limitations

- Linux x86_64 only; the interface is in Turkish.
- Romaji is not converted to Japanese script; out-of-dictionary Latin words are spelled
  out in Japanese.
- The archive does not record which voice produced a WAV.
- The model is reloaded for every generation: about 1.5–3 s per short sentence on the
  test machine; the very first Turkish generation after installation took about 15 s.
- No deletion, renaming or search in the archive; no splitting of very long texts and no
  progress bar.
- Installation needs about 2.8 GB of disk space; all six languages are always installed.
- Generated WAV files are created with owner-only permissions (0600) by the engines.
- Several voices are non-commercial (see above).

## Roadmap

- Show the voice used for each record.
- Optional per-language installation.
- An interface for other ASUNODE applications to request and reuse messages.
- Local-LLM–assisted preparation of new, reusable messages (planned, not started).
- Optional Romaji → Kana conversion for Japanese.

## Repository layout

```text
geveze/
├── README.md, README.tr.md, LICENSE
├── setup.sh                    # installer (everything stays in this folder)
├── run.sh                      # launcher
├── requirements-gui.lock       # PySide6, used only if the system has none
├── geveze/                     # application: core.py (logic), app.py (window)
├── engines/
│   ├── fetch_models.py         # verified model downloader
│   ├── ema/                    # synthesize.py, locks, models/manifest.json
│   └── piper/                  # synthesize.py, lock,  models/manifest.json
├── tests/test_geveze.py
└── docs/                       # installation, architecture, licenses, images
```
