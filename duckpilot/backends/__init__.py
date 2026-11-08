"""Körper der Ente: einfacher Simulator, Simulator mit echter Physik oder echter Roboter."""

import logging

log = logging.getLogger(__name__)


def build_backend(cfg):
    if getattr(cfg, "modul", "duckpilot") == "reachy_mini":        # zweites Modul der Suite (seit 0.38.1)
        from .reachy import ReachyMiniDaemon, ReachyMiniSim

        return ReachyMiniDaemon(cfg.reachy_adresse) if cfg.backend == "robotd" else ReachyMiniSim()
    if getattr(cfg, "modul", "duckpilot") == "open_duck_mini":    # drittes Modul (seit 0.38.4), nur Simulator
        from .open_duck import OpenDuckSim

        be = OpenDuckSim()
        if cfg.backend == "robotd":
            be.limited_by = ["Echte Open Duck: Anbindung an die Open-Duck-Runtime ist geplant – bis dahin der Simulator"]
        return be
    if cfg.backend == "sim":
        from .sim import SimBackend

        if getattr(cfg, "sim_physik", False):
            why = physics_problem()
            if not why:
                try:
                    from .. import settings as S
                    from ..physics.policies import PolicyStore
                    from .physics import PhysicsBackend

                    return PhysicsBackend(PolicyStore(S.settings_path().parent))
                except Exception as exc:  # Policy kaputt o. Ä.: lieber einfacher Simulator als gar nichts
                    log.warning("Physik-Simulator nicht startbar: %s", exc)
                    why = f"{type(exc).__name__}: {exc}"
            sim = SimBackend()
            sim.physics_problem = why
            return sim
        return SimBackend()
    if cfg.backend == "robotd":
        from .robotd import RobotdBackend

        return RobotdBackend(cfg.robot, tof=cfg.tof, head_signs=cfg.head_signs, updater=cfg.updater)
    raise ValueError(f"Unbekanntes Backend '{cfg.backend}' (sim | robotd)")


def physics_problem() -> str:
    """Leer, wenn der Physik-Simulator starten kann; sonst der Grund."""
    import importlib.util

    for mod, label in (("mujoco", "MuJoCo"), ("onnxruntime", "ONNX Runtime"), ("numpy", "numpy")):
        if importlib.util.find_spec(mod) is None:
            return f"{label} ist nicht installiert"
    from .. import settings as S
    from ..modell import ModellStore
    from ..physics.policies import PolicyStore

    if ModellStore(S.settings_path().parent).physics_path() is None:
        return "Pollens Robotermodell ist noch nicht geladen"
    if not PolicyStore(S.settings_path().parent).ready():
        return "Pollens Policies sind noch nicht geladen"
    return ""
