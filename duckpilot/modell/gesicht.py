"""Gesichtserkennung für „Schau mich an“ (seit 0.39): MediaPipe Face Detection – nur auf Klick geladen.

Was es ist: Googles MediaPipe „Face Detection“ als npm-Paket `@mediapipe/face_detection` (Apache License 2.0), mit
WebAssembly-Laufzeit und dem Modell für nahe Gesichter (`face_detection_short_range.tflite`) im selben Paket. Es findet
im Kamerabild Gesichter und liefert je Gesicht nur ein Rechteck – es erkennt **nicht, wer** jemand ist.

Geladen und geprüft wie die Handerkennung (`modell/hand.py`):

- **Nichts beim Start.** Erst der Klick auf „Schau mich an“ lädt – nur am PC (`/api/schau…` steht in
  `remote.PC_ONLY`), nie im Offline-Modus.
- **Fester Stand, Prüfsumme je Datei** (`gesicht_quellen.json`): das npm-Paket (sha256) und jede der acht entnommenen
  Dateien (sha256, Größe); nie Pfade aus dem Archiv. Passt etwas nicht, wird nichts gespeichert.
- **Im Datenordner** (`<daten>/gesichtserkennung/`), nie im Paket; ausgeliefert vom eigenen Server
  (`/api/schau/dateien/<name>`).

Ausgewertet wird im Browser (`static/schau.js`): das Bild bleibt dort, an den Server geht nur die Blickrichtung.
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
from .hand import BLOCK, MAX_DOWNLOAD, _hole, mb

HERE = Path(__file__).resolve().parent
QUELLEN: dict[str, Any] = json.loads((HERE / "gesicht_quellen.json").read_text(encoding="utf-8"))
PAKET: dict[str, Any] = QUELLEN["laufzeit"]
DATEIEN: dict[str, dict[str, Any]] = PAKET["dateien"]
TYPEN = {".js": "text/javascript", ".wasm": "application/wasm"}
PLATTE_BYTES = sum(int(m["bytes"]) for m in DATEIEN.values())


def medientyp(name: str) -> str:
    return TYPEN.get(Path(name).suffix, "application/octet-stream")


class GesichtStore:
    """Liegt die Gesichtserkennung vor (geprüft)? Laden auf Wunsch, Dateien für den Server."""

    def __init__(self, root: Path, fetch: Callable[..., bytes] | None = None) -> None:
        self.dir = root / "gesichtserkennung"
        self.fetch = fetch or _hole
        self.job: dict[str, Any] = {}
        self._geprueft: tuple[Any, ...] | None = None

    def _signatur(self) -> tuple[Any, ...] | None:
        sig = []
        for name, meta in DATEIEN.items():
            try:
                st = (self.dir / name).stat()
            except OSError:
                return None
            if st.st_size != meta["bytes"]:
                return None
            sig.append((name, st.st_size, st.st_mtime_ns))
        return tuple(sig)

    def bereit(self) -> bool:
        sig = self._signatur()
        if sig is None:
            self._geprueft = None
            return False
        if sig != self._geprueft:
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
        return {"ok": True, "bereit": self.bereit(), "offline": offline(), "laden_mb": mb(int(PAKET["bytes"])),
                "platte_mb": mb(PLATTE_BYTES), "name": QUELLEN["name"], "lizenz": QUELLEN["lizenz"],
                "lizenz_url": QUELLEN["lizenz_url"], "seite": QUELLEN["seite"],
                "laufzeit": f"{PAKET['paket']} {PAKET['version']}", "job": dict(self.job)}

    def ensure(self, melden: Callable[[str], None] | None = None) -> dict[str, Any]:
        """Lädt das Paket, prüft es und jede Datei, schreibt erst, wenn alles stimmt."""
        melden = melden or (lambda _text: None)
        if self.bereit():
            return {"geladen": []}
        if offline():
            raise RuntimeError("Offline-Modus (DUCKPILOT_OFFLINE) – die Gesichtserkennung wird nicht geladen")
        groesse = int(PAKET["bytes"])
        if groesse > MAX_DOWNLOAD:
            raise ValueError("unerwartet große Quelle")

        def stand(n: int) -> None:
            melden(f"lade die Gesichtserkennung ({mb(groesse)}) … {min(99, n * 100 // groesse)} %")

        data = self.fetch(PAKET["url"], groesse + BLOCK, stand)
        if len(data) != groesse or hashlib.sha256(data).hexdigest() != PAKET["sha256"]:
            raise ValueError("Gesichtserkennung: Prüfsumme passt nicht – Download abgebrochen")
        fertig: dict[str, bytes] = {}
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
            for name, meta in DATEIEN.items():
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
        self.dir.mkdir(parents=True, exist_ok=True)
        for name, inhalt in fertig.items():
            tmp = self.dir / (name + ".teil")
            tmp.write_bytes(inhalt)
            tmp.replace(self.dir / name)
        if not self.bereit():
            raise ValueError("Nach dem Laden passt eine Prüfsumme nicht")
        (self.dir / "geladen.txt").write_text(time.strftime("%Y-%m-%d %H:%M"), encoding="utf-8")
        return {"geladen": ["paket"]}


def store() -> GesichtStore:
    from .. import settings as S

    return GesichtStore(S.settings_path().parent)
