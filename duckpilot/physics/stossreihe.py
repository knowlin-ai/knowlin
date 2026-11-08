"""Stoßreihe: Wie robust steht die Ente gegen Stöße? Ein Klick, viele unsichtbare Versuche, ein Profil.

Jeder Versuch läuft in einer eigenen, unsichtbaren MuJoCo-Welt (leerer Boden, schneller als Echtzeit): die Ente
steht frisch, schwingt ~1 s ein, bekommt einen Stoß mit demselben Mechanismus wie im Kollisionsmodus
(`Kollision.stoss`) und wird ~3 s weiter beobachtet. Raster: 8 Richtungen × 3 Stärken (`STUFEN`) × 2 Höhen
(Rumpf, Kopf) = 48 Versuche, per Parameter einschränkbar. Ausgang wie bei jeder Episode – steht / wackelt / fällt –
dazu größte Neigung, Versatz und Zeit bis ruhig.

Gerechnet wird in einem eigenen Rechenprozess (`starte_prozess`), damit der Server nicht hängt. Der Prozess schickt
je Versuch ein Ergebnis zurück; Dateien schreibt nur der Server (`StossreiheDienst`): das Profil unter
`<daten>/kollision/profile/<zeitstempel>.json` und jede Episode in `kollision/episoden.jsonl` (`reiz.quelle = "reihe"`).
Stimmung und Erfahrungsnetz lernen daraus nichts – die Reihe läuft an der sichtbaren Ente vorbei.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

# Von wo der Stoß kommt (relativ zur Blickrichtung, Grad; wie `kollision.SEITEN`, nur feiner): geschoben wird in die
# Gegenrichtung (von vorn gestoßen → nach hinten)
RICHTUNGEN: dict[str, float] = {"vorn": 0.0, "vorn_links": 45.0, "links": 90.0, "hinten_links": 135.0,
                                "hinten": 180.0, "hinten_rechts": -135.0, "rechts": -90.0, "vorn_rechts": -45.0}
RICHTUNG_NAMEN = {"vorn": "vorn", "vorn_links": "vorn links", "links": "links", "hinten_links": "hinten links",
                  "hinten": "hinten", "hinten_rechts": "hinten rechts", "rechts": "rechts", "vorn_rechts": "vorn rechts"}
HOEHEN = ("rumpf", "kopf")
HOEHE_NAMEN = {"rumpf": "Rumpf", "kopf": "Kopf"}
EINSCHWINGEN_S = 1.0
NACHLAUF_S = 3.0
LIEGT_NOCH_S = 1.0             # nach dem Sturz noch so lange zusehen, dann ist der Versuch vorbei
FALL_UP = 0.45                 # wie das Physik-Backend: Rumpf-Hochachse darunter …
FALL_HALTEN_S = 0.25           # … länger als das = gefallen
RUHIG_TEMPO_MS = 0.05          # ruhig: Rumpf langsamer als das …
RUHIG_DREH = 0.3               # … dreht sich kaum (rad/s) …
RUHIG_KIPP = 0.01              # … und steht (fast) so aufrecht wie vor dem Stoß (Hochachse)
SCHRITT_M = 0.04               # steht, hat sich aber um mehr als das versetzt = Ausfallschritt (seit 0.37)
MAX_WDH = 5                    # Wiederholungen je Zelle (seit 0.37): leicht gestreut, zeigt Grenzfälle
STREUUNG_GRAD, STREUUNG_STAERKE = 6.0, 0.06
PROFIL_ID = re.compile(r"\d{8}-\d{6}(-\d{1,3})?")
MAX_PROFILE = 200


class ReiheFehler(ValueError):
    pass


OHNE_PHYSIK = ("Die Stoßreihe braucht die echte Physik (MuJoCo und onnxruntime) – unter Einstellungen → Körper "
               "→ Echte Physik einrichten.")


def physik_grund() -> str | None:
    """Warum die Reihe hier nicht rechnen kann – oder None."""
    try:
        import mujoco  # noqa: F401
        import onnxruntime  # noqa: F401
    except ImportError:
        return OHNE_PHYSIK
    try:
        from .core import model_xml

        model_xml()
    except (FileNotFoundError, OSError) as exc:
        return f"Die Stoßreihe braucht die echte Physik: {exc}"
    return None


# ── Raster ───────────────────────────────────────────────────────────────
def raster(richtungen: Any = None, stufen: Any = None, hoehen: Any = None,
           wiederholungen: Any = 1) -> list[dict[str, Any]]:
    """Alle Versuche als [{richtung, stufe, hoehe, wdh}] – Reihenfolge: Höhe, Stärke, Richtung (so liest man die
    Tabelle), je Zelle `wiederholungen` Mal (wdh 0 = genau, ab 1 leicht gestreut). None oder leer heißt „alle“.
    Unbekannte Werte → ReiheFehler."""
    from .kollision import STUFEN

    def auswahl(werte: Any, alle: list[str], was: str) -> list[str]:
        if werte in (None, "", []):
            return list(alle)
        if isinstance(werte, str):
            werte = [werte]
        if not isinstance(werte, (list, tuple)):
            raise ReiheFehler(f"{was}: eine Liste")
        out = []
        for w in werte:
            w = str(w).strip().lower().replace("-", "_").replace(" ", "_")
            if w not in alle:
                raise ReiheFehler(f"{was}: {', '.join(alle)}")
            if w not in out:
                out.append(w)
        return [a for a in alle if a in out]            # immer in fester Reihenfolge

    r = auswahl(richtungen, list(RICHTUNGEN), "Richtungen")
    s = auswahl(stufen, list(STUFEN), "Stärken")
    h = auswahl(hoehen, list(HOEHEN), "Höhen")
    try:
        n = int(wiederholungen if wiederholungen not in (None, "") else 1)
    except (TypeError, ValueError) as exc:
        raise ReiheFehler(f"Wiederholungen: 1 bis {MAX_WDH}") from exc
    if not 1 <= n <= MAX_WDH:
        raise ReiheFehler(f"Wiederholungen: 1 bis {MAX_WDH}")
    return [{"richtung": a, "stufe": b, "hoehe": c, "wdh": k} for c in h for b in s for a in r for k in range(n)]


def streuung(richtung: str, stufe: str, hoehe: str, wdh: int) -> tuple[float, float]:
    """(Grad, Faktor) für eine Wiederholung: wdh 0 genau, sonst reproduzierbar leicht daneben."""
    if wdh <= 0:
        return 0.0, 1.0
    import random

    rng = random.Random(f"{richtung}|{stufe}|{hoehe}|{wdh}")
    return (round(rng.uniform(-STREUUNG_GRAD, STREUUNG_GRAD), 2),
            round(1.0 + rng.uniform(-STREUUNG_STAERKE, STREUUNG_STAERKE), 3))


# ── ein Versuch ──────────────────────────────────────────────────────────
def _gelenke(core: Any) -> list[float]:
    """15 Werte in der Reihenfolge der Episoden (wie `PhysicsBackend._joints`, Mund = 0)."""
    j = core.joints()
    return [j["left_hip_yaw"], j["left_hip_roll"], j["left_hip_pitch"], j["left_knee"], j["left_ankle"],
            j["neck_pitch"], j["head_pitch"], j["head_yaw"], j["head_roll"], 0.0,
            j["right_hip_yaw"], j["right_hip_roll"], j["right_hip_pitch"], j["right_knee"], j["right_ankle"]]


def neigung_grad(up: float) -> float:
    return math.degrees(math.acos(max(-1.0, min(1.0, float(up)))))


class Welt:
    """Eine unsichtbare Welt mit Ente, Policy und Stoß-Mechanismus – für viele Versuche nacheinander."""

    def __init__(self, policy_pfad: str | Path, action_scale: float, name: str = "policy",
                 use_bam: bool | None = None) -> None:
        from .core import PhysicsCore, Policy
        from .kollision import Kollision

        self.core = PhysicsCore(None, use_bam=use_bam, objects=True)
        self.kol = Kollision(self.core)
        self.core.pre_step = self.kol.pre_step
        self.policy = Policy(policy_pfad, name, action_scale)
        self.core.set_policy(self.policy)

    def versuch(self, richtung: str, stufe: str, hoehe: str, einschwingen_s: float = EINSCHWINGEN_S,
                nachlauf_s: float = NACHLAUF_S, abbruch: Callable[[], bool] | None = None,
                wdh: int = 0) -> dict[str, Any] | None:
        """Ein Stoß an der frisch stehenden Ente. → Ergebnis (mit Episode) oder None bei Abbruch."""
        from .core import CONTROL_DT, Command
        from .kollision import STUFEN, Episode, zustand

        core, kol = self.core, self.kol
        core.reset()                                  # setzt auch das Gedächtnis der Policy zurück
        kol._stoss = None
        cmd = Command()
        t = 0.0
        unten_seit: float | None = None
        gefallen = False

        def schritt() -> dict[str, float]:
            nonlocal t, unten_seit, gefallen
            core.control_step(cmd)
            t += CONTROL_DT
            tr = core.trunk()
            if tr["up"] < FALL_UP:
                unten_seit = t if unten_seit is None else unten_seit
                gefallen = gefallen or t - unten_seit > FALL_HALTEN_S
            else:
                unten_seit = None
            return tr

        for i in range(max(1, round(einschwingen_s / CONTROL_DT))):
            schritt()
            if abbruch and i % 25 == 0 and abbruch():
                return None
        schon_gefallen = gefallen
        tr = core.trunk()
        up0, x0, y0 = tr["up"], tr["x"], tr["y"]
        grad, faktor = streuung(richtung, stufe, hoehe, wdh)
        reiz = kol.stoss(ziel=hoehe, staerke=STUFEN[stufe] * faktor, richtung_grad=RICHTUNGEN[richtung] + grad + 180.0)
        reiz |= {"quelle": "reihe", "richtung": richtung, "stufe": stufe, "hoehe": hoehe,
                 "von_grad": RICHTUNGEN[richtung] + grad, "wdh": wdh}
        ep = Episode(art="stoss", reiz=reiz, t0=t, vorher=zustand(tr, gefallen))
        c, sn = math.cos(tr["yaw"]), math.sin(tr["yaw"])
        ep._v0 = (tr["vx"] * c - tr["vy"] * sn, tr["vx"] * sn + tr["vy"] * c)
        unruhig_bis = 0.0                           # zuletzt nicht ruhig (s nach dem Stoß)
        gefallen_um: float | None = None
        n = 0
        while True:
            tr = schritt()
            n += 1
            rel = t - ep.t0
            if gefallen and gefallen_um is None:
                gefallen_um = rel
            ruhig = (math.hypot(tr["vx"], tr["vy"]) < RUHIG_TEMPO_MS and abs(tr["vyaw"]) < RUHIG_DREH
                     and tr["up"] > up0 - RUHIG_KIPP)
            if not ruhig:
                unruhig_bis = rel
            fertig = ep.sample(t, tr, gefallen, _gelenke(core))
            if not fertig and (rel >= nachlauf_s or (gefallen_um is not None and rel - gefallen_um >= LIEGT_NOCH_S)):
                ep.nach, ep.ende, fertig = zustand(tr, gefallen), t, True
            if fertig:
                break
            if abbruch and n % 25 == 0 and abbruch():
                return None
        d = ep.to_dict()
        ruhig_nach = None if ep.gefallen or unruhig_bis >= rel - CONTROL_DT else round(unruhig_bis, 2)
        versatz = math.hypot(tr["x"] - x0, tr["y"] - y0)
        return {"richtung": richtung, "stufe": stufe, "hoehe": hoehe, "wdh": wdh, "ausgang": ep.ausgang,
                "schritt": ep.ausgang in ("steht", "wackelt") and versatz > SCHRITT_M,
                "streuung": {"grad": grad, "faktor": faktor},
                "neigung_max_grad": round(neigung_grad(ep.min_up), 1),
                "versatz_m": round(math.hypot(tr["x"] - x0, tr["y"] - y0), 3),
                "ruhig_nach_s": ruhig_nach, "gefallen_nach_s": None if gefallen_um is None else round(gefallen_um, 2),
                "impuls_ns": reiz["impuls_ns"], "dv_rumpf": ep.dv_rumpf, "schon_vorher_gefallen": schon_gefallen,
                "episode": d}


def fuehre_aus(auftrag: dict[str, Any], abbruch: Callable[[], bool] | None = None,
               welt: Welt | None = None) -> Iterator[dict[str, Any]]:
    """Alle Versuche eines Auftrags nacheinander ({policy_pfad, action_scale, raster, einschwingen_s, nachlauf_s})."""
    welt = welt or Welt(auftrag["policy_pfad"], float(auftrag.get("action_scale") or 1.0),
                        str(auftrag.get("policy_name") or "policy"), auftrag.get("use_bam"))
    for v in auftrag["raster"]:
        if abbruch and abbruch():
            return
        res = welt.versuch(v["richtung"], v["stufe"], v["hoehe"],
                           float(auftrag.get("einschwingen_s", EINSCHWINGEN_S)),
                           float(auftrag.get("nachlauf_s", NACHLAUF_S)), abbruch, int(v.get("wdh", 0)))
        if res is None:
            return
        yield res


# ── Rechenprozess ────────────────────────────────────────────────────────
def _rechenprozess(conn: Any, auftrag: dict[str, Any], stopp: Any) -> None:
    """Läuft im eigenen Prozess: baut die Welt, rechnet, schickt („bereit“ | „versuch“ | „fertig“ | „fehler“, …)."""
    try:
        welt = Welt(auftrag["policy_pfad"], float(auftrag.get("action_scale") or 1.0),
                    str(auftrag.get("policy_name") or "policy"), auftrag.get("use_bam"))
        conn.send(("bereit", {"motor": welt.core.motor_model}))
        for res in fuehre_aus(auftrag, stopp.is_set, welt):
            conn.send(("versuch", res))
        conn.send(("abgebrochen" if stopp.is_set() else "fertig", None))
    except Exception as exc:          # noqa: BLE001 – jeder Fehler geht als Text an den Server
        try:
            conn.send(("fehler", f"{type(exc).__name__}: {exc}"))
        except Exception:
            pass
    finally:
        conn.close()


def starte_prozess(auftrag: dict[str, Any]) -> tuple[Any, Any, Any]:
    """Rechenprozess starten (spawn, wie unter Windows). → (Prozess, Verbindung, Stopp-Signal)."""
    import multiprocessing as mp

    ctx = mp.get_context("spawn")
    a, b = ctx.Pipe()
    stopp = ctx.Event()
    p = ctx.Process(target=_rechenprozess, args=(b, auftrag, stopp), daemon=True, name="stossreihe")
    p.start()
    b.close()
    return p, a, stopp


# ── Profil ───────────────────────────────────────────────────────────────
def pruefsumme(path: str | Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _zaehlen(versuche: list[dict[str, Any]], key: str) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    for v in versuche:
        z = out.setdefault(v[key], {"steht": 0, "wackelt": 0, "faellt": 0})
        a = v["ausgang"] if v["ausgang"] in z else "faellt"
        z[a] += 1
    return out


def zusammenfassen(versuche: list[dict[str, Any]]) -> dict[str, Any]:
    """Zahlen fürs Profil: wie viele bleiben stehen (ruhig oder wackelnd), wie viele fallen – gesamt und je Achse."""
    n = len(versuche)
    ruhig = sum(v["ausgang"] == "steht" for v in versuche)
    wackelt = sum(v["ausgang"] == "wackelt" for v in versuche)
    stehen = ruhig + wackelt
    fallen = n - stehen
    schritte = sum(bool(v.get("schritt")) for v in versuche)
    teile = [f"{ruhig} ruhig"] + ([f"{wackelt} {'wackelt' if wackelt == 1 else 'wackeln'}"] if wackelt else [])
    if schritte:
        teile.append(f"{schritte} mit Ausfallschritt")
    text = f"{stehen} von {n} bleiben stehen ({', '.join(teile)}), {fallen} {'fällt' if fallen == 1 else 'fallen'}."
    # je Zelle (bei Wiederholungen): wie oft bleibt sie stehen? Gemischt = Grenzfall
    zellen: dict[str, dict[str, int]] = {}
    for v in versuche:
        z = zellen.setdefault(f"{v['richtung']}|{v['stufe']}|{v['hoehe']}", {"stehen": 0, "von": 0})
        z["von"] += 1
        z["stehen"] += v["ausgang"] in ("steht", "wackelt")
    grenz = sum(1 for z in zellen.values() if 0 < z["stehen"] < z["von"])
    if any(z["von"] > 1 for z in zellen.values()):
        text += (f" {grenz} {'Grenzfall' if grenz == 1 else 'Grenzfälle'} (mal stehen, mal fallen)." if grenz
                 else " Keine Grenzfälle – jede Wiederholung ging gleich aus.")
    return {"gesamt": n, "stehen": stehen, "ruhig": ruhig, "wackeln": wackelt, "fallen": fallen, "text": text,
            "schritte": schritte, "grenzfaelle": grenz, "zellen": zellen,
            "je_richtung": _zaehlen(versuche, "richtung"), "je_staerke": _zaehlen(versuche, "stufe"),
            "je_hoehe": _zaehlen(versuche, "hoehe")}


def profil_dir(root: str | Path) -> Path:
    return Path(root) / "kollision" / "profile"


def neue_id(root: str | Path) -> str:
    base = time.strftime("%Y%m%d-%H%M%S")
    pid, n = base, 2
    while (profil_dir(root) / f"{pid}.json").exists():
        pid, n = f"{base}-{n}", n + 1
    return pid


def schreibe_profil(root: str | Path, pid: str, policy: dict[str, Any], auftrag: dict[str, Any],
                    versuche: list[dict[str, Any]], extra: dict[str, Any] | None = None) -> dict[str, Any]:
    from .kollision import STUFEN

    ohne_episode = [{k: v for k, v in x.items() if k != "episode"} for x in versuche]
    prof = {"version": 1, "id": pid, "erstellt": time.strftime("%Y-%m-%dT%H:%M:%S"), "policy": policy,
            "raster": {"richtungen": list(dict.fromkeys(v["richtung"] for v in auftrag["raster"])),
                       "stufen": list(dict.fromkeys(v["stufe"] for v in auftrag["raster"])),
                       "hoehen": list(dict.fromkeys(v["hoehe"] for v in auftrag["raster"])),
                       "staerken": {k: STUFEN[k] for k in STUFEN},
                       "einschwingen_s": auftrag.get("einschwingen_s", EINSCHWINGEN_S),
                       "nachlauf_s": auftrag.get("nachlauf_s", NACHLAUF_S),
                       "wiederholungen": max((int(v.get("wdh", 0)) for v in auftrag["raster"]), default=0) + 1},
            "ergebnis": zusammenfassen(ohne_episode), "versuche": ohne_episode, **(extra or {})}
    d = profil_dir(root)
    d.mkdir(parents=True, exist_ok=True)
    tmp = d / f"{pid}.json.tmp"
    tmp.write_text(json.dumps(prof, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(d / f"{pid}.json")
    return prof


def lade_profil(root: str | Path, pid: str) -> dict[str, Any]:
    if not PROFIL_ID.fullmatch(str(pid or "")):
        raise ReiheFehler("Ungültige Profil-Kennung")
    p = profil_dir(root) / f"{pid}.json"
    if not p.exists():
        raise ReiheFehler("Dieses Profil gibt es nicht (mehr).")
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise ReiheFehler("Das Profil ist beschädigt.") from exc


def liste(root: str | Path) -> list[dict[str, Any]]:
    """Gespeicherte Profile, neueste zuerst – nur die Kopfzeilen."""
    d = profil_dir(root)
    out = []
    for p in sorted(d.glob("*.json"), reverse=True)[:MAX_PROFILE] if d.exists() else []:
        if not PROFIL_ID.fullmatch(p.stem):
            continue
        try:
            prof = json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            continue
        pol, erg = prof.get("policy") or {}, prof.get("ergebnis") or {}
        out.append({"id": p.stem, "erstellt": prof.get("erstellt"), "policy_name": pol.get("name"),
                    "policy_quelle": pol.get("quelle"), "sha256": (pol.get("sha256") or "")[:12],
                    "gesamt": erg.get("gesamt"), "stehen": erg.get("stehen"), "fallen": erg.get("fallen"),
                    "text": erg.get("text"), "dauer_s": prof.get("dauer_s")})
    return out
