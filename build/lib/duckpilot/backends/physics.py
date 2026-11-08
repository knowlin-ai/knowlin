"""Simulator mit echter Physik: dieselbe Wohnung, dieselben Befehle – aber der Körper ist
Pollens MuJoCo-Modell, und Pollens Policies laufen ihn.

Alles, was der einfache Simulator kann (Tiefensensor, Ball, Socke, Ereignisse, Totmann,
Skills als Zustand), übernimmt diese Klasse von `SimBackend`. Neu ist nur der Körper:

* Gehen, Stehen, Kopf und Körperhaltung: Pollens VelStand-Policy bekommt den Befehl,
  MuJoCo rechnet. Rempelt die Ente an ein Möbel, fällt sie wirklich – und VelStand steht
  von selbst wieder auf.
* Hinsetzen, Aufheben, Schießen, Purzelbaum: die jeweilige Policy aus Pollens Satz.
* Tricks und Gangarten vom Hub laufen hier vor der Lieferung.
* Die 3D-Ansicht zeigt die berechneten Gelenkwinkel und die echte Lage des Rumpfs.

Braucht `mujoco`, `onnxruntime`, `numpy` und den einmal geladenen Policy-Satz. Fehlt etwas,
nimmt duckpilot den einfachen Simulator.
"""

from __future__ import annotations

import asyncio
import logging
import math
import re
from pathlib import Path
from typing import Any

import numpy as np

from ..api import DEFAULT_SKILLS, DuckState, Head, IntentResult, Twist, wrap_angle
from ..physics.core import (
    BODY_MAX_ANGLE,
    BODY_MAX_XYZ,
    CONTROL_DT,
    HEAD_CAP,
    LIMP_FALL_GAIN,
    POSE_S,
    POWER_OFF_GAIN,
    ROBOT_ACTION_SCALE,
    TWIST_MAX,
    Command,
    PhysicsCore,
    Policy,
    PolicyError,
)
from ..physics.params import CMD_ALPHA, HEAD_ALPHA
from ..physics.policies import PolicyStore
from ..physics.twist import shape_twist  # noqa: F401  (auch von hier importierbar)
from .sim import SimBackend
from .world import World

log = logging.getLogger(__name__)

FALL_UP = 0.45            # Rumpf-Hochachse darunter: umgefallen
ACRO_LANDING_S = 3.0      # nach Purzelbaum/Trick: robotd gibt nach 1 s an die Geh-Policy, die richtet sie in ≈ 1,5 s auf
LANDED_HOLD_S = 0.3       # so lange aufrecht = gelandet (Kopf ruhig und Kopfbefehle wieder an)
RECOVER_TIMEOUT_S = 6.0   # so lange darf das Aufrichten dauern, dann wieder weich liegen (der Reflex versucht es neu)


def default_scale(role: str) -> float:
    """Ausgabe-Faktor wie robotd, wenn das Manifest nichts sagt: Hinsetzen und Aufheben 1,0, sonst 0,9."""
    return 1.0 if role in ("sitstand", "ground_pick") else ROBOT_ACTION_SCALE
# Skills wie robotd (seit 0.37, abgeglichen mit Pollens robotd/src/control.rs): Ein Trick bekommt im Fenster den
# Befehl 0 (Kopf und Rumpf auch 0), danach – falls das Manifest `unwind_s` nennt – so lange `command.idle`. Mit
# Befehl ≈ 0 und geladener Stand-Policy läuft er „standing tuned“: Ausgabe-Faktor 1,0, Motorstärke 0,8 – sofern das
# Manifest keinen eigenen `action_scale` hat. Der Purzelbaum läuft mit vollen Werten (roulade_* = 1,0).
STANDING_ACTION_SCALE = 1.0
STANDING_GAIN_RATIO = 0.8
STANDING_SCHWELLE = 0.05      # Befehlsbetrag, bis zu dem robotd „steht“ (will_stand)
STAND_UP = 0.85           # darüber (und hoch genug): steht wieder
ONE_SHOTS = ("kick_left", "kick_right", "roulade")

# Erschütterung fürs Vibrieren (Handy, Gamepad): Anstieg der Kontaktkraft von außen je Schritt
RUCK_AB_NS = 0.02         # darunter: Streifen, Anlehnen, ein Ding liegt am Fuß
RUCK_VOLL_NS = 0.3        # so viel = volle Stärke (Ball, kräftig geworfen)
RUCK_STOSS_VOLL_NS = 0.5  # Stoß im Kollisionsmodus: so viel Impuls = volle Stärke
RUCK_ABSTAND_S = 0.15
GROUND_PICK_PERIOD = 4.0
GROUND_PICK_END = 0.7


class PhysicsBackend(SimBackend):
    runs_policies = True

    def __init__(self, store: PolicyStore, world: World | None = None, realtime: bool = True,
                 seed: int | None = None, use_bam: bool | None = None) -> None:
        super().__init__(world=world, realtime=realtime, seed=seed)
        self.stabilizer.use_servo_tuning()      # echte Servos: Kopf kommt beim schnellen Nicken nicht mit
        self.store = store
        self.core = PhysicsCore(self.world_model, use_bam=use_bam, objects=True)
        from ..physics.kollision import Kollision

        self.kollision = Kollision(self.core, (self.world_model.width / 2, self.world_model.depth / 2))
        self.core.pre_step = self.kollision.pre_step
        self.kollision_aktiv = False
        self.episode: Any = None
        self.on_episode: Any = None                  # vom Kollisionsdienst gesetzt: fertige Episode speichern
        self._last_reiz = -1e9
        self._recover_ok = False                     # liegt sie, bleibt sie liegen, bis init() es erlaubt
        self._recover_t0: float | None = None        # Beginn des Aufrichtens (Rampe in die Grundstellung)
        self.policies: dict[str, Policy] = {}
        self.manifests: dict[str, dict[str, Any]] = {}
        self.tricks: dict[str, Policy] = {}           # vom Hub geladene One-Shots
        self.gait_policy: Policy | None = None        # vom Hub geladene Gangart
        self._trick_len: dict[str, float] = {}
        self._trick_cfg: dict[str, dict[str, Any]] = {}
        self._load_official()
        self.eigene: dict[str, str] = {}              # Name → Aufgabe der selbst trainierten Policies (seit 0.37.14)
        for e in self.store.eigene():
            try:
                self.add_local_policy(e["pfad"], e["name"], e["art"])
                self.eigene[e["name"]] = e["aufgabe"]
            except Exception as exc:
                log.warning("Eigene Policy %s nicht ladbar: %s", e["name"], exc)
        self.core.reset(self.x, self.y, self.yaw)
        self.powered = True
        self.enabled = True
        self._accum = 0.0
        self._cmd_ema: Command | None = None   # geglättete Befehle wie in robotd
        self._up_since: float | None = None
        self._down_since: float | None = None
        self._touching: set[str] = set()
        self._ruck: dict[str, Any] | None = None     # letzte Erschütterung von außen (fürs Vibrieren)
        self._ruck_f = 0.0
        self._ruck_t = -1e9
        self._body = [0.12, 0.0, 0.0]
        self._sit_flag = 0.0
        self._rise_until = 0.0
        self._skill_cfg: dict[str, Any] = {}

    def _load_official(self) -> None:
        for role, info in self.store.roles().items():
            e = info["eintrag"]
            try:
                self.policies[role] = Policy(info["pfad"], role, float(e.get("action_scale") or default_scale(role)))
                self.manifests[role] = e
            except Exception as exc:
                log.warning("Policy %s nicht ladbar: %s", role, exc)
        if "walk" not in self.policies:
            raise PolicyError("Die Geh-Policy (VelStand) fehlt – erst Pollens Policies laden.")

    # ── Fähigkeiten ──────────────────────────────────────────────────────
    def skills(self) -> list[str]:
        have = [s for s in DEFAULT_SKILLS if s in self.policies or (s == "sit_toggle" and "sitstand" in self.policies)]
        return [*have, *self.tricks]

    def _skill_len(self, name: str) -> float:
        if name in self.tricks:
            return float(self._trick_len.get(name, 3.0))
        if name in ONE_SHOTS:
            e = self.manifests.get(name, {})
            return float(e.get("duration_s") or {"roulade": 2.0}.get(name, 3.0))
        if name == "ground_pick":
            cmd = self.manifests.get("ground_pick", {}).get("command") or {}
            return float(cmd.get("period_s") or GROUND_PICK_PERIOD) * float(cmd.get("end_phase") or GROUND_PICK_END)
        if name == "sit_toggle":
            return float(self.manifests.get("sitstand", {}).get("unwind_s") or 2.2)
        return super()._skill_len(name)

    # ── der Körper ───────────────────────────────────────────────────────
    def _command(self) -> tuple[Policy | None, Command]:
        cmd = Command()
        skill = self.skill
        if self.fallen:                               # Aufrichten: Pollens Stand-Policy (falls da) oder VelStand, Befehl 0
            return self.policies.get("stand") or self.policies["walk"], cmd
        if skill in ONE_SHOTS and skill in self.policies:
            self._skill_tuning(self.policies[skill], skill, cmd)
            return self.policies[skill], cmd          # trainiert mit Befehl 0
        if skill in self.tricks:
            cfg = self._skill_cfg
            # Fenster: Befehl 0 (bis 0.36.3 lief hier fälschlich `idle` die ganze Zeit); danach ggf. idle zum Abschluss
            zurueck = self.skill_t >= float(cfg.get("fenster", self._skill_len(skill)))
            twist = cfg.get("idle") if zurueck else cfg.get("befehl")
            if twist:                                 # ungeglättet und unbegrenzt wie robotd – oft ein Schalter, kein Tempo
                cmd.twist[:] = np.clip(np.asarray(twist[:3], np.float32), -1.0, 1.0)
            self._skill_tuning(self.tricks[skill], skill, cmd)
            return self.tricks[skill], cmd
        if skill == "ground_pick" and "ground_pick" in self.policies:
            period = self._skill_len("ground_pick") / GROUND_PICK_END
            phase = self.skill_t / max(0.1, period)
            cmd.twist[:] = [math.cos(2 * math.pi * phase), math.sin(2 * math.pi * phase), 0.0]
            return self.policies["ground_pick"], cmd
        sitstand = self.policies.get("sitstand")
        if sitstand is not None and (self.sitting or skill in ("sit_toggle", "_rest", "_init") or self.t < self._rise_until):
            if skill == "sit_toggle":
                flag = 0.0 if self.sitting else 1.0
            elif skill == "_rest":
                flag = 1.0
            elif skill == "_init":
                flag = 0.0
            else:
                flag = 1.0 if self.sitting else 0.0
            cmd.twist[0] = flag
            cmd.head[:] = self._head_cmd()
            return sitstand, cmd
        walk = self.gait_policy or self.policies["walk"]
        if self._can_drive():
            v = self.requested
            cmd.twist[:] = np.clip(shape_twist(v.vx, v.vy, v.vyaw), -TWIST_MAX, TWIST_MAX)
        cmd.head[:] = self._head_cmd()
        p = self.pose_now
        cmd.body[2] = float(np.clip(p.z, -BODY_MAX_XYZ[2], BODY_MAX_XYZ[2]))
        cmd.body[3] = float(np.clip(p.roll, -BODY_MAX_ANGLE, BODY_MAX_ANGLE))
        cmd.body[4] = float(np.clip(p.pitch, -BODY_MAX_ANGLE, BODY_MAX_ANGLE))
        return walk, cmd

    def _skill_tuning(self, pol: Policy, skill: str, cmd: Command) -> None:
        """Ausgabe-Faktor und Motorstärke eines Skills, wie robotd sie jeden Takt neu bestimmt."""
        if skill == "roulade":
            scale, ratio = float(self.manifests.get("roulade", {}).get("action_scale") or 1.0), 1.0
        else:
            standing = "stand" in self.policies and float(np.linalg.norm(cmd.twist)) <= STANDING_SCHWELLE
            eigen = (self._trick_cfg.get(skill, {}).get("action_scale") if skill in self.tricks
                     else self.manifests.get(skill, {}).get("action_scale"))
            scale = float(eigen) if eigen else (STANDING_ACTION_SCALE if standing else ROBOT_ACTION_SCALE)
            ratio = STANDING_GAIN_RATIO if standing else 1.0
        pol.action_scale = scale
        self.core.set_gain_ratio(ratio)

    def _trunk_attitude(self) -> tuple[float, float, float]:
        tr = self.core.trunk()                     # echte Lage aus MuJoCo statt der gewünschten Haltung
        return tr["roll"], tr["pitch"], tr["yaw"]

    def _trunk_extra(self) -> dict[str, float]:
        tr = self.core.trunk()                     # echtes Vor und Zurück pro Schritt
        return {"x": tr["x"], "y": tr["y"]}

    def _head_cmd(self) -> np.ndarray:
        override = self._skill_head_override()
        h = override or self.stabilizer.apply(self.head_target.clamped()).clamped()
        if self.fallen or self._landing():
            h = Head()                               # liegend und beim Landen: keine Kopfbefehle (Rolle, Tricks)
        return np.clip(np.array([h.neck_pitch, h.head_pitch, h.head_yaw, h.head_roll], np.float32), -HEAD_CAP, HEAD_CAP)

    def _step_base(self, dt: float) -> None:
        self.limited_by = []
        if self.t - self._last_move > 0.5 and not self.requested.is_zero():
            self.requested = Twist()
            self.limited_by.append("Totmann – kein Intent in den letzten 500 ms")
        if not self._can_drive() and not self.requested.is_zero():
            self.limited_by.append(self._why_not_driving())
        policy, cmd = self._command()
        if self.fallen or not (self.skill in self.tricks or (self.skill in ONE_SHOTS and self.skill in self.policies)):
            self.core.set_gain_ratio(1.0)            # außerhalb eines Skills volle Stärke (Skills setzen ihre eigene)
        walking = policy is not None and policy is (self.gait_policy or self.policies.get("walk"))
        # liegt sie, bleibt sie weich liegen, bis der Sturz-Reflex (Stopp-Fenster, Not-Aus-Sperre) init() ruft –
        # sonst stünde VelStand sofort von selbst auf, auch nach einem Not-Aus. Danach wie robotd: Rampe in die
        # Grundstellung (0,6 s, Stärke 0,8), Policy von vorn, Stand-Policy mit Befehl 0
        lying = self.fallen and not self._recover_ok
        off = not self.powered and self.skill != "_init"
        self.core.set_limp(off or lying, POWER_OFF_GAIN if off else LIMP_FALL_GAIN)
        if lying:
            self.core.hold_current()
            self._recover_t0 = None
        elif self.fallen and not off:
            if self._recover_t0 is None:
                self._recover_t0 = self.t
                self.sitting = False
                self._cmd_ema = None
                self.core.start_pose(POSE_S)
            elif self.t - self._recover_t0 > RECOVER_TIMEOUT_S:
                # nicht hochgekommen: wieder weich hinlegen – der Reflex versucht es nach dem Stopp-Fenster erneut
                self._recover_ok = False
                self._recover_t0 = None
                self.core.set_limp(True, LIMP_FALL_GAIN)
                self.core.hold_current()
                self.emit("recover_fail", message="Kommt so nicht hoch – liegt wieder weich, versucht es gleich nochmal")
        # Kopf ruhig: Gelenke direkt halten – aber nicht während eines Ausdrucks, sonst eilt der Kopf dem Ton voraus
        # … und nicht beim Landen nach Purzelbaum oder Trick: der Ausgleich kippte sie dort ein zweites Mal um (0.33)
        steady = (self.stabilizer.enabled and self.powered and not self.fallen and not self.sitting and self.skill is None
                  and not self.expressing and not self._landing())
        self.core.head_override = cmd.head.copy() if steady else None
        self.core.set_policy(policy)
        self._accum += dt
        while self._accum >= CONTROL_DT - 1e-9:
            self._accum -= CONTROL_DT
            befehl = self._smoothed(cmd) if walking else cmd
            grenzen = getattr(policy, "grenzen", None)
            if grenzen is not None:                  # nur so weit, wie die Policy trainiert wurde
                from ..physics.isaaclab import begrenzen

                befehl = begrenzen(befehl, grenzen)
            self.core.control_step(befehl)
        tr = self.core.trunk()
        self.x, self.y, self.yaw = tr["x"], tr["y"], wrap_angle(tr["yaw"])
        self.applied = Twist(tr["vx"], tr["vy"], tr["vyaw"])
        self._body = [tr["z"], tr["roll"], tr["pitch"]]
        # Lage auch als Quaternion: Euler-Winkel springen kopfüber (Purzelbaum) – die 3D-Ansicht drehte sie dann falsch
        self._body_q = [float(v) for v in self.core.data.qpos[self.core.root_q + 3:self.core.root_q + 7]]
        self._watch_fall(tr)
        self._watch_bumps()
        self._watch_ruck(dt)
        self._push_items()
        if self.kollision_aktiv and self.kollision.hand_aktiv:
            self._watch_hand()
        ep = self.episode
        if ep is not None and ep.art in ("wurf", "rollen") and ep.treffer is None and ep.reiz.get("id"):
            hit = self.kollision.objekt_kontakt(str(ep.reiz["id"]))   # wo und wie fest das Ding sie trifft
            if hit is not None:
                ep.treffer = {**hit, "t": round(self.t - ep.t0, 3)}
        if self.kollision_aktiv and self.kollision.zug is not None:
            self._last_reiz = self.t                 # solange gezogen wird, ist alles Spiel
        if self.episode is not None and self.episode.sample(self.t, tr, self.fallen, self._joints()):
            self._episode_done()
        # Gangphase nur für Anzeigen (die Beine kommen aus der Physik)
        speed = math.hypot(tr["vx"], tr["vy"])
        if speed > 0.01:
            self.gait_phase = (self.gait_phase + 2 * math.pi * (2 + 8 * speed) * dt) % (2 * math.pi)

    def _smoothed(self, cmd: Command) -> Command:
        """Wie robotd: Fahr-, Kopf- und Haltungsbefehle je Takt glätten (cmd_alpha/head_alpha 0,2 bei 50 Hz)."""
        ema = self._cmd_ema
        if ema is None:
            self._cmd_ema = ema = Command()
        ema.twist += CMD_ALPHA * (cmd.twist - ema.twist)
        ema.head += HEAD_ALPHA * (cmd.head - ema.head)
        ema.body += HEAD_ALPHA * (cmd.body - ema.body)
        return ema

    def _acrobatic(self) -> bool:
        """Läuft gerade etwas, das absichtlich kopfüber geht oder zu Boden (Purzelbaum, Hub-Tricks, App-Moves)?"""
        return self.skill == "roulade" or self.skill in self.tricks

    def _landing(self) -> bool:
        """Landephase: während Purzelbaum/Trick und danach, bis sie wieder aufrecht steht (höchstens ACRO_LANDING_S).

        Solange schweigen Kopf-Stabilisator und Kopfbefehle – die Geh-Policy übernimmt (wie bei robotd) mitten in
        der Rolle und richtet sie selbst auf; ein Ausgleich am Kopf störte das und warf sie wieder um.
        """
        return self._acrobatic() or self.t < getattr(self, "_acro_until", -1.0)

    def _watch_fall(self, tr: dict[str, float]) -> None:
        up = tr["up"]
        if self._acrobatic():
            # mitten im Purzelbaum ist „kopfüber“ kein Sturz – sonst bricht die Rolle ab und sie landet auf dem Rücken
            self._acro_until = self.t + ACRO_LANDING_S
            self._down_since = None
            self._landed_since = None
            return
        if not self.fallen and self.t < getattr(self, "_acro_until", -1.0):
            # kurz landen lassen, dann erst urteilen; steht sie wieder aufrecht, ist die Landung vorbei
            if up > STAND_UP and tr["z"] > 0.09:
                since = getattr(self, "_landed_since", None)
                self._landed_since = since = self.t if since is None else since
                if self.t - since >= LANDED_HOLD_S:
                    self._acro_until = self.t
                    self._landed_since = None
                    self.stabilizer.reset()          # Mittelwerte aus der Rolle nicht in den Stand mitnehmen
            else:
                self._landed_since = None
            return
        if not self.fallen:
            if up < FALL_UP:
                self._down_since = self._down_since if self._down_since is not None else self.t
                if self.t - self._down_since > 0.25:
                    self._down_since = None
                    self.fall_side = 1.0 if tr["roll"] > 0 else -1.0
                    touching = sorted(self._touching)
                    self._recover_ok = False
                    super()._fall(f"gegen {touching[0]} gestoßen" if touching else "Gleichgewicht verloren")
            else:
                self._down_since = None
            return
        if up > STAND_UP and tr["z"] > 0.09:
            self._up_since = self._up_since if self._up_since is not None else self.t
            if self.t - self._up_since > 0.5:
                self._up_since = None
                self.fallen = False
                self._recover_ok = False
                self._recover_t0 = None
                self.powered = True
                self.enabled = True
                self.emit("recover", message="Steht wieder – von selbst, mit Pollens Policy")
        else:
            self._up_since = None

    def _fall(self, why: str) -> None:
        """Der einfache Simulator würde hier umkippen lassen – in der Physik entscheidet MuJoCo."""
        return

    def _watch_bumps(self) -> None:
        now = self.core.contacts_with_world()
        new = now - self._touching
        self._touching = now
        if new and self.t - self._last_bump > 1.0 and not self.fallen:
            self._last_bump = self.t
            what = sorted(new)[0]
            self.emit("bump", what=what, message=f"Angestoßen: {what}")

    def _watch_ruck(self, dt: float) -> None:
        """Erschütterung von außen: ein Ding, die Hand oder ein Möbel drückt plötzlich fester gegen sie. Gemessen wird
        der Anstieg der Kontaktkraft (N·s je Schritt), nicht die IMU – beim Gehen schlägt die genauso aus."""
        f, wer = self.core.fremdkraft()
        anstieg = (f - self._ruck_f) * dt
        self._ruck_f = f
        if anstieg >= RUCK_AB_NS:
            self.ruck_melden(anstieg / RUCK_VOLL_NS, _ruck_quelle(wer))

    def ruck_melden(self, staerke: float, quelle: str) -> None:
        """Für Oberfläche und Gamepad: `state.ruck` = {n, staerke 0…1, quelle}. Höchstens alle RUCK_ABSTAND_S,
        dazwischen zählt nur ein stärkerer. Geht nicht ins Ereignisprotokoll (sonst flutet es Claudes Lagebild)."""
        s = max(0.0, min(1.0, float(staerke)))
        alt = self._ruck
        if alt is not None and self.t - self._ruck_t < RUCK_ABSTAND_S and s <= alt["staerke"]:
            return
        self._ruck = {"n": (alt["n"] + 1) if alt else 1, "staerke": round(s, 2), "quelle": quelle}
        self._ruck_t = self.t

    # ── Skills: Ende und Sonderfälle ─────────────────────────────────────
    def _step_skill(self, dt: float) -> None:
        name = self.skill
        if name == "_recover" and self.fallen:
            self.skill_t += dt               # wartet, bis die Policy sie hochgebracht hat
            if self.skill_t > 8.0:
                self.skill = None
            return
        was_sitting = self.sitting
        super()._step_skill(dt)
        if name == "sit_toggle" and self.skill is None and was_sitting and not self.sitting:
            self._rise_until = self.t + 1.0  # Sitstand fertig aufstehen lassen
        if name == "_init" and self.skill is None:
            self._rise_until = self.t + 0.8

    async def init(self) -> IntentResult:
        if self.fallen:
            if not self.powered:
                return IntentResult(False, "liegt stromlos – erst Motoren an")
            self._recover_ok = True                  # jetzt richtet sie sich auf: Rampe, dann Pollens Policy
            self._recover_t0 = None
            return IntentResult(True, "steht gleich auf – erst in die Grundstellung, dann Pollens Policy")
        return await super().init()

    async def relax(self) -> IntentResult:
        """Not-Aus: stromlos wie robot.relax – die Gelenke werden weich (POWER_OFF_GAIN), sie fällt, wie sie fällt."""
        self._recover_ok = False
        self._recover_t0 = None
        self.requested = Twist()
        self.skill = None
        self.powered = self.enabled = False
        return IntentResult(True, "stromlos")

    async def stop(self) -> IntentResult:
        if self.fallen:                              # Not-Aus beim Aufrichten: wieder weich liegen bleiben
            self._recover_ok = False
            self._recover_t0 = None
        return await super().stop()

    # ── Kollisionsmodus (nur Physik-Simulator) ──────────────────────────
    def emit(self, kind: str, **data: Any) -> None:
        # Stürze, Anstoßen und Aufstehen kurz nach einem Stoß/Wurf im Kollisionsmodus sind Spiel: markieren,
        # damit Stimmung, Erfahrungsnetz und Pannen-Protokoll sie nicht als Ärgernis lernen
        if self.kollision_aktiv and kind in ("fall", "bump", "recover", "recover_fail") and self.t - self._last_reiz < 15.0:
            msg = str(data.get("message") or kind)
            data = {**data, "kollision": True, "message": f"{msg} (Spiel im Kollisionsmodus)"}
        super().emit(kind, **data)

    def kollision_an(self, on: bool) -> None:
        self.kollision_aktiv = bool(on)
        if not on:
            if self.episode is not None:
                self._episode_done(abgebrochen=True)
            self.kollision.parken()

    def kollision_reiz(self, art: str, fn: Any, **kw: Any) -> dict[str, Any]:
        """Einen Stoß, Wurf, Roll oder Zug ausführen und als Episode aufnehmen. art: stoss | wurf | rollen | zug | objekt."""
        from ..physics.kollision import KollisionsFehler

        if not self.kollision_aktiv:
            raise KollisionsFehler("Der Kollisionsmodus ist aus")
        res = fn(**kw)
        if art == "stoss":                           # der Stoß ist eine Kraft, kein Kontakt: direkt spüren
            self.ruck_melden(float(res.get("impuls_ns") or 0.0) / RUCK_STOSS_VOLL_NS, "Stoß")
        elif art == "zug":
            self.ruck_melden(0.15, "Zug")
        if art in ("stoss", "wurf", "rollen", "zug"):
            self._start_episode(art, {k: v for k, v in res.items() if k not in ("quat",)})
        return res

    def _start_episode(self, art: str, reiz: dict[str, Any]) -> None:
        from ..physics.kollision import Episode, zustand

        if self.episode is not None:
            self._episode_done(abgebrochen=True)
        tr = self.core.trunk()
        ep = Episode(art=art, reiz=reiz, t0=self.t, vorher=zustand(tr, self.fallen))
        c, sn = math.cos(tr["yaw"]), math.sin(tr["yaw"])
        ep._v0 = (tr["vx"] * c - tr["vy"] * sn, tr["vx"] * sn + tr["vy"] * c)
        self.episode = ep
        self._last_reiz = self.t

    def _watch_hand(self) -> None:
        """Berührt die Hand (oder was sie hält) die Ente: ein Reiz. Beginn einer Berührung = Episode „hand“
        (wenn gerade keine läuft); solange sie dran ist, gilt alles als Spiel (kein Ärger, keine Stimmung)."""
        k = self.kollision
        was = k.beruehrt
        kon = k.hand_kontakt()
        if kon is None:
            return
        self._last_reiz = self.t
        if not was and self.episode is None:
            v = k.hand_v
            self._start_episode("hand", {"geschwindigkeit": [round(float(x), 3) for x in v],
                                         "tempo": round(float(np.linalg.norm(v)), 3), **kon})

    def _episode_done(self, abgebrochen: bool = False) -> None:
        ep, self.episode = self.episode, None
        if ep is None:
            return
        if ep.nach is None:
            from ..physics.kollision import zustand

            ep.nach = zustand(self.core.trunk(), self.fallen)
            ep.ende = self.t
        if self.on_episode is not None:
            try:
                self.on_episode(ep.to_dict(abgebrochen))
            except Exception:
                log.exception("Episode speichern")

    async def haltung(self, gelenke: dict[str, float], sekunden: float) -> IntentResult:
        """Pose im Tanz: in 0,6 s anfahren (Stärke 0,8, ohne Policy), halten, zurück in die Grundstellung – dann
        übernimmt die Geh-Policy wieder. Nie liegend, schlaff, nach Not-Aus oder während eines Tricks."""
        import numpy as np

        from ..physics.core import ACTUATORS, DEFAULT_POSE

        if self.fallen or self.core.limp or not self.powered or self.skill or self.core.posing:
            return IntentResult(False, "Jetzt keine Pose – sie steht nicht ruhig")
        q = DEFAULT_POSE.astype(np.float32).copy()
        for i, n in enumerate(ACTUATORS):
            v = gelenke.get(n)
            if isinstance(v, (int, float)) and math.isfinite(v):
                q[i] = float(v)
        lo, hi = self.core.model.actuator_ctrlrange[:, 0], self.core.model.actuator_ctrlrange[:, 1]
        if np.all(hi > lo):
            q = np.clip(q, lo, hi).astype(np.float32)
        self.core.start_pose(POSE_S, ziel=q, halten=max(0.2, min(4.0, float(sekunden))))
        return IntentResult(True, "Pose")

    async def do(self, skill: str) -> IntentResult:
        if skill in DEFAULT_SKILLS and skill not in self.skills():
            role = "sitstand" if skill == "sit_toggle" else skill
            return IntentResult(False, f"Für „{skill}“ fehlt die Policy ({role}) im geladenen Satz.")
        if skill in self.tricks:
            self._skill_cfg = self._trick_cfg.get(skill, {})
            self.extra_skills[skill] = self._skill_len(skill)
        res = await super().do(skill)
        if res.accepted and skill in self.tricks:
            self.tricks[skill].reset()
        return res

    # ── Hub: Tricks und Gangarten ────────────────────────────────────────
    async def add_trick(self, repo: str, name: str | None = None, seconds: float | None = None,
                        file: str | None = None) -> IntentResult:
        try:
            info = await asyncio.to_thread(self.store.fetch_repo, repo.partition("@")[0], file)
            man = info["manifest"]
            if man.get("kind") == "perpetual" and not (seconds or man.get("duration_s")):
                return IntentResult(False, "Das ist eine Gangart, kein Trick – unter Gangarten laden.")
            enc = (man.get("command") or {}).get("encoding") or "constant"
            if enc != "constant":
                return IntentResult(False, f"Policy mit Befehlsart „{enc}“ lässt sich nicht als Trick abspielen.")
            pol = await asyncio.to_thread(Policy, info["pfad"], name or info["name"],
                                          float(man.get("action_scale") or ROBOT_ACTION_SCALE))
        except Exception as exc:
            return IntentResult(False, f"Laden fehlgeschlagen: {exc}")
        key = name or info["name"]
        cmd = man.get("command") or {}
        idle = cmd.get("idle") if isinstance(cmd.get("idle"), list) and len(cmd.get("idle")) >= 3 else None
        fenster = float(seconds or man.get("duration_s") or 3.0)
        unwind = max(0.0, float(man.get("unwind_s") or 0.0))
        self.tricks[key] = pol
        self._trick_len[key] = fenster + unwind
        self._trick_cfg[key] = {"befehl": None, "idle": idle, "fenster": fenster, "unwind_s": unwind,
                                "action_scale": man.get("action_scale")}
        self.extra_skills[key] = self._trick_len[key]
        return IntentResult(True, f"„{key}“ läuft jetzt im Physik-Simulator")

    async def load_gait(self, repo: str, slot: str = "walk", file: str | None = None) -> IntentResult:
        if slot != "walk":
            return IntentResult(False, "Im Simulator gibt es nur den Platz walk.")
        try:
            info = await asyncio.to_thread(self.store.fetch_repo, repo, file)
            pol = await asyncio.to_thread(Policy, info["pfad"], info["name"],
                                          float(info["manifest"].get("action_scale") or ROBOT_ACTION_SCALE))
        except Exception as exc:
            return IntentResult(False, f"Laden fehlgeschlagen: {exc}")
        self.gait_policy = pol
        return IntentResult(True, f"Gangart „{info['name']}“ läuft im Physik-Simulator")

    def add_local_policy(self, path: str, name: str, art: str, seconds: float = 3.0) -> str:
        """Eine selbst trainierte Policy (Ergebnis eines Trainingslaufs) einsetzen."""
        pol = Policy(path, name)
        from ..physics.isaaclab import lade_grenzen

        extra = lade_grenzen(path)                   # aus Isaac Lab übernommen (seit 0.38.27): Faktor und Grenzen
        if extra is not None:
            pol.action_scale = extra["action_scale"]
            pol.grenzen = extra["grenzen"]
        if art == "gangart":
            self.gait_policy = pol
            return f"Gangart „{name}“ läuft jetzt"
        if art == "platz":
            role = "sitstand" if "sitstand" in name.lower() else "ground_pick"
            self.policies[role] = pol
            return f"„{name}“ ersetzt {role}"
        self.tricks[name] = pol
        self._trick_len[name] = seconds
        self._trick_cfg[name] = {}
        self.extra_skills[name] = seconds
        return f"Trick „{name}“ bereit – „skill {name}“"

    def _ente_setzen(self, x: float, y: float, yaw: float) -> None:
        super()._ente_setzen(x, y, yaw)
        self.core.reset(x, y, yaw)                     # stehend in der Grundstellung, Gedächtnis der Policy von vorn
        for pol in [*self.policies.values(), *self.tricks.values()]:
            pol.reset()
        self._cmd_ema = None

    def eigenschaften(self) -> frozenset[str]:
        return super().eigenschaften() | {"policies", "physik"}

    def fassung(self, skill: str) -> dict[str, Any]:
        """Welche Policy läuft bei diesem Skill? (Für ehrliche Antworten – seit 0.37.14.)"""
        from ..physics.policies import ROLE_LABEL

        if skill in getattr(self, "eigene", {}):
            return {"fassung": f"deine selbst trainierte Fassung „{skill}“"}
        if skill in self.tricks:
            return {"fassung": f"Trick vom Hub „{skill}“"}
        out: dict[str, Any] = {"fassung": "Pollens Original-Policy (microduck-policies)"}
        label = ROLE_LABEL.get(skill)
        if label:
            slug = "eigen_" + re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")[:24]
            if slug in self.tricks:
                out["hinweis_fassung"] = (f"Es gibt eine selbst trainierte Fassung: skill {slug} – "
                                          f"„{skill}“ bleibt Pollens Original.")
        return out

    async def reset_gait(self, slot: str = "walk") -> IntentResult:
        self.gait_policy = None
        return IntentResult(True, "wieder Pollens VelStand")

    # ── Zustand ──────────────────────────────────────────────────────────
    def _joints(self) -> list[float]:
        j = self.core.joints()
        mouth = self.mouth_now
        return [j["left_hip_yaw"], j["left_hip_roll"], j["left_hip_pitch"], j["left_knee"], j["left_ankle"],
                j["neck_pitch"], j["head_pitch"], j["head_yaw"], j["head_roll"], mouth,
                j["right_hip_yaw"], j["right_hip_roll"], j["right_hip_pitch"], j["right_knee"], j["right_ankle"]]

    def _step_actuators(self, dt: float) -> None:
        super()._step_actuators(dt)
        # Kopf: was die Gelenke wirklich tun (für Tiefensensor und Anzeige)
        j = self.core.joints()
        self.head_now = Head(j["neck_pitch"] - 0.3491, j["head_pitch"] - 0.3491, j["head_yaw"], j["head_roll"])
        self.head_out = self.head_now              # in der Physik ist die gemessene Stellung schon mit Ausgleich

    def state(self) -> DuckState:
        st = super().state()
        st.body = [round(v, 4) for v in self._body]
        st.body_q = [round(v, 5) for v in getattr(self, "_body_q", [])]
        st.ruck = dict(self._ruck) if self._ruck else None
        st.physik = {
            "motor": self.core.motor_model,
            "policy": self.core.policy.name if self.core.policy else None,
            "gangart": self.gait_policy.name if self.gait_policy else None,
        }
        return st

    def joint_report(self) -> dict[str, Any]:
        from ..api import JOINT_NAMES
        from ..joints import build

        det = self.core.joint_detail()
        ist, soll, last = [], [], []
        for n in JOINT_NAMES:
            if n == "mouth":
                ist.append(self.mouth_now); soll.append(None); last.append(None)
                continue
            ist.append(det[n]["ist"]); soll.append(det[n]["soll"]); last.append(det[n]["last"])
        return build(ist, soll, last, quelle=f"Physik ({self.core.motor_model})",
                     aktiv=self.powered and not self.fallen)

    def reset_body(self) -> None:
        """Ente zurück auf die Füße an den Startplatz (z. B. nach Purzelbaum ins Regal)."""
        self.x, self.y, self.yaw = -0.6, -0.2, 0.0
        self.core.reset(self.x, self.y, self.yaw)
        self.kollision.held.clear()
        self.kollision._griff_aus()                          # mj_resetData schaltet die Welds ab, gravcomp nicht
        self.kollision.zug_ende()
        self.kollision.hand_aus()
        self.kollision.draussen = set(self.kollision.obj)   # mj_resetData parkt Ball und Würfel wieder
        self._recover_ok = False
        self.fallen = False
        self.sitting = False
        self.skill = None
        self.powered = self.enabled = True


def _ruck_quelle(geom: str | None) -> str:
    """Geom-Name → was es war, in Worten (für die Oberfläche)."""
    g = geom or ""
    if g.startswith("o:"):
        from ..physics.kollision import OBJEKTE

        return str(OBJEKTE.get(g[2:], {}).get("name", g[2:]))
    if g.startswith("h:"):
        return "Hand"
    if g.startswith("m:"):
        return g[2:]
    return "Wand" if g.startswith("wand") else "etwas"


def physics_available() -> tuple[bool, str]:
    import importlib.util

    for mod, label in (("mujoco", "MuJoCo"), ("onnxruntime", "ONNX Runtime"), ("numpy", "numpy")):
        if importlib.util.find_spec(mod) is None:
            return False, f"{label} ist nicht installiert"
    return True, ""


def store_for(root: Path) -> PolicyStore:
    return PolicyStore(root)
