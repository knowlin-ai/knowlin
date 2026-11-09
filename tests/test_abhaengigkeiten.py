"""Jedes Fremdpaket, das Knowlin importiert, ist entweder Pflicht im Paket oder eine Zusatzinstallation mit Knopf.

Gemeldet nach 0.38.32 (Abnahme gegen das installierte Paket): `httpx` kam früher mit `anthropic` mit, seit anthropic
2.x nicht mehr – im Installer gingen lokales Modell und andere Anbieter dann nicht."""

import ast
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# per Knopf nachinstalliert (voice/install.py) oder bewusst optional mit Hinweis
ZUSATZ = {"PIL", "bam", "faster_whisper", "huggingface_hub", "lerobot", "mujoco", "onnx", "onnxruntime", "piper", "qwen_tts",
          "torch"}
MITGEBRACHT = {"starlette": "fastapi"}                   # kommt sicher mit einem Pflichtpaket
NAME = {"fast_simplification": "fast-simplification"}


def _importe() -> set[str]:
    std, mods = set(sys.stdlib_module_names), set()
    for p in (ROOT / "duckpilot").rglob("*.py"):
        for n in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
            if isinstance(n, ast.Import):
                mods |= {a.name.split(".")[0] for a in n.names}
            elif isinstance(n, ast.ImportFrom) and n.level == 0 and n.module:
                mods.add(n.module.split(".")[0])
    return {m for m in mods if m not in std and m != "duckpilot"}


def test_jedes_fremdpaket_ist_pflicht_oder_zusatz():
    deps = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["dependencies"]
    pflicht = {re.split(r"[<>=!;\[ ]", d, maxsplit=1)[0].strip().lower() for d in deps}
    fehlt = [m for m in sorted(_importe()) if m not in ZUSATZ and NAME.get(m, m).lower() not in pflicht
             and MITGEBRACHT.get(m) not in pflicht]
    assert not fehlt, f"Importiert, aber weder Pflichtabhängigkeit noch Zusatzinstallation: {fehlt}"


def test_requirements_und_pyproject_gleich():
    deps = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["dependencies"]
    req = [z.split("#")[0].strip() for z in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()]
    assert {d.replace(" ", "") for d in deps} == {z.replace(" ", "") for z in req if z}
