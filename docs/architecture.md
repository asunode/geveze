# Architecture

Geveze is a small desktop application in front of two local, offline text-to-speech
engines. The interface never imports an engine: each synthesis runs as a separate
process with its own Python environment, and the two sides exchange only a UTF-8 text
file and a WAV file.

```text
┌──────────────────────────── Geveze (PySide6) ────────────────────────────┐
│ text + language + voice ──► core.create_record()  ──► geveze_NNN.txt     │
│                             core.synth_command()                         │
│                                   │ QProcess (async, UI stays responsive)│
└───────────────────────────────────┼──────────────────────────────────────┘
                                    ▼
      engines/ema/.venv/bin/python -I -B engines/ema/synthesize.py   (Türkçe)
      engines/piper/.venv/bin/python -I -B engines/piper/synthesize.py
                                        --voice ID [--speaker N]     (other languages)
                                    │  temp file → os.link (never overwrites)
                                    ▼
                           geveze_NNN.wav  ──► validated ──► archive list ──► player
```

## Components

| Path | Role |
| --- | --- |
| `geveze/core.py` | Qt-free core: voice table, engine paths, record naming, archive listing, WAV validation, VPOOL resolution |
| `geveze/app.py` | PySide6 main window: editor, language/voice selection, QProcess runner, player, archive |
| `engines/ema/synthesize.py` | EMA Lightning wrapper (Turkish), CPU only, 48 kHz output |
| `engines/piper/synthesize.py` | Piper wrapper with a fixed voice registry, `--voice` / `--speaker`, CPU only |
| `engines/*/models/manifest.json` | Exact source URL, revision, size and SHA-256 of every model file |
| `engines/fetch_models.py` | Downloads and verifies the files listed in the manifests |
| `engines/*/requirements.lock`, `engines/ema/torch-cpu.lock`, `requirements-gui.lock` | Pinned versions with wheel SHA-256 hashes |
| `setup.sh` / `run.sh` | Installer and launcher |

The engine wrappers are a verbatim snapshot of the ASUNODE TTS infrastructure prepared
for this project; Geveze only calls their command-line interface.

## Voice table

The voice list is fixed in `core.py` (no automatic model discovery). Each entry names
the engine, the Piper voice ID and, for the two multi-speaker models, the speaker ID:

| Language | Voice | Engine call |
| --- | --- | --- |
| Türkçe | EMA Lightning — kadın | `ema/synthesize.py` |
| English | Jenny Dioco — kadın (default) | `--voice en_GB-jenny_dioco-medium` |
| English | Ryan — erkek | `--voice en_US-ryan-high` |
| English | HFC Female — kadın | `--voice en_US-hfc_female-medium` |
| English | Amy — kadın | `--voice en_US-amy-medium` |
| Deutsch | Thorsten — erkek (default) | `--voice de_DE-thorsten-high` |
| Deutsch | Kerstin — kadın | `--voice de_DE-kerstin-low` |
| 日本語 | Hi-Fi Captain — kadın (default) | `--voice ja_JP-hi_fi_captain-medium --speaker 0` |
| 日本語 | Hi-Fi Captain — erkek | `--voice ja_JP-hi_fi_captain-medium --speaker 1` |
| Français | Jessica — kadın (default) | `--voice fr_FR-upmc-medium --speaker 0` |
| Français | Pierre — erkek | `--voice fr_FR-upmc-medium --speaker 1` |
| Slovenščina | Artur — erkek | `--voice sl_SI-artur-medium` |

Geveze always passes `--voice` explicitly; the Piper wrapper's own default (Amy) is
never relied on. `--force` is never passed.

## Record naming and overwrite protection

1. The next name is one above the highest existing `geveze_NNN` in the archive.
   A number is skipped if either its `.txt` or `.wav` already exists.
2. The text is written with exclusive-create mode (`open(..., "x")`): an existing file
   can never be overwritten, even by a concurrent writer.
3. The engine writes into a temporary file next to the target and publishes it with
   `os.link`, which fails instead of replacing an existing WAV.
4. The finished WAV is read back completely: 16-bit PCM, data length matches the
   header, not silent. Only then is the record reported as saved and played.
5. On failure, cancel or timeout (10 min) Geveze removes only what it created for this
   record: the orphan `.txt` and the engine's temporary `.<name>.wav.*.wav` file.

Files in the archive that do not follow the `geveze_NNN` pattern are listed but never
renamed or touched.

## Paths

**Engine root** (where `ema/` and `piper/` live), first match wins:

1. `GEVEZE_ENGINE_ROOT` environment variable;
2. `engines/` inside this repository, once `setup.sh` created both environments;
3. the parent directory of the repository (the original developer layout, where the
   engines are siblings of the application folder).

**Archive (VPOOL)**, first match wins:

1. `--vpool DIR` argument;
2. `GEVEZE_VPOOL` environment variable;
3. a `vpool/` directory next to the engines, if one exists (developer layout);
4. `${XDG_DATA_HOME:-~/.local/share}/geveze/vpool`, created on first start.

An explicitly given directory must already exist; Geveze does not create it.
The archive is always outside the Git repository in a standard installation.

## Unicode

Text is stored exactly as typed (only leading and trailing whitespace is removed),
UTF-8 encoded, without normalisation or transliteration. The test suite compares the
saved bytes with the input for Japanese, French, Slovenian, decomposed (NFD) text and
the ideographic space.

Byte-exact storage is not the same as correct pronunciation. Pronunciation depends on
each engine's text front end:

- **Japanese** uses OpenJTalk (via `pyopenjtalk-plus`). Kanji, Hiragana and Katakana are
  read correctly, and Latin words that are in its dictionary (e.g. *Google* → グーグル)
  are converted. Latin words that are *not* in the dictionary are spelled letter by
  letter (*Geveze* → ジーイーブイイーゼットイー). **Japanese written in Romaji is therefore
  not read as Japanese**: `konnichiwa` becomes ケーオーエヌエヌアイ… Geveze does not
  convert Romaji to Kana; write Japanese in Japanese script.
- **English, German, French, Slovenian** use eSpeak NG phonemisation bundled with Piper.
- **Turkish** uses EMA Lightning's own normaliser (`normalizer-tr`).

## Offline operation

Network access is needed only during `setup.sh` (packages and models). At synthesis
time the EMA wrapper sets `HF_HUB_OFFLINE=1` and disables telemetry; Piper loads local
ONNX files with the CPU execution provider. No GPU, CUDA, server, database or system
service is involved. Generation with the network disabled was verified in the clean
installation test (see the README).
