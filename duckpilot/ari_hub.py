"""Aris Beispiele auf den Hugging Face Hub (seit 0.42, Fahrplan „Ari mit LeRobot“).

Lädt den Inhalt des LeRobot-Exports (`arm_export.paket`) als Dataset-Repo unter das eigene Hugging-Face-Konto:
`episoden.jsonl`, `meta/…`, `nach_lerobot.py`, `LIESMICH.md` und eine Karte (`README.md`) mit den Hub-Tags `LeRobot`,
`so101` und `knowlin`. Alles in einem Commit.

- Standard ist **privat**; öffentlich nur, wenn man es ausdrücklich ankreuzt. Hochgeladen wird nur nach dem zweiten Klick.
- Der Schlüssel kommt aus dem Tresor (derselbe wie fürs Training), nie aus der Oberfläche.
- Ehrlich: Das ist das Rohformat mit Bauanleitung, kein fertiger LeRobot-Datensatz (dafür bräuchte Knowlin pyarrow).
  Wer LeRobot installiert hat, baut daraus mit `nach_lerobot.py --hochladen` den echten Datensatz.
"""

from __future__ import annotations

import io
import json
import re
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from .hub import HUB

MAX_DATEIEN = 20
MAX_BYTES = 50_000_000
TAGS = ("LeRobot", "so101", "knowlin", "simulation")


class HubFehler(ValueError):
    pass


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9-]+", "-", str(text or "").lower()).strip("-")[:60] or "ari-beispiele"


def dateien(zipdaten: bytes) -> dict[str, bytes]:
    """Inhalt des Exports – nur flache, harmlose Pfade."""
    if len(zipdaten) > MAX_BYTES:
        raise HubFehler("Der Export ist zu groß für den Upload.")
    aus: dict[str, bytes] = {}
    with zipfile.ZipFile(io.BytesIO(zipdaten)) as z:
        for info in z.infolist()[:MAX_DATEIEN]:
            name = info.filename
            if info.is_dir():
                continue
            if name.startswith("/") or ".." in Path(name).parts or "\\" in name:
                raise HubFehler("Der Export enthält einen ungültigen Dateinamen.")
            aus[name] = z.read(info)
    if "meta/info.json" not in aus:
        raise HubFehler("Das ist kein Export von Ari.")
    return aus


def _anzahl(n: int, eins: str, viele: str) -> str:
    return f"{n} {eins if n == 1 else viele}"


def karte(inhalt: dict[str, bytes], titel: str) -> str:
    """README des Repos aus `meta/info.json` und `meta/tasks.jsonl` – nur Zahlen und die Aufgabe."""
    info = json.loads(inhalt["meta/info.json"])
    aufgabe = ""
    if "meta/tasks.jsonl" in inhalt:
        zeile = inhalt["meta/tasks.jsonl"].decode("utf-8", "replace").splitlines()[:1]
        aufgabe = json.loads(zeile[0]).get("task", "") if zeile else ""
    kopf = ("---\n" + "task_categories:\n- robotics\n" + "tags:\n" + "".join(f"- {t}\n" for t in TAGS)
            + f"pretty_name: {json.dumps(titel, ensure_ascii=False)}\n---\n")
    zeilen = [
        f"# {titel}", "",
        f"Aufgabe: {aufgabe}" if aufgabe else "", "",
        f"{_anzahl(info.get('total_episodes', 0), 'Beispiel', 'Beispiele')}, "
        f"{_anzahl(info.get('total_frames', 0), 'Takt', 'Takte')}, {info.get('fps', '?')} Takte je "
        f"Sekunde, Roboter `{info.get('robot_type', '?')}`. Aus dem Simulator, ohne Kamerabilder.", "",
        "Rohformat aus Knowlin (JSON-Zeilen). Einen echten LeRobot-Datensatz daraus bauen:", "",
        "    pip install lerobot", "    python nach_lerobot.py --repo-id <name>/<datensatz>", "",
        "Enthält keine Bilder, keine Stimmen und nichts über Personen – nur Gelenkwinkel und die Lage von Würfel und Kiste.",
    ]
    return kopf + "\n".join(zeilen) + "\n"


def teile(zipdaten: bytes, token: str, *, name: str, oeffentlich: bool = False, api: Any = None) -> dict[str, Any]:
    """Hochladen nach `<du>/<name>` (Dataset). `api` ist für Tests austauschbar."""
    inhalt = dateien(zipdaten)
    if api is None:
        try:
            from huggingface_hub import HfApi
        except ImportError as exc:
            raise HubFehler("huggingface_hub fehlt – unter Lernen → Training installieren.") from exc
        api = HfApi(token=token)
    nutzer = api.whoami().get("name")
    if not isinstance(nutzer, str) or not nutzer:
        raise HubFehler("Der Hugging-Face-Schlüssel gehört zu keinem Konto.")
    repo = f"{nutzer}/{slug(name)}"
    api.create_repo(repo_id=repo, repo_type="dataset", private=not oeffentlich, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="ari-hub-") as tmp:
        for rel, daten in inhalt.items():
            ziel = Path(tmp, rel)
            ziel.parent.mkdir(parents=True, exist_ok=True)
            ziel.write_bytes(daten)
        Path(tmp, "README.md").write_text(karte(inhalt, f"Ari – {name}"), encoding="utf-8")
        api.upload_folder(folder_path=tmp, repo_id=repo, repo_type="dataset",
                          commit_message="Aris Beispiele aus Knowlin")
    return {"repo": repo, "url": f"{HUB}/datasets/{repo}", "oeffentlich": oeffentlich}
