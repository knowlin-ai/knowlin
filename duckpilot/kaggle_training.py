"""Kostenlos trainieren – Pollens Training auf Kaggle Notebooks statt auf bezahlten Hugging Face Jobs.

Kaggle schenkt jedem Konto rund 30 GPU-Stunden pro Woche (NVIDIA T4, eine Sitzung höchstens 12 h,
keine Kreditkarte). duckpilot schickt dafür ein kleines Python-Skript als *privates* Kaggle-Skript
(„Kernel“) los. Das Skript

1. prüft die zugeteilte GPU (T4 = sm_75 ist das Minimum, siehe unten),
2. lädt den aktuellen Stand von `pollen-robotics/microduck_rl` von GitHub und richtet ihn mit `uv` ein,
3. trainiert mit `uv run train <Aufgabe> …` – genau die Argumente wie bei Hugging Face (`training.train_args`),
   auf Wunsch von Pollens geteiltem Stand (`--init-checkpoint hf://…`, öffentlich, kein Token nötig)
   oder vom Zwischenstand eines eigenen Kaggle-Laufs (als Datenquelle eingebunden),
4. hält das Training **vor** Kaggles 12-Stunden-Grenze von selbst an (Wanduhr), exportiert den neuesten
   Zwischenstand mit Pollens `scripts/export.py` nach ONNX und legt ab:
   `policy.onnx`, `metrics.json` (Lernkurve, Zusammenfassung), `checkpoint/model_<N>.pt`.

Die Ergebnisse sind Ausgabedateien des Kernels – es braucht also keinen Hugging-Face-Token.
Während des Laufs schreibt das Skript knappe Fortschrittsblöcke im rsl_rl-Format ins Protokoll, die
`training.parse_log` liest, und Zeilen `[duckpilot] {…}` mit der aktuellen Phase.

Grafikkarte: Kaggle bietet „GPU T4 ×2“ (`NvidiaTeslaT4`, Standard) und – inzwischen ausgemustert –
die P100. Pollens Abhängigkeiten schließen die P100 (sm_60) aus: torch 2.9.1 von PyPI ist mit CUDA 12.8
gebaut und enthält keinen Code mehr für Pascal, und Warp 1.12 nennt sm_75 als kleinste Architektur, die
alle Funktionen kann. Deshalb immer `NvidiaTeslaT4`; mjlab nutzt davon eine Karte (`--gpu-ids` bleibt [0],
denn mit mehreren Karten leitet mjlab die Ausgabe in Dateien um und die Lernkurve fehlte).

Zugangsdaten (Benutzername + API-Schlüssel) liegen nur im Tresor des Systems, nie in einer Datei.
Kaggle verlangt für GPU und Internet ein per Telefon bestätigtes Konto.

Anders als bezahlte Läufe darf Claude kostenlose Läufe selbst starten (`is_free`); jeder Lauf hat
deshalb eine feste Obergrenze (`HARD_CAP_STUNDEN`), die Kaggle zusätzlich serverseitig durchsetzt.

Schnittstelle: Kaggles öffentliche API (wie das offizielle `kaggle`-Paket / kagglesdk), per HTTPS mit urllib:
`POST https://api.kaggle.com/v1/kernels.KernelsApiService/<Methode>` mit JSON,
`GET https://api.kaggle.com/v1/kernels/logs/stream/<besitzer>/<kernel>` für das laufende Protokoll.
"""

from __future__ import annotations

import base64
import datetime as dt
import inspect
import json
import logging
import math
import re
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from . import training as T

log = logging.getLogger(__name__)

API = "https://api.kaggle.com/v1"
WEB = "https://www.kaggle.com"
SERVICE = "kernels.KernelsApiService"
MACHINE_SHAPE = "NvidiaTeslaT4"            # „GPU T4 ×2“ – Kaggles Standard-GPU; P100 ist ausgemustert und zu alt
GPU_NAME = "NVIDIA T4 (16 GB) bei Kaggle – kostenlos"
KEYRING_USER_NAME = "kaggle_username"
KEYRING_USER_KEY = "kaggle_key"

KAGGLE_SESSION_H = 12                      # Kaggles Grenze für eine GPU-Sitzung
HARD_CAP_STUNDEN = 11                      # unsere Obergrenze pro Lauf – sicher unter Kaggles 12 h
SESSION_MARGIN_S = 10 * 60                 # Kaggles eigener Abbruch erst nach unserem Budget + 10 min
EXPORT_RESERVE_MIN = 20                    # so lange vor dem Budgetende hört das Training auf (Anhalten + Export)
SETUP_MIN = 20                             # GPU prüfen, Code laden, uv sync (torch, warp …) – grob
S_IT_T4 = 7.0                              # Schätzung Sekunden/Iteration bei 4096 Umgebungen auf einer T4
SAVE_INTERVAL = 100                        # öfter speichern: beim Anhalten geht höchstens so viel verloren
MAX_AKTIV = 2                              # gleichzeitige Kaggle-Läufe (Kaggle begrenzt GPU-Sitzungen)
MAX_ONNX = 60 * 1024 * 1024
MAX_METRICS = 8 * 1024 * 1024

STATUS = {"QUEUED": "wartet auf eine GPU", "NEW_SCRIPT": "gestartet", "RUNNING": "trainiert",
          "COMPLETE": "fertig", "ERROR": "fehlgeschlagen", "CANCEL_REQUESTED": "abgebrochen",
          "CANCEL_ACKNOWLEDGED": "abgebrochen"}
ACTIVE = ("gestartet", "wartet auf eine GPU", "trainiert")
PHASEN = {"start": "startet", "gpu": "GPU geprüft", "installiert": "Pollens Code eingerichtet",
          "trainiert": "trainiert", "angehalten": "hält an", "exportiert": "exportiert die Policy",
          "fertig": "fertig", "fehler": "Fehler"}


class KaggleError(RuntimeError):
    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


# ── Zugangsdaten im Tresor ──────────────────────────────────────────────────
_USER_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{1,49}")
_KEY_RE = re.compile(r"[0-9a-fA-F]{32}|KGAT_[A-Za-z0-9_-]{10,200}")


def get_credentials() -> tuple[str, str] | None:
    """(Benutzername, Schlüssel) aus dem Tresor – oder None."""
    from . import settings as S

    kr = S._keyring()
    if kr is None:
        return None
    try:
        user = kr.get_password(S.KEYRING_SERVICE, KEYRING_USER_NAME)
        key = kr.get_password(S.KEYRING_SERVICE, KEYRING_USER_KEY)
    except Exception:
        return None
    return (user, key) if user and key else None


def set_credentials(username: str, key: str) -> None:
    from . import settings as S

    username, key = str(username or "").strip(), str(key or "").strip()
    if not _USER_RE.fullmatch(username):
        raise ValueError("Das sieht nicht wie ein Kaggle-Benutzername aus.")
    if not _KEY_RE.fullmatch(key):
        raise ValueError("Das sieht nicht wie ein Kaggle-API-Schlüssel aus (32 Zeichen aus kaggle.json oder KGAT_…).")
    kr = S._keyring()
    if kr is None:
        raise RuntimeError("Kein Tresor verfügbar.")
    kr.set_password(S.KEYRING_SERVICE, KEYRING_USER_NAME, username)
    kr.set_password(S.KEYRING_SERVICE, KEYRING_USER_KEY, key)


def parse_kaggle_json(text: str) -> tuple[str, str]:
    """Inhalt einer kaggle.json ({"username": …, "key": …}) → (Benutzername, Schlüssel). Wird nicht gespeichert."""
    try:
        data = json.loads(text)
        return str(data["username"]).strip(), str(data["key"]).strip()
    except Exception:
        raise ValueError("Das ist keine kaggle.json (erwartet: {\"username\": …, \"key\": …}).") from None


def delete_credentials() -> None:
    from . import settings as S

    kr = S._keyring()
    if kr is None:
        return
    for user in (KEYRING_USER_KEY, KEYRING_USER_NAME):
        try:
            kr.delete_password(S.KEYRING_SERVICE, user)
        except Exception:
            pass


def credentials_hint(creds: tuple[str, str] | None) -> str | None:
    """Für die Anzeige: Benutzername und nur die letzten 4 Zeichen des Schlüssels."""
    return f"{creds[0]} · …{creds[1][-4:]}" if creds else None


# ── Fehler auf Deutsch ──────────────────────────────────────────────────────
SCRIPT_FEHLER = {
    "keine_gpu": "Die Kaggle-Sitzung hat keine GPU bekommen. Meist ist das Wochenkontingent aufgebraucht oder "
                 "das Konto nicht per Telefon bestätigt (kaggle.com/settings → Phone verification).",
    "gpu_zu_alt": "Kaggle hat eine zu alte GPU zugeteilt (z. B. P100) – Pollens Training braucht mindestens eine "
                  "T4 (sm_75). Einfach noch einmal starten.",
    "kein_internet": "Die Kaggle-Sitzung hat kein Internet und kann Pollens Code nicht laden. Kaggle erlaubt "
                     "Internet nur mit per Telefon bestätigtem Konto (kaggle.com/settings → Phone verification).",
    "installation": "Pollens Trainingscode ließ sich auf Kaggle nicht einrichten (uv sync).",
    "kein_startstand": "Der Zwischenstand des Ausgangslaufs war in der Kaggle-Sitzung nicht zu finden.",
    "training": "Das Training ist abgebrochen, bevor es einen Zwischenstand gespeichert hat.",
    "export": "Das Training lief, aber der Export nach ONNX ist fehlgeschlagen.",
    "zu_wenig_zeit": "Nach dem Einrichten blieb zu wenig Zeit für das Training – mehr Stunden wählen.",
}


def erklaere(text: str, status: int | None = None) -> str:
    """Eine Meldung von Kaggle (oder ein HTTP-Status) → verständlicher deutscher Satz."""
    low = (text or "").lower()
    if "phone" in low or "verif" in low or "telefon" in low:
        return ("Kaggle verlangt für GPU und Internet ein per Telefon bestätigtes Konto – auf "
                "kaggle.com/settings unter „Phone verification“ bestätigen und dann neu starten.")
    if "quota" in low or "kontingent" in low or ("exceed" in low and "gpu" in low):
        return "Das kostenlose GPU-Kontingent dieser Woche ist aufgebraucht – es wird wöchentlich erneuert."
    if status == 401 or "unauthenticated" in low or "unauthorized" in low or "invalid credentials" in low:
        return ("Kaggle lehnt die Zugangsdaten ab – Benutzername und API-Schlüssel prüfen "
                "(kaggle.com/settings → API → „Create Legacy API Key“ bzw. neuer Token).")
    if status == 403 or "permission" in low or "forbidden" in low:
        return "Kaggle verweigert den Zugriff – gehört der Kernel zu diesem Konto?"
    if status == 404:
        return "Kaggle kennt diesen Kernel nicht (mehr)."
    if status == 429 or "too many" in low or "rate limit" in low:
        return "Kaggle bremst gerade (zu viele Anfragen) – in ein paar Minuten noch einmal."
    if status is not None and status >= 500:
        return f"Kaggle antwortet gerade nicht richtig (HTTP {status}) – später noch einmal."
    return (text or "Unbekannter Fehler von Kaggle").strip()[:400]


# ── HTTP ────────────────────────────────────────────────────────────────────
@dataclass
class Antwort:
    status: int
    body: bytes = b""
    content_type: str = ""
    headers: dict[str, str] = field(default_factory=dict)

    def json(self) -> Any:
        return json.loads(self.body.decode("utf-8") or "null")


Http = Callable[..., Antwort]


def urllib_http(method: str, url: str, headers: dict[str, str] | None = None, data: bytes | None = None,
                timeout: float = 60.0, max_seconds: float | None = None, max_bytes: int | None = None) -> Antwort:
    """Eine Anfrage. `max_seconds`: einen Datenstrom (Server-Sent Events) nur so lange lesen."""
    req = urllib.request.Request(url, data=data, method=method, headers={"User-Agent": "duckpilot", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=min(timeout, max_seconds) if max_seconds else timeout) as resp:
            ctype = resp.headers.get("Content-Type", "")
            if max_seconds is None:
                body = resp.read(max_bytes + 1) if max_bytes else resp.read()
            else:
                chunks: list[bytes] = []
                end = time.monotonic() + max_seconds
                try:
                    while time.monotonic() < end:
                        line = resp.readline()
                        if not line:
                            break
                        chunks.append(line)
                        if b"END_OF_LOG" in line:
                            break
                except TimeoutError:
                    pass
                body = b"".join(chunks)
            return Antwort(resp.status, body, ctype, dict(resp.headers.items()))
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read()
        except Exception:
            body = b""
        return Antwort(exc.code, body, exc.headers.get("Content-Type", "") if exc.headers else "")


class KaggleApi:
    """Die paar Aufrufe aus Kaggles öffentlicher API, die duckpilot braucht."""

    def __init__(self, username: str, key: str, http: Http | None = None) -> None:
        self.username = username
        self._key = key
        self.http = http or urllib_http

    def _auth(self) -> str:
        if self._key.startswith("KGAT_"):                # neue API-Tokens
            return f"Bearer {self._key}"
        raw = f"{self.username}:{self._key}".encode()
        return "Basic " + base64.b64encode(raw).decode()

    def call(self, method: str, payload: dict[str, Any] | None = None, timeout: float = 60.0) -> dict[str, Any]:
        resp = self.http("POST", f"{API}/{SERVICE}/{method}",
                         headers={"Authorization": self._auth(), "Content-Type": "application/json",
                                  "Accept": "application/json"},
                         data=json.dumps(payload or {}).encode("utf-8"), timeout=timeout)
        try:
            body = resp.json() if resp.body else {}
        except ValueError:
            body = {"message": resp.body[:300].decode("utf-8", "replace")}
        if not isinstance(body, dict):
            body = {}
        code = body.get("code")
        if resp.status >= 400 or (isinstance(code, int) and code >= 400):
            status = resp.status if resp.status >= 400 else int(code)
            raise KaggleError(erklaere(str(body.get("message") or body.get("error") or ""), status), status)
        return body

    def log_stream(self, owner: str, slug: str, seconds: float = 8.0) -> list[str]:
        """Protokoll eines Kernels: live (SSE, nur `seconds` lang gelesen) oder – fertig – als Ganzes."""
        resp = self.http("GET", f"{API}/kernels/logs/stream/{owner}/{slug}",
                         headers={"Authorization": self._auth(), "Accept": "text/event-stream, */*"},
                         timeout=30.0, max_seconds=seconds)
        if resp.status >= 400:
            raise KaggleError(erklaere(resp.body[:300].decode("utf-8", "replace"), resp.status), resp.status)
        return log_events(resp.body.decode("utf-8", "replace"), resp.content_type)

    def download(self, url: str, max_bytes: int) -> bytes:
        """Eine Ausgabedatei über ihre signierte Adresse holen – ohne Zugangsdaten mitzuschicken."""
        if not url.startswith("https://"):
            raise KaggleError("Kaggle hat eine unsichere Download-Adresse geliefert.")
        resp = self.http("GET", url, headers={}, timeout=300.0, max_bytes=max_bytes)
        if resp.status >= 400:
            raise KaggleError(f"Download fehlgeschlagen (HTTP {resp.status}) – der Link ist evtl. abgelaufen, "
                              "noch einmal versuchen.")
        if len(resp.body) > max_bytes:
            raise KaggleError(f"Datei zu groß ({len(resp.body) // 1_000_000} MB)")
        return resp.body


def log_events(text: str, content_type: str = "") -> list[str]:
    """Kaggles Protokoll (SSE `data: {…}`, JSON-Liste von {stream_name, time, data} oder Klartext) → Textstücke."""
    text = text or ""
    out: list[str] = []
    stripped = text.lstrip()
    if "event-stream" in (content_type or "").lower() or stripped.startswith("data:"):
        for line in text.splitlines():
            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if payload == "END_OF_LOG":
                break
            try:
                ev = json.loads(payload)
                out.append(str(ev.get("data", "")) if isinstance(ev, dict) else str(ev))
            except ValueError:
                out.append(payload)
        return [x for x in out if x]
    try:
        data = json.loads(text)
        events = data if isinstance(data, list) else [data]
        return [str(e.get("data", "")) for e in events if isinstance(e, dict) and e.get("data")]
    except ValueError:
        return [ln for ln in text.splitlines() if ln.strip()]


def _hours(value: Any) -> float | None:
    """Kaggles Dauer ("3600s", "12.5s" oder Zahl) → Stunden."""
    if value is None:
        return None
    try:
        return float(str(value).rstrip("s")) / 3600
    except ValueError:
        return None


def _status_name(raw: Any) -> str:
    s = str(raw or "").strip().upper().split(".")[-1]
    return s.replace("KERNEL_WORKER_STATUS_", "")


# ── Plan ────────────────────────────────────────────────────────────────────
def estimate(plan: dict[str, Any], measured: float | None = None) -> dict[str, Any]:
    """Dauer bei Kaggle – Geld kostet es nicht, aber Stunden vom Wochenkontingent."""
    s_it = measured or S_IT_T4
    hours = (SETUP_MIN * 60 + plan["iterationen"] * s_it) / 3600 + EXPORT_RESERVE_MIN / 60
    out = {"stunden": round(hours, 2), "usd": 0.0, "usd_h": 0.0, "s_it": round(s_it, 2), "gemessen": bool(measured)}
    if plan.get("max_stunden"):
        out["usd_max"] = 0.0
        train_s = plan["max_stunden"] * 3600 - (SETUP_MIN + EXPORT_RESERVE_MIN) * 60
        out["iterationen_moeglich"] = max(0, int(train_s / s_it))
        out["kontingent_h_max"] = plan["max_stunden"]
    return out


def check_plan(task: str, iterations: int | None = None, overrides: dict[str, Any] | None = None,
               start_von: str | None = None, max_stunden: Any = None, bei_stillstand: str = "weiter",
               measured: float | None = None) -> dict[str, Any]:
    """Wie `training.check_plan`, aber für Kaggle: feste GPU (T4), Obergrenze HARD_CAP_STUNDEN.
    Ein Lauf, der länger dauern würde, ist erlaubt – das Skript hält rechtzeitig an und exportiert den Stand."""
    if task not in T.TASKS:
        raise ValueError(f"Unbekannte Aufgabe – erlaubt: {', '.join(T.TASKS)}")
    it = int(iterations or T.TASKS[task]["iter"])
    if not 100 <= it <= 20000:
        raise ValueError("Iterationen: 100 bis 20 000")
    start = (start_von or "").strip() or None
    if start == "pollen":
        if T.pollen_start(task) is None:
            raise ValueError("Für diese Aufgabe gibt es keinen geteilten Stand von Pollen – „von vorn“ oder einen eigenen Lauf.")
    elif start is not None and not re.fullmatch(r"lauf:[\w-]{1,40}", start):
        raise ValueError("Start: „pollen“, „lauf:<id>“ oder leer (von vorn)")
    if bei_stillstand not in ("weiter", "abbrechen"):
        raise ValueError("Bei Stillstand: „weiter“ oder „abbrechen“")
    plan: dict[str, Any] = {"aufgabe": task, "iterationen": it, "anpassungen": T.check_overrides(overrides),
                            "grafikkarte": "kaggle-t4", "start_von": start, "bei_stillstand": bei_stillstand}
    est = estimate(plan, measured)
    if max_stunden in (None, ""):
        hours = min(HARD_CAP_STUNDEN, max(1, math.ceil(est["stunden"] * 1.2)))
    else:
        try:
            hours = int(max_stunden)
        except (TypeError, ValueError):
            raise ValueError(f"Höchstdauer: ganze Stunden von 1 bis {HARD_CAP_STUNDEN}") from None
        if not 1 <= hours <= HARD_CAP_STUNDEN:
            raise ValueError(f"Höchstdauer: ganze Stunden von 1 bis {HARD_CAP_STUNDEN} – Kaggle beendet eine "
                             f"Sitzung nach {KAGGLE_SESSION_H} h, Einrichten und Export brauchen Puffer.")
    plan["max_stunden"] = hours
    if est["stunden"] > hours:
        possible = estimate(plan, measured)["iterationen_moeglich"]
        plan["hinweis"] = (f"Geschätzt ≈ {est['stunden']:.1f} h – nach {hours} h hält das Skript an (≈ {possible} "
                           "Iterationen) und exportiert den Stand bis dahin.")
    return plan


def kaggle_train_args(plan: dict[str, Any], init: str | None) -> list[str]:
    args = T.train_args(plan, False, init)
    if "agent.save_interval" not in plan.get("anpassungen", {}):
        args[1:1] = ["--agent.save_interval", str(SAVE_INTERVAL)]
    return args


def _slugify(text: str) -> str:
    return re.sub(r"-{2,}", "-", re.sub(r"[^a-z0-9]+", "-", text.lower())).strip("-")


# ── Das Skript, das auf Kaggle läuft ────────────────────────────────────────
def _helpers_source() -> str:
    """parse_log/summarize/skill_of aus training.py – dieselbe Auswertung im Kernel wie in duckpilot."""
    parts = [f"_ANSI = re.compile({T._ANSI.pattern!r})", f"_ITER = re.compile({T._ITER.pattern!r})",
             f"_KV = re.compile({T._KV.pattern!r})", f"_TIME = re.compile({T._TIME.pattern!r})"]
    for fn in (T.parse_log, T.summarize, T.skill_of):
        parts.append(inspect.getsource(fn))
    return "\n\n".join(parts)


SCRIPT = r'''# duckpilot – Microduck-Training auf Kaggle (automatisch erzeugt; Änderungen gehen beim nächsten Lauf verloren)
from __future__ import annotations

import collections
import glob
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tarfile
import threading
import time
import urllib.request
from typing import Any

START = time.monotonic()
CFG = json.loads(__CFG__)
OUT = "/kaggle/working"
BASE = "/tmp/duckpilot"
WORK = BASE + "/src"
TAIL: collections.deque = collections.deque(maxlen=300)
POINTS: list = []
STATE: dict = {"grund": None, "checkpoint": None, "warnung": None}

__HELPERS__


def elapsed() -> float:
    return time.monotonic() - START


def left() -> float:
    return CFG["budget_s"] - elapsed()


def say(phase: str, **kw: Any) -> None:
    print("[duckpilot] " + json.dumps({"phase": phase, "t": round(elapsed()), **kw}, ensure_ascii=False), flush=True)


def thin(pts: list, keep: int = 400) -> list:
    if len(pts) <= keep:
        return pts
    head, tail = pts[:-60], pts[-60:]
    step = -(-len(head) // (keep - 60))
    return head[::step] + tail


def write_metrics(fehler: dict | None = None) -> None:
    pts = sorted({p["it"]: p for p in POINTS}.values(), key=lambda p: p["it"])
    data = {"version": 1, "aufgabe": CFG["task"], "iterationen": CFG["iterations"], "grund": STATE["grund"],
            "checkpoint": STATE["checkpoint"], "warnung": STATE["warnung"], "fehler": fehler,
            "dauer_s": round(elapsed()), "zusammenfassung": summarize(pts), "punkte": thin(pts),
            "log_ende": list(TAIL)[-60:]}
    os.makedirs(OUT, exist_ok=True)
    with open(OUT + "/metrics.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)


def fail(code: str, text: str = "") -> None:
    say("fehler", code=code, text=text[-1500:])
    try:
        write_metrics({"code": code, "text": text[-1500:]})
    except Exception as exc:
        print("metrics.json:", exc, flush=True)
    sys.exit(1)


def latest_checkpoint(paths: list) -> str | None:
    best = None
    for p in paths:
        m = re.search(r"model_(\d+)\.pt$", p)
        if m and (best is None or int(m.group(1)) > best[0]):
            best = (int(m.group(1)), p)
    return best[1] if best else None


def check_gpu() -> None:
    try:
        res = subprocess.run(["nvidia-smi", "--query-gpu=name,compute_cap", "--format=csv,noheader"],
                             capture_output=True, text=True, timeout=60)
        rows = [r.strip() for r in res.stdout.splitlines() if r.strip()] if res.returncode == 0 else []
    except (OSError, subprocess.TimeoutExpired):
        rows = []
    if not rows:
        fail("keine_gpu", "nvidia-smi findet keine GPU")
    caps = []
    for r in rows:
        try:
            caps.append(float(r.rsplit(",", 1)[1]))
        except (IndexError, ValueError):
            pass
    too_old = bool(caps) and max(caps) < 7.5
    if too_old or (any("P100" in r for r in rows) and not any("T4" in r or "L4" in r for r in rows)):
        fail("gpu_zu_alt", "; ".join(rows))
    say("gpu", gpus=rows)


def fetch_source() -> None:
    try:
        req = urllib.request.Request(CFG["tarball"], headers={"User-Agent": "duckpilot-kaggle"})
        data = urllib.request.urlopen(req, timeout=180).read()
    except Exception as exc:
        fail("kein_internet", f"{CFG['tarball']}: {exc}")
    import io

    os.makedirs(WORK, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as src:
        for m in src.getmembers():
            if not m.isfile():
                continue
            parts = m.name.split("/", 1)
            if len(parts) < 2 or not parts[1] or ".." in parts[1].split("/") or parts[1].startswith("/"):
                continue
            dest = os.path.join(WORK, parts[1])
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            f = src.extractfile(m)
            if f is None:
                continue
            with open(dest, "wb") as out:
                shutil.copyfileobj(f, out)
            os.chmod(dest, m.mode & 0o755 | 0o600)


def uv_cmd() -> list:
    try:
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "uv==" + CFG["uv"]], check=True,
                       capture_output=True, timeout=600)
        return [sys.executable, "-m", "uv"]
    except Exception:
        subprocess.run("curl -LsSf https://astral.sh/uv/" + CFG["uv"] + "/install.sh | sh", shell=True,
                       capture_output=True, timeout=600)
        return [os.path.expanduser("~/.local/bin/uv")]


def env() -> dict:
    e = dict(os.environ)
    e.update({"UV_CACHE_DIR": BASE + "/uv-cache", "UV_PYTHON_INSTALL_DIR": BASE + "/python", "UV_LINK_MODE": "copy",
              "UV_HTTP_TIMEOUT": "600", "PYTHONUNBUFFERED": "1"})
    if CFG.get("warm"):
        e["MICRODUCK_WARM_START"] = "1"
    return e


def install(uv: list) -> None:
    t0 = elapsed()
    res = None
    for attempt in range(2):
        try:
            res = subprocess.run(uv + ["sync", "--no-progress"], cwd=WORK, env=env(), capture_output=True, text=True,
                                 timeout=max(300, min(3600, left() - 1800)))
        except subprocess.TimeoutExpired:
            fail("installation", "uv sync dauerte zu lange")
        if res.returncode == 0:
            break
        subprocess.run(uv + ["cache", "clean"], cwd=WORK, env=env(), capture_output=True, timeout=600)
    if res is None or res.returncode != 0:
        fail("installation", "\n".join(((res.stdout or "") + (res.stderr or "")).splitlines()[-40:]) if res else "")
    say("installiert", minuten=round((elapsed() - t0) / 60, 1))


def init_checkpoint() -> str | None:
    spec = CFG.get("init")
    if spec == "kaggle-input":
        best = latest_checkpoint(glob.glob("/kaggle/input/**/model_*.pt", recursive=True))
        if not best:
            fail("kein_startstand", "kein model_*.pt unter /kaggle/input")
        return best
    return spec


_SHOW = re.compile(r"Traceback|Error|error:|Exception|Killed|CUDA|out of memory", re.I)


class Reader(threading.Thread):
    """Liest die Ausgabe von `uv run train`: alle Iterationen für die Kurve, jede `every`-te ins Protokoll."""

    def __init__(self, stream) -> None:
        super().__init__(daemon=True)
        self.stream = stream
        self.block: list = []
        self.show = False
        self.started = False
        self.printed = 0

    def _flush(self) -> None:
        if not self.block:
            return
        pts = parse_log(self.block)
        POINTS.extend(pts)
        if self.show:
            keep = [self.block[0]] + [ln for ln in self.block[1:] if _KV.match(ln) or _TIME.match(ln)]
            print("\n".join(keep), flush=True)
        self.block = []

    def run(self) -> None:
        every = CFG["every"]
        for raw in self.stream:
            line = _ANSI.sub("", raw.rstrip("\n"))[:500]
            TAIL.append(line)
            m = _ITER.search(line)
            if m:
                self._flush()
                self.started = True
                it, total = int(m.group(1)), int(m.group(2))
                self.show = it % every == 0 or it >= total - 1
                self.block = [line.strip()]
                continue
            if self.started:
                if self.block:
                    self.block.append(line)
                if _SHOW.search(line):
                    print(line, flush=True)
            elif self.printed < 3000:
                self.printed += 1
                print(line, flush=True)
        self._flush()


def _default_sigint() -> None:
    # Im Hintergrund gestartete Prozesse erben oft ein ignoriertes SIGINT – dann käme das Anhalten nie an.
    signal.signal(signal.SIGINT, signal.SIG_DFL)


def stop(proc, grund: str) -> None:
    say("angehalten", grund=grund, iteration=POINTS[-1]["it"] if POINTS else None)
    for sig, wait in ((signal.SIGINT, 60), (signal.SIGTERM, 30), (signal.SIGKILL, 15)):
        try:
            os.killpg(proc.pid, sig)
        except (ProcessLookupError, PermissionError):
            return
        try:
            proc.wait(wait)
            return
        except subprocess.TimeoutExpired:
            continue


def train(uv: list, init: str | None) -> tuple:
    stop_at = CFG["budget_s"] - CFG["export_reserve_s"]
    if stop_at - elapsed() < 600:
        fail("zu_wenig_zeit", f"nur noch {round((stop_at - elapsed()) / 60)} min")
    args = list(CFG["args"]) + (["--init-checkpoint", init] if init else [])
    say("trainiert", args=args, stop_nach_s=round(stop_at))
    proc = subprocess.Popen(uv + ["run", "train", *args], cwd=WORK, env=env(), stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, bufsize=1, errors="replace", start_new_session=True,
                            preexec_fn=_default_sigint)
    reader = Reader(proc.stdout)
    reader.start()
    grund = None
    checked = 0.0
    while proc.poll() is None:
        time.sleep(5)
        if elapsed() >= stop_at:
            grund = "zeit"
            stop(proc, grund)
            break
        if CFG["bei_stillstand"] == "abbrechen" and elapsed() - checked > 60:
            checked = elapsed()
            if summarize(list(POINTS)).get("stillstand"):
                grund = "stillstand"
                stop(proc, grund)
                break
    rc = proc.wait()
    reader.join(timeout=60)
    return rc, grund


def export(uv: list, ckpt: str) -> None:
    say("exportiert", checkpoint=os.path.basename(ckpt))
    onnx = OUT + "/policy.onnx"
    try:
        res = subprocess.run(uv + ["run", "python", "scripts/export.py", CFG["task"], "--checkpoint-file", ckpt,
                                   "--num-envs", "1", "--onnx-file", onnx], cwd=WORK, env=env(),
                             capture_output=True, text=True, timeout=max(120, min(1500, left() - 60)))
    except subprocess.TimeoutExpired:
        fail("export", "Export dauerte zu lange")
    if res.returncode != 0 or not os.path.exists(onnx):
        fail("export", "\n".join(((res.stdout or "") + (res.stderr or "")).splitlines()[-40:]))


def main() -> None:
    say("start", aufgabe=CFG["task"], budget_h=round(CFG["budget_s"] / 3600, 2))
    check_gpu()
    fetch_source()
    uv = uv_cmd()
    install(uv)
    init = init_checkpoint()
    rc, grund = train(uv, init)
    ckpt = latest_checkpoint(glob.glob(WORK + "/logs/rsl_rl/*/*/model_*.pt"))
    if not ckpt:
        fail("training", "\n".join(list(TAIL)[-40:]))
    if rc != 0 and grund is None:
        STATE["warnung"] = f"Das Training endete mit Code {rc} – exportiert wird der letzte Zwischenstand."
    export(uv, ckpt)
    os.makedirs(OUT + "/checkpoint", exist_ok=True)
    shutil.copy2(ckpt, OUT + "/checkpoint/" + os.path.basename(ckpt))
    STATE["checkpoint"] = os.path.basename(ckpt)
    STATE["grund"] = grund or ("fertig" if rc == 0 else "abbruch")
    write_metrics()
    say("fertig", grund=STATE["grund"], checkpoint=STATE["checkpoint"])


if __name__ == "__main__":
    main()
'''


def build_script(plan: dict[str, Any], init: str | None, warm: bool) -> str:
    """Das Python-Skript für den Kaggle-Kernel. `init`: hf://-Pfad, "kaggle-input" oder None."""
    cfg = {"task": plan["aufgabe"], "iterations": plan["iterationen"],
           "args": kaggle_train_args(plan, None), "init": init, "warm": bool(warm),
           "budget_s": int(plan["max_stunden"] * 3600), "export_reserve_s": EXPORT_RESERVE_MIN * 60,
           "every": max(1, plan["iterationen"] // 300), "bei_stillstand": plan.get("bei_stillstand", "weiter"),
           "tarball": T.RL_TARBALL, "uv": "0.11.30"}
    text = SCRIPT.replace("__CFG__", repr(json.dumps(cfg, ensure_ascii=False)))
    return text.replace("__HELPERS__", _helpers_source())


# ── Läufe ───────────────────────────────────────────────────────────────────
class KaggleTrainer:
    """Kostenlose Trainingsläufe auf Kaggle. Gleiche Form der Läufe wie `training.Trainer` plus
    `"anbieter": "kaggle"` und `"kosten": 0`."""

    is_free = True
    hard_cap_stunden = HARD_CAP_STUNDEN

    def __init__(self, root: Path, http: Http | None = None, credentials: Callable[[], tuple[str, str] | None] | None = None) -> None:
        self.root = Path(root)
        self.file = self.root / "kaggle_runs.json"
        self.curve_dir = self.root / "kaggle" / "kurven"
        self.result_dir = self.root / "policies" / "kaggle"
        self.http = http or urllib_http
        self.credentials = credentials or get_credentials
        self.vorschlag: dict[str, Any] | None = None
        self._lock = threading.RLock()

    # Speicher
    def runs(self) -> list[dict[str, Any]]:
        try:
            data = json.loads(self.file.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def _save(self, runs: list[dict[str, Any]]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        tmp = self.file.with_suffix(".tmp")
        tmp.write_text(json.dumps(runs[-50:], ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.file)

    def _get(self, rid: str) -> dict[str, Any]:
        r = next((x for x in self.runs() if x["id"] == rid), None)
        if r is None:
            raise KeyError(rid)
        return r

    def _update(self, rid: str, **fields: Any) -> dict[str, Any]:
        with self._lock:
            runs = self.runs()
            for r in runs:
                if r["id"] == rid:
                    r.update(fields)
                    self._save(runs)
                    return dict(r)
        raise KeyError(rid)

    def _claim(self, rid: str, expect: tuple[str, ...], **fields: Any) -> dict[str, Any] | None:
        with self._lock:
            runs = self.runs()
            r = next((x for x in runs if x["id"] == rid), None)
            if r is None or r.get("status") not in expect:
                return None
            r.update(fields)
            self._save(runs)
            return dict(r)

    def _api(self) -> KaggleApi:
        creds = self.credentials()
        if not creds:
            raise KaggleError("Keine Kaggle-Zugangsdaten – unter Lernen → Training Benutzername und API-Schlüssel "
                              "eintragen (kaggle.com/settings → API).")
        return KaggleApi(creds[0], creds[1], self.http)

    # Konto
    def account(self) -> dict[str, Any]:
        """Prüft die Zugangsdaten. → {"name", "kontingent": {gpu_h_gesamt, gpu_h_genutzt, gpu_h_frei, erneuert} | None}"""
        api = self._api()
        try:
            q = api.call("GetAcceleratorQuotaStatistics", {})
        except KaggleError as exc:
            if exc.status != 404:                       # Kontingent-Abfrage gibt es nicht → anders prüfen
                raise
            api.call("ListKernels", {"user": api.username, "pageSize": 1})
            return {"name": api.username, "kontingent": None}
        gpu = q.get("gpuQuota") or {}
        total, used, reserved = (_hours(gpu.get(k)) for k in ("totalTimeAllowed", "timeUsed", "timeReserved"))
        quota = None
        if total is not None:
            free = max(0.0, total - (used or 0.0) - (reserved or 0.0))
            quota = {"gpu_h_gesamt": round(total, 2), "gpu_h_genutzt": round(used or 0.0, 2),
                     "gpu_h_frei": round(free, 2), "erneuert": q.get("quotaRefreshTime")}
        return {"name": api.username, "kontingent": quota}

    def measured(self) -> float | None:
        vals = sorted(float(v) for r in self.runs() if (v := (r.get("kurve") or {}).get("s_it")))
        return vals[len(vals) // 2] if vals else None

    def _init_spec(self, plan: dict[str, Any]) -> tuple[str | None, bool, str, list[str]]:
        """(init für das Skript, Warmstart?, Beschreibung, Kernel-Datenquellen)."""
        start = plan.get("start_von")
        if not start:
            return None, False, "von vorn", []
        if start == "pollen":
            got = T.pollen_start(plan["aufgabe"])
            if got is None:
                raise KaggleError("Kein Stand von Pollen für diese Aufgabe.")
            bundle, warm = got
            return f"hf://{T.POLLEN_TRAINING}/bundles/{bundle}", warm, f"Pollens Stand {bundle}", []
        rid = start.split(":", 1)[1]
        src = next((r for r in self.runs() if r["id"] == rid), None)
        if src is None or not src.get("job"):
            raise KaggleError("Diesen Kaggle-Lauf gibt es nicht (weitertrainieren geht nur von Kaggle-Läufen).")
        if T.family(src["plan"]["aufgabe"]) != T.family(plan["aufgabe"]):
            raise KaggleError("Weitertrainieren geht nur innerhalb derselben Aufgabe (eben/uneben/Getriebespiel).")
        if src.get("status") != "fertig" or not src.get("checkpoint"):
            raise KaggleError("Der Ausgangslauf ist nicht fertig oder hat keinen Zwischenstand abgelegt.")
        warm = src["plan"]["aufgabe"] != plan["aufgabe"]
        return "kaggle-input", warm, f"eigener Lauf {rid} ({src['checkpoint']})", [src["job"]]

    def submit(self, plan: dict[str, Any], progress=None, gruppe: str | None = None,
               variante: str | None = None) -> dict[str, Any]:
        """Plan prüfen, Kontingent prüfen, Skript erzeugen und als privaten GPU-Kernel starten."""
        plan = check_plan(plan["aufgabe"], plan.get("iterationen"), plan.get("anpassungen"), plan.get("start_von"),
                          plan.get("max_stunden"), plan.get("bei_stillstand", "weiter"), self.measured())
        api = self._api()
        active = [r for r in self.runs() if r.get("status") in ACTIVE]
        if len(active) >= MAX_AKTIV:
            raise KaggleError(f"Es laufen schon {len(active)} Kaggle-Läufe – erst abwarten.")
        acc = self.account()
        quota = acc.get("kontingent")
        if quota is not None:
            if quota["gpu_h_frei"] < 1:
                when = f" – neu ab {quota['erneuert']}" if quota.get("erneuert") else ""
                raise KaggleError(f"Das kostenlose GPU-Kontingent dieser Woche ist aufgebraucht "
                                  f"({quota['gpu_h_genutzt']:.1f} von {quota['gpu_h_gesamt']:.0f} h){when}.")
            if quota["gpu_h_frei"] < plan["max_stunden"]:
                raise KaggleError(f"Nur noch {quota['gpu_h_frei']:.1f} h GPU-Zeit frei, der Lauf darf bis zu "
                                  f"{plan['max_stunden']} h dauern – höchstens {int(quota['gpu_h_frei'])} h wählen.")
        init, warm, start_text, sources = self._init_spec(plan)
        stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        short = _slugify(plan["aufgabe"].removeprefix("Mjlab-").removesuffix("-MicroDuck"))
        with self._lock:
            runs = self.runs()
            rid, n = f"kg-{stamp}", 2
            while any(r["id"] == rid for r in runs):
                rid, n = f"kg-{stamp}-{n}", n + 1
            title = f"duckpilot {short} {rid.removeprefix('kg-')}"[:50]
            slug = _slugify(title)
            runs.append({"id": rid, "anbieter": "kaggle", "kosten": 0, "plan": plan, "status": "bereitet vor",
                         "start": time.strftime("%Y-%m-%d %H:%M"), "job": None, "url": None, "fehler": None,
                         "schaetzung": estimate(plan, self.measured()), "gruppe": gruppe, "variante": variante,
                         "start_von": start_text, "warmstart": warm, "phase": None, "hinweis": plan.get("hinweis")})
            self._save(runs)
        try:
            if progress:
                progress("starte den Kaggle-Kernel …")
            payload = {"slug": f"{api.username}/{slug}", "newTitle": title, "text": build_script(plan, init, warm),
                       "language": "python", "kernelType": "script", "isPrivate": True, "enableGpu": True,
                       "enableTpu": False, "enableInternet": True, "machineShape": MACHINE_SHAPE,
                       "sessionTimeoutSeconds": plan["max_stunden"] * 3600 + SESSION_MARGIN_S,
                       "datasetDataSources": [], "competitionDataSources": [], "kernelDataSources": sources,
                       "modelDataSources": [], "categoryIds": []}
            res = api.call("SaveKernel", payload, timeout=120)
            if res.get("error"):
                raise KaggleError(erklaere(str(res["error"])))
            url = str(res.get("url") or f"{WEB}/code/{api.username}/{slug}")
            m = re.search(r"/code/([\w-]+)/([\w-]+)", url)
            job = f"{m.group(1)}/{m.group(2)}" if m else f"{api.username}/{slug}"
            return self._update(rid, job=job, url=url, status="gestartet", version=res.get("versionNumber"),
                                 kernel_id=res.get("kernelId"))
        except Exception as exc:
            msg = str(exc) if isinstance(exc, KaggleError) else erklaere(str(exc))
            self._update(rid, status="fehlgeschlagen", fehler=msg[:400])
            raise KaggleError(msg) from exc

    # Protokoll und Kurve
    def _lines(self, api: KaggleApi, r: dict[str, Any], seconds: float = 8.0) -> list[str]:
        owner, slug = r["job"].split("/", 1)
        return [ln for chunk in api.log_stream(owner, slug, seconds) for ln in str(chunk).splitlines() if ln.strip()]

    @staticmethod
    def _marker(lines: list[str]) -> dict[str, Any]:
        """Die letzte `[duckpilot] {…}`-Zeile (Phase, Fehlercode)."""
        last: dict[str, Any] = {}
        for ln in lines:
            i = ln.find("[duckpilot] {")
            if i >= 0:
                try:
                    last = json.loads(ln[i + 12:])
                except ValueError:
                    pass
        return last

    def _curve_file(self, rid: str) -> Path:
        return self.curve_dir / f"{rid}.json"

    def series(self, rid: str) -> list[dict[str, Any]]:
        try:
            return json.loads(self._curve_file(rid).read_text(encoding="utf-8"))
        except Exception:
            return []

    def _merge_curve(self, rid: str, new: list[dict[str, Any]]) -> dict[str, Any]:
        with self._lock:
            known = {p["it"]: p for p in self.series(rid)}
            for p in new:
                known[p["it"]] = p
            pts = [known[k] for k in sorted(known)]
            if len(pts) > 400:
                head, tail = pts[:-60], pts[-60:]
                pts = head[::math.ceil(len(head) / 340)] + tail
            f = self._curve_file(rid)
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(json.dumps(pts, separators=(",", ":")), encoding="utf-8")
            return T.summarize(pts)

    def _outputs(self, api: KaggleApi, r: dict[str, Any]) -> tuple[dict[str, str], str]:
        """Ausgabedateien (Name → signierte Adresse) und das Protokoll eines beendeten Kernels."""
        owner, slug = r["job"].split("/", 1)
        files: dict[str, str] = {}
        log_text, token = "", None
        for _ in range(10):
            payload: dict[str, Any] = {"userName": owner, "kernelSlug": slug, "pageSize": 50}
            if token:
                payload["pageToken"] = token
            res = api.call("ListKernelSessionOutput", payload)
            for f in res.get("files") or []:
                if isinstance(f, dict) and f.get("fileName") and f.get("url"):
                    files[str(f["fileName"])] = str(f["url"])
            log_text = log_text or str(res.get("log") or "")
            token = res.get("nextPageToken")
            if not token:
                break
        return files, log_text

    def _failure(self, lines: list[str], extra: str = "") -> str:
        mark = self._marker(lines)
        if mark.get("phase") == "fehler":
            base = SCRIPT_FEHLER.get(str(mark.get("code")), "Das Kaggle-Skript meldet einen Fehler.")
            detail = str(mark.get("text") or "").strip().splitlines()[-3:]
            return (base + (" Letzte Zeilen: " + " | ".join(detail) if detail else ""))[:600]
        tail = [ln.strip() for ln in lines if ln.strip()][-5:]
        text = erklaere(extra) if extra else "Der Kaggle-Lauf ist fehlgeschlagen."
        return (text + (" Letzte Zeilen: " + " | ".join(tail) if tail else ""))[:600]

    def refresh(self, curves: bool = True) -> list[dict[str, Any]]:
        """Status aller laufenden Kernels nachfragen, Lernkurven nachziehen, Ergebnisse erkennen."""
        api = None
        for snap in self.runs():
            rid, status = snap["id"], snap.get("status")
            if status not in ACTIVE or not snap.get("job"):
                continue
            api = api or self._api()
            owner, slug = snap["job"].split("/", 1)
            try:
                st = api.call("GetKernelSessionStatus", {"userName": owner, "kernelSlug": slug})
            except KaggleError as exc:
                self._claim(rid, (status,), fehler=str(exc)[:300])
                continue
            stage = _status_name(st.get("status"))
            fields: dict[str, Any] = {"kaggle_status": stage}
            label = STATUS.get(stage, status)
            if stage == "RUNNING" and curves:
                try:
                    lines = self._lines(api, snap)
                    mark = self._marker(lines)
                    if mark.get("phase"):
                        fields["phase"] = PHASEN.get(str(mark["phase"]), str(mark["phase"]))
                    pts = T.parse_log(lines)
                    if pts:
                        fields["kurve"] = self._merge_curve(rid, pts)
                except Exception as exc:
                    log.info("Kaggle-Protokoll %s: %s", rid, exc)
            elif stage in ("COMPLETE", "ERROR"):
                try:
                    files, log_text = self._outputs(api, snap)
                except KaggleError as exc:
                    files, log_text = {}, ""
                    log.info("Kaggle-Ausgaben %s: %s", rid, exc)
                lines = [ln for chunk in log_events(log_text) for ln in chunk.splitlines() if ln.strip()]
                metrics = self._metrics(api, rid, files)
                if metrics.get("punkte"):
                    fields["kurve"] = self._merge_curve(rid, metrics["punkte"])
                elif lines:
                    pts = T.parse_log(lines)
                    if pts:
                        fields["kurve"] = self._merge_curve(rid, pts)
                fields["ausgaben"] = sorted(files)
                if stage == "COMPLETE" and "policy.onnx" in files:
                    label = "fertig"
                    fields.update(phase=PHASEN["fertig"], fehler=None, checkpoint=metrics.get("checkpoint"),
                                  ende=metrics.get("grund"))
                    if metrics.get("grund") == "zeit":
                        fields["hinweis"] = "Nach der Höchstdauer angehalten – exportiert ist der Stand bis dahin."
                    elif metrics.get("grund") == "stillstand":
                        fields["hinweis"] = ("Angehalten, weil sich die Belohnung nicht mehr verbessert hat – "
                                             "exportiert ist der letzte Zwischenstand.")
                    elif metrics.get("warnung"):
                        fields["hinweis"] = str(metrics["warnung"])[:300]
                else:
                    label = "fehlgeschlagen"
                    if metrics.get("fehler") and not self._marker(lines):
                        f = metrics["fehler"]
                        lines = lines + ["[duckpilot] " + json.dumps({"phase": "fehler", **f})]
                    fields["fehler"] = self._failure(lines, str(st.get("failureMessage") or ""))
            if label != status:
                fields["status"] = label
            self._claim(rid, ACTIVE, **fields)
        return self.runs()

    def _metrics(self, api: KaggleApi, rid: str, files: dict[str, str]) -> dict[str, Any]:
        if "metrics.json" not in files:
            return {}
        try:
            data = json.loads(api.download(files["metrics.json"], MAX_METRICS).decode("utf-8"))
        except Exception as exc:
            log.info("metrics.json %s: %s", rid, exc)
            return {}
        if not isinstance(data, dict):
            return {}
        pts = [p for p in data.get("punkte") or [] if isinstance(p, dict) and isinstance(p.get("it"), int)]
        data["punkte"] = pts
        return data

    def curve(self, rid: str) -> dict[str, Any]:
        """Lernkurve eines Laufs (bei laufendem Kernel frisch aus dem Protokoll)."""
        r = self._get(rid)
        if r.get("job") and r.get("status") == "trainiert":
            try:
                pts = T.parse_log(self._lines(self._api(), r))
                if pts:
                    self._update(rid, kurve=self._merge_curve(rid, pts))
            except Exception as exc:
                log.info("Kaggle-Lernkurve %s: %s", rid, exc)
        pts = self.series(rid)
        return {"lauf": rid, "aufgabe": r["plan"]["aufgabe"], "status": r["status"], "anbieter": "kaggle",
                "zusammenfassung": T.summarize(pts),
                "punkte": [{"it": p["it"], "belohnung": p.get("belohnung"), "laenge": p.get("laenge"),
                            "faehigkeit": T.skill_of(p)} for p in pts]}

    def logs(self, rid: str, lines: int = 80) -> list[str]:
        r = self._get(rid)
        if not r.get("job"):
            raise KeyError(rid)
        return [ln[:300] for ln in self._lines(self._api(), r)][-lines:]

    def cancel(self, rid: str) -> dict[str, Any]:
        """Kaggles öffentliche API kann eine laufende Sitzung nur über ihre Sitzungsnummer abbrechen
        (CancelKernelSession), und die liefert sie beim Starten nicht mit. Deshalb: erklären und den Link
        geben; der Lauf endet spätestens nach seiner Höchstdauer von selbst und exportiert dann."""
        r = self._get(rid)
        if r.get("session_id"):
            res = self._api().call("CancelKernelSession", {"kernelSessionId": int(r["session_id"])})
            if res.get("errorMessage"):
                raise KaggleError(erklaere(str(res["errorMessage"])))
            return self._update(rid, status="abgebrochen")
        url = r.get("url") or (f"{WEB}/code/{r['job']}" if r.get("job") else WEB)
        raise KaggleError(f"Kaggle erlaubt das Abbrechen nicht über die Schnittstelle – auf {url} → „Cancel run“ "
                          f"klicken. Sonst endet der Lauf spätestens nach {r['plan'].get('max_stunden')} h von "
                          "selbst und exportiert den Stand bis dahin.")

    def result(self, rid: str) -> Path:
        """policy.onnx (und metrics.json) des Laufs nach <root>/policies/kaggle/<id>/ laden → Pfad."""
        r = self._get(rid)
        if r.get("status") != "fertig":
            raise KaggleError(f"Der Lauf ist noch nicht fertig ({r.get('status')}).")
        folder = self.result_dir / rid
        target = folder / "policy.onnx"
        if r.get("onnx") and Path(r["onnx"]).exists():
            return Path(r["onnx"])
        api = self._api()
        files, _ = self._outputs(api, r)
        if "policy.onnx" not in files:
            raise KaggleError("In den Ausgaben des Kernels liegt keine policy.onnx.")
        data = api.download(files["policy.onnx"], MAX_ONNX)
        if len(data) < 64 or data.lstrip()[:1] in (b"<", b"{"):
            raise KaggleError("Die geladene policy.onnx ist keine ONNX-Datei.")
        folder.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(".onnx.teil")
        tmp.write_bytes(data)
        tmp.replace(target)
        if "metrics.json" in files:
            try:
                (folder / "metrics.json").write_bytes(api.download(files["metrics.json"], MAX_METRICS))
            except Exception as exc:
                log.info("metrics.json %s: %s", rid, exc)
        self._update(rid, onnx=str(target))
        return target
