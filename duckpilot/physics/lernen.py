"""Selbst lernen am PC: Pollens Geh-Policy auf einem Parcours nachtrainieren – kostenlos, über Nacht.

Statt eine GPU bei Hugging Face zu mieten, rechnet der eigene PC:

* **Physik auf dem Prozessor.** MuJoCos GPU-Wege (Warp/MJX) gibt es für AMD unter Windows nicht. Deshalb laufen
  mehrere Rechenprozesse nebeneinander (Standard: alle Kerne bis auf einen), jeder mit ein paar Enten in seiner
  eigenen MuJoCo-Welt – genau die Welt, die auch `course.evaluate()` baut.
* **Das Netz auf der Grafikkarte.** Der PPO-Schritt läuft mit PyTorch auf `cuda` (AMDs PyTorch für Windows meldet die
  Radeon über `torch.cuda`), sonst auf dem Prozessor.

Ablauf (PPO, wie rsl_rl, nur klein):

1. Start-Policy: ein ONNX-MLP aus dem Policy-Satz (Pollens Geh-Policy, ein Cloud-Lauf oder ein früheres lokales
   Ergebnis). Der ONNX-Graph wird Baustein für Baustein in PyTorch nachgebaut; die Gewichte der Matrix-Bausteine
   (MatMul/Gemm und ihre Bias-Addition) lernen mit, alles andere (z. B. eine eingebaute Normierung) bleibt fest. Dazu
   kommt eine lernbare Streuung (log-std). Der Kritiker (Wertnetz) ist ein eigenes, frisches Netz und wird in den
   ersten Runden allein aufgewärmt, damit er die gute Start-Policy nicht mit Unsinn verbiegt.
2. Jede Runde fährt jede Ente 24 Regelschritte (50 Hz) mit etwas Rauschen auf der Aktion; die Rechenprozesse rechnen
   das Netz dabei selbst (NumPy) und schicken nur die Messreihen zurück.
3. GAE, beschnittenes PPO-Ziel, kleine Lernrate (wir verfeinern, wir lernen nicht neu), Abbruch der Epochen, wenn
   sich die Policy zu stark ändert (KL).
4. Der beste Stand (Fähigkeit + Anteil im Ziel) wird am Ende als ONNX exportiert – derselbe Graph wie die
   Start-Policy, nur mit neuen Gewichten. Gleiche Ein- und Ausgänge, also läuft er überall, wo die Start-Policy läuft.

Beobachtung, Aktion und Takt sind genau die aus `core.py`: 61 Werte rein, 14 Aktionen raus, Zielwinkel =
Grundstellung + Aktion × action_scale, 50 Hz. Den Fahrbefehl gibt wie in `course.evaluate()` der einfache Wegfolger
(zur nächsten Wegmarke drehen und gehen) – die Policy lernt also, den Befehlen auf diesem Parcours zu folgen.

Belohnung je Regelschritt (bewusst einfach):

* Fortschritt:    +8 × zurückgelegte Meter entlang der Bahn (x)
* Am Leben:       +0,5 pro Sekunde
* Befehl folgen:  +0,5 × exp(−|v − v_soll|² / 0,02) + 0,25 × exp(−(ω − ω_soll)² / 0,2), pro Sekunde
* Ruckeln:        −0,5 × |a − a_vorher|² pro Sekunde
* Gelenkanschlag: −1 pro Sekunde und Gelenk, das näher als 0,03 rad am Anschlag steht
* Sturz:          −5, Durchgang endet (Rumpf kippt wie in `course.py` unter „up“ 0,45)
* Ziel:           +5, Durchgang endet

Ein Durchgang endet außerdem, wenn die Zeit abläuft oder die Ente 8 s lang nicht vorankommt (zählt nicht als Sturz).
Zufällig je Durchgang (wie in `evaluate()`): Reibung ×0,7…1,15, Startlage ±2 cm und ±4°, alle 2–5 s ein kleiner
Schubs (bis 0,15 m/s). Die Hälfte der Durchgänge beginnt vor einem zufälligen Element statt am Start – so übt die
Ente schwere Stellen öfter.

Kennzahlen (über die letzten 40 beendeten Durchgänge): **Fähigkeit** = Anteil ohne Sturz (0–100, wie der time_out-
Anteil beim Cloud-Training), **im Ziel** = Anteil, der das Ziel erreicht (0–100). Die **Belohnung** in der Kurve ist
die Belohnung pro simulierter Sekunde in der Runde.
"""

from __future__ import annotations

import collections
import datetime as dt
import importlib.util
import json
import logging
import math
import os
import re
import threading
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

log = logging.getLogger(__name__)

# ── Einstellungen ───────────────────────────────────────────────────────
ROLLOUT_STEPS = 24                 # Regelschritte je Ente und Runde (wie Pollens rsl_rl)
UMGEBUNGEN_JE_PROZESS = 8          # Enten je Rechenprozess
GAMMA = 0.99
LAMBDA = 0.95
CLIP = 0.1                         # PPO-Beschneidung (klein: wir verfeinern)
EPOCHEN = 5
MINIBATCHES = 4
LR_AKTEUR = 5e-5
LR_STREUUNG = 1e-3
LR_KRITIKER = 3e-4
ZIEL_KL = 0.015                    # ändert sich die Policy stärker, hören die Epochen der Runde auf
MAX_GRAD = 1.0
START_STREUUNG = 0.1               # Rauschen auf der Aktion zu Beginn
STREUUNG_MIN, STREUUNG_MAX = 0.02, 0.5
KRITIKER_AUFWAERMEN = 5            # so viele Runden lernt nur der Kritiker
FENSTER = 40                       # Durchgänge für Fähigkeit/im Ziel
MIN_DURCHGAENGE = 8                # so viele braucht es, bevor ein Stand „bester“ werden kann
MAX_KURVE = 600
SPEICHERN_S = 5.0                  # Fortschritt höchstens so oft auf die Platte

# Belohnung (siehe Moduldoku)
W_FORTSCHRITT = 8.0
W_LEBEN = 0.5
W_BEFEHL_V = 0.5
W_BEFEHL_W = 0.25
W_RUCKELN = 0.5
W_ANSCHLAG = 1.0
W_STURZ = -5.0
W_ZIEL = 5.0
ANSCHLAG_RAD = 0.03

# Durchgänge
SETTLE_S = 0.6                     # erst stehen, wie evaluate()
MAX_DURCHGANG_S = 60.0
FEST_S = 8.0
EBEN_LAENGE = 3.0                  # ohne Parcours: 3 m geradeaus
EBEN_ZEIT_S = 20.0
REIBUNG = (0.7, 1.15)
START_Y = 0.02
START_YAW_GRAD = 4.0
SCHUBS = (2.0, 5.0)                # Sekunden zwischen zwei Schubsen
SCHUBS_MS = 0.15
SCHUBS_ECHT_ANTEIL = 0.5           # mit Stoß-Profil: jeder zweite Schubs ist ein echter aus dem Kollisionsmodus …
SCHUBS_ECHT_FAKTOR = 0.6           # … etwas gedämpft (wir verfeinern, wir lernen nicht neu)
MITTEN_START = 0.5                 # Anteil der Durchgänge, die vor einem zufälligen Element beginnen

# Netz-Bausteine, die der Nachbau kennt
BAUSTEINE = {"Gemm", "MatMul", "Add", "Sub", "Mul", "Div", "Neg", "Elu", "Relu", "LeakyRelu", "Tanh", "Sigmoid",
             "Softsign", "Softplus", "Clip", "Identity", "Constant", "Cast", "Flatten"}
LOKAL_DIR = "lokal"                # unter <root>/policies/
LOKAL_STEM = re.compile(r"lokal-[A-Za-z0-9_-]{1,80}")
JOB_ID = re.compile(r"\d{8}-\d{6}(-\d{1,3})?")
OBS_LEN, ACT_LEN = 61, 14          # wie core.py (hier ohne MuJoCo zu laden)

_find_spec = importlib.util.find_spec


class LernFehler(ValueError):
    """Verständlicher Fehler fürs Lernen am PC (Text auf Deutsch, für die Oberfläche)."""


def available() -> tuple[bool, str]:
    """Kann der PC selbst lernen? → (ja/nein, Grund auf Deutsch)."""
    def fehlt(mod: str) -> bool:
        try:
            return _find_spec(mod) is None
        except (ImportError, ValueError):
            return True

    if fehlt("torch"):
        return False, "PyTorch fehlt – unter Lernen mit einem Klick installieren"
    missing = [name for name, mod in (("MuJoCo", "mujoco"), ("onnx", "onnx"), ("onnxruntime", "onnxruntime"))
               if fehlt(mod)]
    if missing:
        return False, f"{' und '.join(missing)} fehlt – erst die echte Physik installieren (Einstellungen → Körper)"
    return True, "bereit"


# ── Start-Policies finden ───────────────────────────────────────────────
def _lokal_dir(root: Path) -> Path:
    return Path(root) / "policies" / LOKAL_DIR


def quellen(root: Path) -> list[dict[str, Any]]:
    """Policies, mit denen das Lernen starten kann: {id, name}. ids: „standard“, „lauf:<id>“, „lokal:<name>“."""
    root = Path(root)
    out: list[dict[str, Any]] = []
    try:
        from .policies import PolicyStore

        if "walk" in PolicyStore(root).roles():
            out.append({"id": "standard", "name": "Pollens Geh-Policy (VelStand)"})
    except Exception:
        pass
    for r in _cloud_runs(root)[::-1]:
        if r.get("status") == "fertig" and r.get("onnx") and Path(r["onnx"]).exists():
            out.append({"id": f"lauf:{r['id']}", "name": f"Training {r.get('start', '')} (Cloud)"})
    for meta in ergebnisse(root):
        out.append({"id": meta["id"], "name": f"Selbst gelernt: {meta.get('name', '')} ({meta.get('erstellt', '')})"})
    return out


def ergebnisse(root: Path) -> list[dict[str, Any]]:
    """Lokal gelernte Policies (neueste zuerst) mit ihrer Zusammenfassung."""
    out = []
    folder = _lokal_dir(root)
    for f in sorted(folder.glob("lokal-*.onnx"), key=lambda p: p.stat().st_mtime, reverse=True) if folder.exists() else []:
        if not LOKAL_STEM.fullmatch(f.stem):
            continue
        try:
            meta = json.loads(f.with_suffix(".json").read_text(encoding="utf-8"))
        except Exception:
            meta = {}
        out.append({**(meta if isinstance(meta, dict) else {}), "id": f"lokal:{f.stem}", "pfad": str(f)})
    return out


def _cloud_runs(root: Path) -> list[dict[str, Any]]:
    try:
        data = json.loads((Path(root) / "training" / "laeufe.json").read_text(encoding="utf-8"))
        return [r for r in data if isinstance(r, dict) and "id" in r] if isinstance(data, list) else []
    except Exception:
        return []


def aufloesen(root: Path, quelle: str) -> tuple[Path, float, str]:
    """Policy-Kennung → (ONNX-Pfad, action_scale, Bezeichnung). Wirft LernFehler."""
    root = Path(root)
    quelle = str(quelle or "").strip()
    if quelle in ("standard", "walk"):
        from .policies import PolicyStore

        roles = PolicyStore(root).roles()
        if "walk" not in roles:
            raise LernFehler("Pollens Geh-Policy fehlt – erst unter Einstellungen → Körper laden.")
        e = roles["walk"]["eintrag"]
        return Path(roles["walk"]["pfad"]), float(e.get("action_scale") or 1.0), "Pollens Geh-Policy"
    if quelle.startswith("lauf:"):
        rid = quelle[5:]
        run = next((r for r in _cloud_runs(root) if r.get("id") == rid), None)
        if run is None:
            raise LernFehler("Diesen Trainingslauf gibt es nicht.")
        path = run.get("onnx")
        if run.get("status") != "fertig" or not path or not Path(path).exists():
            raise LernFehler("Das Ergebnis dieses Cloud-Laufs liegt noch nicht auf dem PC – erst unter Lernen → Training "
                             "herunterladen (z. B. einmal auf dem Parcours prüfen).")
        return Path(path), 1.0, f"Training {run.get('start', rid)}"
    if quelle.startswith("lokal:"):
        stem = quelle[6:]
        if not LOKAL_STEM.fullmatch(stem):
            raise LernFehler("Ungültiger Name einer lokal gelernten Policy.")
        path = _lokal_dir(root) / f"{stem}.onnx"
        if not path.exists():
            raise LernFehler("Diese selbst gelernte Policy gibt es nicht (mehr).")
        try:
            meta = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
        except Exception:
            meta = {}
        return path, float(meta.get("action_scale") or 1.0), f"Selbst gelernt: {meta.get('name', stem)}"
    raise LernFehler("Unbekannte Start-Policy – „standard“, „lauf:<id>“ oder „lokal:<name>“")


# ── ONNX ↔ Netz ─────────────────────────────────────────────────────────
@dataclass
class Netz:
    """Ein ONNX-MLP als einfache, picklebare Bausteinliste (für PyTorch und NumPy)."""
    pfad: str
    obs_name: str
    out_name: str
    obs_form: list[Any]
    out_form: list[Any]
    knoten: list[tuple[str, list[str], list[str], dict[str, Any]]]
    tensoren: dict[str, np.ndarray]
    lernbar: list[str]
    konstanten: dict[str, int] = field(default_factory=dict)     # Tensorname → Index des Constant-Knotens

    def gewichte(self) -> dict[str, np.ndarray]:
        return {n: self.tensoren[n] for n in self.lernbar}


def _form(vi) -> list[Any]:
    dims = vi.type.tensor_type.shape.dim
    return [d.dim_value if d.HasField("dim_value") else (d.dim_param or None) for d in dims]


def lade_netz(path: str | Path) -> Netz:
    """ONNX-Datei lesen und prüfen, ob das Lernen am PC sie nachbauen kann. Wirft LernFehler."""
    import onnx
    from onnx import helper, numpy_helper

    path = Path(path)
    try:
        model = onnx.load(str(path))
    except Exception as exc:
        raise LernFehler(f"Die Start-Policy lässt sich nicht lesen ({type(exc).__name__}).") from exc
    g = model.graph
    tensors = {t.name: numpy_helper.to_array(t) for t in g.initializer}
    inputs = [i for i in g.input if i.name not in tensors]
    names = {i.name for i in inputs}
    if {"h_in", "c_in"} <= names:
        raise LernFehler("Das ist eine LSTM-Policy (mit Gedächtnis) – die kann das Lernen am PC noch nicht "
                         "weitertrainieren. Bitte eine Policy ohne Gedächtnis (MLP) wählen.")
    if len(inputs) != 1:
        raise LernFehler(f"Die Start-Policy hat {len(inputs)} Eingänge – das Lernen am PC kann nur einfache Netze "
                         "mit einem Eingang (Beobachtung) nachtrainieren.")
    obs = inputs[0]
    if not g.output:
        raise LernFehler("Die Start-Policy hat keinen Ausgang.")
    out = g.output[0]
    nodes: list[tuple[str, list[str], list[str], dict[str, Any]]] = []
    consts: dict[str, int] = {}
    for i, n in enumerate(g.node):
        if n.domain not in ("", "ai.onnx"):
            raise LernFehler(f"Das Netz enthält den Sonderbaustein „{n.op_type}“ ({n.domain}) – das Lernen am PC kann nur "
                             "einfache MLPs (MatMul/Gemm, Add, Elu, Relu, Tanh …) nachtrainieren.")
        if n.op_type not in BAUSTEINE:
            raise LernFehler(f"Das Netz enthält den Baustein „{n.op_type}“, den das Lernen am PC nicht kennt – "
                             "unterstützt sind einfache MLPs (MatMul/Gemm, Add, Elu, Relu, Tanh …).")
        attrs = {a.name: helper.get_attribute_value(a) for a in n.attribute}
        if n.op_type == "Constant":
            if "value" in attrs:
                val = numpy_helper.to_array(attrs["value"])
            elif "value_float" in attrs:
                val = np.array(attrs["value_float"], np.float32)
            elif "value_floats" in attrs:
                val = np.array(attrs["value_floats"], np.float32)
            elif "value_int" in attrs:
                val = np.array(attrs["value_int"], np.int64)
            elif "value_ints" in attrs:
                val = np.array(attrs["value_ints"], np.int64)
            else:
                raise LernFehler("Das Netz enthält eine Konstante, die das Lernen am PC nicht lesen kann.")
            tensors[n.output[0]] = val
            consts[n.output[0]] = i
            continue
        if n.op_type == "Cast" and int(attrs.get("to", 1)) != onnx.TensorProto.FLOAT:
            raise LernFehler("Das Netz wandelt Zahlen in einen anderen Typ um – das kann das Lernen am PC nicht.")
        nodes.append((n.op_type, list(n.input), list(n.output), {k: v for k, v in attrs.items()
                                                                  if isinstance(v, (int, float))}))
    # Lernbar: Gewichte von MatMul/Gemm und die Bias-Addition direkt danach
    producer = {o: op for op, _, outs, _ in nodes for o in outs}
    learn: list[str] = []
    for op, ins, _, _ in nodes:
        cand = []
        if op in ("MatMul", "Gemm"):
            cand = [x for x in ins if x in tensors]
        elif op == "Add" and len(ins) == 2:
            a, b = ins
            if a in tensors and producer.get(b) in ("MatMul", "Gemm"):
                cand = [a]
            elif b in tensors and producer.get(a) in ("MatMul", "Gemm"):
                cand = [b]
        for x in cand:
            if tensors[x].dtype == np.float32 and tensors[x].ndim >= 1 and x not in learn:
                learn.append(x)
    if not learn:
        raise LernFehler("In der Start-Policy gibt es keine lernbaren Gewichte (MatMul/Gemm).")
    net = Netz(str(path), obs.name, out.name, _form(obs), _form(out), nodes, tensors, learn, consts)
    # Nachbau prüfen: dieselben Zahlen wie onnxruntime?
    rng = np.random.default_rng(0)
    probe = (rng.standard_normal((2, OBS_LEN)) * 0.5).astype(np.float32)
    try:
        import onnxruntime as ort

        sess = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
        batch = obs.type.tensor_type.shape.dim[0] if obs.type.tensor_type.shape.dim else None
        fixed1 = batch is not None and batch.HasField("dim_value") and batch.dim_value == 1
        want = np.concatenate([sess.run([out.name], {obs.name: probe[i:i + 1]})[0] for i in range(2)]) if fixed1 \
            else sess.run([out.name], {obs.name: probe})[0]
    except Exception as exc:
        raise LernFehler(f"Die Start-Policy läuft nicht ({type(exc).__name__}: {str(exc)[:120]}).") from exc
    want = np.asarray(want, np.float32).reshape(2, -1)
    if want.shape[1] != ACT_LEN:
        raise LernFehler(f"Die Start-Policy liefert {want.shape[1]} Aktionen statt {ACT_LEN}.")
    try:
        got = netz_numpy(net, probe)
    except Exception as exc:
        raise LernFehler(f"Das Netz der Start-Policy lässt sich nicht nachbauen ({type(exc).__name__}).") from exc
    if got.shape != want.shape or not np.allclose(got, want, atol=1e-4, rtol=1e-4):
        raise LernFehler("Der Nachbau des Netzes rechnet anders als die Start-Policy – dieses Netz wird nicht unterstützt.")
    return net


def _ausfuehren(net: Netz, werte: dict[str, Any], x, xp):
    """Die Bausteine der Reihe nach rechnen – xp ist numpy oder torch."""
    is_torch = xp.__name__ == "torch"
    if is_torch:
        import torch.nn.functional as F
    env = dict(werte)
    env[net.obs_name] = x
    for op, ins, outs, at in net.knoten:
        a = [env[i] if i else None for i in ins]
        if op == "Gemm":
            A, B = a[0], a[1]
            if at.get("transA"):
                A = A.T
            if at.get("transB"):
                B = B.T
            y = (A @ B) * at.get("alpha", 1.0)
            if len(a) > 2 and a[2] is not None:
                y = y + a[2] * at.get("beta", 1.0)
        elif op == "MatMul":
            y = a[0] @ a[1]
        elif op == "Add":
            y = a[0] + a[1]
        elif op == "Sub":
            y = a[0] - a[1]
        elif op == "Mul":
            y = a[0] * a[1]
        elif op == "Div":
            y = a[0] / a[1]
        elif op == "Neg":
            y = -a[0]
        elif op in ("Identity", "Cast"):
            y = a[0]
        elif op == "Flatten":
            y = a[0].reshape(a[0].shape[0], -1) if int(at.get("axis", 1)) == 1 else a[0].reshape(1, -1)
        elif op == "Elu":
            al = at.get("alpha", 1.0)
            y = F.elu(a[0], alpha=al) if is_torch else np.where(a[0] > 0, a[0], al * np.expm1(np.minimum(a[0], 0)))
        elif op == "Relu":
            y = F.relu(a[0]) if is_torch else np.maximum(a[0], 0)
        elif op == "LeakyRelu":
            al = at.get("alpha", 0.01)
            y = F.leaky_relu(a[0], al) if is_torch else np.where(a[0] > 0, a[0], al * a[0])
        elif op == "Tanh":
            y = xp.tanh(a[0])
        elif op == "Sigmoid":
            y = xp.sigmoid(a[0]) if is_torch else 1 / (1 + np.exp(-a[0]))
        elif op == "Softsign":
            y = a[0] / (1 + xp.abs(a[0]))
        elif op == "Softplus":
            y = F.softplus(a[0]) if is_torch else np.logaddexp(0, a[0])
        elif op == "Clip":
            lo = a[1] if len(a) > 1 and a[1] is not None else at.get("min")
            hi = a[2] if len(a) > 2 and a[2] is not None else at.get("max")
            lo = None if lo is None else float(lo)
            hi = None if hi is None else float(hi)
            y = xp.clamp(a[0], min=lo, max=hi) if is_torch else np.clip(a[0], lo, hi)
        else:                                   # pragma: no cover – lade_netz lässt nichts anderes durch
            raise LernFehler(f"Baustein „{op}“ nicht unterstützt")
        env[outs[0]] = y
    return env[net.out_name]


def netz_numpy(net: Netz, obs: np.ndarray, gewichte: dict[str, np.ndarray] | None = None) -> np.ndarray:
    """Das Netz mit NumPy rechnen (Rechenprozesse). obs: [B, 61] → [B, 14]."""
    werte = dict(net.tensoren)
    if gewichte:
        werte.update(gewichte)
    y = _ausfuehren(net, werte, np.asarray(obs, np.float32), np)
    return np.asarray(y, np.float32).reshape(obs.shape[0], -1)


def onnx_nach_torch(quelle: str | Path | Netz):
    """ONNX-MLP → torch.nn.Module (lernbare Gewichte als Parameter, der Rest als feste Puffer)."""
    import torch

    net = quelle if isinstance(quelle, Netz) else lade_netz(quelle)

    class Akteur(torch.nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.netz = net
            self.namen: dict[str, str] = {}
            self.params = torch.nn.ParameterDict()
            for i, n in enumerate(net.lernbar):
                self.namen[n] = f"p{i}"
                self.params[f"p{i}"] = torch.nn.Parameter(torch.tensor(np.array(net.tensoren[n], copy=True)))
            self.feste: dict[str, str] = {}
            for i, (n, arr) in enumerate(net.tensoren.items()):
                if n not in self.namen:
                    self.feste[n] = f"f{i}"
                    self.register_buffer(f"f{i}", torch.tensor(np.array(arr, copy=True)), persistent=False)

        def forward(self, obs):
            werte = {n: self.params[k] for n, k in self.namen.items()}
            werte.update({n: getattr(self, k) for n, k in self.feste.items()})
            return _ausfuehren(self.netz, werte, obs, torch)

        def gewichte(self) -> dict[str, np.ndarray]:
            return {n: self.params[k].detach().float().cpu().numpy().copy() for n, k in self.namen.items()}

        def setze(self, gewichte: dict[str, np.ndarray]) -> None:
            with torch.no_grad():
                for n, k in self.namen.items():
                    if n in gewichte:
                        self.params[k].copy_(torch.as_tensor(gewichte[n]))

    return Akteur()


def torch_nach_onnx(net: Netz, gewichte: dict[str, np.ndarray], ziel: str | Path, info: dict[str, str] | None = None) -> Path:
    """Den Graph der Start-Policy mit neuen Gewichten speichern – gleiche Ein-/Ausgänge, gleiche Formen."""
    import onnx
    from onnx import numpy_helper

    model = onnx.load(net.pfad)
    g = model.graph
    inits = {t.name: t for t in g.initializer}
    for name, arr in gewichte.items():
        old = net.tensoren[name]
        arr = np.asarray(arr, dtype=old.dtype).reshape(old.shape)
        if not np.all(np.isfinite(arr)):
            raise LernFehler("Das gelernte Netz enthält ungültige Zahlen (NaN) – nicht exportiert.")
        if name in inits:
            inits[name].CopyFrom(numpy_helper.from_array(arr, name))
        elif name in net.konstanten:
            node = g.node[net.konstanten[name]]
            for a in node.attribute:
                if a.name == "value":
                    a.t.CopyFrom(numpy_helper.from_array(arr, a.t.name or name))
        else:                                    # pragma: no cover
            raise LernFehler(f"Gewicht {name} nicht im Graph gefunden")
    for k, v in (info or {}).items():
        prop = next((p for p in model.metadata_props if p.key == k), None) or model.metadata_props.add()
        prop.key, prop.value = k, str(v)
    onnx.checker.check_model(model)
    ziel = Path(ziel)
    ziel.parent.mkdir(parents=True, exist_ok=True)
    tmp = ziel.with_suffix(".onnx.teil")
    onnx.save(model, str(tmp))
    os.replace(tmp, ziel)
    return ziel


# ── Die Übungswelt (läuft in den Rechenprozessen) ───────────────────────
class _Umgebung:
    """Eine Ente auf dem Parcours (oder ebenem Boden) – Beobachtung, Belohnung, Ende eines Durchgangs."""

    def __init__(self, spec: dict[str, Any] | None, action_scale: float, rng: np.random.Generator,
                 use_bam: bool | None, schubs: list[list[float]] | None = None) -> None:
        from . import course as K

        # Stoß-Profil aus dem Kollisionsmodus: [Δv vor, Δv links] in m/s, im Blick der Ente gemessen
        self.schubs = np.asarray(schubs, np.float64).reshape(-1, 2) if schubs else None
        from .core import CONTROL_DT, DEFAULT_POSE, Command, PhysicsCore

        self.K = K
        self.Command = Command
        self.dt = CONTROL_DT
        self.pose0 = DEFAULT_POSE
        self.rng = rng
        self.scale = float(action_scale)
        self.course = K.build(spec) if spec else None
        if self.course is not None:
            c = self.course
            self.start, self.goal, self.wps = c.start, c.goal, list(c.waypoints)
            self.mitten = [e.x0 - 0.15 for e in c.elements if e.x0 - 0.15 > c.start[0] + 0.1]
        else:
            self.start, self.goal = (0.0, 0.0), (EBEN_LAENGE, 0.0)
            self.wps, self.mitten = [self.goal], []
        self.core = PhysicsCore(None, use_bam=use_bam, course=self.course)
        m = self.core.model
        self.fric0 = m.geom_friction[:, 0].copy()
        lo, hi = [], []
        for i in range(m.nu):
            j = int(m.actuator_trnid[i, 0])
            if m.jnt_limited[j]:
                lo.append(m.jnt_range[j, 0])
                hi.append(m.jnt_range[j, 1])
            else:
                lo.append(-np.inf)
                hi.append(np.inf)
        self.lo = np.array(lo) + ANSCHLAG_RAD
        self.hi = np.array(hi) - ANSCHLAG_RAD
        self.reset()

    def reset(self) -> None:
        r = self.rng
        self.core.model.geom_friction[:, 0] = self.fric0 * r.uniform(*REIBUNG)
        x0 = self.start[0]
        if self.mitten and r.random() < MITTEN_START:
            x0 = float(r.choice(self.mitten))
        self.core.reset(x0, r.uniform(-START_Y, START_Y), math.radians(r.uniform(-START_YAW_GRAD, START_YAW_GRAD)))
        self.ab_start = x0 == self.start[0]
        self.wp = 0
        self.t = 0.0
        self.ret = 0.0
        self.x_prev = self.best_x = x0
        self.x_start = x0
        self.best_t = 0.0
        self.next_push = r.uniform(*SCHUBS)
        self.limit = (EBEN_ZEIT_S if self.course is None
                      else min(MAX_DURCHGANG_S, SETTLE_S + 6.0 + (self.goal[0] - x0) / 0.15))
        self.prev_a = np.zeros(14, np.float32)
        self.cmd = self.Command()
        self.obs = self.core.observation(self.cmd)

    def _befehl(self, tr: dict[str, float]) -> bool:
        """Fahrbefehl wie in evaluate(); True = Ziel erreicht."""
        self.cmd = self.Command()
        if self.t < SETTLE_S:
            return False
        while self.wp < len(self.wps) and (
                math.hypot(self.wps[self.wp][0] - tr["x"], self.wps[self.wp][1] - tr["y"]) < 0.07
                or self.wps[self.wp][0] < tr["x"] - 0.1):
            self.wp += 1
        if self.wp >= len(self.wps) or tr["x"] >= self.goal[0]:
            return True
        vx, vyaw = self.K._drive(self.wps[self.wp], tr)
        self.cmd.twist[:] = [vx, 0.0, vyaw]
        return False

    def step(self, a: np.ndarray) -> tuple[float, bool, bool, np.ndarray | None, dict[str, Any] | None]:
        """Ein Regelschritt. → (Belohnung, Ende mit Endzustand, Ende durch Zeit, letzte Beobachtung bei Zeitende, Bericht)."""
        core = self.core
        a = np.where(np.isfinite(a), a, 0.0).astype(np.float32)
        cmd = self.cmd
        core.last_action = a
        core._set_targets(self.pose0 + a * self.scale)
        core.control_step(cmd)                     # ohne eigene Policy: nur die Physik (4 × 5 ms)
        self.t += self.dt
        CONTROL_DT = self.dt
        tr = core.trunk()
        if self.t >= self.next_push:              # kleiner Schubs – oder einer der echten aus dem Kollisionsmodus
            d = core.data
            if self.schubs is not None and len(self.schubs) and self.rng.random() < SCHUBS_ECHT_ANTEIL:
                fx, fy = self.schubs[int(self.rng.integers(len(self.schubs)))] * SCHUBS_ECHT_FAKTOR
                c, sn = math.cos(tr["yaw"]), math.sin(tr["yaw"])
                d.qvel[core.root_v:core.root_v + 2] += [c * fx - sn * fy, sn * fx + c * fy]
            else:
                d.qvel[core.root_v:core.root_v + 2] += self.rng.uniform(-SCHUBS_MS, SCHUBS_MS, 2)
            self.next_push += self.rng.uniform(*SCHUBS)
        q = core.data.qpos[core.qpos_idx]
        dx = tr["x"] - self.x_prev
        self.x_prev = tr["x"]
        v_err = (tr["vx"] - float(cmd.twist[0])) ** 2 + (tr["vy"] - float(cmd.twist[1])) ** 2
        w_err = (tr["vyaw"] - float(cmd.twist[2])) ** 2
        r = (W_FORTSCHRITT * dx
             + CONTROL_DT * (W_LEBEN + W_BEFEHL_V * math.exp(-v_err / 0.02) + W_BEFEHL_W * math.exp(-w_err / 0.2)
                             - W_RUCKELN * float(np.sum((a - self.prev_a) ** 2))
                             - W_ANSCHLAG * float(np.sum((q < self.lo) | (q > self.hi)))))
        self.prev_a = a
        ende = None
        if tr["up"] < self.K.FALL_UP:
            r += W_STURZ
            ende = "sturz"
        elif self._befehl(tr):
            r += W_ZIEL
            ende = "ziel"
        else:
            if tr["x"] > self.best_x + 0.03:
                self.best_x, self.best_t = tr["x"], self.t
            if self.t >= self.limit:
                ende = "zeit"
            elif self.t - max(self.best_t, SETTLE_S) > FEST_S:
                ende = "fest"
        self.ret += r
        if ende is None:
            self.obs = core.observation(self.cmd)
            return r, False, False, None, None
        bericht = {"ende": ende, "rueckgabe": round(self.ret, 3), "dauer_s": round(self.t, 2),
                   "strecke_m": round(tr["x"] - self.x_start, 3), "ab_start": self.ab_start}
        last = core.observation(self.cmd) if ende in ("zeit", "fest") else None
        self.reset()
        return r, ende in ("sturz", "ziel"), ende in ("zeit", "fest"), last, bericht


def _rechenprozess(conn, spec, net: Netz, action_scale: float, anzahl: int, seed: int, use_bam,
                   schubs: list[list[float]] | None = None) -> None:
    """Ein Rechenprozess: hält `anzahl` Enten und fährt auf Zuruf eine Runde mit den geschickten Gewichten."""
    try:
        try:                                      # die Oberfläche soll flüssig bleiben
            if hasattr(os, "nice"):
                os.nice(5)
            elif os.name == "nt":
                import ctypes

                k32 = ctypes.windll.kernel32
                k32.SetPriorityClass(k32.GetCurrentProcess(), 0x4000)     # BELOW_NORMAL_PRIORITY_CLASS
        except Exception:
            pass
        rng = np.random.default_rng(seed)
        envs = [_Umgebung(spec, action_scale, rng, use_bam, schubs) for _ in range(anzahl)]
        werte = dict(net.tensoren)
        conn.send(("bereit", None))
        log2pi = math.log(2 * math.pi)
        while True:
            msg = conn.recv()
            if msg[0] != "runde":
                break
            _, gewichte, log_std, T = msg
            werte.update(gewichte)
            std = np.exp(log_std).astype(np.float32)
            K = len(envs)
            obs = np.zeros((T, K, 61), np.float32)
            act = np.zeros((T, K, 14), np.float32)
            logp = np.zeros((T, K), np.float32)
            rew = np.zeros((T, K), np.float32)
            term = np.zeros((T, K), bool)
            trunc = np.zeros((T, K), bool)
            fobs = np.zeros((T, K, 61), np.float32)
            berichte = []
            for t in range(T):
                o = np.stack([e.obs for e in envs])
                mu = _ausfuehren(net, werte, o, np).reshape(K, -1).astype(np.float32)
                eps = rng.standard_normal(mu.shape).astype(np.float32)
                a = mu + std * eps
                obs[t], act[t] = o, a
                logp[t] = -0.5 * np.sum(eps ** 2, axis=1) - np.sum(log_std) - 0.5 * 14 * log2pi
                for k, e in enumerate(envs):
                    r, te, tu, last, ber = e.step(a[k])
                    rew[t, k], term[t, k], trunc[t, k] = r, te, tu
                    if last is not None:
                        fobs[t, k] = last
                    if ber is not None:
                        berichte.append(ber)
            conn.send(("daten", {"obs": obs, "act": act, "logp": logp, "rew": rew, "term": term, "trunc": trunc,
                                 "fobs": fobs, "last": np.stack([e.obs for e in envs]), "berichte": berichte}))
    except (EOFError, KeyboardInterrupt, BrokenPipeError):
        pass
    except Exception as exc:
        try:
            conn.send(("fehler", f"{type(exc).__name__}: {exc}\n{traceback.format_exc()[-1500:]}"))
        except Exception:
            pass


# ── Lernen (Hintergrund-Thread) ─────────────────────────────────────────
def _slug(text: str) -> str:
    t = str(text or "").strip().lower()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        t = t.replace(a, b)
    t = re.sub(r"[^a-z0-9_-]+", "-", t).strip("-_")
    return t[:40] or "parcours"


def _schreiben(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".teil")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    for _ in range(5):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:               # Windows: gerade von jemandem geöffnet
            time.sleep(0.05)
    log.warning("Lernstand %s nicht gespeichert", path)


def _geraet(torch, wunsch: str) -> tuple[Any, str]:
    if wunsch != "cpu" and torch.cuda.is_available():
        try:
            dev = torch.device("cuda")
            float(torch.ones(8, device=dev).sum().item())
            torch.backends.cuda.matmul.allow_tf32 = False
            torch.backends.cudnn.allow_tf32 = False
            return dev, f"Radeon/GPU · {torch.cuda.get_device_name(0)}"
        except Exception as exc:
            log.warning("Grafikkarte nicht nutzbar (%s) – lerne auf dem Prozessor", exc)
    return torch.device("cpu"), "Prozessor · cpu"


class LocalTrainer:
    """Lernen am PC: ein Lauf zur Zeit, im Hintergrund-Thread; die Physik in eigenen Rechenprozessen."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.dir = self.root / "lernen"
        self._lock = threading.RLock()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self.job: dict[str, Any] | None = None
        self._saved = 0.0
        self._schubs: list[list[float]] | None = None

    # ── öffentliche Schnittstelle ────────────────────────────────────────
    def start(self, course: dict[str, Any] | None, quelle: str, minuten: float, name: str,
              workers: int | None = None, *, umgebungen: int | None = None, geraet: str = "auto",
              use_bam: bool | None = None, stoesse: bool = True) -> dict[str, Any]:
        """Einen Lauf starten (kehrt sofort zurück). Wirft LernFehler/ValueError bei falschen Angaben.
        stoesse: die im Kollisionsmodus gemessenen Stöße mit üben (falls es welche gibt)."""
        ok, why = available()
        if not ok:
            raise LernFehler(why)
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                raise LernFehler("Es lernt schon – erst den laufenden Lauf beenden.")
            try:
                minuten = float(minuten)
            except (TypeError, ValueError):
                raise LernFehler("Dauer: Minuten als Zahl") from None
            if not math.isfinite(minuten) or not 0.1 <= minuten <= 24 * 60:
                raise LernFehler("Dauer: 0,1 bis 1440 Minuten (24 Stunden)")
            spec = None
            if course:
                from . import course as K

                built = K.build(course)              # wirft CourseError (ValueError) mit deutschem Text
                spec = built.spec()
            path, scale, label = aufloesen(self.root, quelle)
            net = lade_netz(path)
            n_workers = int(workers) if workers else max(1, (os.cpu_count() or 2) - 1)
            n_workers = max(1, min(64, n_workers))
            n_env = max(1, min(64, int(umgebungen or UMGEBUNGEN_JE_PROZESS)))
            if geraet not in ("auto", "cpu", "gpu"):
                raise LernFehler("Gerät: auto, cpu oder gpu")
            from .kollision import stossproben

            self._schubs = (stossproben(self.root) or None) if stoesse else None
            stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
            jid, n = stamp, 2
            while (self.dir / f"{jid}.json").exists():
                jid, n = f"{stamp}-{n}", n + 1
            clean = " ".join(str(name or "").split())[:48] or (built.name if course else "Ebener Boden")
            self.job = {
                "id": jid, "name": clean, "quelle": str(quelle), "quelle_name": label, "start_onnx": str(path),
                "action_scale": scale, "parcours": spec, "parcours_name": (spec or {}).get("name") or "Ebener Boden",
                "start": time.strftime("%Y-%m-%d %H:%M"), "ende": None, "budget_minuten": round(minuten, 2),
                "minuten": 0.0, "prozesse": n_workers, "umgebungen": n_workers * n_env, "laeuft": True,
                "phase": "bereitet vor …", "iteration": 0, "schritte": 0, "schritte_pro_s": None,
                "geraet": None, "kurve": [], "faehigkeit": None, "im_ziel": None, "bester": None, "ergebnis": None,
                "fehler": None, "hinweis": None, "streuung": START_STREUUNG,
                "stoesse": len(self._schubs or []),
            }
            self._stop.clear()
            self._save(force=True)
            self._thread = threading.Thread(target=self._lauf, args=(net, spec, n_workers, n_env, geraet, use_bam,
                                                                    minuten), name="lernen", daemon=True)
            self._thread.start()
            return self.status()

    def stop(self, warten: float = 60.0) -> dict[str, Any]:
        """Beenden: der Lauf hört nach der laufenden Runde auf, exportiert den besten Stand und gibt den Status."""
        self._stop.set()
        t = self._thread
        if t is not None and t.is_alive() and t is not threading.current_thread():
            with self._lock:
                if self.job and self.job.get("laeuft"):
                    self.job["phase"] = "hört auf …"
            t.join(max(0.0, warten))
        return self.status()

    def status(self) -> dict[str, Any]:
        with self._lock:
            if self.job is not None:
                return json.loads(json.dumps(self.job))
        past = self.history()
        if past:
            return self.laden(past[0]["id"]) or self._leer()
        return self._leer()

    def history(self) -> list[dict[str, Any]]:
        """Frühere und laufende Läufe (neueste zuerst), ohne Kurve."""
        out = []
        for f in self.dir.glob("*.json") if self.dir.exists() else []:
            if not JOB_ID.fullmatch(f.stem):
                continue
            j = self.laden(f.stem)
            if j:
                j["punkte"] = len(j.pop("kurve", []) or [])
                j.pop("parcours", None)
                out.append(j)
        return sorted(out, key=lambda j: j["id"], reverse=True)

    def laden(self, job_id: str) -> dict[str, Any] | None:
        """Ein Lauf mit Kurve (auch nach einem Neustart von duckpilot)."""
        if not JOB_ID.fullmatch(str(job_id)):
            return None
        with self._lock:
            if self.job is not None and self.job["id"] == job_id:
                return json.loads(json.dumps(self.job))
        try:
            j = json.loads((self.dir / f"{job_id}.json").read_text(encoding="utf-8"))
        except Exception:
            return None
        if not isinstance(j, dict):
            return None
        if j.get("laeuft"):                      # lief, als duckpilot beendet wurde
            j["laeuft"] = False
            j["phase"] = "unterbrochen – duckpilot wurde beendet"
            j["rettbar"] = (self.dir / job_id / "bester.npz").exists() and not j.get("ergebnis")
        return j

    def exportieren(self, job_id: str) -> dict[str, Any]:
        """Den gesicherten besten Stand eines unterbrochenen Laufs nachträglich als Policy speichern."""
        j = self.laden(job_id)
        if j is None:
            raise LernFehler("Diesen Lauf gibt es nicht.")
        if self.job is not None and self.job["id"] == job_id and self.job.get("laeuft"):
            raise LernFehler("Der Lauf läuft noch.")
        if j.get("ergebnis"):
            return j
        npz = self.dir / job_id / "bester.npz"
        if not npz.exists():
            raise LernFehler("Für diesen Lauf ist kein Zwischenstand gesichert.")
        net = lade_netz(j["start_onnx"])
        with np.load(npz) as z:
            gew = {n: z[f"w{i}"] for i, n in enumerate(net.lernbar)}
        j["ergebnis"] = self._export(net, gew, j)
        j["phase"] = "unterbrochen – bester Stand nachträglich gespeichert"
        j["rettbar"] = False
        _schreiben(self.dir / f"{job_id}.json", j)
        return j

    # ── intern ───────────────────────────────────────────────────────────
    @staticmethod
    def _leer() -> dict[str, Any]:
        return {"id": None, "laeuft": False, "phase": "bereit", "iteration": 0, "schritte": 0, "minuten": 0.0,
                "geraet": None, "kurve": [], "faehigkeit": None, "im_ziel": None, "bester": None, "ergebnis": None,
                "fehler": None}

    def _set(self, **fields: Any) -> None:
        with self._lock:
            if self.job is not None:
                self.job.update(fields)

    def _save(self, force: bool = False) -> None:
        now = time.monotonic()
        if not force and now - self._saved < SPEICHERN_S:
            return
        self._saved = now
        with self._lock:
            if self.job is None:
                return
            data = json.loads(json.dumps(self.job))
        _schreiben(self.dir / f"{data['id']}.json", data)

    def _export(self, net: Netz, gewichte: dict[str, np.ndarray], job: dict[str, Any]) -> str:
        from .core import Policy

        stem = f"lokal-{_slug(job['name'])}-{dt.datetime.now().strftime('%Y%m%d-%H%M')}"
        folder = _lokal_dir(self.root)
        base, n = stem, 2
        while (folder / f"{stem}.onnx").exists():
            stem, n = f"{base}-{n}", n + 1
        path = torch_nach_onnx(net, gewichte, folder / f"{stem}.onnx",
                               {"duckpilot_lernen": job["id"], "duckpilot_quelle": job["quelle"]})
        try:
            Policy(path, stem, job.get("action_scale") or 1.0)       # läuft sie wie jede andere Policy?
            ref = lade_netz(path)
            if ref.obs_form != net.obs_form or ref.out_form != net.out_form:
                raise LernFehler("Ein- oder Ausgang hat sich beim Export verändert.")
        except Exception:
            path.unlink(missing_ok=True)
            raise
        best = job.get("bester") or {}
        meta = {"name": job["name"], "erstellt": time.strftime("%Y-%m-%d %H:%M"), "job": job["id"],
                "quelle": job["quelle"], "quelle_name": job.get("quelle_name"), "parcours": job.get("parcours"),
                "parcours_name": job.get("parcours_name"), "action_scale": job.get("action_scale") or 1.0,
                "iteration": best.get("iteration", job.get("iteration")), "iterationen": job.get("iteration"),
                "schritte": job.get("schritte"), "minuten": job.get("minuten"), "geraet": job.get("geraet"),
                "faehigkeit": best.get("faehigkeit"), "im_ziel": best.get("im_ziel"),
                "belohnung": best.get("belohnung"), "art": "lokal"}
        _schreiben(path.with_suffix(".json"), meta)
        return f"lokal:{stem}"

    def _lauf(self, net: Netz, spec, n_workers: int, n_env: int, wunsch: str, use_bam, minuten: float) -> None:
        import multiprocessing as mp

        t0 = time.monotonic()
        deadline = t0 + minuten * 60
        ctx = mp.get_context("spawn")             # wie unter Windows – und sicher neben Threads
        procs: list[Any] = []
        conns: list[Any] = []
        best_w: dict[str, np.ndarray] | None = None
        last_w: dict[str, np.ndarray] | None = None
        grund = "fertig"
        job_id = self.job["id"] if self.job else "?"
        best_dir = self.dir / job_id
        try:
            import torch

            device, label = _geraet(torch, wunsch)
            self._set(geraet=label, phase=f"startet {n_workers} Rechenprozesse …")
            scale = float(self.job.get("action_scale") or 1.0)
            seed0 = int(time.time()) % 100000
            for w in range(n_workers):
                a, b = ctx.Pipe()
                p = ctx.Process(target=_rechenprozess, args=(b, spec, net, scale, n_env, seed0 + 7919 * w, use_bam,
                                                              self._schubs),
                                daemon=True, name=f"lernen-{w}")
                p.start()
                b.close()
                procs.append(p)
                conns.append(a)
            for i, c in enumerate(conns):
                kind, data = self._empfang(c, procs[i], t0 + 300, stoppbar=True)
                if kind == "stopp":
                    raise _Abbruch()
                if kind != "bereit":
                    raise LernFehler(f"Rechenprozess {i + 1} startet nicht: {data}")
            # Netze
            akteur = onnx_nach_torch(net).to(device)
            log_std = torch.nn.Parameter(torch.full((14,), math.log(START_STREUUNG), device=device))
            kritiker = torch.nn.Sequential(torch.nn.Linear(61, 256), torch.nn.ELU(), torch.nn.Linear(256, 128),
                                           torch.nn.ELU(), torch.nn.Linear(128, 1)).to(device)
            norm = _Normierer(61, device, torch)

            def optimierer():
                return torch.optim.Adam([{"params": list(akteur.parameters()), "lr": LR_AKTEUR},
                                         {"params": [log_std], "lr": LR_STREUUNG},
                                         {"params": list(kritiker.parameters()), "lr": LR_KRITIKER}])

            opt = optimierer()
            fenster: collections.deque[dict[str, Any]] = collections.deque(maxlen=FENSTER)
            best_score: tuple[float, float] | None = None
            last_best_save = 0.0
            it = 0
            steps = 0
            t_learn = time.monotonic()
            while True:
                if self._stop.is_set():
                    grund = "abgebrochen"
                    break
                if time.monotonic() >= deadline:
                    grund = "fertig"
                    break
                warm = it < KRITIKER_AUFWAERMEN
                self._set(phase="wärmt den Kritiker auf" if warm else "lernt")
                gew = akteur.gewichte()
                last_w = gew
                ls = log_std.detach().float().cpu().numpy()
                for c in conns:
                    c.send(("runde", gew, ls, ROLLOUT_STEPS))
                teile = []
                for i, c in enumerate(conns):
                    kind, data = self._empfang(c, procs[i], time.monotonic() + 600)
                    if kind != "daten":
                        raise LernFehler(f"Rechenprozess {i + 1}: {data}")
                    teile.append(data)
                batch = {k: np.concatenate([d[k] for d in teile], axis=1)
                         for k in ("obs", "act", "logp", "rew", "term", "trunc", "fobs")}
                batch["last"] = np.concatenate([d["last"] for d in teile], axis=0)
                for d in teile:
                    fenster.extend(d["berichte"])
                T, E = batch["rew"].shape
                steps += T * E
                belohnung = float(batch["rew"].sum() / (T * E * 0.02))
                try:
                    kl = self._ppo(torch, device, akteur, log_std, kritiker, norm, opt, batch, warm)
                except RuntimeError as exc:
                    if device.type != "cuda":
                        raise
                    log.warning("Grafikkarte fällt aus (%s) – weiter auf dem Prozessor", exc)
                    device = torch.device("cpu")
                    akteur.to(device)
                    kritiker.to(device)
                    log_std = torch.nn.Parameter(log_std.detach().to(device))
                    norm.to(device)
                    opt = optimierer()
                    self._set(geraet="Prozessor · cpu", hinweis="Die Grafikkarte ist ausgefallen – es lernt auf dem "
                                                                "Prozessor weiter.")
                    kl = None
                it += 1
                # Kennzahlen
                n = len(fenster)
                faeh = round(100 * sum(e["ende"] != "sturz" for e in fenster) / n, 1) if n else None
                ziel = round(100 * sum(e["ende"] == "ziel" for e in fenster) / n, 1) if n else None
                punkt = {"iteration": it, "belohnung": round(belohnung, 3), "faehigkeit": faeh,
                         "im_ziel_anteil": ziel, "streuung": round(float(np.exp(ls).mean()), 4),
                         "kl": None if kl is None else round(kl, 5), "durchgaenge": n}
                fields: dict[str, Any] = {}
                if n >= MIN_DURCHGAENGE:
                    score = (faeh + ziel, belohnung)
                    if best_score is None or score > best_score:
                        best_score = score
                        best_w = gew                   # die Gewichte, mit denen diese Runde gefahren ist
                        fields["bester"] = {"iteration": it, "faehigkeit": faeh, "im_ziel": ziel,
                                            "belohnung": round(belohnung, 3)}
                        if time.monotonic() - last_best_save > 20:
                            last_best_save = time.monotonic()
                            self._sichern(best_dir, net, best_w)
                el = time.monotonic() - t_learn
                with self._lock:
                    kurve = self.job["kurve"]
                    kurve.append(punkt)
                    if len(kurve) > MAX_KURVE:
                        head, tail = kurve[:-100], kurve[-100:]
                        step = math.ceil(len(head) / (MAX_KURVE - 150))
                        self.job["kurve"] = head[::step] + tail
                    self.job.update(iteration=it, schritte=steps, faehigkeit=faeh, im_ziel=ziel,
                                    minuten=round((time.monotonic() - t0) / 60, 2), streuung=punkt["streuung"],
                                    schritte_pro_s=round(steps / max(el, 1e-6)), **fields)
                self._save()
        except _Abbruch:
            grund = "abgebrochen"
        except Exception as exc:
            grund = "fehlgeschlagen"
            msg = str(exc) if isinstance(exc, LernFehler) else f"{type(exc).__name__}: {exc}"
            log.exception("Lernen am PC fehlgeschlagen")
            self._set(fehler=msg[:500])
        finally:
            for c in conns:
                try:
                    c.send(("ende",))
                except Exception:
                    pass
            for p in procs:
                p.join(3)
                if p.is_alive():
                    p.terminate()
                    p.join(2)
            for c in conns:
                try:
                    c.close()
                except Exception:
                    pass
            self._abschluss(net, best_w, last_w, grund, t0, best_dir)

    def _abschluss(self, net: Netz, best_w, last_w, grund: str, t0: float, best_dir: Path) -> None:
        gew = best_w if best_w is not None else last_w
        hinweis = None
        if best_w is None and last_w is not None:
            hinweis = "Zu wenige Durchgänge für eine Bewertung – gespeichert ist der letzte Stand."
        self._set(phase="speichert das beste Netz …", minuten=round((time.monotonic() - t0) / 60, 2))
        ergebnis = None
        if gew is not None:
            try:
                with self._lock:
                    job = json.loads(json.dumps(self.job))
                ergebnis = self._export(net, gew, job)
            except Exception as exc:
                log.exception("Export fehlgeschlagen")
                with self._lock:
                    self.job["fehler"] = (self.job.get("fehler") or f"Export fehlgeschlagen: {exc}")[:500]
        phase = {"fertig": "fertig – Zeit abgelaufen", "abgebrochen": "beendet – bester Stand gespeichert",
                 "fehlgeschlagen": "fehlgeschlagen"}[grund]
        if grund == "abgebrochen" and ergebnis is None:
            phase = "beendet"
        if grund == "fehlgeschlagen" and ergebnis is not None:
            phase = "fehlgeschlagen – bester Stand bis dahin gespeichert"
        with self._lock:
            self.job.update(laeuft=False, phase=phase, ergebnis=ergebnis, ende=time.strftime("%Y-%m-%d %H:%M"),
                            minuten=round((time.monotonic() - t0) / 60, 2))
            if hinweis and ergebnis and not self.job.get("hinweis"):
                self.job["hinweis"] = hinweis
        self._save(force=True)
        try:
            (best_dir / "bester.npz").unlink(missing_ok=True)
            if best_dir.exists() and not any(best_dir.iterdir()):
                best_dir.rmdir()
        except OSError:
            pass

    @staticmethod
    def _sichern(folder: Path, net: Netz, gew: dict[str, np.ndarray]) -> None:
        try:
            folder.mkdir(parents=True, exist_ok=True)
            tmp = folder / "bester.teil.npz"
            np.savez(tmp, **{f"w{i}": gew[n] for i, n in enumerate(net.lernbar)})
            os.replace(tmp, folder / "bester.npz")
        except OSError as exc:
            log.info("Zwischenstand nicht gesichert: %s", exc)

    def _empfang(self, conn, proc, bis: float, stoppbar: bool = False) -> tuple[str, Any]:
        while True:
            if stoppbar and self._stop.is_set():
                return "stopp", None
            if conn.poll(0.2):
                try:
                    return conn.recv()
                except (EOFError, OSError):
                    return "fehler", "Verbindung abgebrochen"
            if not proc.is_alive():
                return "fehler", f"abgestürzt (Code {proc.exitcode})"
            if time.monotonic() > bis:
                return "fehler", "antwortet nicht"

    @staticmethod
    def _ppo(torch, device, akteur, log_std, kritiker, norm, opt, batch, warm: bool) -> float | None:
        T, E = batch["rew"].shape
        f = lambda k: torch.as_tensor(batch[k], device=device)
        obs, act, old_logp = f("obs"), f("act"), f("logp")
        rew = f("rew").clone()
        term, trunc = f("term"), f("trunc")
        norm.update(obs.reshape(-1, 61))
        with torch.no_grad():
            values = kritiker(norm(obs.reshape(-1, 61))).reshape(T, E)
            last_v = kritiker(norm(f("last"))).reshape(E)
            if bool(trunc.any()):                  # Zeitende: mit dem Wert des letzten Zustands weiterrechnen
                fv = kritiker(norm(f("fobs")[trunc])).reshape(-1)
                rew[trunc] += GAMMA * fv
            done = (term | trunc).float()
            adv = torch.zeros_like(rew)
            last = torch.zeros(E, device=device)
            for t in reversed(range(T)):
                nv = last_v if t == T - 1 else values[t + 1]
                nonterm = 1.0 - done[t]
                delta = rew[t] + GAMMA * nv * nonterm - values[t]
                last = delta + GAMMA * LAMBDA * nonterm * last
                adv[t] = last
            ret = adv + values
        B = T * E
        obs_f, act_f, logp_f = obs.reshape(B, -1), act.reshape(B, -1), old_logp.reshape(B)
        adv_f, ret_f = adv.reshape(B), ret.reshape(B)
        adv_f = (adv_f - adv_f.mean()) / (adv_f.std() + 1e-8)
        obs_n = norm(obs_f)
        mb = max(1, B // MINIBATCHES)
        kl_mean = None
        params = list(akteur.parameters()) + [log_std] + list(kritiker.parameters())
        for _ in range(EPOCHEN):
            perm = torch.randperm(B, device=device)
            kls = []
            for s in range(0, B, mb):
                idx = perm[s:s + mb]
                v = kritiker(obs_n[idx]).reshape(-1)
                loss = 0.5 * ((v - ret_f[idx]) ** 2).mean()
                if not warm:
                    mu = akteur(obs_f[idx])
                    ls = log_std.clamp(math.log(STREUUNG_MIN), math.log(STREUUNG_MAX))
                    z = (act_f[idx] - mu) / ls.exp()
                    logp = -0.5 * (z ** 2).sum(-1) - ls.sum() - 0.5 * 14 * math.log(2 * math.pi)
                    ratio = (logp - logp_f[idx]).exp()
                    a = adv_f[idx]
                    loss = loss - torch.min(ratio * a, ratio.clamp(1 - CLIP, 1 + CLIP) * a).mean()
                    with torch.no_grad():
                        kls.append(float(((ratio - 1) - (logp - logp_f[idx])).mean()))
                opt.zero_grad(set_to_none=True)
                loss.backward()
                torch.nn.utils.clip_grad_norm_([p for p in params if p.grad is not None], MAX_GRAD)
                opt.step()
                with torch.no_grad():
                    log_std.clamp_(math.log(STREUUNG_MIN), math.log(STREUUNG_MAX))
            if kls:
                kl_mean = sum(kls) / len(kls)
                if kl_mean > ZIEL_KL:
                    break
        return kl_mean


class _Abbruch(Exception):
    pass


class _Normierer:
    """Laufender Mittelwert/Streuung der Beobachtungen – nur für den Kritiker."""

    def __init__(self, n: int, device, torch) -> None:
        self.torch = torch
        self.mean = torch.zeros(n, device=device)
        self.var = torch.ones(n, device=device)
        self.count = 1e-4

    def to(self, device) -> None:
        self.mean, self.var = self.mean.to(device), self.var.to(device)

    def update(self, x) -> None:
        bm, bv, bc = x.mean(0), x.var(0, unbiased=False), x.shape[0]
        d = bm - self.mean
        tot = self.count + bc
        self.mean = self.mean + d * bc / tot
        self.var = (self.var * self.count + bv * bc + d ** 2 * self.count * bc / tot) / tot
        self.count = tot

    def __call__(self, x):
        return ((x - self.mean) / (self.var.sqrt() + 1e-6)).clamp(-10, 10)
