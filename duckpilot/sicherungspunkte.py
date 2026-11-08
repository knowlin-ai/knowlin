"""Sicherungspunkte für Gedächtnis, Erfahrung und Verhalten (seit 0.38.24).

Wunsch: „in den Einstellungen sollten bestimmte Sachen wieder resettet werden können. Ggf. kann man zuvor
Zwischenstände zum Wissen oder Verhalten etc. exportieren oder hat mehrere Versionen mit Historie – wie im Leben –
manchmal will man bestimmte Erlebnisse am besten eigentlich wieder rückgängig machen.“

Ein Sicherungspunkt ist ein Ordner unter `<Datenordner>/sicherungspunkte/<Zeit>-<Art>/` mit `punkt.json` (Zeit, Name,
Art, Bereiche, Zahlen) und den Dateien der gesicherten Bereiche. Bereiche:

- `gedaechtnis` – Wissen, Vorlieben, Orte, Tricks und Tagebuch (memory.json)
- `erfahrung` – das Erfahrungsnetz der Hirnaktivität (erfahrung.json)
- `charakter` – Charakter je Verkörperung (Energie, Humor, Eigenschaften, Eigenständigkeit)
- `uebungen` – eingeübte Akrobatik und Posen (akrobatik.json)
- `taenze` – eigene Choreografien (choreos.json; die Musikstücke selbst bleiben, wo sie sind)
- `raum` – Karten und zuletzt gesehene Dinge je Körper (raum/*.json)

Nie in einem Sicherungspunkt: Personen (Gesichter), Schlüssel, Einstellungen. Automatisch entsteht ein Punkt pro Tag
(die letzten `AUTO_BEHALTEN` bleiben) und einer vor jedem Zurücksetzen und Wiederherstellen (die letzten `VOR_BEHALTEN`);
selbst angelegte und importierte Punkte löscht nur der Mensch. Export und Import als ZIP – nur am PC.

Dieses Modul kennt nur Dateien; was die laufenden Teile neu laden müssen, macht `server/sicherung.py`.
"""

from __future__ import annotations

import io
import json
import re
import shutil
import time
import zipfile
from pathlib import Path
from typing import Any

BEREICHE: dict[str, dict[str, str]] = {
    "gedaechtnis": {"titel": "Gedächtnis", "text": "Wissen, Vorlieben, Orte, Tricks und Tagebuch"},
    "erfahrung": {"titel": "Erfahrungsnetz", "text": "Knoten und Verbindungen der Hirnaktivität"},
    "charakter": {"titel": "Charakter", "text": "Energie, Humor, Eigenschaften und Eigenständigkeit je Verkörperung"},
    "uebungen": {"titel": "Übungen", "text": "eingeübte Akrobatik und Posen"},
    "taenze": {"titel": "Tänze", "text": "eigene Choreografien (die Musik bleibt, wo sie ist)"},
    "raum": {"titel": "Raum", "text": "Karten und zuletzt gesehene Dinge"},
}
ARTEN = ("hand", "auto", "vor-zuruecksetzen", "vor-wiederherstellen", "import")
AUTO_BEHALTEN = 14
VOR_BEHALTEN = 10
MAX_DATEI = 20 * 1024 * 1024
MAX_ZIP = 60 * 1024 * 1024
CHARAKTER_KEYS = ("energie", "humor", "eigenschaften", "eigenstaendig", "idle_life", "plaudern")
_RAUM = re.compile(r"^raum/(karte|sichtungen)-[a-z_]{1,32}\.json$")
_ID = re.compile(r"^\d{8}-\d{6}(-\d+)?-[a-z\-]{3,24}$")


class SicherungFehler(ValueError):
    pass


def _dateien(bereich: str, quellen: dict[str, Path]) -> list[tuple[str, Path]]:
    """(Name im Punkt, Pfad im Datenordner) eines Bereichs – nur Dateien, die es gibt."""
    root = quellen["daten"]
    if bereich == "gedaechtnis":
        paare = [("memory.json", quellen["gedaechtnis"])]
    elif bereich == "erfahrung":
        paare = [("erfahrung.json", root / "erfahrung.json")]
    elif bereich == "uebungen":
        paare = [("akrobatik.json", root / "akrobatik.json")]
    elif bereich == "taenze":
        paare = [("choreos.json", root / "choreos.json")]
    elif bereich == "raum":
        ordner = root / "raum"
        paare = [(f"raum/{p.name}", p) for p in sorted(ordner.glob("*.json"))] if ordner.is_dir() else []
        paare = [(n, p) for n, p in paare if _RAUM.match(n)]
    else:                                                       # charakter: kommt als Werte, nicht als Datei
        paare = []
    return [(n, p) for n, p in paare if p.is_file()]


def _zahlen(bereich: str, lesen) -> dict[str, int]:
    """Was in einem Bereich steckt – für die Liste („42 Erinnerungen, 310 Verbindungen“)."""
    try:
        if bereich == "gedaechtnis":
            d = lesen("memory.json") or {}
            tricks = len(d.get("tricks") or {}) + sum(len(t or {}) for t in (d.get("tricks_je_figur") or {}).values())
            return {"wissen": len(d.get("wissen") or []), "vorlieben": len(d.get("vorlieben") or []),
                    "orte": len(d.get("orte") or {}), "tricks": tricks, "tagebuch": len(d.get("protokoll") or [])}
        if bereich == "erfahrung":
            d = lesen("erfahrung.json") or {}
            return {"knoten": len(d.get("knoten") or {}), "verbindungen": len(d.get("kanten") or {})}
        if bereich == "uebungen":
            d = lesen("akrobatik.json") or {}
            return {"uebungen": len(d.get("uebungen") or {}), "posen": len(d.get("posen") or {})}
        if bereich == "taenze":
            d = lesen("choreos.json") or {}
            return {"taenze": len([v for v in d.values() if isinstance(v, dict)])}
        if bereich == "raum":
            return {"dateien": lesen("raum") or 0}
        if bereich == "charakter":
            return {"verkoerperungen": len(lesen("charakter.json") or {})}
    except (AttributeError, TypeError):
        pass
    return {}


class Sicherungspunkte:
    """Sicherungspunkte im Datenordner. `quellen`: {"daten": Datenordner, "gedaechtnis": Pfad der memory.json}."""

    def __init__(self, daten: Path, gedaechtnis: Path) -> None:
        self.quellen = {"daten": Path(daten), "gedaechtnis": Path(gedaechtnis)}
        self.ordner = Path(daten) / "sicherungspunkte"

    # ── Liste ─────────────────────────────────────────────────────────────
    def liste(self) -> list[dict[str, Any]]:
        out = []
        if self.ordner.is_dir():
            for d in self.ordner.iterdir():
                p = self._punkt(d)
                if p:
                    out.append(p)
        return sorted(out, key=lambda p: p["id"], reverse=True)

    def _punkt(self, d: Path) -> dict[str, Any] | None:
        if not d.is_dir() or not _ID.match(d.name):
            return None
        try:
            meta = json.loads((d / "punkt.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if not isinstance(meta, dict):
            return None
        groesse = sum(f.stat().st_size for f in d.rglob("*") if f.is_file())
        return {"id": d.name, "zeit": meta.get("zeit"), "name": str(meta.get("name") or "")[:60],
                "art": meta.get("art") if meta.get("art") in ARTEN else "hand",
                "bereiche": [b for b in meta.get("bereiche", []) if b in BEREICHE],
                "zahlen": meta.get("zahlen") if isinstance(meta.get("zahlen"), dict) else {}, "kb": max(1, groesse // 1024)}

    def pfad(self, pid: str) -> Path:
        if not isinstance(pid, str) or not _ID.match(pid) or not (self.ordner / pid / "punkt.json").is_file():
            raise SicherungFehler("Diesen Sicherungspunkt gibt es nicht.")
        return self.ordner / pid

    # ── Anlegen ───────────────────────────────────────────────────────────
    def jetzt(self) -> dict[str, dict[str, int]]:
        """Zahlen des aktuellen Stands je Bereich (ohne Charakter – den kennt nur die Laufzeit)."""
        out = {}
        for b in BEREICHE:
            if b == "charakter":
                continue
            dateien = dict(_dateien(b, self.quellen))
            out[b] = _zahlen(b, lambda n, dateien=dateien: len(dateien) if n == "raum" else _json(dateien.get(n)))
        return out

    def anlegen(self, art: str = "hand", name: str = "", bereiche: list[str] | None = None,
                charakter: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
        if art not in ARTEN:
            raise SicherungFehler("unbekannte Art")
        bereiche = [b for b in (bereiche or list(BEREICHE)) if b in BEREICHE]
        if not bereiche:
            raise SicherungFehler("Kein Bereich gewählt.")
        ziel = self._neuer_ordner(art)
        try:
            for b in bereiche:
                for name_im_punkt, quelle in _dateien(b, self.quellen):
                    z = ziel / name_im_punkt
                    z.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(quelle, z)
            if "charakter" in bereiche and charakter is not None:
                (ziel / "charakter.json").write_text(json.dumps(charakter, ensure_ascii=False), encoding="utf-8")
            meta = {"version": 1, "zeit": time.strftime("%Y-%m-%dT%H:%M:%S"), "name": str(name or "").strip()[:60],
                    "art": art, "bereiche": bereiche, "zahlen": self._zahlen_im(ziel, bereiche)}
            (ziel / "punkt.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
        except Exception:
            shutil.rmtree(ziel, ignore_errors=True)
            raise
        self.aufraeumen()
        return self._punkt(ziel) or {}

    def _neuer_ordner(self, art: str) -> Path:
        self.ordner.mkdir(parents=True, exist_ok=True)
        basis = time.strftime("%Y%m%d-%H%M%S")
        for i in range(100):
            d = self.ordner / (f"{basis}-{art}" if i == 0 else f"{basis}-{i}-{art}")
            try:
                d.mkdir()
                return d
            except FileExistsError:
                continue
        raise SicherungFehler("Zu viele Sicherungspunkte in einer Sekunde.")

    @staticmethod
    def _zahlen_im(ordner: Path, bereiche: list[str]) -> dict[str, dict[str, int]]:
        def lesen(n: str) -> Any:
            if n == "raum":
                return len(list((ordner / "raum").glob("*.json"))) if (ordner / "raum").is_dir() else 0
            return _json(ordner / n)
        return {b: _zahlen(b, lesen) for b in bereiche}

    def taeglich(self, charakter: dict[str, dict[str, Any]] | None = None, stunden: float = 20.0) -> dict[str, Any] | None:
        """Einmal am Tag automatisch (beim Start) – nur, wenn es überhaupt etwas zu sichern gibt."""
        letzte = next((p for p in self.liste() if p["art"] == "auto"), None)
        if letzte and time.time() - self._zeit(letzte["id"]) < stunden * 3600:
            return None
        # nur, wenn es wirklich etwas zu sichern gibt – eine frische Installation braucht keinen leeren Punkt
        if not any(v for z in self.jetzt().values() for v in z.values()):
            return None
        return self.anlegen("auto", "", None, charakter)

    @staticmethod
    def _zeit(pid: str) -> float:
        try:
            return time.mktime(time.strptime(pid[:15], "%Y%m%d-%H%M%S"))
        except ValueError:
            return 0.0

    def aufraeumen(self) -> None:
        """Nur automatische Punkte werden ausgedünnt; selbst angelegte und importierte bleiben."""
        punkte = self.liste()
        for arten, behalten in ((("auto",), AUTO_BEHALTEN), (("vor-zuruecksetzen", "vor-wiederherstellen"), VOR_BEHALTEN)):
            for p in [p for p in punkte if p["art"] in arten][behalten:]:
                shutil.rmtree(self.ordner / p["id"], ignore_errors=True)

    def loeschen(self, pid: str) -> None:
        shutil.rmtree(self.pfad(pid))

    # ── Zurückholen ───────────────────────────────────────────────────────
    def dateien_im(self, pid: str, bereich: str) -> list[tuple[Path, Path]]:
        """(Datei im Punkt, Ziel im Datenordner) für einen Bereich."""
        d = self.pfad(pid)
        root = self.quellen["daten"]
        if bereich == "gedaechtnis":
            paare = [(d / "memory.json", self.quellen["gedaechtnis"])]
        elif bereich in ("erfahrung", "uebungen", "taenze"):
            n = {"erfahrung": "erfahrung.json", "uebungen": "akrobatik.json", "taenze": "choreos.json"}[bereich]
            paare = [(d / n, root / n)]
        elif bereich == "raum":
            paare = [(f, root / "raum" / f.name) for f in sorted((d / "raum").glob("*.json"))] if (d / "raum").is_dir() else []
        else:
            paare = []
        return [(q, z) for q, z in paare if q.is_file()]

    def charakter_im(self, pid: str) -> dict[str, dict[str, Any]]:
        roh = _json(self.pfad(pid) / "charakter.json")
        if not isinstance(roh, dict):
            return {}
        return {m: {k: v for k, v in w.items() if k in CHARAKTER_KEYS} for m, w in roh.items() if isinstance(w, dict)}

    # ── Export / Import ───────────────────────────────────────────────────
    def export(self, pid: str) -> bytes:
        d = self.pfad(pid)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for f in sorted(d.rglob("*")):
                if f.is_file():
                    z.write(f, f.relative_to(d).as_posix())
        return buf.getvalue()

    def importieren(self, daten: bytes) -> dict[str, Any]:
        """ZIP eines Sicherungspunkts annehmen – nur bekannte Dateinamen, nur gültiges JSON, Größen begrenzt."""
        if len(daten) > MAX_ZIP:
            raise SicherungFehler("Die Datei ist zu groß.")
        try:
            z = zipfile.ZipFile(io.BytesIO(daten))
        except zipfile.BadZipFile as exc:
            raise SicherungFehler("Das ist keine Knowlin-Sicherung (kein ZIP).") from exc
        erlaubt = {"punkt.json", "memory.json", "erfahrung.json", "akrobatik.json", "choreos.json", "charakter.json"}
        inhalt: dict[str, bytes] = {}
        for info in z.infolist():
            if info.is_dir():
                continue
            n = info.filename
            if n not in erlaubt and not _RAUM.match(n):
                raise SicherungFehler(f"Unbekannte Datei in der Sicherung: {n[:60]}")
            if info.file_size > MAX_DATEI:
                raise SicherungFehler(f"{n} ist zu groß.")
            roh = z.read(info)
            try:
                json.loads(roh.decode("utf-8"))
            except (UnicodeDecodeError, ValueError) as exc:
                raise SicherungFehler(f"{n} ist kein gültiges JSON.") from exc
            inhalt[n] = roh
        try:
            meta = json.loads(inhalt.get("punkt.json", b"{}"))
        except ValueError:
            meta = {}
        if not isinstance(meta, dict) or "punkt.json" not in inhalt:
            raise SicherungFehler("Das ist keine Knowlin-Sicherung (punkt.json fehlt).")
        bereiche = [b for b in meta.get("bereiche", []) if b in BEREICHE]
        ziel = self._neuer_ordner("import")
        for n, roh in inhalt.items():
            if n == "punkt.json":
                continue
            (ziel / n).parent.mkdir(parents=True, exist_ok=True)
            (ziel / n).write_bytes(roh)
        alt = str(meta.get("zeit") or "")[:19]
        name = str(meta.get("name") or "").strip()[:40] or (f"Stand vom {alt[:10]}" if alt else "Import")
        neu = {"version": 1, "zeit": time.strftime("%Y-%m-%dT%H:%M:%S"), "name": name, "art": "import",
               "bereiche": bereiche, "von": alt, "zahlen": self._zahlen_im(ziel, bereiche)}
        (ziel / "punkt.json").write_text(json.dumps(neu, ensure_ascii=False, indent=1), encoding="utf-8")
        return self._punkt(ziel) or {}


def _json(p: Path | None) -> Any:
    if p is None:
        return None
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
