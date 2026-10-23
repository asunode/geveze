# Installation

## Requirements

- Ubuntu (or a similar glibc-based Linux) on **x86_64**. glibc 2.34 or newer is needed
  by the PySide6 wheels (Ubuntu 22.04 and later; only the reference system was tested); the reference system is Ubuntu 26.04.
- `/usr/bin/python3` (installed by default on Ubuntu; used only to run the installer's
  standard-library helper scripts) and `git`.
- Internet access **during installation only**. About 1.4 GB is downloaded:
  ~710 MB of voice models, ~190 MB PyTorch CPU, ~240 MB PySide6 (only if the system has
  no PySide6), ~35 MB Python and smaller packages. The finished installation takes about
  2.8 GB of disk space (about 2.2 GB when the system PySide6 is used). In the clean
  installation test the whole setup took about 4.5 minutes.
- For playback: a working desktop audio session.
- For Japanese text in the interface: a CJK font such as `fonts-noto-cjk`
  (Ubuntu desktop installs it by default).

No GPU, `sudo`, system service or database is needed.

## Install

```bash
git clone https://github.com/asunode/geveze.git
cd geveze
./setup.sh
./run.sh
```

`setup.sh` first prints a license summary of the voice models and asks for
confirmation (several voices are non-commercial, see
[third-party-licenses.md](third-party-licenses.md)). For an unattended installation
pass `--accept-model-licenses` after reading that document.

What `setup.sh` does, in order — everything stays inside the cloned folder:

| Step | Result |
| --- | --- |
| Download `uv` 0.13.1 from its GitHub release, check the SHA-256 | `.tools/uv-0.13.1/` |
| Install CPython 3.12.15 with uv (no links in `PATH`) | `.tools/python/` |
| Create the EMA environment, install PyTorch CPU from `download.pytorch.org` and the rest from PyPI, all with `--require-hashes` | `engines/ema/.venv/` |
| Create the Piper environment the same way | `engines/piper/.venv/` |
| If `/usr/bin/python3` can import PySide6 with QtMultimedia, use it; otherwise create a GUI environment with PySide6-Essentials 6.10.2 | `.venv/` (only when needed) |
| Download the 31 model files listed in the manifests, verify size and SHA-256, publish without overwriting | `engines/ema/models/`, `engines/piper/models/` |
| Create the default archive folder and print its location | `~/.local/share/geveze/vpool/` |

Options:

- `--accept-model-licenses` — skip the confirmation prompt.
- `--gui-venv` — create the `.venv` GUI environment even if the system has PySide6.

### Running setup.sh again

Re-running is safe. Existing environments are reused (their Python version is checked)
and pinned packages are only installed if missing. Model files that already match the
manifest are skipped; a file with different content stops the installation instead of
being overwritten. The archive is never touched. An interrupted download leaves no
partial model file behind.

If an environment is broken, `setup.sh` stops and tells you which folder to delete;
it never deletes environments itself.

### Using the system PySide6 instead

On Ubuntu the interface can also use the distribution packages:

```bash
sudo apt install python3-pyside6.qtwidgets python3-pyside6.qtmultimedia
```

When they are present `setup.sh` does not create `.venv`, and `run.sh` uses
`/usr/bin/python3`. If both exist, `run.sh` prefers `.venv`.

## Start

```bash
./run.sh                       # archive in ~/.local/share/geveze/vpool
./run.sh --vpool ~/Ses/arsiv   # any existing folder
GEVEZE_VPOOL=~/Ses/arsiv ./run.sh
```

`GEVEZE_ENGINE_ROOT=/path` points Geveze at another engine installation that has the
same `ema/` and `piper/` layout.

## Run the tests

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -B -m unittest -v tests.test_geveze
```

(Use `/usr/bin/python3` instead of `.venv/bin/python` with the system PySide6.)
The GUI tests synthesise real audio with ten of the twelve voices into
`test_area/run_<time>/`, which is ignored by Git. The pitch comparison between female
and male speakers additionally needs NumPy and is skipped without it.

## Uninstall

Delete the cloned folder. The archive in `~/.local/share/geveze/` is kept; delete it
separately only if you no longer need your recordings.

## Troubleshooting

| Symptom | Cause / fix |
| --- | --- |
| "Ses motoru dosyaları bulunamadı" in the window | `setup.sh` has not completed; run it again |
| `qt.qpa.plugin: Could not load the Qt platform plugin "xcb"` | Install `libxcb-cursor0` (needed by Qt ≥ 6.5 under X11) |
| "No QtMultimedia backends found", playback does nothing | The Qt FFmpeg plugin needs `libxrandr2` (present on every Ubuntu desktop, missing in minimal containers) |
| Japanese characters shown as boxes | Install `fonts-noto-cjk` |
| No sound, but the WAV is created | Check the desktop audio output; the file is still in the archive |
| `HATA: ... manifestle eşleşmiyor` | A model file was modified; delete that file and run `setup.sh` again |
