"""Akrobatik: die Ente als Gliederpuppe – hält sie das Gleichgewicht?

Du biegst die Gelenke, MuJoCo sagt, ob sie so stehen kann:

* **Sofort-Check (statisch):** Die Ente ruht flach auf dem Fuß, der unten ist (der Rumpf neigt sich dafür so,
  wie die Gelenke es vorgeben – sie hat kein seitliches Fußgelenk), der tiefste Punkt berührt den Boden. Alle Punkte der
  Kollisionsformen, die (fast) den Boden berühren, spannen die **Stützfläche** auf (konvexe Hülle). Liegt der
  **Schwerpunkt** senkrecht darüber, steht sie – der Abstand zum Rand ist die **Reserve**. Ampel:
  grün = Reserve ≥ 4 mm, gelb = knapp darüber, rot = Schwerpunkt außerhalb (sie kippt).
* **Probe (dynamisch):** Die Motoren halten die Stellung wie eine gute Regelung (steif, aber mit der echten
  Kraftgrenze des XL330 – Pollens weicher Firmware-Regler allein ließe sie einsacken), MuJoCo rechnet 2 Sekunden. Steht sie danach noch? Die Bilder kommen als kleine Animation zurück.
* **Üben:** Eine Übung (z. B. auf einem Bein stehen) wird mit dem Kreuzentropie-Verfahren verbessert: viele
  leicht veränderte Haltungen probieren, die besten behalten, um sie herum weitersuchen. Bewertet wird mit
  Stößen steigender Stärke – die **Fähigkeit** (0–100 %) sagt, wie viele davon sie in der Übung übersteht.

Wichtig: Das ist Simulation. Am echten Roboter nimmt robotd für die Beine nur Policies an – eine geübte
Haltung ist dort ein Trainingsziel, kein Befehl. Nur die Kopfgelenke lassen sich am Roboter direkt stellen.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Any, Callable

import mujoco
import numpy as np

from .core import ACTUATORS, DEFAULT_POSE, DT, PhysicsCore

HOLD_S = 2.0
FRAME_HZ = 20
CONTACT_MM = 3.0                  # so nah am Boden zählt ein Punkt zur Stützfläche
GREEN_MM, YELLOW_MM = 4.0, 0.0
LIFT_MM = 25.0                    # so hoch muss der freie Fuß sein, damit „auf einem Bein“ zählt
PUSHES_N = (0.0, 0.4, 0.8, 1.2, 1.6)   # Stoßstärken für die Fähigkeit (Rumpf, 0,1 s, Ente wiegt ≈ 0,74 kg)
LEG_JOINTS = [n for n in ACTUATORS if "hip" in n or "knee" in n or "ankle" in n]
HEAD_JOINTS = ["neck_pitch", "head_pitch", "head_yaw", "head_roll"]
# Solange jede Haltung schon ohne Stoß umfällt, ist die Fähigkeit überall 0 – die Suche tappte dann blind und fand
# „Auf einem Bein“ nur mit Glück (mit Pollens nachgeladenem Modell gar nicht, 9.11.). Wie lange sie steht, bevor sie
# fällt, gibt ihr die Richtung. Klein gegen die Fähigkeit (bis 100), damit die Rangfolge stehender Haltungen bleibt.
HALTEN_PUNKTE = 10.0
HOLD_KP, HOLD_KD = 4.0, 0.06      # Nm/rad, Nm·s/rad – Haltung wie eine Policy sie hält; Kraftgrenze bleibt echt


@dataclass(frozen=True)
class Exercise:
    id: str
    name: str
    beschreibung: str
    standbein: str | None = None          # "left"/"right": der andere Fuß muss in der Luft sein
    hocke: bool = False


EXERCISES = {e.id: e for e in (
    Exercise("frei", "Deine Haltung halten", "Die Haltung so wenig wie nötig verändern, bis sie Stöße aushält."),
    Exercise("links", "Auf dem linken Bein", "Rechter Fuß mindestens 2,5 cm in der Luft.", standbein="left"),
    Exercise("rechts", "Auf dem rechten Bein", "Linker Fuß mindestens 2,5 cm in der Luft.", standbein="right"),
    Exercise("hocke", "Tiefe Hocke", "Rumpf mindestens 2 cm tiefer als im Stehen – und dabei stabil.", hocke=True),
)}


def _hull(pts: np.ndarray) -> np.ndarray:
    """Konvexe Hülle (Andrew) der 2D-Punkte, gegen den Uhrzeigersinn."""
    pts = np.unique(np.round(pts, 5), axis=0)
    if len(pts) < 3:
        return pts
    pts = pts[np.lexsort((pts[:, 1], pts[:, 0]))]

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: list[np.ndarray] = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper: list[np.ndarray] = []
    for p in pts[::-1]:
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return np.array(lower[:-1] + upper[:-1])


def _seg_dist(p: np.ndarray, a: np.ndarray, b: np.ndarray) -> float:
    ab = b - a
    t = float(np.clip(np.dot(p - a, ab) / max(1e-12, np.dot(ab, ab)), 0.0, 1.0))
    return float(np.linalg.norm(p - (a + t * ab)))


def margin(com: np.ndarray, hull: np.ndarray) -> float:
    """Abstand des Schwerpunkts zum Rand der Stützfläche (m), positiv = innen."""
    if len(hull) == 0:
        return -1.0
    if len(hull) < 3:
        d = min(_seg_dist(com, hull[i], hull[(i + 1) % len(hull)]) for i in range(len(hull))) if len(hull) == 2 \
            else float(np.linalg.norm(com - hull[0]))
        return -d
    inside = True
    dist = math.inf
    for i in range(len(hull)):
        a, b = hull[i], hull[(i + 1) % len(hull)]
        if (b[0] - a[0]) * (com[1] - a[1]) - (b[1] - a[1]) * (com[0] - a[0]) < 0:
            inside = False
        dist = min(dist, _seg_dist(com, a, b))
    return dist if inside else -dist


class Acrobat:
    """Eigene, unsichtbare MuJoCo-Welt (nur Boden) – die Ente auf dem Bildschirm bleibt, wie sie ist."""

    def __init__(self) -> None:
        self.core = PhysicsCore(None, use_bam=False)
        m = self.core.model
        self.m, self.d = m, self.core.data
        m.actuator_gainprm[:, 0] = HOLD_KP
        m.actuator_biasprm[:, 1] = -HOLD_KP
        m.actuator_biasprm[:, 2] = -HOLD_KD
        self.lo = np.array([m.jnt_range[m.actuator_trnid[i, 0], 0] for i in range(m.nu)])
        self.hi = np.array([m.jnt_range[m.actuator_trnid[i, 0], 1] for i in range(m.nu)])
        limited = np.array([bool(m.jnt_limited[m.actuator_trnid[i, 0]]) for i in range(m.nu)])
        self.lo[~limited], self.hi[~limited] = -math.pi, math.pi
        self.geoms = [i for i in range(m.ngeom) if m.geom_bodyid[i] != 0 and (m.geom_contype[i] or m.geom_conaffinity[i])]
        self.foot_geom = {side: mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_GEOM, f"{side}_foot_collision")
                          for side in ("left", "right")}
        self.foot_body = {side: int(m.geom_bodyid[g]) for side, g in self.foot_geom.items()}
        self._verts = {}
        for g in self.geoms:
            if m.geom_type[g] == mujoco.mjtGeom.mjGEOM_MESH:
                mid = m.geom_dataid[g]
                a, n = m.mesh_vertadr[mid], m.mesh_vertnum[mid]
                v = m.mesh_vert[a:a + n]
                if len(v) > 400:                       # für die Stützfläche reicht eine Auswahl
                    v = v[np.linspace(0, len(v) - 1, 400).astype(int)]
                self._verts[g] = v.copy()
        self._set(DEFAULT_POSE.astype(float), 0.3)
        self.flat = {side: self.d.xmat[b].reshape(3, 3).copy() for side, b in self.foot_body.items()}
        self.stand_z = self.place(self.pose_from({}))["z"]

    # ── Haltung ──────────────────────────────────────────────────────────
    def pose_from(self, joints: dict[str, Any]) -> np.ndarray:
        q = DEFAULT_POSE.astype(float).copy()
        for i, n in enumerate(ACTUATORS):
            v = joints.get(n)
            if isinstance(v, (int, float)) and math.isfinite(v):
                q[i] = float(v)
        return np.clip(q, self.lo, self.hi)

    def as_dict(self, q: np.ndarray) -> dict[str, float]:
        return {n: round(float(q[i]), 4) for i, n in enumerate(ACTUATORS)}

    def _set(self, q: np.ndarray, z: float, quat: np.ndarray | None = None) -> None:
        d, c = self.d, self.core
        mujoco.mj_resetData(self.m, d)
        d.qpos[c.root_q:c.root_q + 3] = [0.0, 0.0, z]
        d.qpos[c.root_q + 3:c.root_q + 7] = [1, 0, 0, 0] if quat is None else quat
        for i, a in enumerate(c.qpos_idx):
            d.qpos[a] = q[i]
        d.ctrl[:] = q
        mujoco.mj_kinematics(self.m, d)

    def _world_verts(self, g: int) -> np.ndarray:
        d = self.d
        if g in self._verts:
            return d.geom_xpos[g] + self._verts[g] @ d.geom_xmat[g].reshape(3, 3).T
        return d.geom_xpos[g][None, :]

    def _level_on(self, q: np.ndarray, side: str) -> np.ndarray:
        """Rumpflage, bei der dieser Fuß flach aufliegt (Gieren bleibt null)."""
        self._set(q, 0.3)
        rf = self.d.xmat[self.foot_body[side]].reshape(3, 3)
        rt = self.flat[side] @ rf.T
        yaw = math.atan2(rt[1, 0], rt[0, 0])
        cz, sz = math.cos(-yaw), math.sin(-yaw)
        rt = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]]) @ rt
        quat = np.zeros(4)
        mujoco.mju_mat2Quat(quat, rt.ravel())
        return quat

    def _rest(self, q: np.ndarray, quat: np.ndarray) -> tuple[float, float]:
        """Mit dieser Rumpflage absenken, bis der tiefste Punkt den Boden berührt: (Höhe, tiefster Punkt)."""
        self._set(q, 0.3, quat)
        low = min(float(self._world_verts(g)[:, 2].min()) for g in self.geoms)
        return 0.3 - low, low

    def place(self, q: np.ndarray) -> dict[str, Any]:
        """Auf den unteren Fuß stellen (flach), tiefster Punkt auf dem Boden – dann das Gleichgewicht prüfen."""
        options = []
        for side in ("left", "right"):
            quat = self._level_on(q, side)
            z, _low = self._rest(q, quat)
            self._set(q, z, quat)
            foot_low = float(self._world_verts(self.foot_geom[side])[:, 2].min())
            tilt = 2 * math.acos(min(1.0, abs(float(quat[0]))))
            options.append((abs(foot_low) > 0.002, tilt, side, quat, z))   # gültig: dieser Fuß liegt unten
        options.sort(key=lambda o: (o[0], o[1]))
        _bad, _tilt, _side, quat, z = options[0]
        self._quat = quat
        self._set(q, z, quat)
        mujoco.mj_comPos(self.m, self.d)
        pts, feet_mm = [], {}
        for g in self.geoms:
            v = self._world_verts(g)
            near = v[v[:, 2] < CONTACT_MM / 1000]
            if len(near):
                pts.append(near[:, :2])
        for side, g in self.foot_geom.items():
            feet_mm[side] = round(float(self._world_verts(g)[:, 2].min()) * 1000, 1)
        hull = _hull(np.concatenate(pts)) if pts else np.zeros((0, 2))
        com3 = self.d.subtree_com[self.core.trunk_id].copy()
        com = com3[:2]
        w, x, y, zq = (float(v) for v in quat)
        roll = math.atan2(2 * (w * x + y * zq), 1 - 2 * (x * x + y * y))
        pitch = math.asin(max(-1.0, min(1.0, 2 * (w * y - zq * x))))
        mg = margin(com, hull)
        mm = mg * 1000
        ampel = "gruen" if mm >= GREEN_MM else "gelb" if mm >= YELLOW_MM else "rot"
        foot_only = set()
        for g in self.geoms:
            if g not in self.foot_geom.values() and float(self._world_verts(g)[:, 2].min()) < CONTACT_MM / 1000:
                foot_only.add(g)
        return {"z": round(z, 4), "quat": [round(float(v), 5) for v in quat], "rollen": round(roll, 4),
                "kippen": round(pitch, 4), "schwerpunkt_hoehe": round(float(com3[2]), 4),
                "schwerpunkt": [round(float(com[0]), 4), round(float(com[1]), 4)],
                "stuetzflaeche": [[round(float(x), 4), round(float(y), 4)] for x, y in hull],
                "reserve_mm": round(mm, 1), "ampel": ampel, "fuesse_mm": feet_mm,
                "nicht_nur_fuesse": bool(foot_only)}

    # ── Probe: die Motoren halten die Stellung, MuJoCo rechnet ──────────
    def hold(self, q: np.ndarray, seconds: float = HOLD_S, push: tuple[float, float] | None = None,
             frames: bool = True) -> dict[str, Any]:
        st = self.place(q)
        self._set(q, st["z"] + 0.001, self._quat)
        d, c = self.d, self.core
        n = int(seconds / DT)
        every = max(1, int(1 / (FRAME_HZ * DT)))
        push_at = (int(0.5 / DT), int(0.6 / DT))
        out, tilt_max, fell_at = [], 0.0, None
        lifted = {"left": 1e9, "right": 1e9}
        z_sum, z_n = 0.0, 0
        for k in range(n):
            if push is not None and push_at[0] <= k < push_at[1]:
                d.xfrc_applied[c.trunk_id, :2] = push
            else:
                d.xfrc_applied[c.trunk_id, :] = 0
            mujoco.mj_step(self.m, d)
            w, x, y, _z = d.qpos[c.root_q + 3:c.root_q + 7]
            up = 1 - 2 * (x * x + y * y)
            tilt = math.acos(max(-1.0, min(1.0, up)))
            tilt_max = max(tilt_max, tilt)
            if fell_at is None and (tilt > 0.6 or d.qpos[c.root_q + 2] < 0.04):
                fell_at = round(k * DT, 2)
            if k > int(0.3 / DT):
                for side, g in self.foot_geom.items():
                    lifted[side] = min(lifted[side], float(self._world_verts(g)[:, 2].min()))
                z_sum += float(d.qpos[c.root_q + 2])
                z_n += 1
            if frames and k % every == 0:
                tr = c.trunk()
                j = c.joints()
                out.append({"t": round(k * DT, 2), "x": round(tr["x"], 4), "y": round(tr["y"], 4),
                            "yaw": round(tr["yaw"], 4), "body": [round(tr["z"], 4), round(tr["roll"], 4),
                                                                   round(tr["pitch"], 4)],
                            "joints": [round(j[nm], 4) for nm in ACTUATORS]})
        drift = math.hypot(float(d.qpos[c.root_q]), float(d.qpos[c.root_q + 1]))
        return {"steht": fell_at is None, "faellt_nach_s": fell_at, "kippen_max_grad": round(math.degrees(tilt_max), 1),
                "rutscht_mm": round(drift * 1000, 1), "fuss_hoch_mm": {s: round(v * 1000, 1) for s, v in lifted.items()},
                "rumpf_z": round(z_sum / max(1, z_n), 4), "bilder": out, "statisch": st}

    # ── Übung bewerten ───────────────────────────────────────────────────
    def skill(self, q: np.ndarray, ex: Exercise, rng: np.random.Generator | None = None) -> dict[str, Any]:
        """Fähigkeit 0–100 %: Wie viele Stöße steigender Stärke übersteht sie und erfüllt dabei die Übung?"""
        rng = rng or np.random.default_rng(0)
        ok, tilt, detail, haelt = 0.0, 0.0, [], HOLD_S
        for f in PUSHES_N:
            ang = rng.uniform(0, 2 * math.pi)
            r = self.hold(q, push=(f * math.cos(ang), f * math.sin(ang)) if f else None, frames=False)
            if f == 0.0 and r["faellt_nach_s"] is not None:
                haelt = float(r["faellt_nach_s"])
            goal = goal_met(r, ex, self.stand_z)
            if r["steht"] and goal:
                ok += 1.0
            elif r["steht"]:
                ok += 0.3                        # steht, aber die Übung ist nicht erfüllt
            tilt += r["kippen_max_grad"]
            detail.append({"stoss_n": f, "steht": r["steht"], "uebung_erfuellt": goal})
            if not r["steht"] and f == 0.0:
                break                            # fällt schon ohne Stoß: der Rest lohnt nicht
        score = 100.0 * ok / len(PUSHES_N) - 0.15 * tilt / len(PUSHES_N)
        return {"faehigkeit": round(max(0.0, min(100.0, score)), 1), "versuche": detail, "haelt_s": haelt}

    def practice(self, start: np.ndarray, ex: Exercise, generations: int = 10, samples: int = 14,
                 on_step: Callable[[dict[str, Any]], None] | None = None, seed: int = 1,
                 stop: Callable[[], bool] | None = None) -> dict[str, Any]:
        """Kreuzentropie-Suche um die Starthaltung – Beine und Kopf (der Kopf ist ihr Balancier-Arm)."""
        rng = np.random.default_rng(seed)
        free = [ACTUATORS.index(n) for n in LEG_JOINTS + HEAD_JOINTS]
        mean = template(start, ex, self)
        sigma = np.full(len(free), 0.10)
        best_q, best = mean.copy(), self._objective(mean, ex, start, rng)
        history = [{"generation": 0, "faehigkeit": best["faehigkeit"]}]
        if on_step:
            on_step({"generation": 0, "von": generations, "faehigkeit": best["faehigkeit"], "pose": self.as_dict(best_q)})
        t0 = time.perf_counter()
        for gen in range(1, generations + 1):
            if stop and stop():
                break
            cands = []
            for _ in range(samples):
                q = mean.copy()
                q[free] += rng.normal(0, sigma)
                q = np.clip(q, self.lo, self.hi)
                cands.append((self._objective(q, ex, start, rng), q))
            cands.sort(key=lambda c: c[0]["wert"], reverse=True)
            elite = np.array([c[1] for c in cands[:4]])
            mean = elite.mean(axis=0)
            sigma = np.maximum(0.015, 0.7 * sigma + 0.3 * elite[:, free].std(axis=0))
            if cands[0][0]["wert"] > best["wert"]:
                best, best_q = cands[0][0], cands[0][1].copy()
            history.append({"generation": gen, "faehigkeit": best["faehigkeit"]})
            if on_step:
                on_step({"generation": gen, "von": generations, "faehigkeit": best["faehigkeit"],
                         "pose": self.as_dict(best_q)})
        final = self.hold(best_q)
        return {"uebung": ex.id, "pose": self.as_dict(best_q), "faehigkeit": best["faehigkeit"],
                "verlauf": history, "probe": final, "sekunden": round(time.perf_counter() - t0, 1)}

    def _objective(self, q: np.ndarray, ex: Exercise, start: np.ndarray, rng: np.random.Generator) -> dict[str, Any]:
        s = self.skill(q, ex, np.random.default_rng(int(rng.integers(1 << 30))))
        change = float(np.abs(q - start).sum())
        weight = 6.0 if ex.id == "frei" else 1.0             # „Deine Haltung“: so nah wie möglich an deiner
        st = self.place(q)
        return {"faehigkeit": s["faehigkeit"],
                "wert": s["faehigkeit"] - weight * change + 0.5 * max(-10.0, min(10.0, st["reserve_mm"]))
                + HALTEN_PUNKTE * s["haelt_s"] / HOLD_S}


def goal_met(r: dict[str, Any], ex: Exercise, stand_z: float) -> bool:
    if ex.standbein:
        other = "right" if ex.standbein == "left" else "left"
        return r["fuss_hoch_mm"][other] >= LIFT_MM and r["fuss_hoch_mm"][ex.standbein] < CONTACT_MM + 2
    if ex.hocke:
        return r["rumpf_z"] <= stand_z - 0.02
    return True


def template(start: np.ndarray, ex: Exercise, acro: Acrobat) -> np.ndarray:
    """Erfüllt die Starthaltung die Übung nicht, mit einer groben Vorlage beginnen (z. B. Bein anheben)."""
    q = start.copy()
    if ex.standbein:
        other = "right" if ex.standbein == "left" else "left"
        if acro.place(q)["fuesse_mm"][other] >= LIFT_MM:
            return q
        # Jede Art, das freie Bein zu heben (Hüfte vor/zurück, Knie gebeugt), wird statisch unter den Schwerpunkt
        # gerückt: Standbein seitlich (Hüfte rollen), beide Hüften gedreht. Welche Vorlage gewinnt, entscheidet die
        # Probe – wie lange sie wirklich steht. Früher nur die statische Reserve: Unterschiede von 1 mm entschieden,
        # mit Pollens nachgeladenem Modell gewann ein nach vorn gestrecktes Bein, und das Üben blieb bei 0 % (9.11.).
        best: tuple[float, np.ndarray] | None = None
        for hip in np.linspace(-1.2, 1.2, 13):
            for knee in np.linspace(-1.6, 1.6, 9):
                t = q.copy()
                t[ACTUATORS.index(f"{other}_hip_pitch")] += hip
                t[ACTUATORS.index(f"{other}_knee")] += knee
                t = np.clip(t, acro.lo, acro.hi)
                if acro.place(t)["fuesse_mm"][other] < LIFT_MM + 5:
                    continue
                t = _best_static(acro, t, f"{ex.standbein}_hip_roll", np.linspace(-0.6, 0.6, 13))
                t = _best_static(acro, t, f"{ex.standbein}_hip_yaw", np.linspace(-0.5, 0.5, 11))
                t = _best_static(acro, t, f"{other}_hip_yaw", np.linspace(-0.5, 0.5, 11))
                if acro.place(t)["fuesse_mm"][other] < LIFT_MM + 5:
                    continue
                r = acro.hold(t, frames=False)
                score = (HOLD_S if r["faellt_nach_s"] is None else r["faellt_nach_s"]) \
                    + (1.0 if r["steht"] and goal_met(r, ex, acro.stand_z) else 0.0)
                if best is None or score > best[0]:
                    best = (score, t)
        return q if best is None else best[1]
    if ex.hocke and acro.place(q)["z"] > acro.stand_z - 0.02:
        for i, n in enumerate(ACTUATORS):
            if n.endswith("knee") or n.endswith("hip_pitch") or n.endswith("ankle"):
                q[i] = DEFAULT_POSE[i] * 1.8
        return np.clip(q, acro.lo, acro.hi)
    return q


def _best_static(acro: Acrobat, q: np.ndarray, joint: str, deltas: np.ndarray) -> np.ndarray:
    """Dieses Gelenk so verstellen, dass die statische Reserve am größten ist."""
    i = ACTUATORS.index(joint)
    cand = [(acro.place(np.clip(_with(q, i, d), acro.lo, acro.hi))["reserve_mm"], d) for d in deltas]
    return np.clip(_with(q, i, max(cand)[1]), acro.lo, acro.hi)


def _with(q: np.ndarray, i: int, delta: float) -> np.ndarray:
    t = q.copy()
    t[i] += delta
    return t
