"""Aus der Antwort der Ente wird eine Abfolge zum Abspielen: Sätze und Entenlaute.

Claude darf Laute selbst einstreuen (`*quak*`, `*quak?*`, `*gurr*` …). Dazu streut
duckpilot je nach Einstellung („Entenlaute: selten/manchmal/oft“) selbst welche ein –
nie zwei hintereinander, nie mehr als drei pro Antwort, nie bei Stopp und Sicherheit.

Sätze werden einzeln erzeugt: Der erste ist schnell fertig und läuft schon, während die
nächsten noch entstehen. Die Laute kommen aus Pollens Stimmbank (am Roboter aus dem
Roboter selbst).
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import random
import re
import threading
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Awaitable, Callable

from . import describe, tts

log = logging.getLogger(__name__)

ENGINE_NAME = {"qwen": "Qwen3-TTS", "piper": "Piper"}


def explain(exc: BaseException, engine: str = "qwen") -> str:
    """Fehler in einen Satz, mit dem man etwas anfangen kann."""
    name = ENGINE_NAME.get(engine, engine)
    repair = f"Unter Charakter → Stimme bei {name} auf „Reparieren“ klicken, dann duckpilot neu starten."
    if isinstance(exc, ModuleNotFoundError):
        return f"{name} ist nicht vollständig installiert – es fehlt „{exc.name or exc}“. {repair}"
    if isinstance(exc, ImportError) and "huggingface-hub" in str(exc):
        # transformers 4.57 prüft beim Laden die Version (z. B. nach der Installation fürs Training)
        return f"huggingface_hub hat die falsche Version für {name}. {repair}"
    if isinstance(exc, tts.EngineError):
        return str(exc)
    roh = f"{type(exc).__name__}: {exc}"
    # Seit 0.38.40: statt seitenlanger Rohtexte (gemeldet 11.11. mit drei Bildern) ein Satz, was passiert ist und wo
    if "Unrecognized model" in roh or "no file named" in roh or "model.safetensors" in roh:
        return (f"Das Modell für {name} ist nicht vollständig auf diesem PC (ein früherer Download brach ab). Beim "
                "nächsten Klick prüft Knowlin die Dateien und lädt nur nach, was fehlt.")
    return einordnen(roh, "Hugging Face")

from ..fehlerort import einordnen  # noqa: E402

FREQ = {"aus": 0.0, "selten": 0.15, "manchmal": 0.35, "oft": 0.6}
MOTOREN = ("browser", "piper", "qwen")
MAX_CLIPS = 80
MAX_LAUTE = 3

MARK = re.compile(r"\*([^*\n]{1,40})\*")
PAREN = re.compile(r"\(([^()\n]{0,80})\)")
QUAK = re.compile(r"(?<![\wäöüß])((?:qu+a+k+|gack+(?:er)?)(?:[\s-]+(?:qu+a+k+|gack+))*)([!?.…]*)(?![\wäöüß])", re.I)
EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿️]")
SENT = re.compile(r"(?<=[.!?…])\s+")
SOUNDY = ("qua", "gack", "gurr", "brumm", "pick", "klapper", "juhu", "wiii", "hui", "grr", "schnatter", "kicher")


def tag_for(word: str, punct: str = "") -> str:
    """Welcher Laut aus der Stimmbank passt zu einem geschriebenen Laut?"""
    w = word.lower().strip()
    p = punct + ("?" if w.endswith("?") else "") + ("!" if w.endswith("!") else "")
    if any(k in w for k in ("gurr", "brumm", "gähn", "gaehn", "schnurr")):
        return "coo"
    if any(k in w for k in ("pick", "klapper", "tock")):
        return "peck"
    if any(k in w for k in ("juhu", "wiii", "hui", "yay")):
        return "wheee"
    if "grr" in w or "empör" in w:
        return "alarm"
    if "?" in p:
        return "inquire"
    if re.search(r"a{3,}", w) or "!!" in p:
        return "greet"            # „quaaak!“ ist ein kräftiges Quaken, kein langes Jauchzen
    if re.search(r"(qu\w*|gack\w*)[\s-]+(qu|gack)", w) or "hallo" in w:
        return "greet"
    return "chirp"


def _soundy(s: str) -> bool:
    s = s.lower()
    return any(k in s for k in SOUNDY)


def clean(text: str) -> str:
    text = EMOJI.sub("", text)
    text = re.sub(r"[#_`>]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def parse(text: str) -> list[tuple[str, str]]:
    """→ [("text", "…"), ("laut", "chirp"), …]. Regieanweisungen (*wackelt*) fallen weg."""
    text = PAREN.sub(lambda m: f"*{m.group(1)}*" if _soundy(m.group(1)) else "", text or "")
    parts: list[tuple[str, str]] = []

    def add_text(s: str) -> None:
        pos = 0
        for m in QUAK.finditer(s):
            before = s[pos:m.start()]
            if before.strip():
                parts.append(("text", before))
            parts.append(("laut", tag_for(m.group(1), m.group(2))))
            pos = m.end()
        if s[pos:].strip():
            parts.append(("text", s[pos:]))

    pos = 0
    for m in MARK.finditer(text):
        add_text(text[pos:m.start()])
        inner = m.group(1).strip()
        if _soundy(inner):
            parts.append(("laut", tag_for(inner)))
        pos = m.end()
    add_text(text[pos:])
    out: list[tuple[str, str]] = []
    for kind, value in parts:
        if kind == "text":
            value = clean(value).strip(" ,;:–-")
            if not re.search(r"[\wäöüß]", value):
                continue
        out.append((kind, value))
    return out


def sentences(text: str) -> list[str]:
    """In Sätze teilen; ganz kurze an den Nachbarn hängen, sehr lange am Komma teilen.

    Teilstücke eines langen Satzes enden auf „,“ – dort kommt kein Laut dazwischen."""
    raw = [s.strip() for s in SENT.split(text) if s.strip()]
    out: list[str] = []
    carry = ""
    for i, s in enumerate(raw):
        s = f"{carry} {s}".strip() if carry else s
        carry = ""
        last = i == len(raw) - 1
        if len(s) < 14 and not last:
            carry = s
            continue
        if len(s) < 14 and last and out and not out[-1].endswith(","):
            out[-1] = f"{out[-1]} {s}"
            continue
        while len(s) > 170 and "," in s[60:150]:
            cut = s.index(",", 60) + 1
            out.append(s[:cut].strip())
            s = s[cut:].strip()
        out.append(s)
    if carry:
        out.append(carry)
    return out


def spoken_text(text: str) -> str:
    """Was im Chat steht – ohne Regieanweisungen, Laute bleiben als *quak* sichtbar."""
    text = PAREN.sub(lambda m: f"*{m.group(1)}*" if _soundy(m.group(1)) else "", text or "")
    return clean(MARK.sub(lambda m: m.group(0) if _soundy(m.group(1)) else "", text))


def plan(text: str, freq: float, rng: random.Random, stimmung: str = "ausgeglichen",
         goofy: bool = False, ernst: bool = False) -> list[dict[str, Any]]:
    """Die Abfolge: Sätze und Laute, mit eingestreuten Lauten je nach Häufigkeit."""
    parts = parse(text)
    if ernst or freq <= 0:
        parts = [p for p in parts if p[0] == "text"]
    explicit = any(k == "laut" for k, _ in parts)
    items: list[dict[str, Any]] = []
    for kind, value in parts:
        if kind == "laut":
            items.append({"art": "laut", "ton": value})
        else:
            items.extend({"art": "text", "text": s} for s in sentences(value))
    if not ernst and freq > 0 and not explicit:
        calm = stimmung in ("mitfühlend", "müde")
        happy = goofy or stimmung in ("begeistert", "fröhlich", "stolz", "erleichtert")
        boost = 1.4 if happy else 0.5 if calm else 1.0
        if rng.random() < min(0.9, freq * 1.2 * boost):
            first = ("coo" if calm else "alarm" if stimmung == "erschrocken"
                     else rng.choice(("greet", "chirp")) if happy else "chirp")
            items.insert(0, {"art": "laut", "ton": first})
        i = 1
        while i < len(items):
            prev = items[i - 1]
            if (prev["art"] == "text" and items[i]["art"] == "text" and not prev["text"].endswith(",")
                    and rng.random() < freq * 0.6 * boost):
                tag = "inquire" if prev["text"].endswith("?") else ("coo" if calm else "chirp")
                items.insert(i, {"art": "laut", "ton": tag})
                i += 1
            i += 1
        last = items[-1] if items else None
        if last and last["art"] == "text" and last["text"].endswith("?") and rng.random() < freq * 0.8:
            items.append({"art": "laut", "ton": "inquire"})
    # nie zwei Laute hintereinander, höchstens drei
    out: list[dict[str, Any]] = []
    count = 0
    for it in items:
        if it["art"] == "laut":
            if (out and out[-1]["art"] == "laut") or count >= MAX_LAUTE:
                continue
            count += 1
        out.append(it)
    return out


class Speaker:
    """Erzeugt die Sätze im Hintergrund und hält sie kurz zum Abholen bereit."""

    def __init__(self, root: Path, config: Any, on_change: Callable[[], None] | None = None) -> None:
        self.root = root
        self.config = config
        self.synth = tts.Synth(root)
        self.clips: OrderedDict[str, asyncio.Future] = OrderedDict()
        self.texts: dict[str, str] = {}
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="stimme")
        self.rng = random.Random()
        self.on_change = on_change
        self.jobs: dict[str, dict[str, Any]] = {}       # Downloads und Entwürfe
        self.takes: dict[str, tuple[Any, int, str, str, str]] = {}
        # übersetzt die Stimmbeschreibung fürs Modell: async (text) -> (englisch, weg); None = unverändert
        self.translator: Callable[[str], Awaitable[tuple[str, str]]] | None = None
        self.last_error: str | None = None
        self._lock = threading.Lock()
        # seit 0.37.9: Sekunden Rechnen je Sekunde Sprache, je Motor (gleitender Mittelwert) – entscheidet, ob eine
        # Antwort mit der eigenen Stimme flüssig gesprochen werden kann
        self.faktor: dict[str, float] = {}
        self.messungen: dict[str, int] = {}

    # ── Zustand ──────────────────────────────────────────────────────────
    def motor(self) -> str:
        m = getattr(self.config, "stimme_motor", "browser")
        m = m if m in MOTOREN else "browser"
        # Englisch (seit 0.34): Qwen spricht Englisch selbst; eine deutsche Piper-Stimme läse Englisch mit deutscher
        # Aussprache – dann die englische Browser-Stimme, bis eine englische Piper-Stimme gewählt ist.
        if m == "piper" and getattr(self.config, "sprache", "de") == "en" and not str(self.config.stimme_piper).startswith("en"):
            return "browser"
        return m

    def voice(self) -> str:
        return self.config.stimme_qwen if self.motor() == "qwen" else self.config.stimme_piper

    def ready(self) -> tuple[bool, str]:
        m = self.motor()
        if m == "browser":
            return True, ""
        if m == "piper":
            if not self.synth.piper.installed():
                return False, "Piper ist noch nicht installiert"
            if not self.synth.piper.has_voice(self.config.stimme_piper):
                return False, "die Piper-Stimme ist noch nicht geladen"
            return True, ""
        fehlt = self.synth.qwen.missing()
        if fehlt:
            if "qwen_tts" in fehlt:
                return False, "Qwen3-TTS ist noch nicht installiert"
            return False, f"Qwen3-TTS ist nicht vollständig installiert (es fehlt {', '.join(fehlt)})"
        if not self.config.stimme_qwen or not any(v["id"] == self.config.stimme_qwen for v in self.synth.qwen.voices()):
            return False, "es gibt noch keine entworfene Entenstimme"
        # seit 0.37.6 (Hinweis aus dem Test „spielt sie nur im Test ab, das Programm hängt“): Die Fassungen beim Entwerfen
        # kommen vom Entwurfsmodell; gesprochen wird mit dem Sprechmodell (Base, beim ersten Mal ≈ 2,4 GB Download).
        # Bis es geladen ist, spricht die Browser-Stimme – vorher warteten Sätze und Mikrofon still auf den Download.
        if not self.synth.qwen.loaded(self._qualitaet()):
            job = self.jobs.get("sprechmodell") or {}
            if job.get("fehler"):
                return False, f"das Sprechmodell lädt nicht ({job['fehler']})"
            return False, job.get("text") or "das Sprechmodell ist noch nicht geladen"
        return True, ""

    def _qualitaet(self) -> str:
        return getattr(self.config, "qwen_qualitaet", "schnell")

    def info(self) -> dict[str, Any]:
        ok, why = self.ready()
        piper = self.synth.piper
        qwen = self.synth.qwen
        return {
            "motor": self.motor(),
            "bereit": ok,
            "tempo": {m: {"faktor": f, "saetze": self.messungen.get(m, 0)} for m, f in self.faktor.items()},
            "rueckfall": "piper" if self._piper_bereit() else "browser",
            "grund": why,
            "fehler": self.last_error,
            "piper": {
                "installiert": piper.installed(),
                "stimmen": [{"id": k, **{x: v[x] for x in ("name", "art", "mb")}, "geladen": piper.has_voice(k)}
                            for k, v in tts.PIPER_VOICES.items()],
            },
            "qwen": {
                "installiert": qwen.installed(),
                "fehlt": qwen.missing(),
                "stimmen": qwen.voices(),
                "modelle": {q: qwen.has_model(r) for q, r in {**tts.QWEN_BASE, "entwurf": tts.QWEN_DESIGN}.items()},
                "mb": tts.QWEN_MB,
                "vorlagen": describe.PRESETS_DE,
                "uebersetzer": self.translator is not None,
                "geraet": qwen.device,
            },
            "jobs": self.jobs,
            "fassungen": [{"id": k, "sekunden": round(len(v[0]) / v[1], 1)} for k, v in self.takes.items()],
        }

    def _changed(self) -> None:
        if self.on_change:
            try:
                self.on_change()
            except Exception:
                log.exception("Stimme: Benachrichtigung")

    def warm_up(self) -> None:
        """Modell schon laden, damit der erste Satz nicht wartet (im Hintergrund, mit Fortschritt auf der Stimme-Seite)."""
        m = self.motor()
        if m == "browser":
            return
        if m == "piper":
            ok, _ = self.ready()
            if not ok:
                return

            def load_piper() -> None:
                try:
                    self.synth.piper._voice(self.config.stimme_piper)
                except Exception as exc:
                    self.last_error = explain(exc, "piper")
                    log.warning("Stimme vorladen: %s", self.last_error)

            self.pool.submit(load_piper)
            return
        qwen, q = self.synth.qwen, self._qualitaet()
        if qwen.missing() or qwen.loaded(q):
            return
        job = self.jobs.get("sprechmodell")
        if job and job.get("laeuft"):
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        repo = tts.QWEN_BASE.get(q, tts.QWEN_BASE["schnell"])
        neu = not qwen.has_model(repo)
        mb = tts.QWEN_MB.get(q, 2400)
        if not neu:
            text = "lädt das Sprechmodell …"
        elif qwen.angefangen(repo):
            text = "setzt den Download des Sprechmodells fort …"
        else:
            text = f"lädt das Sprechmodell herunter (einmalig ≈ {mb / 1000:.1f} GB) …".replace(".", ",", 1)
        job = self.jobs["sprechmodell"] = {"laeuft": True, "fehler": None, "text": text, "anteil": None}

        def melden() -> None:
            if loop is not None:
                loop.call_soon_threadsafe(self._changed)

        def fortschritt(n: int, gesamt: int | None) -> None:
            # seit 0.37.7 (Wunsch des Maintainers): Fortschritt sehen; ein abgebrochener Download geht beim nächsten Start weiter
            if not gesamt or n >= gesamt:
                job.update(text="lädt das Sprechmodell …", anteil=None)
            else:
                weiter = " (fortgesetzt)" if job.get("fortgesetzt") else ""
                job.update(text=f"lädt das Sprechmodell herunter: {tts.download_text(n, gesamt)}{weiter}",
                           anteil=round(n / gesamt, 3))
            melden()

        if neu and qwen.angefangen(repo):
            job["fortgesetzt"] = True

        def load() -> None:
            try:
                qwen.base(q, fortschritt)
                job.update(text="wärmt sich auf …", anteil=None)
                melden()
                self._aufwaermen(q)
                job.update(laeuft=False, text="Sprechmodell geladen", anteil=None)
            except Exception as exc:
                self.last_error = explain(exc, "qwen")
                job.update(laeuft=False, fehler=self.last_error, text="fehlgeschlagen")
                log.warning("Stimme vorladen: %s", self.last_error)
            melden()

        melden()
        self.pool.submit(load)

    def _aufwaermen(self, q: str) -> None:
        """Einen kurzen Satz rechnen (seit 0.37.9): Beim ersten Satz übersetzt PyTorch die Programme für Grafikkarte bzw.
        Prozessor – das soll nicht der erste echte Satz abbekommen. Nebenbei die erste Messung des Tempos."""
        vid = self.config.stimme_qwen
        if not vid:
            return
        try:
            st = self.style("ausgeglichen", False, 0.5, motor="qwen")
            audio = self.synth.render("Hallo, ich bin bereit.", "qwen", vid, st, q)
            self.messen("qwen", audio)
        except Exception as exc:
            log.warning("Stimme aufwärmen: %s", explain(exc, "qwen"))

    # ── Sprechen ─────────────────────────────────────────────────────────
    def _ente(self) -> bool:
        """Verkörperungen, die keine Ente sind (Reachy), bekommen nie Entenlaute oder Entenfilter – egal, was eingestellt ist."""
        from ..figuren import ist_ente

        return ist_ente(getattr(self.config, "modul", "duckpilot"))

    def style(self, stimmung: str, goofy: bool, energie: float, motor: str | None = None,
              ente: bool | None = None) -> tts.Style:
        tempo = 1.0 + (energie - 0.5) * 0.14 + (0.06 if goofy else 0.0)
        tempo += {"begeistert": 0.05, "erschrocken": 0.06, "mitfühlend": -0.08, "müde": -0.1}.get(stimmung, 0.0)
        # entworfene Qwen-Stimmen brauchen keinen Entenfilter – sie klingen schon wie beschrieben (0.37.8);
        # `ente=False`: Knowlins Kopf spricht (Startseite, seit 0.38.8) – nie wie eine Ente
        ente = self._ente() if ente is None else ente
        entenhaft = 0.0 if (motor or self.motor()) == "qwen" or not ente else float(self.config.entenhaft)
        return tts.Style(stimmung=stimmung, goofy=goofy, energie=energie, entenhaft=entenhaft, tempo=round(tempo, 3))

    def prepare(self, text: str, stimmung: str = "ausgeglichen", goofy: bool = False, energie: float = 0.5,
                ernst: bool = False, ente: bool | None = None) -> dict[str, Any]:
        """Die Abfolge planen und die Sätze schon erzeugen lassen. Kein Motor bereit → Browser-Stimme."""
        ente = self._ente() if ente is None else ente
        freq = FREQ.get(getattr(self.config, "entenlaute", "manchmal"), 0.35) if ente else 0.0
        items = plan(text, freq, self.rng, stimmung, goofy, ernst)
        ok, why = self.ready()
        if not ok and self.motor() == "qwen":
            self.warm_up()                     # lädt (wieder), falls nötig – bis dahin die Browser-Stimme
            ok, why = self.ready()
        motor = self.motor() if ok else "browser"
        warten = None
        if motor == "qwen":
            # je Antwort entscheiden, nicht mitten im Satz wechseln (seit 0.37.9): schafft Qwen es auf diesem Gerät
            # nicht flüssig, spricht die ganze Antwort Piper (falls geladen), sonst die Browser-Stimme
            schafft, warten = self._schaffts("qwen", [i["text"] for i in items if i["art"] == "text"])
            if not schafft and getattr(self.config, "qwen_geduldig", False):
                schafft = True                 # „darf halt langsamer sein“ (seit 0.38.40): warten statt wechseln
                warten = self._gesamt_s("qwen", [i["text"] for i in items if i["art"] == "text"])
            if not schafft:
                ok, why = False, ("die entworfene Stimme rechnet auf diesem Gerät zu langsam "
                                  f"({self.faktor['qwen']:.1f} s je Sekunde Sprache)").replace(".", ",", 1)
                motor = "piper" if self._piper_bereit() else "browser"
        elif not ok and self.motor() == "qwen" and self._piper_bereit():
            motor = "piper"                    # Sprechmodell lädt noch: lieber Piper als die Browser-Stimme
        if motor != "browser":
            st = self.style(stimmung, goofy, energie, motor=motor, ente=ente)
            voice = self.config.stimme_qwen if motor == "qwen" else self.config.stimme_piper
            self._vorrechnen(items, motor, voice, st, getattr(self.config, "qwen_qualitaet", "schnell"))
        out: dict[str, Any] = {"motor": motor, "teile": items}
        if not ok and self.motor() != "browser":
            out["hinweis"] = why
        if warten is not None:
            grenze = self.GEDULD_MAX_S if motor == "qwen" and getattr(self.config, "qwen_geduldig", False) else 45.0
            out["warten_s"] = round(min(grenze, max(15.0, warten * 2 + 5)), 1)
        return out

    def _vorrechnen(self, items: list[dict[str, Any]], motor: str, voice: str, st: tts.Style, quality: str) -> None:
        """Sätze schon im Hintergrund erzeugen lassen; jeder Satz bekommt seine Kennung (`id`) zum Abholen."""
        loop = asyncio.get_running_loop()
        for it in items:
            if it["art"] != "text":
                continue
            key = "|".join(map(str, (motor, voice, quality, st.entenhaft, st.tempo, st.stimmung, st.goofy,
                                     it["text"])))
            cid = hashlib.sha1(key.encode()).hexdigest()[:16]
            it["id"] = cid
            if cid not in self.clips:
                self.clips[cid] = loop.run_in_executor(self.pool, self._render, it["text"], motor, voice, st, quality)
                self.texts[cid] = it["text"]
            self.clips.move_to_end(cid)
        while len(self.clips) > MAX_CLIPS:
            old, fut = self.clips.popitem(last=False)
            self.texts.pop(old, None)
            if not fut.done():
                fut.cancel()

    # ── Knowlins Kopf (seit 0.38.9, wählbar seit 0.38.10): eigene Stimme, ohne Entenlaute, ruhig – ohne künstliches
    # Absenken (Rückmeldung „die Stimme von Knowlin ist nicht gut“). Gewählt in Einstellungen → Stimme.
    def _kopf_config(self) -> Any:
        """Die Einstellungen, wie `prepare` sie liest – nur mit Knowlins Stimme statt der der Verkörperung."""
        c = self.config
        werte = {k: getattr(c, k) for k in dir(c) if not k.startswith("_") and not callable(getattr(c, k, None))}
        werte.update(stimme_motor=getattr(c, "kopf_stimme_motor", "piper"),
                     stimme_piper=getattr(c, "kopf_stimme_piper", "thorsten"),
                     stimme_qwen=getattr(c, "kopf_stimme_qwen", ""), modul="kopf", entenhaft=0.0, entenlaute="aus")
        return SimpleNamespace(**werte)

    def kopf_motor(self) -> str:
        alt = self.config
        self.config = self._kopf_config()
        try:
            return self.motor()
        finally:
            self.config = alt

    def prepare_kopf(self, text: str, stimmung: str = "ausgeglichen", ernst: bool = False) -> dict[str, Any]:
        """Wie `prepare`, aber mit Knowlins Stimme: keine Entenlaute, kein Entenfilter, ruhig, nie albern.
        Fehlt die gewählte Stimme, spricht er mit der Browser-Stimme in normaler Lage."""
        alt = self.config
        self.config = self._kopf_config()
        try:
            out = self.prepare(text, stimmung, False, 0.4, ernst=ernst, ente=False)
        finally:
            self.config = alt
        out["stimme"] = "kopf"
        return out

    # ── Tempo der eigenen Stimme (seit 0.37.9, Hinweis aus dem Test „springt wegen geringer Leistung auf die Browserstimme“) ──
    SPRECH_S_JE_ZEICHEN = 0.07         # grob: 14 Zeichen je Sekunde Sprache
    ERSTER_SATZ_MAX_S = 10.0           # länger soll niemand auf den ersten Satz warten
    FLUESSIG_FAKTOR = 1.0              # rechnet sie langsamer als sie spricht, holt sie bei langen Antworten nicht auf

    def messen(self, motor: str, audio: tts.Audio) -> None:
        if audio.sekunden < 0.3 or audio.rechenzeit <= 0:
            return
        f = audio.rechenzeit / audio.sekunden
        n = self.messungen.get(motor, 0)
        alt = self.faktor.get(motor)
        self.faktor[motor] = f if alt is None else round(alt * 0.7 + f * 0.3, 3)
        self.messungen[motor] = n + 1
        log.info("Stimme %s: %.1f s Ton in %.1f s gerechnet (Faktor %.2f)", motor, audio.sekunden, audio.rechenzeit, f)

    def _schaffts(self, motor: str, saetze: list[str]) -> tuple[bool, float | None]:
        """Kann dieser Motor die Antwort flüssig sprechen? → (ja/nein, geschätzte Wartezeit auf den ersten Satz)."""
        f = self.faktor.get(motor)
        if f is None or not saetze:
            return True, None
        erster = f * len(saetze[0]) * self.SPRECH_S_JE_ZEICHEN
        if erster > self.ERSTER_SATZ_MAX_S:
            return False, erster
        # danach muss sie mithalten: Rechnen des nächsten Satzes ≤ Sprechen des vorigen (mit etwas Luft)
        if len(saetze) > 1 and f > self.FLUESSIG_FAKTOR * 1.15:
            return False, erster
        return True, erster

    GEDULD_MAX_S = 240.0                # so lange wartet das Fenster höchstens auf einen Satz, wenn langsam erlaubt ist

    def _gesamt_s(self, motor: str, saetze: list[str]) -> float | None:
        """Geschätzte Rechenzeit der ganzen Antwort (die Sätze werden nacheinander gerechnet)."""
        f = self.faktor.get(motor)
        if f is None or not saetze:
            return None
        return f * sum(len(s) for s in saetze) * self.SPRECH_S_JE_ZEICHEN

    def _piper_bereit(self) -> bool:
        piper = self.synth.piper
        if not piper.installed() or not piper.has_voice(self.config.stimme_piper):
            return False
        return not (getattr(self.config, "sprache", "de") == "en" and not str(self.config.stimme_piper).startswith("en"))

    def _render(self, text: str, motor: str, voice: str, st: tts.Style, quality: str) -> tts.Audio:
        try:
            audio = self.synth.render(text, motor, voice, st, quality)
            self.last_error = None
            self.messen(motor, audio)
            return audio
        except Exception as exc:
            self.last_error = explain(exc, motor)
            log.warning("Stimme: %s", self.last_error)
            raise

    async def clip(self, cid: str) -> tts.Audio:
        fut = self.clips.get(cid)
        if fut is None:
            raise KeyError(cid)
        return await asyncio.shield(fut)

    def mouth_of(self, cid: str) -> list[float] | None:
        fut = self.clips.get(cid)
        if fut is None or not fut.done() or fut.cancelled() or fut.exception():
            return None
        return fut.result().mund

    # ── Stimmen laden ────────────────────────────────────────────────────
    async def download_piper(self, vid: str) -> None:
        if vid not in tts.PIPER_VOICES:
            raise ValueError(f"Keine Piper-Stimme '{vid}'")
        key = f"piper:{vid}"
        if self.jobs.get(key, {}).get("laeuft"):
            return
        job = self.jobs[key] = {"laeuft": True, "anteil": 0.0, "fehler": None, "text": "lädt …"}
        self._changed()
        loop = asyncio.get_running_loop()
        last = [0.0]

        def progress(f: float) -> None:
            job["anteil"] = round(f, 3)
            if f - last[0] > 0.05:
                last[0] = f
                loop.call_soon_threadsafe(self._changed)

        try:
            await loop.run_in_executor(None, self.synth.piper.download, vid, progress)
            job.update(laeuft=False, anteil=1.0, text="geladen")
        except Exception as exc:
            job.update(laeuft=False, fehler=explain(exc, "piper"), text="fehlgeschlagen")
        self._changed()

    # ── Entenstimme entwerfen (Qwen3-TTS) ────────────────────────────────
    async def design(self, instruct: str, name: str, takes: int = 3, art: str = "duckpilot") -> None:
        """Stimme nach Beschreibung entwerfen. `art`: Körper (`config.modul`) oder „kopf“ – bestimmt den Probesatz."""
        instruct = re.sub(r"\s+", " ", instruct or "").strip()[:500]
        if len(instruct) < 10:
            raise ValueError("Beschreib die Stimme in ein, zwei Sätzen.")
        if not self.synth.qwen.installed():
            raise ValueError("Qwen3-TTS ist noch nicht installiert.")
        job = self.jobs.get("entwurf")
        if job and job.get("laeuft"):
            raise ValueError("Es wird schon eine Stimme entworfen.")
        job = self.jobs["entwurf"] = {"laeuft": True, "fehler": None, "text": "startet …", "beschreibung": instruct}
        self.takes.clear()
        self._changed()
        loop = asyncio.get_running_loop()
        text = tts.design_text(art, name)
        original = instruct
        if self.translator is not None:
            job["text"] = "übersetzt die Beschreibung ins Englische …"
            self._changed()
            try:
                instruct, weg = await self.translator(original)
            except Exception as exc:          # Übersetzen ist nur eine Hilfe – dann eben auf Deutsch
                log.warning("Stimmbeschreibung übersetzen: %s", exc)
                instruct, weg = original, "deutsch"
            job.update(modell_text=instruct, weg=weg)

        def progress(msg: str) -> None:
            job["text"] = msg
            loop.call_soon_threadsafe(self._changed)

        try:
            out = await loop.run_in_executor(self.pool, self.synth.qwen.design, instruct, text, max(1, min(4, takes)), progress)
            for i, (x, sr) in enumerate(out):
                tid = f"f{i + 1}-{hashlib.sha1(instruct.encode()).hexdigest()[:6]}"
                self.takes[tid] = (x, sr, text, instruct, original)
                audio = tts.Audio(tts.to_wav(x, sr), tts.mouth_track(x, sr), round(len(x) / sr, 2))
                fut = loop.create_future()
                fut.set_result(audio)
                self.clips[tid] = fut
            job.update(laeuft=False, text=f"{len(out)} Fassungen – anhören und eine übernehmen")
        except Exception as exc:
            log.exception("Stimme entwerfen")
            job.update(laeuft=False, fehler=explain(exc), text="fehlgeschlagen")
        self._changed()

    def adopt(self, take: str, name: str) -> str:
        if take not in self.takes:
            raise KeyError("Diese Fassung gibt es nicht mehr – bitte neu entwerfen.")
        x, sr, text, instruct, original = self.takes[take]
        name = re.sub(r"\s+", " ", name or "").strip()[:40] or "Entenstimme"
        vid = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:30] or "stimme"
        base, n = vid, 2
        while (self.synth.qwen.voices_dir / f"{vid}.wav").exists():
            vid, n = f"{base}-{n}", n + 1
        self.synth.qwen.save_voice(vid, name, x, sr, text, instruct, beschreibung=original)
        self._changed()
        return vid

    def delete_voice(self, vid: str) -> None:
        if not re.fullmatch(r"[a-z0-9-]{1,40}", vid or ""):
            raise ValueError("ungültige Stimme")
        self.synth.qwen.delete_voice(vid)
        self._changed()

    def style_dict(self, stimmung: str, goofy: bool, energie: float) -> dict[str, Any]:
        return asdict(self.style(stimmung, goofy, energie))
