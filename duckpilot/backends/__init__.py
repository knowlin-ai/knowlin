"""Die Körper, die Knowlin mitbringt: Fabriken für die Profile aus `duckpilot.koerper`.

`build_backend(cfg)` baut den Körper aus der Einstellung `modul` über sein Profil (Körperschnittstelle 1.0, seit
0.38.35). Ein neuer eingebauter Körper bekommt hier eine Fabrik `baue_<name>(cfg)` und ein Profil in
`duckpilot/koerper.py`; fremde Körper kommen als eigenes Paket über den Entry Point `knowlin.koerper`.
"""

import logging

log = logging.getLogger(__name__)


def build_backend(cfg):
    from .. import koerper

    modul = getattr(cfg, "modul", "duckpilot") or "duckpilot"
    if cfg.backend not in ("sim", "robotd"):
        raise ValueError(f"Unbekanntes Backend '{cfg.backend}' (sim | robotd)")
    try:
        profil = koerper.holen(modul)
    except KeyError:
        log.warning("Körper „%s“ ist nicht (mehr) installiert – starte die Microduck", modul)
        profil = koerper.holen("duckpilot")
    return profil.bauen(cfg)


def baue_microduck(cfg):
    """Microduck: einfacher Simulator, Simulator mit echter Physik oder echter Roboter über robotd."""
    if cfg.backend == "robotd":
        from .robotd import RobotdBackend

        return RobotdBackend(cfg.robot, tof=cfg.tof, head_signs=cfg.head_signs, updater=cfg.updater)
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


def baue_reachy_mini(cfg):
    """Reachy Mini (seit 0.38.1): Simulator oder Pollens Daemon."""
    from .reachy import ReachyMiniDaemon, ReachyMiniSim

    return ReachyMiniDaemon(cfg.reachy_adresse) if cfg.backend == "robotd" else ReachyMiniSim()


def baue_open_duck(cfg):
    """Open Duck Mini v2 (seit 0.38.4): nur Simulator – die echte Anbindung an die Open-Duck-Runtime ist geplant."""
    from .open_duck import OpenDuckSim

    be = OpenDuckSim()
    if cfg.backend == "robotd":
        be.limited_by = ["Echte Open Duck: Anbindung an die Open-Duck-Runtime ist geplant – bis dahin der Simulator"]
    return be


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
