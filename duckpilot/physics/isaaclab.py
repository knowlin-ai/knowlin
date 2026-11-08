"""Policies aus Isaac Lab übernehmen (seit 0.38.27) – Wunsch „3. fänd ich sehr wichtig“.

NVIDIA trainiert die Microduck in Isaac Lab (`isaaclab_tasks/contrib/microduck`, BSD-3-Clause): Aufgaben
`IsaacContrib-Velocity-Flat-MicroDuck` und `…-Rough-MicroDuck`, PPO mit rsl_rl, Newton/MJWarp mit Rhobans BAM-Servos.
Gelesen am 8.11.2026 (Stand des Repos an diesem Tag) – das Wichtigste für uns:

* **Beobachtung (61 Werte, der „deploy contract“):** Drehrate der IMU (3) · Schwerkraft im Rumpf (3) ·
  Gelenkwinkel relativ zur Grundstellung (14) · Gelenkgeschwindigkeit (14) · letzte Aktion (14) · Fahrbefehl vx, vy,
  Drehung (3) · Kopfbefehl als Gelenk-Abweichung Hals/Kopf-Nicken/Drehen/Rollen (4) · Körperhaltung (6). Das ist genau
  die Reihenfolge von Pollens Policies und von `core.py`.
* **Aktion (14):** Zielwinkel = Grundstellung + Aktion × 1,0, Servo-Reihenfolge linkes Bein, Hals/Kopf, rechtes Bein
  (wie `ACTUATORS`), Grundstellung wie Pollens STAND2 (`DEFAULT_POSE`). Der Schnabel ist nicht modelliert.
* **Takt:** 200 Hz Physik, Entscheidung alle 4 Schritte = 50 Hz – wie bei uns. Keine Glättung der Ziele im Training
  (robotd glättet am echten Roboter) – deshalb prüft der Prüfstand beides.
* **Trainierte Befehle:** vorwärts ±0,4 m/s, seitwärts ±0,3 m/s, drehen ±1,0 rad/s; Kopf am Ende des Lehrplans
  ±1,1 / ±1,1 / ±1,4 / ±0,31 rad (wie `HEAD_CAP`); Körperhaltung nur ±5 mm und ±0,05 rad (Belohnung dafür ist aus) –
  Haltungen aus Choreografien werden mit dieser Gangart deshalb auf diesen kleinen Bereich begrenzt.
* **Export:** rsl_rl legt `exported/policy.onnx` an (Normierung eingebaut, Eingang `obs`, Ausgang `actions`). Fertige
  Policies verlinkt NVIDIA nicht – man trainiert selbst (NVIDIA-GPU) oder bekommt eine Datei aus der Community.

Ablauf: Datei prüfen (61 rein, 14 raus) → Manifest schreiben (Quelle, Aufgabe, Grenzen, Ausgabe-Faktor, Glättung) →
**Pflicht-Prüfstand** in MuJoCo (stehen, vorwärts, seitwärts, drehen, ein Schubs; ohne und mit robotd-Glättung) →
als Gangart merken. Für den echten Roboter freigegeben ist sie nur, wenn der Prüfstand bestanden ist.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import re
import time
from pathlib import Path
from typing import Any, Callable

import numpy as np

log = logging.getLogger(__name__)

QUELLE = "https://github.com/isaac-sim/IsaacLab/tree/main/source/isaaclab_tasks/isaaclab_tasks/contrib/microduck"
AUFGABEN = {
    "IsaacContrib-Velocity-Flat-MicroDuck": "Gehen auf ebenem Boden (Isaac Lab)",
    "IsaacContrib-Velocity-Rough-MicroDuck": "Gehen auf unebenem Boden (Isaac Lab)",
}
STANDARD_AUFGABE = "IsaacContrib-Velocity-Rough-MicroDuck"
GRENZEN = {
    "fahren": [0.4, 0.3, 1.0],
    "kopf": [1.1, 1.1, 1.4, 0.31],
    "haltung": [0.005, 0.005, 0.005, 0.05, 0.05, 0.05],
}
AUSGABE_FAKTOR = 1.0
MAX_BYTES = 60 * 1024 * 1024
NAME = re.compile(r"[a-z0-9][a-z0-9_]{0,30}")

# Prüfstand: (Kennung, Titel, Fahrbefehl, Dauer s). Gemessen wird ab der Hälfte, wenn die Ente auf Tempo ist.
PRUEFUNGEN = (
    ("stehen", "Stehen", (0.0, 0.0, 0.0), 4.0),
    ("vor", "Vorwärts 0,25 m/s", (0.25, 0.0, 0.0), 6.0),
    ("seite", "Seitwärts 0,15 m/s", (0.0, 0.15, 0.0), 5.0),
    ("drehen", "Drehen 0,8 rad/s", (0.0, 0.0, 0.8), 5.0),
    ("schubs", "Schubs von der Seite", (0.0, 0.0, 0.0), 4.0),
)
SCHUBS_MS = 0.35          # seitliche Geschwindigkeit, die der Rumpf beim Schubs bekommt
KIPP_GRENZE = math.radians(55)
FOLGT_MIN, FOLGT_MAX = 0.45, 1.8      # erreichtes Tempo / verlangtes Tempo
STEHEN_DRIFT_M = 0.15


class ImportFehler(ValueError):
    pass


def name_aus(text: str) -> str:
    n = re.sub(r"[^a-z0-9]+", "_", (text or "").lower()).strip("_")[:24] or "isaaclab"
    return n if n.startswith("isaac") else f"isaac_{n}"[:31]


def pruefe_datei(pfad: str | Path) -> dict[str, Any]:
    """Passt die ONNX-Datei zur Microduck? → Kurzinfo; ImportFehler, wenn nicht."""
    from .core import ACT_LEN, OBS_LEN, Policy, PolicyError

    p = Path(pfad)
    if not p.is_file() or p.stat().st_size == 0:
        raise ImportFehler("Datei fehlt oder ist leer")
    if p.stat().st_size > MAX_BYTES:
        raise ImportFehler("Datei ist zu groß für eine Microduck-Policy")
    try:
        pol = Policy(p, p.stem, AUSGABE_FAKTOR)
    except PolicyError as exc:
        raise ImportFehler(str(exc)) from exc
    except Exception as exc:                       # kein ONNX, kaputt, unbekannte Bausteine
        log.info("Isaac-Lab-Import: Datei nicht lesbar: %s", exc)
        raise ImportFehler("Das ist keine lesbare ONNX-Datei – bitte exported/policy.onnx aus Isaac Lab wählen.") from exc
    ins = [i.name for i in pol.session.get_inputs()]
    return {"eingaenge": ins, "rekurrent": pol.recurrent, "beobachtung": OBS_LEN, "aktion": ACT_LEN,
            "sha256": hashlib.sha256(p.read_bytes()).hexdigest()[:16]}


def manifest(aufgabe: str, info: dict[str, Any], pruefung: dict[str, Any] | None = None) -> dict[str, Any]:
    from .core import ACTUATORS, DEFAULT_POSE

    return {
        "schema": "knowlin-import-1", "quelle": "isaaclab", "aufgabe": aufgabe, "titel": AUFGABEN.get(aufgabe, aufgabe),
        "herkunft": QUELLE, "lizenz_rahmen": "Isaac Lab: BSD-3-Clause (die Policy-Datei gehört dem, der sie trainiert hat)",
        "robot": {"model": "microduck"}, "obs_len": 61, "action_len": 14, "action_scale": AUSGABE_FAKTOR,
        "tiefpass": False, "gelenke": list(ACTUATORS), "grundstellung": [round(float(v), 4) for v in DEFAULT_POSE],
        "takt_hz": 50, "grenzen": GRENZEN, "datei": info, "pruefung": pruefung,
    }


def lade_grenzen(policy_pfad: str | Path) -> dict[str, Any] | None:
    """Manifest neben der Policy lesen (nur Zahlen, nichts ausführen) → Grenzen, Faktor, Glättung."""
    try:
        m = json.loads((Path(policy_pfad).parent / "manifest.json").read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(m, dict) or m.get("quelle") != "isaaclab":
        return None
    g = m.get("grenzen") or {}
    try:
        out = {k: np.asarray([float(x) for x in g[k]], np.float32) for k in ("fahren", "kopf", "haltung")}
    except Exception:
        out = {k: np.asarray(v, np.float32) for k, v in GRENZEN.items()}
    if [len(out["fahren"]), len(out["kopf"]), len(out["haltung"])] != [3, 4, 6]:
        out = {k: np.asarray(v, np.float32) for k, v in GRENZEN.items()}
    return {"grenzen": out, "action_scale": float(m.get("action_scale") or AUSGABE_FAKTOR),
            "tiefpass": bool(m.get("tiefpass", False)), "pruefung": m.get("pruefung")}


def begrenzen(cmd: Any, grenzen: dict[str, np.ndarray]) -> Any:
    """Befehl auf den trainierten Bereich stutzen (Kopie) – außerhalb rät die Policy nur."""
    from .core import Command

    c = Command()
    c.twist[:] = np.clip(cmd.twist, -grenzen["fahren"], grenzen["fahren"])
    c.head[:] = np.clip(cmd.head, -grenzen["kopf"], grenzen["kopf"])
    c.body[:] = np.clip(cmd.body, -grenzen["haltung"], grenzen["haltung"])
    return c


# ── Prüfstand ────────────────────────────────────────────────────────────
def _lauf(core: Any, cmd: Any, sekunden: float, schubs: bool) -> dict[str, Any]:
    from .core import CONTROL_DT, Command
    from .params import CMD_ALPHA

    core.reset()
    ziel = np.asarray(cmd, np.float32)
    c = Command()
    gekippt, max_kipp = False, 0.0
    proben: list[tuple[float, float, float, float, float]] = []   # t, x, y, yaw (fortlaufend), vyaw
    yaw_lauf, yaw_vorher = 0.0, None
    schritte = int(sekunden / CONTROL_DT)
    for i in range(schritte):
        c.twist += CMD_ALPHA * (ziel - c.twist)                   # Rampe wie robotd
        if schubs and i == int(1.0 / CONTROL_DT):
            core.data.qvel[core.root_v + 1] += SCHUBS_MS          # Rumpf seitlich anstoßen
        core.control_step(c)
        tr = core.trunk()
        kipp = math.acos(max(-1.0, min(1.0, tr["up"])))
        max_kipp = max(max_kipp, kipp)
        gekippt = gekippt or kipp > KIPP_GRENZE or tr["z"] < 0.05
        if yaw_vorher is not None:
            d = (tr["yaw"] - yaw_vorher + math.pi) % (2 * math.pi) - math.pi
            yaw_lauf += d
        yaw_vorher = tr["yaw"]
        proben.append((i * CONTROL_DT, tr["x"], tr["y"], yaw_lauf, tr["vyaw"]))
        if gekippt:
            break
    return {"gekippt": gekippt, "max_kipp_grad": round(math.degrees(max_kipp), 1), "proben": proben,
            "dauer": schritte * CONTROL_DT}


def _bewerten(art: str, titel: str, befehl: tuple[float, float, float], r: dict[str, Any]) -> dict[str, Any]:
    pr = r["proben"]
    out: dict[str, Any] = {"art": art, "titel": titel, "gekippt": r["gekippt"], "max_kipp_grad": r["max_kipp_grad"]}
    if r["gekippt"] or len(pr) < 10:
        out.update(ok=False, grund="umgefallen")
        return out
    h = len(pr) // 2
    t0, x0, y0, w0, _ = pr[h]
    t1, x1, y1, w1, _ = pr[-1]
    dt = max(1e-3, t1 - t0)
    # Tempo im eigenen Rahmen (zu Beginn der Messung ausgerichtet)
    yaw0 = pr[h][3]
    dx, dy = x1 - x0, y1 - y0
    vx = (math.cos(yaw0) * dx + math.sin(yaw0) * dy) / dt
    vy = (-math.sin(yaw0) * dx + math.cos(yaw0) * dy) / dt
    wz = (w1 - w0) / dt
    out.update(vx=round(vx, 3), vy=round(vy, 3), wz=round(wz, 3))
    if art in ("stehen", "schubs"):
        drift = math.hypot(pr[-1][1] - pr[0][1], pr[-1][2] - pr[0][2])
        out["drift_m"] = round(drift, 3)
        grenze = STEHEN_DRIFT_M if art == "stehen" else STEHEN_DRIFT_M * 3
        out["ok"] = drift <= grenze
        out["grund"] = "" if out["ok"] else f"wandert {drift:.2f} m"
        return out
    soll = {"vor": befehl[0], "seite": befehl[1], "drehen": befehl[2]}[art]
    ist = {"vor": vx, "seite": vy, "drehen": wz}[art]
    anteil = ist / soll if soll else 0.0
    out["folgt"] = round(anteil, 2)
    out["ok"] = FOLGT_MIN <= anteil <= FOLGT_MAX
    out["grund"] = "" if out["ok"] else (f"folgt nur zu {max(0, round(anteil * 100))} %" if anteil < FOLGT_MIN
                                         else f"schießt über ({round(anteil * 100)} %)")
    return out


def pruefstand(policy_pfad: str | Path, use_bam: bool | None = None,
               fortschritt: Callable[[str], None] | None = None, vergleich_pfad: str | Path | None = None) -> dict[str, Any]:
    """Alle Prüfungen, einmal wie trainiert (ohne Glättung) und einmal wie am Roboter (mit robotd-Glättung).

    `vergleich_pfad`: Pollens Geh-Policy, falls geladen – dieselben Prüfungen wie am Roboter. Eine Bewegung gilt dann
    auch als bestanden, wenn sie mindestens 80 % von dem schafft, was Pollens Gangart im selben Modell schafft (so hängt
    das Urteil nicht an meinen Schwellen, sondern am Maßstab, der heute auf der Ente läuft)."""
    from .core import PhysicsCore, Policy
    from .params import ROBOT_ACTION_SCALE

    t_start = time.perf_counter()
    core = PhysicsCore(None, use_bam=use_bam)

    def reihe_fuer(pol: Any, glatt: bool, wer: str) -> list[dict[str, Any]]:
        core.set_policy(pol)
        core.lowpass = glatt
        reihe = []
        for art, titel, befehl, sek in PRUEFUNGEN:
            if fortschritt:
                fortschritt(f"{wer}: {titel} ({'mit' if glatt else 'ohne'} Glättung)")
            reihe.append(_bewerten(art, titel, befehl, _lauf(core, befehl, sek, art == "schubs")))
        return reihe

    pol = Policy(policy_pfad, Path(policy_pfad).stem, AUSGABE_FAKTOR)
    teile = {"wie_trainiert": reihe_fuer(pol, False, "Isaac Lab"), "wie_am_roboter": reihe_fuer(pol, True, "Isaac Lab")}
    vergleich = None
    if vergleich_pfad is not None and Path(vergleich_pfad).exists():
        vergleich = reihe_fuer(Policy(vergleich_pfad, "pollen_walk", ROBOT_ACTION_SCALE), True, "Pollens Gangart")
        massstab = {v["art"]: v for v in vergleich}
        for reihe in teile.values():
            for p in reihe:
                v = massstab.get(p["art"])
                if p["ok"] or p["gekippt"] or not v or "folgt" not in v or "folgt" not in p:
                    continue
                if v["folgt"] > 0 and p["folgt"] >= 0.8 * v["folgt"]:
                    p.update(ok=True, grund=f"wie Pollens Gangart ({round(p['folgt'] * 100)} % zu {round(v['folgt'] * 100)} %)")
    bestanden = all(p["ok"] for r in teile.values() for p in r)
    return {"bestanden": bestanden, "roboter_frei": bestanden, "pruefungen": teile, "vergleich": vergleich,
            "bam": core.bam is not None, "sekunden": round(time.perf_counter() - t_start, 1),
            "zeit": time.strftime("%Y-%m-%d %H:%M")}


# ── Übernehmen ───────────────────────────────────────────────────────────
def importieren(root: Path, quelle_pfad: str | Path, name: str = "", aufgabe: str = STANDARD_AUFGABE,
                mit_pruefstand: bool = True, use_bam: bool | None = None,
                fortschritt: Callable[[str], None] | None = None, herkunft: dict[str, Any] | None = None) -> dict[str, Any]:
    """Policy-Datei prüfen, ablegen, Manifest schreiben, Prüfstand rechnen. → Eintrag für die Oberfläche."""
    from .policies import PolicyStore

    if aufgabe not in AUFGABEN:
        raise ImportFehler("unbekannte Isaac-Lab-Aufgabe")
    name = name_aus(name or Path(quelle_pfad).stem)
    if not NAME.fullmatch(name):
        raise ImportFehler("ungültiger Name")
    info = pruefe_datei(quelle_pfad)
    ziel = Path(root) / "policies" / "import" / name
    ziel.mkdir(parents=True, exist_ok=True)
    datei = ziel / "policy.onnx"
    tmp = datei.with_suffix(".onnx.teil")
    tmp.write_bytes(Path(quelle_pfad).read_bytes())
    tmp.replace(datei)
    walk = PolicyStore(Path(root)).roles().get("walk")
    pruefung = (pruefstand(datei, use_bam, fortschritt, walk["pfad"] if walk else None)
                if mit_pruefstand else None)
    m = manifest(aufgabe, info, pruefung)
    if herkunft:                                   # von Hugging Face geladen (seit 0.38.30): Repo, Pfad, Stand, Lizenz
        m["download"] = herkunft
    (ziel / "manifest.json").write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding="utf-8")
    PolicyStore(Path(root)).merke_eigen(str(datei), name, "gangart", m["titel"])
    return eintrag(name, m)


def eintrag(name: str, m: dict[str, Any]) -> dict[str, Any]:
    p = m.get("pruefung") or {}
    return {"name": name, "titel": m.get("titel"), "aufgabe": m.get("aufgabe"), "datei": m.get("datei"),
            "bestanden": p.get("bestanden"), "roboter_frei": bool(p.get("roboter_frei")),
            "pruefungen": p.get("pruefungen"), "zeit": p.get("zeit"), "bam": p.get("bam"), "download": m.get("download")}


def liste(root: Path) -> list[dict[str, Any]]:
    out = []
    ordner = Path(root) / "policies" / "import"
    for d in sorted(ordner.glob("*/manifest.json")) if ordner.exists() else []:
        try:
            m = json.loads(d.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(m, dict) and m.get("quelle") == "isaaclab" and NAME.fullmatch(d.parent.name):
            out.append(eintrag(d.parent.name, m))
    return out
