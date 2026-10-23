# Third-party licenses

Geveze involves three separate layers with **separate licenses**. Do not read one as
covering another:

1. **Geveze source code** in this repository: MIT (see [`LICENSE`](../LICENSE)).
2. **TTS engine software**, installed from PyPI by `setup.sh`: EMA Lightning, Piper and
   their dependencies.
3. **Voice models and their training data**, downloaded by `setup.sh` from Hugging Face.

No engine package and no model weight is stored in this repository. Downloading them
through `setup.sh` does not remove any of their terms. Making the Geveze source public
does not change the license of any model.

This summary is based on a technical review of the official package metadata and
model cards at the pinned revisions (23 October 2026). It is not legal advice.

## Engine software

| Component | Version | License | Notes |
| --- | --- | --- | --- |
| [EMA Lightning](https://pypi.org/project/ema-lightning/1.1.2/) | 1.1.2 | Apache-2.0 | Turkish engine; keep license/NOTICE files when redistributing |
| [Piper TTS](https://pypi.org/project/piper-tts/1.8.0/) | 1.8.0 | GPL-3.0-or-later | Older MIT-licensed Piper releases do not apply to this version |
| eSpeak NG | bundled in the Piper wheel | GPL-3.0-or-later | Present even without a system espeak package |
| [pyopenjtalk-plus](https://github.com/tsukumijima/pyopenjtalk-plus) | 0.4.1.post10 | MIT | Japanese front end; bundled dictionary carries its own NAIST / UniDic / HTS notices (`pyopenjtalk/dictionary/COPYING`) |
| ONNX Runtime | 1.31.0 | MIT | |
| PyTorch (CPU) | 2.14.1+cpu | BSD-style (with bundled third-party notices) | |
| SudachiPy / SudachiDict | 0.7.0 / 20261015 | Apache-2.0 | |
| [PySide6 / Qt](https://doc.qt.io/qtforpython-6/licenses.html) | 6.10.2 | LGPL-3.0 / GPL (open-source options) or commercial | Geveze uses QtCore, QtGui, QtWidgets, QtMultimedia |

The complete pinned dependency lists are in `engines/ema/requirements.lock`,
`engines/ema/torch-cpu.lock`, `engines/piper/requirements.lock` and
`requirements-gui.lock`.

**How Geveze uses Piper:** the Geveze interface does not import Piper. It starts the
Piper wrapper (`engines/piper/synthesize.py`) as a separate process and communicates
only through a text file and a WAV file. The wrapper itself imports Piper and therefore
runs together with GPL code. Using a separate process is a technical fact, not an
automatic guarantee about how the GPL applies; anyone redistributing Piper (for example
in a binary bundle) must meet Piper's GPL obligations. This repository distributes
source code only; Piper is installed by the user from PyPI.

## Voice models

Model files come from two Hugging Face repositories at fixed revisions:

- [`canberkkkkkk/ema-lightning`](https://huggingface.co/canberkkkkkk/ema-lightning/tree/e7c96f2fc0ba843cd0f86e02786655bb56f50df8) @ `e7c96f2fc0ba843cd0f86e02786655bb56f50df8`
- [`rhasspy/piper-voices`](https://huggingface.co/rhasspy/piper-voices/tree/5041a7a49ae5b3a0f30e6837769eb03fdbb231bd) @ `5041a7a49ae5b3a0f30e6837769eb03fdbb231bd`

The `rhasspy/piper-voices` repository is tagged MIT as a collection, but most of its
MODEL_CARD files state the license of the **training dataset** rather than a separate
license for the weights. The collection tag is not treated here as removing
dataset-specific terms. "Unclear" below means the reviewed cards do not state an
explicit weight license; it does not mean that use is forbidden.

| Voice in Geveze | Model | Training data license | Commercial use |
| --- | --- | --- | --- |
| EMA Lightning — kadın | `canberkkkkkk/ema-lightning` | Code **and weights: Apache-2.0** per the [model card](https://huggingface.co/canberkkkkkk/ema-lightning/blob/e7c96f2fc0ba843cd0f86e02786655bb56f50df8/README.md); trained on an internal synthetic Turkish corpus | Allowed by the model card |
| Jenny Dioco — kadın | `en_GB-jenny_dioco-medium` | [Jenny dataset](https://github.com/dioco-group/jenny-tts-dataset) custom terms; fine-tuned from Lessac | Allowed by the dataset terms, **attribution required**: apps must credit the voice as *Jenny (Dioco)* |
| Ryan — erkek | `en_US-ryan-high` | RyanSpeech: **CC BY-NC-SA 4.0** | **Restricted (non-commercial)** |
| HFC Female — kadın | `en_US-hfc_female-medium` | Hi-Fi Captain: **CC BY-NC-SA 4.0** | **Restricted (non-commercial)** |
| Amy — kadın | `en_US-amy-medium` | Card points to [mimic3-voices](https://github.com/MycroftAI/mimic3-voices) (repository CC BY-SA 4.0); mapping for Amy not explicit | **Unclear** — do not assume commercial use |
| Thorsten — erkek | `de_DE-thorsten-high` | [Thorsten-Voice](https://github.com/thorstenMueller/Thorsten-Voice): CC0 | No NC term in the data; weight license not stated separately |
| Kerstin — kadın | `de_DE-kerstin-low` | [Kerstin dataset](https://github.com/rhasspy/dataset-voice-kerstin): CC0; fine-tuned from Ryan *low*, whose terms were not verified | **Unclear** |
| Hi-Fi Captain — kadın / erkek | `ja_JP-hi_fi_captain-medium` (speakers 0 and 1) | Hi-Fi Captain: **CC BY-NC-SA 4.0** | **Restricted (non-commercial), both speakers** |
| Jessica — kadın / Pierre — erkek | `fr_FR-upmc-medium` (speakers 0 and 1) | [UPMC Jessica](https://github.com/marytts/upmc-jessica-data) / [UPMC Pierre](https://github.com/marytts/upmc-pierre-data): CC BY-SA 4.0 | No NC term; attribution and share-alike apply |
| Artur — erkek | `sl_SI-artur-medium` | Model card: CC BY 4.0; linked [dataset README](https://huggingface.co/datasets/ppisljar/artur_studio_tts/blob/feb6181d00291140904ed7662d8689f45b099002/README.md): CC BY 3.0 (discrepancy not resolved) | No NC term; attribution required |

Artur attribution: @ppisljar; Verdonik, Darinka; et al., 2023, *ASR database ARTUR 1.0
(audio)*, CLARIN.SI, [http://hdl.handle.net/11356/1776](http://hdl.handle.net/11356/1776).

Each downloaded model folder contains the official `MODEL_CARD` (or `README.md` for
EMA). Those files are the authoritative source for each model.

## Generated audio

Whether a dataset license (for example CC BY-NC-SA) carries over to every WAV file a
model generates has not been determined. Geveze makes **no claim that generated audio
is free for any purpose**. For commercial use, choose voices whose terms clearly allow
it and verify them yourself.

## Open questions

- Amy: which license applies to the published weights.
- Kerstin: the terms of the Ryan *low* checkpoint it was fine-tuned from.
- Artur: CC BY 4.0 (model card) versus CC BY 3.0 (dataset README).
- Fine-tuned Piper voices in general: the license of the base checkpoints
  (Lessac, LibriTTS-R) is not the same question as the dataset license.
