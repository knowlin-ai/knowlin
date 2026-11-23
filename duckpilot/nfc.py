"""NFC-Tags als Auslöser: einen Tag berühren – die Ente tut, was ihm zugeordnet ist.

Ein Tag wird an seiner Seriennummer (UID) erkannt; beschrieben werden muss er nicht. Zugeordnet ist ihm ein
Satz, so wie man ihn der Ente sagen würde („setz dich“, „tanz“, „zeig mir, wie du lachst“). Berühren schickt
genau diesen Satz durch dieselbe Verarbeitung wie ein getippter Befehl – mit allen Sicherheitsregeln
(Not-Aus gewinnt, 120 s Sperre, Aufstehen nach Sturz erst nach dem Stopp-Fenster). Kurze Befehle erledigt duckpilot ohne Claude.

Woher die Berührung kommt:
- **Handy** (Chrome unter Android, Web NFC): auf der Alltag-Seite „Tags lesen“ – nur über eine https-Adresse,
  also mit Tailscale. Das ist heute der Weg.
- **Ohne Lesegerät:** „Auslösen“ in der Liste – zum Ausprobieren im Simulator.
- **Roboter:** Pollens `nfcd` handelt bei seinen eigenen Tags selbst (Gamepad koppeln, Gehen, Rollen, Laser, Fußball,
  „die Ente allein“, Foto) und meldet Berührungen nicht weiter. Knowlin sieht danach nur, welches Spiel läuft
  (robot.state, `backends/robotd.py` `pollen_an`).

Pollens Tags (seit 0.52): Trägt ein Tag einen von Pollens Texten (`walk_mode`, `soccer_mode` …, Pollens
`docs/robot/nfc-tags.md`), schlägt Knowlin beim ersten Berühren den passenden eigenen Satz vor – so tun Pollens Karten
auch im Simulator, was auf der Karte steht. Der Satz lässt sich danach wie jeder andere ändern.

Die Zuordnungen liegen lokal in `nfc_tags.json` im Datenordner.
"""

from __future__ import annotations

import json
import re
import secrets
import time
from pathlib import Path
from typing import Any

UID_RE = re.compile(r"^[A-Za-z0-9_-]{2,40}$")
MAX_TAGS = 50
MAX_SATZ = 200
VORSCHLAEGE = ("setz dich", "steh auf", "tanz", "zeig mir, wie du lachst", "sag hallo", "Ruhemodus", "lauf zum Ball und schieß ihn")


# Pollens Tag-Texte → Name und Knowlins Satz (None: das macht nur der echte Roboter, Knowlin sagt es nur)
POLLEN_TAGS: dict[str, tuple[str, str | None]] = {
    "walk_mode": ("Pollen: Gehen", "Rollen ab"),
    "roller_skating_mode": ("Pollen: Rollschuh", "Rollen an"),
    "laser_mode": ("Pollen: Laser", "folge dem Laser"),
    "soccer_mode": ("Pollen: Fußball", "spiel Ball mit mir"),
    "autonomous_mode": ("Pollen: Ente allein", "streif ein bisschen herum"),
    "take_photo": ("Pollen: Foto", None),
    "microduck_gamepad_pairing": ("Pollen: Gamepad koppeln", None),
}


def pollen_tag(text: Any) -> str | None:
    """Pollens Regel: Der ganze Text ist die Nachricht – Leerzeichen außen egal, Groß/klein egal."""
    key = str(text or "").strip().lower()
    return key if key in POLLEN_TAGS else None


def normalize_uid(uid: Any) -> str | None:
    """„04:A2:3B:…“ → „04A23B…“. Gibt None zurück, wenn es keine gültige Kennung ist."""
    raw = re.sub(r"[\s:.]", "", str(uid or "")).strip()
    if not UID_RE.match(raw):
        return None
    return raw.upper() if re.fullmatch(r"[0-9A-Fa-f]+", raw) else raw


class TagStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        try:
            data = json.loads(path.read_text("utf-8"))
            self.tags: list[dict[str, Any]] = [t for t in data.get("tags", []) if isinstance(t, dict) and t.get("uid")]
        except (OSError, ValueError, AttributeError):
            self.tags = []

    def _save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps({"tags": self.tags}, ensure_ascii=False, indent=1), "utf-8")
        except OSError:
            pass

    def find(self, uid: str) -> dict[str, Any] | None:
        return next((t for t in self.tags if t["uid"] == uid), None)

    def message(self) -> dict[str, Any]:
        return {"type": "nfc", "tags": self.tags, "vorschlaege": list(VORSCHLAEGE)}

    def put(self, uid: Any, name: Any = None, satz: Any = None) -> dict[str, Any]:
        """Anlegen oder ändern. uid "neu" legt einen Probe-Tag ohne Lesegerät an."""
        key = "TEST-" + secrets.token_hex(3).upper() if uid == "neu" else normalize_uid(uid)
        if not key:
            return {"ok": False, "fehler": "Diese Tag-Kennung verstehe ich nicht."}
        tag = self.find(key)
        if tag is None:
            if len(self.tags) >= MAX_TAGS:
                return {"ok": False, "fehler": f"Mehr als {MAX_TAGS} Tags gehen nicht."}
            tag = {"uid": key, "name": "", "satz": "", "zuletzt": None}
            self.tags.append(tag)
        if name is not None:
            tag["name"] = str(name).strip()[:40]
        if satz is not None:
            tag["satz"] = str(satz).strip()[:MAX_SATZ]
        if not tag["name"]:
            tag["name"] = f"Tag {len(self.tags)}"
        self._save()
        return {"ok": True, "tag": tag}

    def remove(self, uid: Any) -> bool:
        key = normalize_uid(uid)
        before = len(self.tags)
        self.tags = [t for t in self.tags if t["uid"] != key]
        if len(self.tags) != before:
            self._save()
            return True
        return False

    def touched(self, uid: Any, text: Any = None) -> dict[str, Any]:
        """Ein Tag wurde berührt. Unbekannt → wird als neuer Tag gemerkt; trägt er einen von Pollens Texten, mit
        Pollens Namen und Knowlins passendem Satz (seit 0.52), sonst ohne Satz."""
        key = normalize_uid(uid)
        if not key:
            return {"ok": False, "fehler": "Diese Tag-Kennung verstehe ich nicht."}
        tag = self.find(key)
        neu = tag is None
        pollen = pollen_tag(text)
        if neu:
            name, satz = POLLEN_TAGS[pollen] if pollen else (None, None)
            res = self.put(key, name, satz)
            if not res["ok"]:
                return res
            tag = res["tag"]
        tag["zuletzt"] = time.strftime("%Y-%m-%d %H:%M")
        self._save()
        res = {"ok": True, "tag": tag, "neu": neu, "satz": tag.get("satz") or ""}
        if pollen:
            res["pollen"] = pollen
            if POLLEN_TAGS[pollen][1] is None and not res["satz"]:
                res["hinweis"] = ("Das ist Pollens Gamepad-Karte – sie koppelt am echten Roboter ein Gamepad."
                                  if pollen == "microduck_gamepad_pairing" else
                                  "Das ist Pollens Foto-Karte – am echten Roboter macht sie ein Foto (Roboter-Pflege → "
                                  "Fotos der Ente). Im Simulator: Steuern → Zubehör → Foto machen.")
        return res
