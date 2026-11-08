"""Handerkennung für die Kamera-Spiele (seit 0.38.14): MediaPipe Hand Landmarker – nur auf Klick geladen.

Was es ist: Googles MediaPipe „Hand Landmarker“ (Modell `hand_landmarker.task`, Laufzeit `@mediapipe/tasks-vision`
mit WebAssembly), beides unter der Apache License 2.0. Es findet in einem Kamerabild eine Hand und liefert 21 Punkte
(Handgelenk, Fingergelenke, Fingerspitzen) – keine Gesichter, keine Personen.

Wie es geladen wird (wie Pollens Modell in `modell/__init__.py`):

- **Nichts beim Start.** Erst der Klick „Handerkennung laden“ (Steuern → Spiele) lädt – nur am PC
  (`/api/spiele…` steht in `remote.PC_ONLY`), nie im Offline-Modus.
- **Fester Stand, Prüfsumme je Datei** (`hand_quellen.json`): die Laufzeit als npm-Paket (Tarball, sha256 des Pakets
  und jeder entnommenen Datei – nur die fünf gebrauchten Dateien werden entnommen, nie Pfade aus dem Archiv), das
  Modell von Googles Modellablage (sha256). Passt eine Prüfsumme nicht, wird nichts gespeichert.
- **Im Datenordner** (`<daten>/handerkennung/`), nie im Paket. Ausgeliefert wird es vom eigenen Server
  (`/api/spiele/hand/dateien/<name>`); der Browser lädt zur Laufzeit nichts aus dem Netz.

Ausgewertet wird im Browser (`static/hand.js`): Bilder bleiben dort, an den Server gehen nur Richtung und Zahlen.
"""

from __future__ import annotations

import hashlib
import io
import json
import tarfile
import time
from pathlib import Path
from typing import Any, Callable

from . import offline

HERE = Path(__file__).resolve().parent
QUELLEN: dict[str, Any] = json.loads((HERE / "hand_quellen.json").read_text(encoding="utf-8"))
LAUFZEIT: dict[str, Any] = QUELLEN["laufzeit"]
MODELL: dict[str, Any] = QUELLEN["modell"]

# Alle Dateien, die der Server ausliefert: Name → (sha256, Bytes, Medientyp)
TYPEN = {".mjs": "text/javascript", ".js": "text/javascript", ".wasm": "application/wasm",
         ".task": "application/octet-stream"}
DATEIEN: dict[str, dict[str, Any]] = {
    **{name: {"sha256": m["sha256"], "bytes": m["bytes"]} for name, m in LAUFZEIT["dateien"].items()},
    MODELL["datei"]: {"sha256": MODELL["sha256"], "bytes": MODELL["bytes"]},
}
DOWNLOAD_BYTES = int(LAUFZEIT["bytes"]) + int(MODELL["bytes"])
PLATTE_BYTES = sum(int(m["bytes"]) for m in DATEIEN.values())
MAX_DOWNLOAD = 64 * 1024 * 1024       # mehr nimmt kein einzelner Abruf an
BLOCK = 256 * 1024


def medientyp(name: str) -> str:
    return TYPEN.get(Path(name).suffix, "application/octet-stream")


def mb(n: int) -> str:
    """„14 MB“ – deutsch, ganze MB."""
    return f"{round(n / 1e6):.0f} MB"


def _hole(url: str, max_bytes: int, fortschritt: Callable[[int], None] | None = None) -> bytes:
    """Lädt eine Datei in Blöcken (höchstens `max_bytes`), meldet den Stand in Bytes."""
    import urllib.request

    req = urllib.request.Request(url, headers={"User-Agent": "Knowlin duckpilot (Handerkennung)"})
    teile: list[bytes] = []
    n = 0
    with urllib.request.urlopen(req, timeout=60) as res:
        while True:
            block = res.read(BLOCK)
            if not block:
                break
            n += len(block)
            if n > max_bytes:
                raise ValueError(f"{url}: größer als erwartet – Download abgebrochen")
            teile.append(block)
            if fortschritt:
                fortschritt(n)
    return b"".join(teile)


class HandStore:
    """Liegt die Handerkennung vor (geprüft)? Laden auf Wunsch, Dateien für den Server."""

    def __init__(self, root: Path, fetch: Callable[..., bytes] | None = None) -> None:
        self.dir = root / "handerkennung"
        self.fetch = fetch or _hole
        self.job: dict[str, Any] = {}
        self._geprueft: tuple[Any, ...] | None = None    # Größe und Zeit der zuletzt geprüften Dateien

    # ── was liegt vor ────────────────────────────────────────────────────
    def _signatur(self) -> tuple[Any, ...] | None:
        sig = []
        for name, meta in DATEIEN.items():
            p = self.dir / name
            try:
                st = p.stat()
            except OSError:
                return None
            if st.st_size != meta["bytes"]:
                return None
            sig.append((name, st.st_size, st.st_mtime_ns))
        return tuple(sig)

    def bereit(self) -> bool:
        """Alle Dateien da und mit passender Prüfsumme (einmal je Stand gerechnet, dann gemerkt)."""
        sig = self._signatur()
        if sig is None:
            self._geprueft = None
            return False
        if sig == self._geprueft:
            return True
        for name, meta in DATEIEN.items():
            if hashlib.sha256((self.dir / name).read_bytes()).hexdigest() != meta["sha256"]:
                self._geprueft = None
                return False
        self._geprueft = sig
        return True

    def datei(self, name: str) -> Path | None:
        """Pfad einer ausgelieferten Datei – nur bekannte Namen und nur, wenn alles geprüft vorliegt."""
        if name not in DATEIEN or not self.bereit():
            return None
        return self.dir / name

    def status(self) -> dict[str, Any]:
        try:
            wann = (self.dir / "geladen.txt").read_text(encoding="utf-8").strip()
        except OSError:
            wann = None
        return {"ok": True, "bereit": self.bereit(), "geladen": wann, "offline": offline(),
                "laden_mb": mb(DOWNLOAD_BYTES), "platte_mb": mb(PLATTE_BYTES),
                "name": QUELLEN["name"], "lizenz": QUELLEN["lizenz"], "lizenz_url": QUELLEN["lizenz_url"],
                "seite": QUELLEN["seite"], "laufzeit": f"{LAUFZEIT['paket']} {LAUFZEIT['version']}",
                "laufzeit_seite": LAUFZEIT["seite"], "modell_stand": MODELL["stand"],
                "job": dict(self.job)}

    # ── laden ────────────────────────────────────────────────────────────
    def _schreiben(self, name: str, data: bytes) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        ziel = self.dir / name
        tmp = ziel.with_name(name + ".teil")
        tmp.write_bytes(data)
        tmp.replace(ziel)

    def _laufzeit_laden(self, melden: Callable[[str], None]) -> None:
        groesse = mb(LAUFZEIT["bytes"])

        def stand(n: int) -> None:
            melden(f"lade die Laufzeit ({groesse}) … {min(99, n * 100 // LAUFZEIT['bytes'])} %")

        data = self.fetch(LAUFZEIT["url"], LAUFZEIT["bytes"] + BLOCK, stand)
        if len(data) != LAUFZEIT["bytes"] or hashlib.sha256(data).hexdigest() != LAUFZEIT["sha256"]:
            raise ValueError("Laufzeit: Prüfsumme passt nicht – Download abgebrochen")
        fertig: dict[str, bytes] = {}
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
            for name, meta in LAUFZEIT["dateien"].items():
                try:
                    eintrag = tar.getmember(meta["im_paket"])
                except KeyError:
                    raise ValueError(f"{name}: fehlt im Paket – Download abgebrochen") from None
                if not eintrag.isfile() or eintrag.size != meta["bytes"]:
                    raise ValueError(f"{name}: unerwartete Größe – Download abgebrochen")
                f = tar.extractfile(eintrag)
                inhalt = f.read() if f is not None else b""
                if hashlib.sha256(inhalt).hexdigest() != meta["sha256"]:
                    raise ValueError(f"{name}: Prüfsumme passt nicht – Download abgebrochen")
                fertig[name] = inhalt
        for name, inhalt in fertig.items():            # erst schreiben, wenn alle fünf stimmen
            self._schreiben(name, inhalt)

    def _modell_laden(self, melden: Callable[[str], None]) -> None:
        groesse = mb(MODELL["bytes"])

        def stand(n: int) -> None:
            melden(f"lade das Handmodell ({groesse}) … {min(99, n * 100 // MODELL['bytes'])} %")

        data = self.fetch(MODELL["url"], MODELL["bytes"] + BLOCK, stand)
        if len(data) != MODELL["bytes"] or hashlib.sha256(data).hexdigest() != MODELL["sha256"]:
            raise ValueError("Handmodell: Prüfsumme passt nicht – Download abgebrochen")
        self._schreiben(MODELL["datei"], data)

    def ensure(self, melden: Callable[[str], None] | None = None) -> dict[str, Any]:
        """Lädt, was fehlt oder nicht stimmt. Gibt zurück, was geladen wurde."""
        melden = melden or (lambda _text: None)
        if self.bereit():
            return {"geladen": []}
        if offline():
            raise RuntimeError("Offline-Modus (DUCKPILOT_OFFLINE) – die Handerkennung wird nicht geladen")
        if max(LAUFZEIT["bytes"], MODELL["bytes"]) > MAX_DOWNLOAD:
            raise ValueError("unerwartet große Quelle")
        geladen = []
        laufzeit_ok = all(self._passt(n) for n in LAUFZEIT["dateien"])
        if not laufzeit_ok:
            self._laufzeit_laden(melden)
            geladen.append("laufzeit")
        if not self._passt(MODELL["datei"]):
            self._modell_laden(melden)
            geladen.append("modell")
        if not self.bereit():
            raise ValueError("Nach dem Laden passt eine Prüfsumme nicht")
        (self.dir / "geladen.txt").write_text(time.strftime("%Y-%m-%d %H:%M"), encoding="utf-8")
        return {"geladen": geladen}

    def _passt(self, name: str) -> bool:
        p = self.dir / name
        meta = DATEIEN[name]
        try:
            return p.stat().st_size == meta["bytes"] and hashlib.sha256(p.read_bytes()).hexdigest() == meta["sha256"]
        except OSError:
            return False


def store() -> HandStore:
    from .. import settings as S

    return HandStore(S.settings_path().parent)
