# Contributing to Knowlin / duckpilot

Thanks for helping! **Knowlin** is one mind for many small robots – shared knowledge, one character per body. duckpilot is
its module for the Microduck (Pollen Robotics / Hugging Face); Reachy Mini, the Open Duck Mini v2 and the SO-101
gripper arm (TheRobotStudio / Hugging Face) run as further bodies. Simulator with real physics, voice, personality, memory and a phone controller. It is a free, non-commercial
hobby project (Apache-2.0).

*Deutsch:* Beiträge gern auf Deutsch oder Englisch. Code-Kommentare und Oberfläche sind deutsch, die englische
Oberfläche kommt aus `duckpilot/i18n/ui_en.json`.

## Safety rules – never relaxed

A contribution that weakens any of these will not be merged:

- **Emergency stop wins.** “Stop” (any language) and the stop button halt everything at once, with or without an AI model.
- **120 s lock** after an emergency stop – nothing stands up or starts by itself.
- **Getting up after a fall** only after the stop window and never while the robot is picked up.
- **Paid training** (cloud GPUs) only with two clicks.
- **Secrets** only in the system vault (keyring) – never in files, logs, reports or the repository.
- **People** (faces, names) only on the PC, only enrolled persons with consent; never answered to a phone.
- Smart home never controls locks, alarms or heating.

## Getting started

```bash
python -m venv .venv && . .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e ".[dev]" ruff                      # dev = pytest and httpx (FastAPI's test client)
python -m duckpilot.modell                        # fetch Pollen's Microduck model from its original source
python -m duckpilot                               # opens the UI in your browser
```

Real physics (MuJoCo, ONNX), local speech recognition and the local voices are optional; tests that need them skip
themselves when the packages are missing.

Before every pull request:

```bash
ruff check duckpilot tests tools
python -m pytest -q
```

The full chain the maintainers run before every push (lint, tests, the public export, the installed package, the
browser acceptance test and the website) is one command: `python tools/pruefen_alles.py <folder> --schnell` skips the
browser parts if you don't have Playwright.

New features get tests; reported bugs get a regression test. Read `ARCHITECTURE.md` first – it shows where things
live (layers: core/brain, motor, lab, body) and which layer may import which (`tests/test_schichten.py` checks it).

## One rule for what a body can do

A body says what it has (`eigenschaften()`: legs, head, beak, depth sensor, antennas …) and which learned moves it knows
(`skills()`). The brain (`brain/tools.py` → `fehlt_dem_koerper`), skills (`motion/faehigkeit.py` → `braucht`) and the
interface (CSS classes `braucht-*`, `nur-*`, `keine-ente` set by `static/modul.js`) all follow that – please don't add a
button or tool that a body would only reject. Never ask a body for its name (`== "reachy_mini"`) – ask for its
capabilities or its profile (`tests/test_koerper_leitplanke.py` guards this).

**A new robot** doesn't need changes in Knowlin: write it as its own package with a profile and the entry point
`knowlin.koerper` – see [`docs/body-interface.md`](docs/body-interface.md) and the template
[`examples/knowlin-koerper-vorlage`](examples/knowlin-koerper-vorlage). Built-in bodies additionally get an embodiment in
`figuren.py`.

## Good places to start

- **Translations** – one file per language (`duckpilot/i18n/ui_<lang>.json`); `python tools/i18n_texte.py` lists gaps.
- **Skill packs and extensions** – `duckpilot/skills`, one entry in `PACKS`.
- **AI providers and robot modules** – clearly separated building blocks (`brain/anbieter.py`, `backends/`).
- **Reports from real ducks** – use the issue template “Report from a real robot”.

See `docs/good-first-issues.md` for concrete ideas.

## Developer Certificate of Origin (DCO)

We use the [DCO](https://developercertificate.org/) instead of a contributor licence agreement. Sign off every commit:

```bash
git commit -s -m "Your message"
```

This adds `Signed-off-by: Your Name <you@example.com>` and certifies that you wrote the change or have the right to
submit it under the project licence. A check on every pull request looks for this line; if you forgot it, fix the
last commit with `git commit --amend -s --no-edit` (or all commits with `git rebase --signoff main`) and push again.

## Third-party models

Pollen's 3D parts and physics models for the Microduck and Reachy Mini (CC BY-NC-SA) are **not** in this repository;
Knowlin downloads them from the original source and prepares them on the user's PC. Please never commit them
(`.gitignore` keeps them out). The Open Duck Mini v2 model is Apache-2.0 and ships prepared, with attribution in
`NOTICE` and `duckpilot/server/static/model/LIZENZ-open-duck-mini.md`.
