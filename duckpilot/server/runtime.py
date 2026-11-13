"""Laufzeit von duckpilot: Körper, Engine, Claude, Stimme, Training … und was die Oberfläche davon sieht."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from pathlib import Path
from typing import Any, Callable

from fastapi import WebSocket

from .. import __version__, i18n, koerper
from .. import remote as R
from .. import settings as S
from ..aio import spawn
from ..api import DuckBackend, Head, Twist
from ..backends import build_backend
from ..brain.agent import AgentConfig, DuckAgent
from ..brain.tools import ToolRunner
from ..config import Config
from ..figuren import FIGUR_KEYS, FigurenStore, start_ergaenzen
from ..motion.engine import EngineConfig, MotionEngine
from .plans import _plans_from  # noqa: F401  (auch von hier importierbar, wie bisher)
from .runtime_eigenstaendig import EigenstaendigTeil
from .runtime_gespraech import GespraechTeil
from .runtime_kern import VOICE_KEYS, KernTeil, _json_default
from .runtime_lab import LabTeil
from .runtime_reachy import PollenAdapter, ReachyTeil

log = logging.getLogger(__name__)
STATIC = Path(__file__).parent / "static"

AGENT_KEYS = {"model", "duck_name", "gehirn", "lokal_modell", "lokal_adresse", "sprache", "anbieter", "anbieter_modell",
              "anbieter_adresse", "lokal_programm", "lmstudio_modell", "lmstudio_adresse"}


def gehirn_fuer_agent(cfg: Any) -> dict[str, Any]:
    """Welches Gehirn der Agent bekommt. LM Studio steht seit 0.38.41 unter „Lokales Modell“, spricht aber dieselbe
    Schnittstelle wie die anderen Anbieter – der Agent bekommt es deshalb als Anbieter „lmstudio“ mit eigenen Feldern."""
    if cfg.gehirn == "lokal" and getattr(cfg, "lokal_programm", "ollama") == "lmstudio":
        return {"gehirn": "anbieter", "anbieter": "lmstudio", "anbieter_modell": cfg.lmstudio_modell,
                "anbieter_adresse": cfg.lmstudio_adresse, "anbieter_schluessel": None}
    return {"gehirn": cfg.gehirn, "anbieter": cfg.anbieter, "anbieter_modell": cfg.anbieter_modell,
            "anbieter_adresse": cfg.anbieter_adresse,
            "anbieter_schluessel": S.get_anbieter_key(cfg.anbieter) if cfg.gehirn == "anbieter" else None}
LIVE_AGENT_KEYS = {"plaudern", "entenlaute", "schnellbefehle"}          # gelten ab der nächsten Antwort, Verlauf bleibt
ENGINE_KEYS = {"idle_life", "obstacle_guard", "ausweichen", "auto_recover", "stopp_fenster_s", "humor", "energie", "emotions",
               "notaus_sperre_s", "notaus_danach"}
BODY_KEYS = {"backend", "robot", "tof", "head_signs", "updater", "sim_physik", "modul", "reachy_adresse", "koerper_optionen"}


class _KaggleSource:
    """Fertige Kaggle-Läufe als Policy für den Parcours-Test."""

    def __init__(self, kaggle) -> None:
        self.kaggle = kaggle

    def sources(self) -> list[dict[str, Any]]:
        from ..training import TASKS

        out = []
        for r in self.kaggle.runs()[::-1]:
            t = TASKS.get(r["plan"]["aufgabe"], {})
            if r.get("status") == "fertig" and t.get("art") == "gangart":
                out.append({"id": f"kaggle:{r['id']}", "name": f"Kaggle {r.get('start', '')} – {t.get('name', '')} (kostenlos)"})
        return out

    def resolve(self, quelle: str):
        if not quelle.startswith("kaggle:"):
            return None
        rid = quelle[7:]
        run = next((r for r in self.kaggle.runs() if r["id"] == rid), None)
        if run is None or run.get("status") != "fertig":
            raise ValueError("Dieser Kaggle-Lauf ist nicht fertig.")
        path = run.get("onnx")
        if not path or not Path(path).exists():
            path = str(self.kaggle.result(rid))
        return path, 1.0, f"Kaggle {run.get('start', '')}"


class _LocalSource:
    """Am PC selbst gelernte Policies für den Parcours-Test („lokal:<name>“)."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def sources(self) -> list[dict[str, Any]]:
        from ..physics import lernen as L

        return [{"id": m["id"], "name": f"Am PC gelernt: {m.get('name', '')} ({m.get('erstellt', '')}, kostenlos)"}
                for m in L.ergebnisse(self.root)]

    def resolve(self, quelle: str):
        if not quelle.startswith("lokal:"):
            return None
        from ..physics import lernen as L

        path, scale, label = L.aufloesen(self.root, quelle)
        return str(path), scale, label


class Runtime(KernTeil, LabTeil, ReachyTeil, EigenstaendigTeil, GespraechTeil):
    """Hält alles zusammen: Körper, Engine, Gedächtnis, Gehirn, Browser-Verbindungen."""

    def __init__(self, config: Config, backend: DuckBackend | None = None) -> None:
        self.config = config
        i18n.setze_sprache(config.sprache)
        try:                                                    # einmalig: Verkörperungen aus der Zeit vor 0.38.3 richten
            repariert = FigurenStore(S.settings_path().parent).reparieren(
                config.modul, {k: getattr(config, k) for k in FIGUR_KEYS if hasattr(config, k)})
            if repariert:
                for k, v in S.save_user_settings(repariert).items():
                    setattr(config, k, v)
            fehlt = start_ergaenzen(config.modul, S.load_user_settings())   # frisch mit Reachy/Open Duck: nicht „Quacki“
            if fehlt:
                for k, v in S.save_user_settings(fehlt).items():
                    setattr(config, k, v)
        except Exception as exc:
            log.warning("Verkörperungen reparieren: %s", exc)
        self._allein_starten()
        self.backend = backend or build_backend(config)
        self.memory = None
        if config.memory:
            self._open_memory()
        self.clients: set[WebSocket] = set()
        self.ws_extra: dict[str, Callable[[dict[str, Any]], Any]] = {}   # weitere Nachrichtenarten (Kollisionsmodus)
        self.chat_lock = asyncio.Lock()
        self.kopf_lock = asyncio.Lock()
        self.reconfig_lock = asyncio.Lock()
        self.stt = None
        self._setup_stt()
        self._tasks: list[asyncio.Task] = []
        self.on_idle_exit: Callable[[], None] | None = None   # App-Modus: Fenster zu → beenden
        self.keep_open = False          # „Im Hintergrund weiterlaufen“ gewählt: Fenster zu beendet nicht
        self.restart = False            # nach dem Beenden neu starten (neue Version)
        self.update_ready: str | None = None
        from ..aktualisieren import Aktualisierer  # Updates aus dem Netz (seit 0.38.32)

        self.aktualisierer = Aktualisierer(S.settings_path().parent)
        self.remote = R.RemoteAccess(S.settings_path().parent / "fernzugang.json")
        self.remote_listener = R.RemoteListener()
        self.app: Any = None                                  # die FastAPI-App (für den Handy-Zugang)
        self._had_client = False
        self._empty_since: float | None = None
        self.started_at = time.time()
        from ..skills import SkillManager

        self.skills = SkillManager(self)
        self.gait: str | None = None      # am Roboter geladene Gangart (nur diese Sitzung)
        from ..voice.describe import to_english
        from ..voice.install import Installer
        from ..voice.speech import Speaker

        self.speaker = Speaker(S.settings_path().parent, self.config, on_change=self._voice_changed)
        # Stimmbeschreibung auf Deutsch → Englisch fürs Modell (Claude, sonst lokales Modell); Agent zur Laufzeit holen
        self.speaker.translator = lambda text: to_english(text, getattr(self, "agent", None))
        self.installer = Installer(on_change=self._voice_changed)
        self.pulls: dict[str, dict[str, Any]] = {}       # Ollama-Modelle, die gerade laden
        self.physik_job: dict[str, Any] = {}
        from ..modell import ModellStore

        self.modell = ModellStore(S.settings_path().parent)    # Pollens Robotermodell (von GitHub nachgeladen)
        self._reachy_einrichten()                               # Reachy Mini: Pollens Modell und Bewegungen (0.38.2)
        self.figuren = FigurenStore(S.settings_path().parent)  # Verkörperungen je Körper (seit 0.38.3)
        # Kopf zuerst (seit 0.38.4, Wunsch des Maintainers „am Anfang wirklich nur im Hirn“): Knowlin startet ohne wachen
        # Körper – erst wenn jemand eine Verkörperung betritt (Fenster, Handy, Direktstart), wacht sie auf
        self.im_koerper = False
        from ..acrobatics_service import AcrobaticsService
        from ..buddy import Planner
        from ..care import RobotCare
        from ..skills.alltag import AlltagService
        from ..training import Trainer
        from ..vision import Camera

        self.alltag = AlltagService(self, Planner(S.settings_path().parent / "alltag.json"))

        self.camera = Camera(None, S.settings_path().parent)
        from ..brain.usage import UsageMeter
        from ..laser import LaserWatch

        self.usage = UsageMeter(S.data_dir() / "verbrauch.json")
        from ..nfc import TagStore

        self.nfc = TagStore(S.settings_path().parent / "nfc_tags.json")

        self.laser_watch = LaserWatch()
        from ..augen import Eyes
        from ..faces import Faces

        self.eyes = Eyes(self)
        self.faces = Faces(S.settings_path().parent)
        self._greeted: dict[str, float] = {}
        self.acro = AcrobaticsService(S.settings_path().parent)
        self.care = RobotCare(self.config)
        self.trainer = Trainer(S.settings_path().parent)
        from ..kaggle_training import KaggleTrainer

        self.kaggle = KaggleTrainer(S.settings_path().parent)
        self.kaggle_job: dict[str, Any] = {}
        self.training_job: dict[str, Any] = {}
        from ..mission import CourseLab
        from ..physics.policies import PolicyStore
        from ..training import get_token

        root = S.settings_path().parent
        self.lab = CourseLab(root, lambda: PolicyStore(root), self.trainer, on_change=self._lab_changed,
                             note=lambda e: self.engine.note(e), token=get_token)
        self.lab.providers = [_KaggleSource(self.kaggle), _LocalSource(root)]
        from ..lernschleife import LearnLoop
        from ..physics.lernen import LocalTrainer

        self.local = LocalTrainer(root)
        self.lernen = LearnLoop(self.local, self.lab, self._lernen_changed, self._duck_says,
                                note=lambda e: self.engine.note(e))
        self._lernen_push: asyncio.TimerHandle | None = None
        self._lab_push: asyncio.TimerHandle | None = None
        self._gpus: list[str] | None = None
        self._voice_push: asyncio.TimerHandle | None = None
        from ..erfahrung_service import ErfahrungService

        self.erfahrung = ErfahrungService(self)
        from .sicherung import SicherungService

        self.sicherung = SicherungService(self)                 # Sicherungspunkte (seit 0.38.24)
        self._wire()

    # ── Aufbau ────────────────────────────────────────────────────────────
    def _open_memory(self) -> None:
        from ..brain.memory import Memory

        self.memory = Memory(self.config.memory_path)
        self.memory.listeners.append(self._on_memory)
        self.memory.set_figur(self.config.modul)          # Tricks der Verkörperung, die gerade einen Körper hat
        # wer etwas gemerkt hat (seit 0.38.10) – im Gespräch mit dem Kopf setzt `_kopf_antwortet` „kopf“
        self.memory.herkunft = lambda: f"{self.config.modul}:{'sim' if self.config.backend == 'sim' else 'echt'}"

    def _setup_stt(self) -> None:
        self.stt = None
        if self.config.stt == "whisper":
            from ..voice.whisper_stt import WhisperSTT

            if WhisperSTT.available():
                self.stt = WhisperSTT(self.config.whisper_model, self.config.whisper_device,
                                      language=self.config.sprache)
                self.stt.warm_up()
            else:
                log.warning("stt = whisper, aber faster-whisper ist nicht installiert – nutze Browser-Erkennung")

    def _wire(self) -> None:
        cfg = self.config
        self.engine = MotionEngine(self.backend, EngineConfig(
            idle_life=cfg.idle_life, obstacle_guard=cfg.obstacle_guard, ausweichen=cfg.ausweichen,
            auto_recover=cfg.auto_recover, notaus_sperre_s=cfg.notaus_sperre_s, notaus_danach=cfg.notaus_danach,
            humor=cfg.humor, energie=cfg.energie, emotions=cfg.emotions, recover_delay=cfg.stopp_fenster_s,
        ))
        self.engine.listeners.append(self._on_event)
        self.backend.set_stabilize(cfg.kopf_stabil)
        self._schwarm()
        self._new_runner()

    def _new_runner(self) -> None:
        self.runner = ToolRunner(self.engine, self.memory)
        self.runner.packs = self.skills
        self.runner.trainer = getattr(self, "trainer", None)
        from ..choreo import ChoreoBuch

        self.choreos = ChoreoBuch(S.settings_path().parent)
        self.runner.choreos = self.choreos
        # Tanzposen nur so stark, wie sie in der Physik sicher stehen (seit 0.38.42)
        self.runner.gedanken = self.gedanken     # Absichten mit Ersatz oder Nein in die Gedankenspur (seit 0.38.44)
        self.runner.posen = lambda: (self.acro.tanzposen() if getattr(self, "acro", None) is not None else {})
        self.runner.on_musik = lambda datei, ab=0.0: spawn(self.broadcast({"type": "musik", "datei": datei, "ab": ab}))
        self.runner.on_choreo = lambda name: spawn(self.broadcast({"type": "choreo", "name": name}))
        self.runner.schwarm = getattr(self, "schwarm", None)
        self.runner.raum = self.raum
        self.runner.pollen = PollenAdapter(self)
        self.runner.free_training = self.free_training
        self._wire_practice()
        self.runner.on_setting = self._setting_from_duck
        self.runner.on_trick = self.add_trick
        self._new_agent()

    def koerper(self) -> str:
        """sim | physik | robotd – für die Oberfläche (was kann hier laufen?); Reachy Mini: reachy_sim | reachy;
        Open Duck Mini: open_duck_sim."""
        if getattr(self.backend, "koerper_art", "") == "open_duck_mini":
            return "open_duck_sim"
        if getattr(self.backend, "koerper_art", "") == "reachy_mini":
            return "reachy_sim" if self.backend.state().backend == "sim" else "reachy"
        st = self.backend.state().backend or self.config.backend
        return "physik" if st == "sim" and getattr(self.backend, "runs_policies", False) else st

    @property
    def raum(self):
        """Sichtungen und Karte (seit 0.37) – je Körper; wechselt der Körper, wird das alte gespeichert."""
        k = self.koerper()
        alt = getattr(self, "_raum", None)
        if alt is None or alt.koerper != k:
            from .raum import Raum

            if alt is not None:
                alt.kartieren_stopp()
            self._raum = Raum(S.settings_path().parent, k)
            if getattr(self, "runner", None) is not None:
                self.runner.raum = self._raum
        return self._raum

    def _allein_starten(self) -> None:
        """Jeder Start beginnt mit einer Ente (0.38.24, Hinweis „beim Öffnen waren direkt mehrere – per Default
        starten wir erstmal mit einer“): weitere Enten gelten bis zum Beenden, danach wieder null."""
        try:                                                   # auch gespeicherte Zahlen in den Profilen der Verkörperungen
            from ..figuren import FIGUREN

            store = FigurenStore(S.settings_path().parent)
            for modul in FIGUREN:
                if store.profil(modul).get("weitere_enten"):
                    store.setze(modul, {"weitere_enten": 0})
        except Exception as exc:
            log.warning("weitere Enten in den Profilen zurücksetzen: %s", exc)
        if not getattr(self.config, "weitere_enten", 0):
            return
        try:
            for k, v in S.save_user_settings({"weitere_enten": 0}).items():
                setattr(self.config, k, v)
        except Exception as exc:
            log.warning("weitere Enten zurücksetzen: %s", exc)
            self.config.weitere_enten = 0

    def _schwarm(self) -> None:
        """Weitere Enten (seit 0.36.3) – nur im einfachen Simulator; in der Physik und am Roboter gibt es eine Ente."""
        from ..backends.sim import SimBackend

        self.schwarm = None
        b = self.backend
        if not isinstance(b, SimBackend) or getattr(b, "runs_policies", False):
            return
        from ..backends.begleiter import Begleitente
        from ..motion.schwarm import Schwarm

        self.schwarm = Schwarm(b, self.engine, lambda i, x, y, yaw: Begleitente(b.world_model, i, x, y, yaw))
        b.nach_schritt.append(self.schwarm.step)
        self.schwarm.anzahl(self.config.weitere_enten if self.im_koerper else 0)   # im Kopf: niemand im Zimmer

    def _wire_practice(self) -> None:
        """Üben in der Physik anbieten, sobald MuJoCo und Pollens Policies da sind."""
        from ..backends import physics_problem
        from ..physics.policies import PolicyStore

        try:
            ok = not physics_problem()
        except Exception:
            ok = False
        self.runner.practice = PolicyStore(S.settings_path().parent) if ok else None
        self.runner.lab = getattr(self, "lab", None) if ok else None

    def _new_agent(self) -> None:
        cfg = self.config
        self.agent = DuckAgent(self.runner, AgentConfig(
            api_key=cfg.api_key, model=cfg.model, duck_name=cfg.duck_name, plaudern=cfg.plaudern,
            entenlaute=cfg.entenlaute, lokal_modell=cfg.lokal_modell, lokal_adresse=cfg.lokal_adresse,
            schnellbefehle=cfg.schnellbefehle, sprache=cfg.sprache, **gehirn_fuer_agent(cfg),
            andere_figuren=tuple(f"{f['name']} ({f['art']})" for m, f in self.figuren.alle(cfg.modul, {}).items()
                                 if m != cfg.modul),
        ))
        self.agent.usage = self.usage
        self.agent.erfahrung = self.erfahrung.context
        from ..figuren import gestalt_text

        self.agent.gestalt = lambda: gestalt_text(self.config.modul, self.config.eigenschaften)   # seit 0.38.10
        from ..brain.kopf import KopfAgent

        # Knowlin ohne Körper auf der Startseite (0.38.8); Namen im Gespräch vergeben (0.38.9)
        self.kopf = KopfAgent(self.agent, self.kopf_figuren, einstellen=self.apply_settings,
                              namen=lambda: (self.config.kopf_name, self.config.nutzer_name),
                              charakter=lambda: (self.config.grund_energie, self.config.grund_humor))

    def gestalt_liste(self) -> list[dict[str, Any]]:
        from ..figuren import GESTALT, gestalt_standard

        an = self.config.eigenschaften
        an = gestalt_standard(self.config.modul) if an is None else an
        return [{"id": e["id"], "name": e["name"], "text": e["text"], "an": e["id"] in an}
                for e in GESTALT.get(self.config.modul, [])]

    def kopf_figuren(self) -> list[dict[str, Any]]:
        """Die Verkörperungen für den Kopf: Name, Körper, Ausprägung (Temperament, Humor), ob sie zuletzt einen Körper
        hatte und ob sie gerade wach ist."""
        cfg = self.config
        jetzt = {"duck_name": cfg.duck_name, "energie": cfg.energie, "humor": cfg.humor}
        return [{"modul": m, "name": f["name"], "art": f["art"], "aktiv": f["aktiv"], "energie": f["energie"],
                 "humor": f["humor"], "wach": f["aktiv"] and self.im_koerper}
                for m, f in self.figuren.alle(cfg.modul, jetzt).items()]

    async def start(self) -> None:
        await self.backend.connect()
        await self.engine.start()
        self._tasks.append(asyncio.create_task(self._push_state(), name="push-state"))
        self._tasks.append(asyncio.create_task(self._aufzeichnen(), name="fehlerbericht"))
        self._tasks.append(asyncio.create_task(self._watch_clients(), name="watch-clients"))
        self._tasks.append(asyncio.create_task(self._watch_training(), name="watch-training"))
        self._tasks.append(asyncio.create_task(self._watch_people(), name="watch-people"))
        self._tasks.append(asyncio.create_task(self._watch_update(), name="watch-update"))
        self._tasks.append(asyncio.create_task(self._watch_online_update(), name="watch-online-update"))
        self._tasks.append(asyncio.create_task(self.laser_watch.run(self), name="watch-laser"))
        self._tasks.append(asyncio.create_task(self.erfahrung.run(), name="erfahrungsnetz"))
        if self.modell.missing():
            self._tasks.append(asyncio.create_task(self.load_modell(), name="pollen-modell"))
        self.reachy_beim_zuweisen()
        self._tasks.append(asyncio.create_task(self._reachy_leerlauf(), name="reachy-leerlauf"))
        self._tasks.append(asyncio.create_task(self._eigenstaendig(), name="eigenstaendig"))
        self.alltag.start()
        if self.memory is not None:                             # einmal am Tag ein Sicherungspunkt (seit 0.38.24)
            self._tasks.append(asyncio.create_task(asyncio.to_thread(self.sicherung.taeglich), name="sicherungspunkt"))
        if self.config.hintergrund:
            if self.alltag.on and self.alltag.mode != "ruhe":
                await self.alltag.set_mode("ruhe", "im Hintergrund gestartet")
        # Die simulierte Verkörperung steht erst auf, wenn jemand sie betritt (koerper_betreten) – Knowlin startet im Kopf
        if self.config.tts:
            self.speaker.warm_up()
        if self.remote.enabled and self.app is not None:
            await self.remote_listener.start(self.app, self.remote.port)

    async def stop(self) -> None:
        if self.lernen.running or self.local.status().get("laeuft"):
            await self.lernen.stop(warten=60)  # bester Stand wird gespeichert – darauf warten
        await self.remote_listener.stop()
        await self.alltag.stop()
        self.usage.save()
        self.erfahrung.netz.save()
        self.raum.speichern()
        for t in self._tasks:
            t.cancel()
        await self.engine.close()
        await self.backend.close()

    # ── Einstellungen live übernehmen ─────────────────────────────────────
    def _figur_profil(self, wert: Any) -> dict[str, Any]:
        """Charakter einer Verkörperung aus Knowlins Feld (Wunsch des Maintainers 5.11.): Knowlins Grundcharakter wirkt nur auf
        Knowlin; jede Verkörperung lässt sich einzeln verschieben – auch, wenn sie gerade nicht wach ist (`figuren.json`).
        Für die wache Rückgabe als `energie`/`humor` für die Einstellungen."""
        from ..figuren import FIGUREN

        if not isinstance(wert, dict) or wert.get("modul") not in FIGUREN:
            raise ValueError("figur_profil: {modul, energie, humor} mit bekannter Verkörperung erwartet")
        werte = S.validate({k: wert[k] for k in ("energie", "humor") if k in wert})
        if wert["modul"] == self.config.modul:
            return werte
        self.figuren.setze(wert["modul"], werte)
        return {}

    async def apply_settings(self, patch: dict[str, Any], persist: bool = True) -> dict[str, Any]:
        if "figur_profil" in patch:
            patch = dict(patch)
            patch = {**self._figur_profil(patch.pop("figur_profil")), **patch}
            if not patch:                                  # nur eine schlafende Verkörperung verschoben
                await self.broadcast(self.init_message())
                return {"ok": True, "geaendert": ["figur_profil"]}
        neu_modul = patch.get("modul")
        if neu_modul and neu_modul != self.config.modul and neu_modul in koerper.ids():
            # Körperwechsel = Figurwechsel (seit 0.38.3): eigene Werte der bisherigen Verkörperung sichern, die der neuen laden
            jetzt = {k: getattr(self.config, k) for k in FIGUR_KEYS if hasattr(self.config, k)}
            patch = {**self.figuren.wechsel(self.config.modul, neu_modul, jetzt), **patch}
        clean = S.save_user_settings(patch) if persist else S.validate(patch)
        changed = {k for k, v in clean.items() if getattr(self.config, k) != v}
        if not changed:
            return {"ok": True, "geaendert": []}
        async with self.reconfig_lock:
            for k in changed:
                setattr(self.config, k, clean[k])
            if "sprache" in changed:
                i18n.setze_sprache(clean["sprache"])
            if changed & ENGINE_KEYS:
                for k in changed & ENGINE_KEYS:
                    setattr(self.engine.config, k, clean[k])
                if "energie" in changed:
                    self.erfahrung.apply_praegung()      # Prägung bleibt auf dem neuen Anker
            if "kopf_stabil" in changed:
                self.backend.set_stabilize(clean["kopf_stabil"])
            if "stt" in changed or "whisper_model" in changed or "sprache" in changed:
                self._setup_stt()
            if "memory" in changed:
                if self.config.memory and self.memory is None:
                    self._open_memory()
                elif not self.config.memory:
                    self.memory = None
            if "weitere_enten" in changed and getattr(self, "schwarm", None):
                self.schwarm.anzahl(clean["weitere_enten"])
            if changed & BODY_KEYS:
                await self._swap_body()
                if "modul" in changed:                     # andere Verkörperung: eigene Tricks, eigenes Gespräch
                    if self.memory is not None:
                        self.memory.set_figur(self.config.modul)
                    self.agent.reset()
                    if self.im_koerper:
                        spawn(self._begruessen())
            elif "memory" in changed:
                self.engine.listeners.clear()
                self.engine.listeners.append(self._on_event)
                self._new_runner()
                self._new_agent()
            elif changed & AGENT_KEYS:
                self._new_agent()
            for k in changed & LIVE_AGENT_KEYS:
                setattr(self.agent.config, k, clean[k])
        if changed & {"kopf_stimme_motor", "kopf_stimme_piper", "kopf_stimme_qwen"}:
            await self.broadcast(self.voice_message())      # Knowlins Stimme (seit 0.38.10)
        if changed & VOICE_KEYS:
            self._voice_changed()
            if changed & {"stimme_motor", "stimme_piper", "stimme_qwen", "qwen_qualitaet"} and self.config.tts:
                self.speaker.warm_up()
        await self.broadcast(self.init_message())
        await self.broadcast(self.memory_message())
        return {"ok": True, "geaendert": sorted(changed)}

    async def _setting_from_duck(self, patch: dict[str, Any]) -> None:
        """Die Ente (Claude oder einfache Befehle) ändert eine Einstellung – z. B. Goofy-Modus per Sprache."""
        before = self.config.goofy
        await self.apply_settings(patch)
        if "goofy" in patch and before != self.config.goofy:
            self.engine.note({"type": "goofy" if patch["goofy"] else "memory",
                              "message": "Goofy-Modus an – Quak!" if patch["goofy"] else "Goofy-Modus aus – wieder ganz ordentlich"})

    async def _swap_body(self) -> None:
        self.engine.note({"type": "connected", "message": "Wechsle den Körper …"})
        estop_at, still = self.engine.estop_at, self.engine.still
        self.engine._cancel_all("Körper gewechselt")      # sauber beenden (mit Meldung), nicht still verwerfen
        await self.engine.close()
        await self.backend.close()
        self.backend = build_backend(self.config)
        self._wire()
        self.engine.estop_at, self.engine.still = estop_at, still   # die Not-Aus-Sperre gilt auch für den neuen Körper
        await self.backend.connect()
        await self.engine.start()
        resting = self.alltag.on and self.alltag.mode == "ruhe"
        if self.engine.notaus_gesperrt():
            await self.backend.relax()                     # nach dem Not-Aus bleibt auch der neue Körper stromlos
        elif resting:
            await self.backend.rest()                      # Ruhe bleibt Ruhe (die Physik startet sonst mit Strom)
        elif self.config.backend == "sim" and not self.engine.notaus_gesperrt() and self.im_koerper:
            await self.engine.stand_up()
        self.reachy_beim_zuweisen()

    async def koerper_betreten(self) -> None:
        """Jemand betritt die Verkörperung (Cockpit, Handy-Controller, Direktstart): Körper aufwecken, Mitbewohner ins Zimmer.
        Einmal wach, bleibt sie wach – zurück zu Knowlin heißt nicht schlafen legen."""
        if self.im_koerper:
            return
        self.im_koerper = True
        if getattr(self, "schwarm", None):
            self.schwarm.anzahl(self.config.weitere_enten)
        if self.config.backend == "sim" and not self.engine.notaus_gesperrt() \
                and not (self.alltag.on and self.alltag.mode == "ruhe"):
            await self.engine.stand_up()
        await self.broadcast({"type": "koerper", "an": True})
        await self._begruessen()

    async def _begruessen(self) -> None:
        """Die Verkörperung meldet sich beim Aufwachen in ihrer Art (wie Pollens Profile mit eigenem Gruß, seit 0.38.4)."""
        from ..figuren import figur

        if self.alltag.on and self.alltag.mode == "ruhe":
            return
        if self.ist_reachy():                              # eigene Begrüßung mit Geste (seit 0.38.13, abschaltbar)
            await self._reachy_begruessen()
            return
        gruss = i18n.t(figur(self.config.modul).get("gruss", ""), name=self.config.duck_name or figur(self.config.modul)["name"])
        if gruss and self.config.tts:
            await self._duck_says(gruss if self.config.entenlaute != "aus" else gruss.replace("*quak* ", ""))

    def settings_message(self) -> dict[str, Any]:
        cfg = self.config
        return {
            "werte": {k: getattr(cfg, k) for k in S.EDITABLE},
            "auswahl": {"model": S.MODELS, "whisper_model": list(S.WHISPER_MODELS)},
            "schluessel": self.key_status(),
            "whisper_installiert": _whisper_installed(),
            "pfade": {
                "einstellungen": str(S.settings_path()),
                "gedaechtnis": str(self.memory.path) if self.memory else None,
                "daten": str(S.data_dir()),
            },
            "version": __version__,
            "app_modus": cfg.app_mode,
            "verbrauch": self.usage.summary(),
        }

    # ── Tricks vom Hub und Gefühle ────────────────────────────────────────
    async def search_tricks(self, query: str) -> dict[str, Any]:
        """Erst vom PC aus (Hub-API), sonst – am echten Roboter – über dessen updaterd."""
        from .. import hub

        loop = asyncio.get_running_loop()
        try:
            found = await loop.run_in_executor(None, hub.search, query)
            return {"ok": True, "quelle": "pc", "tricks": found}
        except Exception as exc:
            pc_error = f"{type(exc).__name__}: {exc}"
        search = getattr(self.backend, "search_tricks", None)
        if search is not None and self.backend.state().connected:
            try:
                models = await search(query)
                tricks = [{"repo": m.get("id"), "herkunft": "offiziell" if m.get("origin") == "official" else "community",
                           "likes": m.get("likes"), "downloads": m.get("downloads"), "vorschau": m.get("preview"),
                           "seite": f"https://huggingface.co/{m.get('id')}", "beschreibung": hub.one_line(m.get("description")),
                           "name": hub.trick_name(str(m.get("id"))), "geht": True, "hinweis": ""} for m in models if m.get("id")]
                return {"ok": True, "quelle": "roboter", "tricks": tricks}
            except Exception as exc:
                return {"ok": False, "fehler": f"Hub nicht erreichbar (PC: {pc_error}; Roboter: {exc})", "tricks": []}
        return {"ok": False, "fehler": f"Hub nicht erreichbar: {pc_error}", "tricks": []}

    async def add_trick(self, repo: str, name: str | None = None, seconds: float | None = None,
                        file: str | None = None) -> dict[str, Any]:
        """Auf den Roboter laden; im Simulator (oder wenn es scheitert) vormerken."""
        repo = repo.strip()
        S.validate({"tricks": [repo.partition("@")[0]]})  # wirft bei Unsinn
        if file is not None and not re.fullmatch(r"[\w./-]{1,120}\.onnx", file):
            raise ValueError("datei: nur ein .onnx-Pfad im Repo")
        res = await self.backend.add_trick(repo, name=name, seconds=seconds, file=file)
        saved = list(self.config.tricks)
        base = repo.partition("@")[0]
        if base not in saved:
            await self.apply_settings({"tricks": [*saved, base][-40:]})
        if res.accepted:
            self.engine.note({"type": "memory", "message": f"Trick geladen: {res.reason}"})
        return {"ok": res.accepted, "grund": res.reason, "vorgemerkt": True,
                "skills": self.backend.skills(), "koerper": self.koerper()}

    async def forget_trick(self, repo: str) -> dict[str, Any]:
        await self.apply_settings({"tricks": [r for r in self.config.tricks if r != repo]})
        return {"ok": True}

    def emotions_catalog(self) -> list[dict[str, Any]]:
        from ..motion import behaviors as B
        from ..motion import character as C

        out = []
        for name, spec in B.EMOTIONS.items():
            info = B.POLLEN.get(name)
            art = "pollen" if info else "charakter" if name in B.CHARACTER else "eigen"
            bei = [p for p, rep in C.REPERTOIRE.items() if any(g == name for g, _ in rep["gesten"])]
            out.append({"name": name, "pollen": bool(info), "art": art, "bei": bei,
                        "text": info["text"] if info else (_leerlauf_text(name) if art == "charakter" else ""),
                        "dauer": round(max(k.get("t", 0) for k in spec), 1) if spec else 0})
        return out

    # ── an alle Browser ──────────────────────────────────────────────────
    MODELL_QUELLEN = ("claude", "lokal", "anbieter")

    def _lokal(self, message: dict[str, Any]) -> dict[str, Any]:
        """Eigene Sätze der Ente (Reflex, Alltag, Beschwerde, System) in der gewählten Sprache – angezeigt und
        gesprochen (seit 0.36). Antworten der Modelle sind schon in der richtigen Sprache."""
        if (getattr(self.config, "sprache", "de") == "de" or message.get("type") != "chat" or message.get("role") != "duck"
                or message.get("source") in self.MODELL_QUELLEN or not message.get("text")):
            return message
        from ..i18n import ui_text

        neu = ui_text(message["text"], self.config.sprache)
        if neu == message["text"]:
            return message
        out = {**message, "text": neu}
        if message.get("sprache"):
            out["sprache"] = self._speech(neu, message.get("gefuehl") or "ausgeglichen")
        return out

    async def broadcast(self, message: dict[str, Any]) -> None:
        message = self._lokal(message)
        if message.get("type") in ("stimme", "physik", "training", "parcours"):
            self._tasks_changed()           # Hintergrund-Aufgaben haben sich vielleicht geändert
        if not self.clients:
            return
        text = json.dumps(message, ensure_ascii=False, default=_json_default)
        await asyncio.gather(*(self.send_to(ws, text) for ws in list(self.clients)))

    async def send_to(self, ws, text: str) -> bool:
        """Eine Nachricht an ein Fenster – immer nur ein Senden gleichzeitig je Verbindung.

        Zustand (20 Hz), Ereignisse (Laute!), Chat und Antworten kommen aus verschiedenen Aufgaben. Zwei gleichzeitige
        Sendungen auf derselben Verbindung scheitern, und dann fiel das Fenster still aus der Verteilerliste: keine
        Laute, keine Antworten mehr. Die Sperre hält die Reihenfolge (wer zuerst wartet, sendet zuerst)."""
        lock = getattr(ws, "send_lock", None)
        if lock is None:
            lock = ws.send_lock = asyncio.Lock()
        try:
            async with lock:
                await ws.send_text(text)
            return True
        except Exception as exc:
            if ws in self.clients:
                log.info("Fenster abgemeldet (%s: %s)", type(exc).__name__, exc)
            self.clients.discard(ws)
            return False

    # ── Hintergrund-Aufgaben: eine Liste für die Kopfzeile ────────────────
    def tasks_message(self) -> dict[str, Any]:
        out: list[dict[str, Any]] = []

        def add(id_: str, titel: str, text: str, view: str, part: str | None = None, anteil: float | None = None) -> None:
            out.append({"id": id_, "titel": titel, "text": str(text or "")[:120], "anteil": anteil,
                        "ziel": {"view": view, "part": part}})

        from ..voice.install import PAKETE

        for key, job in getattr(self.installer, "jobs", {}).items():
            if job.get("laeuft"):
                name = PAKETE.get(key, {}).get("name", key)
                where = {"piper": ("stimme", "stimme"), "qwen": ("stimme", "stimme"), "whisper": ("settings", "allgemein"),
                         "training": ("training", None)}.get(key, ("settings", "koerper"))
                add(f"install:{key}", f"Installiert {name}", f"Schritt {job.get('schritt')} von {job.get('schritte')}", *where)
        for key, job in getattr(self.speaker, "jobs", {}).items():
            if job.get("laeuft"):
                titel = "Entenstimme entwerfen" if key == "entwurf" else f"Stimme laden ({key.split(':', 1)[-1]})"
                add(f"stimme:{key}", titel, job.get("text"), "stimme", "stimme", anteil=job.get("anteil"))
        for model, job in getattr(self, "pulls", {}).items():
            if job.get("laeuft"):
                add(f"ollama:{model}", f"Sprachmodell laden ({model})", job.get("status"), "stimme", "gespraech",
                    anteil=job.get("anteil"))
        if (self.physik_job or {}).get("laeuft"):
            add("physik", "Pollens Policies laden", self.physik_job.get("text"), "settings", "koerper")
        if (self.modell.job or {}).get("laeuft"):
            add("modell", "Pollens Robotermodell laden", self.modell.job.get("text"), "settings", "ueber")
        if (self.training_job or {}).get("laeuft"):
            add("training-start", "Training wird gestartet", self.training_job.get("text"), "training")
        try:
            for r in self.trainer.runs():
                if r.get("job") and r.get("status") in ("gestartet", "wartet auf eine GPU", "trainiert", "exportiert"):
                    add(f"lauf:{r['id']}", "Training auf Hugging Face", f"{r['plan']['aufgabe']} – {r['status']}", "training")
        except Exception:
            pass
        lab = getattr(self, "lab", None)
        if lab is not None and lab.job.get("laeuft"):
            add("parcours", "Parcours-Test", lab.job.get("text"), "parcours")
        return {"type": "aufgaben", "liste": out}

    def _tasks_changed(self) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        if getattr(self, "_tasks_push", None) is not None:
            return

        def push() -> None:
            self._tasks_push = None
            spawn(self.broadcast(self.tasks_message()))

        self._tasks_push = loop.call_later(0.3, push)

    def _on_event(self, event: dict[str, Any]) -> None:
        self.blackbox.ereignis(event)
        self.erfahrung.on_event(event)
        spawn(self.broadcast({"type": "event", "event": event}))

    def _on_memory(self, data: dict[str, Any]) -> None:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return
        spawn(self.broadcast(self.memory_message()))

    def memory_message(self) -> dict[str, Any]:
        if self.memory is None:
            return {"type": "memory", "enabled": False}
        body = self.backend.state().backend or self.config.backend
        return {"type": "memory", "enabled": True, "data": self.memory.snapshot(), "body": body,
                "path": str(self.memory.path), "error": self.memory.error, "herkuenfte": self.herkunft_namen()}

    def herkunft_namen(self) -> dict[str, str]:
        """Für „gemerkt von …“ und die Hirnaktivität (seit 0.38.10): Kennung der Herkunft → Name."""
        namen = {"kopf": self.config.kopf_name or "Knowlin"}
        for f in self.kopf_figuren():
            namen[f["modul"]] = f["name"]
        return namen

    def init_message(self) -> dict[str, Any]:
        items = getattr(self.backend, "items", None)
        return {
            "type": "init",
            "aufgaben": self.tasks_message()["liste"],
            "world": self.backend.world(),
            "items": items() if items else [],
            "events": list(self.engine.events)[-30:],
            "config": {
                **self.config.public(),
                "online": self.agent.online,
                "anbieter_bereit": self.agent.anbieter.configured,
                "whisper": self.stt is not None,
                "agent_error": self.agent.last_error,
                "skills": self.backend.skills(),
                "physik": bool(getattr(self.backend, "runs_policies", False)) and self.config.backend == "sim",
                "eigenschaften": sorted(self.backend.eigenschaften()),     # Körpermodus der Oberfläche (seit 0.38.4)
                "gestalt": self.gestalt_liste(),                          # Eigenschaften der Gestalt (seit 0.38.10)
                "verkoerperungen": self.kopf_figuren(),                    # Punkte im Charakterfeld bei Knowlin
                "im_koerper": self.im_koerper,
                "version": __version__,
                "modell": self.modell.status(),
                "app_mode": self.config.app_mode, "beenden": self.quit_message(),
                "needs_setup": not self.config.api_key and not S.settings_path().exists(),
            },
        }

    @property
    def blackbox(self):
        """Aufzeichnung der letzten 30 s für den Fehlerbericht „Das lief schief“ (seit 0.36.2)."""
        if getattr(self, "_blackbox", None) is None:
            from .fehlerbericht import Blackbox

            self._blackbox = Blackbox()
        return self._blackbox

    async def _aufzeichnen(self) -> None:
        from .fehlerbericht import TAKT_S

        while True:
            await asyncio.sleep(TAKT_S)
            try:
                st = self.backend.state()
                self.blackbox.zustand(st.to_dict(), self.engine.describe())
                self.raum.tick(st)
            except Exception:          # die Aufzeichnung darf nie etwas anderes stören
                log.debug("Aufzeichnung", exc_info=True)

    async def _push_state(self) -> None:
        """Zustand 20× pro Sekunde an die Fenster am PC, 10× an Handys (spart mobiles Datenvolumen).
        Hängt eine Verbindung noch am letzten Bild, wird ihr dieses ausgelassen – ein langsames Handy bremst
        so weder den Takt noch die anderen Fenster."""
        tick = 0
        while True:
            await asyncio.sleep(0.05)
            tick += 1
            if not self.clients:
                continue
            items = getattr(self.backend, "items", None)
            laser = getattr(self.backend, "laser", None)
            person = getattr(self.backend, "person", None)
            st = self.backend.state()
            text = json.dumps({
                "type": "state",
                "state": st.to_dict(),
                "items": items() if items else None,
                "laser": laser() if laser else None,
                "mensch": person() if person else None,
                "engine": self.engine.describe(),
                "enten": self.schwarm.anzeige() if getattr(self, "schwarm", None) and self.schwarm.enten else None,
                "antrieb": self.antrieb.hinweis(),      # seit 0.38.44: nur ein feiner Hinweis (Tooltip)
            }, ensure_ascii=False, default=_json_default)
            for ws in list(self.clients):
                if getattr(ws, "fern_geraet", None) is not None and tick % 2:
                    continue
                if getattr(ws, "state_busy", False):
                    continue
                ws.state_busy = True
                spawn(self._send_state(ws, text))

    async def _send_state(self, ws, text: str) -> None:
        # kein Zeitlimit: ein abgebrochenes Senden zerreißt die Verbindung. Wer langsam ist, bekommt einfach
        # weniger Bilder (state_busy), bis sein Senden durch ist.
        try:
            await self.send_to(ws, text)
        finally:
            ws.state_busy = False

    async def _watch_people(self) -> None:
        """Angelernte Personen begrüßen (nur wenn „Personen erkennen“ an ist; Unbekannte bleiben unbekannt)."""
        while True:
            await asyncio.sleep(2.0)
            p = self.alltag.planner.data
            if not (self.alltag.on and p.get("personen") and p.get("begruessen")):
                continue
            robot = self.config.backend == "robotd" and self.camera_address()
            if not robot and not self.eyes.fresh():
                continue                                  # im Simulator schickt das Fenster Bilder, wenn die Webcam an ist
            if not self.faces.available()[0] or not self.faces.persons():
                continue
            try:
                data, _k, _q = await self.eyes.image(timeout=2.0)
                seen = await asyncio.to_thread(self.faces.who, data)
            except Exception:
                continue
            now = time.monotonic()
            self._anschauen(seen, data)
            for f in seen:
                name = f.get("name")
                if not name or name == "unbekannt" or now - self._greeted.get(name, -1e9) < 1800:
                    continue
                self._greeted[name] = now
                self.erfahrung.person(name)
                self.alltag.touch(wake=False)
                if self.alltag.mode != "ruhe" and not self.engine.notaus_gesperrt():
                    await self.runner.run("emote", {"emotion": "begruessen"})   # nach einem Not-Aus nur Worte
                # Namen nur in die Fenster am PC – ein Handy (auch unterwegs) erfährt nicht, wer zu Hause ist
                await self.broadcast_local({"type": "chat", "role": "duck", "text": f"Hallo {name}!", "source": "alltag",
                                            "seconds": 0, "sprache": self._speech(f"Hallo {name}!", "fröhlich")})
                break

    def _anschauen(self, seen: list[dict[str, Any]], data: bytes) -> None:
        """Angelernte Person im Bild → kurz zu ihr schauen (seit 0.38.2, vor allem für Reachy Mini im Gespräch).
        Nur erkannte Personen, nie Unbekannte; nichts wird gespeichert; nicht mitten in einer Aufgabe."""
        bekannt = [f for f in seen if f.get("name") and f["name"] != "unbekannt" and f.get("box")]
        if not bekannt or self.engine.busy() or self.engine.notaus_gesperrt():
            return
        try:
            from ..faces import _to_rgb

            h, w = _to_rgb(data).shape[:2]
        except Exception:  # noqa: BLE001
            return
        x, y, bw, bh = max(bekannt, key=lambda f: f["box"][2] * f["box"][3])["box"]
        cx, cy = (x + bw / 2) / max(1, w), (y + bh / 2) / max(1, h)
        from ..api import Head

        # Bildmitte = geradeaus; Bild links = Person links (Kamera sieht wie die Augen), ≈ 60° Bildwinkel
        self.engine.look_at(head=Head(0.0, max(-0.4, min(0.4, (cy - 0.5) * 0.7)), max(-0.6, min(0.6, (0.5 - cx) * 1.05)), 0.0),
                            seconds=3.0)

    async def _watch_clients(self) -> None:
        """App-Modus: ist das Fenster 8 s lang zu, beendet sich duckpilot."""
        while True:
            await asyncio.sleep(1.0)
            if self.clients:
                self._had_client = True
                self._empty_since = None
                continue
            if not (self.config.app_mode and self._had_client and self.on_idle_exit):
                continue
            if self.keep_open:
                self._empty_since = None   # „Im Hintergrund weiterlaufen“ gewählt
                continue
            if self.remote.enabled and self.remote_listener.listening:
                self._empty_since = None   # Handy-Fernbedienung an: im Hintergrund weiterlaufen
                continue
            self._empty_since = self._empty_since or time.monotonic()
            if time.monotonic() - self._empty_since > 8.0:
                log.info("Fenster geschlossen – duckpilot beendet sich")
                self.on_idle_exit()
                return

    async def _watch_update(self) -> None:
        """Liegt eine neuere Version im Programmordner (z. B. nach einem Update in OneDrive)? Dann Neustart anbieten."""
        init = Path(__file__).resolve().parent.parent / "__init__.py"  # noqa: ASYNC240 – einmalig, kein Warten
        while True:
            await asyncio.sleep(30)
            try:
                m = re.search(r'__version__\s*=\s*"([^"]+)"', init.read_text(encoding="utf-8"))
            except OSError:
                continue
            new = m.group(1) if m else None
            if new and new != __version__ and new != self.update_ready:
                self.update_ready = new
                await self.broadcast_local(self.quit_message())

    async def _watch_online_update(self) -> None:
        """Seit 0.38.32: höchstens einmal am Tag bei GitHub nach einer neuen Version sehen (abschaltbar)."""
        from ..aktualisieren import UpdateFehler

        await asyncio.sleep(20)
        while True:
            if getattr(self.config, "updates_suchen", True):
                vorher = (self.aktualisierer.status().get("neu") or {}).get("version")
                try:
                    st = await asyncio.to_thread(self.aktualisierer.pruefen)
                except UpdateFehler as exc:
                    log.info("Update-Suche: %s", exc)
                else:
                    if (st.get("neu") or {}).get("version") != vorher:
                        await self.broadcast_local(self.quit_message())
            await asyncio.sleep(6 * 3600)

    def quit_message(self) -> dict[str, Any]:
        """Für den Beenden-Dialog: was läuft noch, kann man beenden, liegt eine neue Version bereit?"""
        from ..kaggle_training import ACTIVE as K_ACTIVE

        laeuft = []
        if self.lernen.running or self.local.status().get("laeuft"):
            laeuft.append("Lernen am PC – beim Beenden wird der beste Stand gespeichert")
        if any(r.get("status") in K_ACTIVE for r in self.kaggle.runs()):
            laeuft.append("Training auf Kaggle – läuft in der Cloud weiter")
        if any(r.get("job") and r.get("status") not in ("fertig", "fehlgeschlagen", "abgebrochen") for r in self.trainer.runs()):
            laeuft.append("Training auf Hugging Face – läuft in der Cloud weiter")
        if self.installer.running():
            laeuft.append("eine Installation – sie würde abbrechen")
        return {"type": "beenden", "kann": self.on_idle_exit is not None and bool(self.config.app_mode),
                "version": __version__, "neu": self.update_ready, "laeuft": laeuft,
                "fernbedienung": bool(self.remote.enabled), "hintergrund": self.keep_open,
                "online": self.aktualisierer.status() if getattr(self.config, "updates_suchen", True) else None}

    async def _mentor_hand(self, msg: dict[str, Any]) -> None:
        """Vormachen: Handpunkte → Ziel der Greiferspitze (`mentor.py`) → `backend.nachmachen`. Höchstens 20 je Sekunde;
        eine Absage (Motoren aus, Hindernis, Auftrag) geht als kurze Meldung zurück, nicht öfter als alle 2 s."""
        from ..mentor import Nachmacher, hand_aus

        nachmachen = getattr(self.backend, "nachmachen", None)
        hand = hand_aus(msg)
        if nachmachen is None or hand is None:
            return
        jetzt = time.monotonic()
        if jetzt - getattr(self, "_mentor_zuletzt", 0.0) < 0.05:
            return
        self._mentor_zuletzt = jetzt
        if getattr(self, "_mentor", None) is None:
            self._mentor = Nachmacher()
        self.alltag.touch()
        self.engine.kontakt("Vormachen")
        r = await nachmachen(self._mentor.weiter(hand, jetzt))
        if not r.accepted and jetzt - getattr(self, "_mentor_absage", 0.0) > 2.0:
            self._mentor_absage = jetzt
            await self.broadcast({"type": "mentor", "ok": False, "grund": r.reason})

    async def handle_client_message(self, msg: dict[str, Any], remote: bool = False) -> None:
        kind = msg.get("type")
        R.REMOTE_TURN.set(remote)          # gilt für alles, was diese Nachricht auslöst (auch Claudes Werkzeuge)
        if kind == "chat":
            cid = str(msg.get("cid") or "")[:16] or None
            spawn(self.chat(str(msg.get("text", "")), msg.get("via", "text"), "kopf" if msg.get("an") == "kopf" else "figur",
                            cid))
        elif kind == "drive":
            moving = any(float(msg.get(k, 0) or 0) for k in ("vx", "vy", "vyaw"))
            if moving or msg.get("head") is not None:
                self.alltag.touch(wake=moving)         # Fahren weckt, Kopf ziehen nur „ist beschäftigt“
            head = None
            if msg.get("head") is not None:
                h = msg["head"]
                head = Head(0.0, float(h.get("pitch", 0)), float(h.get("yaw", 0)), 0.0)
            self.engine.manual_drive(
                Twist(float(msg.get("vx", 0)), float(msg.get("vy", 0)), float(msg.get("vyaw", 0))), head,
            )
        elif kind in ("blick", "hingehen"):
            self.alltag.touch(wake=kind == "hingehen")
            await self._gaze_message(kind, msg)
        elif kind == "laser":
            self._laser_message(msg)
        elif kind == "mensch":
            self._person_message(msg)
        elif kind == "tool":
            args = msg.get("args") or {}
            if msg.get("name") == "power" and args.get("action") in ("sit_down", "rest"):
                self.alltag.touch(wake=False)      # Hinsetzen/Ausruhen darf sie nicht erst aufwecken
            elif msg.get("name") not in ("stop", "alltag"):
                self.engine.angesprochen()
                self.alltag.touch()
            result = await self.runner.run(str(msg.get("name")), msg.get("args") or {})
            if isinstance(result, dict):
                result.pop("_bild", None)
            await self.broadcast({"type": "action", "tool": msg.get("name"), "input": msg.get("args"), "result": result})
        elif kind == "mentor_hand":                # Vormachen (seit 0.38.57): 21 Handpunkte, nie ein Bild
            await self._mentor_hand(msg)
        elif kind == "mentor_ende":
            self._mentor = None
        elif kind == "stop":
            self.alltag.emergency_stop()
            await self.engine.not_aus("Not-Aus")
        elif kind == "koerper":
            await self.koerper_betreten()
        elif kind == "listening":
            self.engine.attention(4.0)
        elif kind == "speaking":
            track = self.speaker.mouth_of(str(msg.get("id") or "")) if msg.get("id") else None
            if track is None and msg.get("sekunden"):
                track = _flap(float(msg["sekunden"]))
            self.engine.speak(track)
        elif kind == "speaking_end":
            self.engine.speak(None)
        elif kind == "laut":
            from ..api import SOUND_TAGS

            tag = str(msg.get("ton") or "")
            if tag in SOUND_TAGS:
                self.engine.fire(self.backend.sound(tag))
        elif kind == "reset_chat":
            self.agent.reset()
        elif kind == "memory_get":
            await self.broadcast(self.memory_message())
        elif kind == "memory_forget" and self.memory is not None:
            try:
                key = self.memory.forget(str(msg.get("kind")), msg.get("name"))
                self.engine.note({"type": "memory", "message": f"Vergessen: {key}"})
            except (KeyError, ValueError) as exc:
                await self.broadcast({"type": "event", "event": {"type": "memory", "message": str(exc)}})
        elif kind == "memory_clear" and self.memory is not None:
            self.sicherung.vorher("Vor „Alles vergessen“", ["gedaechtnis", "erfahrung"])   # rückgängig machbar (0.38.24)
            self.memory.forget_all()
            self.erfahrung.netz.reset()                 # „alles vergessen“ heißt auch: keine Verknüpfungen mehr
            self.engine.note({"type": "memory", "message": "Gedächtnis komplett gelöscht"})
        elif kind == "memory_run" and self.memory is not None:
            tool = "do_trick" if msg.get("kind") == "trick" else "go_to_place"
            result = await self.runner.run(tool, {"name": msg.get("name")})
            await self.broadcast({"type": "action", "tool": tool, "input": {"name": msg.get("name")}, "result": result})
        elif (extra := self.ws_extra.get(str(kind))) is not None:
            res = extra(msg)
            if asyncio.iscoroutine(res):
                await res


def _leerlauf_text(name: str) -> str:
    """Was eine Leerlauf-Geste ist, in der gewählten Sprache (`i18n` „leerlauf.<name>“, sonst `character.MESSAGES`)."""
    from ..motion.character import MESSAGES

    text = i18n.t(f"leerlauf.{name}")
    return MESSAGES.get(name, "") if text == f"leerlauf.{name}" else text


def _flap(seconds: float) -> list[float]:
    """Schnabel für die Browser-Stimme (ohne Hüllkurve): Silben im Wechsel, gut 4 pro Sekunde."""
    n = max(1, min(600, int(seconds * 10)))
    return [0.0 if i % 5 in (2,) or i % 11 == 10 else (0.55 if i % 2 else 0.85) for i in range(n)]


def _whisper_installed() -> bool:
    try:
        from ..voice.whisper_stt import WhisperSTT

        return WhisperSTT.available()
    except Exception:
        return False

