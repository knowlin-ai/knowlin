"""Laufzeit, Bereich Lab: Physik und Policies, Robotermodell, Parcours/Auftrag, Training (PC, Kaggle, Hugging Face), Modelle laden.

Teil der Klasse `Runtime` (server/runtime.py), ausgelagert nach Bereichen, damit runtime.py überschaubar bleibt.
Schicht: Verbindung (fachlich Knowlin Lab, die Trainingshalle; siehe duckpilot/schichten.py). Die Methoden greifen auf Felder von `Runtime` zu (self.config, self.broadcast …).
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any

from .. import settings as S
from ..aio import spawn

log = logging.getLogger(__name__)


class LabTeil:
    """Mischklasse für `Runtime` – nicht allein benutzbar."""

    def physik_message(self) -> dict[str, Any]:
        from ..backends import physics_problem
        from ..physics.policies import PolicyStore
        from ..voice import install as I

        store = PolicyStore(S.settings_path().parent)
        status = store.status()
        status["job"] = self.physik_job
        aktiv = bool(getattr(self.backend, "runs_policies", False)) and self.config.backend == "sim"
        core = getattr(self.backend, "core", None)
        return {
            "type": "physik", "sim_physik": self.config.sim_physik, "aktiv": aktiv,
            "problem": physics_problem(), "fallback": getattr(self.backend, "physics_problem", None),
            "installiert": {k: I.installed(k) for k in ("physik", "bam")},
            "policies": status, "motor": core.motor_model if core is not None else None,
            "ueben": self.runner.practice is not None, "geuebt": list(self.runner.practice_log)[-6:],
            "installation": {k: self.installer.jobs.get(k) for k in ("physik", "bam")},
        }

    async def load_policies(self) -> None:
        from ..physics.policies import PolicyStore

        store = PolicyStore(S.settings_path().parent)
        self.physik_job = {"laeuft": True, "text": "startet …", "fehler": None}
        await self.broadcast(self.physik_message())
        loop = asyncio.get_running_loop()

        def progress(text: str) -> None:
            self.physik_job["text"] = text
            loop.call_soon_threadsafe(lambda: spawn(self.broadcast(self.physik_message())))

        try:
            if self.modell.physics_path() is None:
                await asyncio.to_thread(self.modell.ensure, False, True, progress)
                await self.broadcast(self.modell_message())
            res = await asyncio.to_thread(store.download_official, progress)
            self.physik_job = {"laeuft": False, "text": f"{len(res['dateien'])} Policies geladen", "fehler": None}
            self._wire_practice()
            if self.config.sim_physik and self.config.backend == "sim" and not getattr(self.backend, "runs_policies", False):
                async with self.reconfig_lock:
                    await self._swap_body()
        except Exception as exc:
            self.physik_job = {"laeuft": False, "text": "fehlgeschlagen", "fehler": f"{type(exc).__name__}: {exc}"}
        await self.broadcast(self.physik_message())
        await self.broadcast(self.init_message())

    def modell_message(self) -> dict[str, Any]:
        return {"type": "modell", **self.modell.status()}

    async def load_modell(self, force: bool = False) -> None:
        from ..modell.service import load

        await load(self, force)

    def lab_message(self) -> dict[str, Any]:
        from ..backends import physics_problem

        try:
            problem = physics_problem()
        except Exception as exc:
            problem = str(exc)
        msg = self.lab.message(not problem, problem)
        msg["claude"] = bool(getattr(self, "agent", None) and self.agent.online)
        return msg

    def _lab_changed(self) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        if self._lab_push is not None:
            return

        def push() -> None:
            self._lab_push = None
            spawn(self.broadcast(self.lab_message()))

        self._lab_push = loop.call_later(0.2, push)

    async def _watch_training(self) -> None:
        """Laufende Trainings alle 10 Minuten nachfragen; ist der Lauf des Auftrags fertig, selbst prüfen."""
        from ..training import get_token

        while True:
            await asyncio.sleep(600)
            try:
                active = [r for r in self.trainer.runs() if r.get("job") and r.get("status") not in
                          ("fertig", "fehlgeschlagen", "abgebrochen")]
                token = get_token() if active else None
                if token:
                    await asyncio.to_thread(self.trainer.refresh, token)
                    await self.broadcast(self.training_message())
                from ..kaggle_training import ACTIVE as K_ACTIVE

                if any(r.get("status") in K_ACTIVE for r in self.kaggle.runs()):
                    await asyncio.to_thread(self.kaggle.refresh)
                await self.after_training_refresh()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("Training beobachten")

    async def after_training_refresh(self) -> None:
        if self.runner.lab is None:
            return
        tests = await self.lab.check_finished_runs()
        if tests:
            base = next((t for t in reversed(self.lab.missions.current()["tests"]) if t["quelle"] == "standard"), None)
            vorher = f" (vorher {base['im_ziel']} von {base['versuche']})" if base else ""
            if len(tests) == 1:
                t = tests[0]
                text = (f"Das Training ist fertig, ich habe es auf dem Parcours geprüft: {t['im_ziel']} von "
                        f"{t['versuche']} Versuchen im Ziel{vorher}. Die Aufzeichnung liegt unter Lernen → Parcours.")
            else:
                best = max(tests, key=lambda t: (t["im_ziel"], sum(e["geschafft"] for e in t.get("elemente", []))))
                text = (f"{len(tests)} Varianten sind fertig und auf dem Parcours geprüft. Am besten: {best['policy']} mit "
                        f"{best['im_ziel']} von {best['versuche']} im Ziel{vorher}. Details unter Lernen → Parcours.")
            await self.broadcast({"type": "chat", "role": "duck", "text": text, "source": "system", "seconds": 0})

    def training_message(self) -> dict[str, Any]:
        from ..training import (
            FLAVORS,
            GPUS,
            POLLEN_BUNDLES,
            TASKS,
            family,
            get_token,
            pollen_start,
            token_hint,
        )
        from ..voice import install as I

        token = get_token()
        runs = self.trainer.runs()
        return {
            "type": "training", "aufgaben": TASKS, "grafikkarten": FLAVORS, "token": token_hint(token),
            "preise": {k: v["usd_h"] for k, v in GPUS.items()}, "gemessen": self.trainer.measured(),
            "pollen": {t: {"buendel": pollen_start(t)[0], "warm": pollen_start(t)[1]} for t in TASKS if pollen_start(t)},
            "pollen_direkt": list(POLLEN_BUNDLES),
            "familien": {t: family(t) for t in TASKS},
            "installiert": I.installed("training"), "laeufe": runs[::-1][:20],
            "vorschlag": self.trainer.vorschlag, "job": self.training_job,
            "physik": bool(getattr(self.backend, "runs_policies", False)) and self.config.backend == "sim",
            "installation": self.installer.jobs.get("training"),
        }

    async def free_training(self, a: dict[str, Any]) -> dict[str, Any]:
        """Werkzeug für Claude: kostenloses Training starten (dieser PC oder Kaggle)."""
        if a.get("anbieter") == "kaggle":
            res = await self.start_kaggle({"aufgabe": a.get("aufgabe") or "Mjlab-Velocity-Rough-MicroDuck",
                                           "iterationen": a.get("iterationen"), "start_von": a.get("start_von") or "pollen",
                                           "max_stunden": a.get("max_stunden"), "bei_stillstand": "abbrechen"})
            return {"ok": True, "anbieter": "kaggle", "hinweis": "Läuft auf Kaggle – Lernen → Training zeigt die Kurve.",
                    "plan": res["plan"]}
        starter = getattr(self, "start_local", None)
        if starter is None:
            return {"ok": False, "fehler": "Training auf diesem PC ist noch nicht eingerichtet."}
        return await starter({"minuten": a.get("minuten") or 60, "lernschleife": a.get("lernschleife", True),
                              "von": "claude", "begruendung": str(a.get("begruendung") or "")[:300]})

    async def start_local(self, body: dict[str, Any]) -> dict[str, Any]:
        """Lernen am PC (mit Lernschleife über den Parcours) – kostenlos, darf auch Claude starten."""
        try:
            st = await self.lernen.start(body)
        except ValueError as exc:
            return {"ok": False, "fehler": str(exc)}
        art = "mit Lernschleife über den Parcours" if st["schleife"] else "ohne Schleife"
        return {"ok": True, "anbieter": "pc", "budget_minuten": st["budget_minuten"], "runde_minuten": st["runde_minuten"],
                "parcours": st["parcours"], "hinweis": f"Lernt auf diesem PC {art}; Lernen → Training → Dieser PC zeigt "
                                                       "Kurve und Runden. Die Ente selbst bewegt sich dabei nicht."}

    def lernen_message(self, full_curve: bool = False) -> dict[str, Any]:
        from ..physics import lernen as L
        from ..voice import install as I

        ok, why = L.available()
        lauf = self.local.status()
        kurve = lauf.get("kurve") or []
        if not full_curve and len(kurve) > 150:
            step = -(-len(kurve) // 150)
            lauf["kurve"] = kurve[:-1:step] + kurve[-1:]
        m = self.lab.missions.current() or {}
        course = self.lab.course()
        return {
            "type": "lernen", "verfuegbar": ok, "grund": why, "installiert": I.installed("lernen"),
            "installation": self.installer.jobs.get("lernen"), "lauf": lauf, "schleife": self.lernen.status(),
            "verlauf": self.local.history()[:12], "quellen": L.quellen(self.local.root),
            "parcours": course.name if course and m.get("parcours") else None,
            "kerne": os.cpu_count() or 1, "gpu_vorschlag": I.suggest_gpu(self._gpus or []),
        }

    def _lernen_changed(self) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        if self._lernen_push is not None:
            return

        def push() -> None:
            self._lernen_push = None
            spawn(self.broadcast(self.lernen_message()))

        self._lernen_push = loop.call_later(0.3, push)

    async def start_kaggle(self, body: dict[str, Any]) -> dict[str, Any]:
        """Kostenloser Lauf auf Kaggle (darf auch Claude starten – kostet nichts, feste Obergrenze)."""
        from .. import kaggle_training as K

        if not K.get_credentials():
            raise ValueError("Erst den Kaggle-Zugang hinterlegen (Lernen → Training → Kaggle).")
        if self.kaggle_job.get("laeuft"):
            raise ValueError("Es wird gerade schon ein Kaggle-Lauf gestartet.")
        plan = K.check_plan(str(body.get("aufgabe") or ""), body.get("iterationen"), body.get("anpassungen") or {},
                            body.get("start_von") or None, body.get("max_stunden"), str(body.get("bei_stillstand") or "weiter"),
                            self.kaggle.measured())
        self.kaggle_job = {"laeuft": True, "text": "Starte auf Kaggle …"}

        def progress(text: str) -> None:
            self.kaggle_job["text"] = str(text)[:200]

        try:
            run = await asyncio.to_thread(self.kaggle.submit, plan, progress)
        except Exception as exc:
            self.kaggle_job = {"laeuft": False, "fehler": str(exc)[:300]}
            raise RuntimeError(str(exc)) from exc
        self.kaggle_job = {"laeuft": False, "text": f"Läuft auf Kaggle: {plan['aufgabe']}"}
        self.engine.note({"type": "training", "message": f"Kostenloses Training auf Kaggle gestartet: {plan['aufgabe']}"})
        return {"lauf": run, "plan": plan}

    async def start_training(self, plans: list[dict[str, Any]], namespace: str | None) -> None:
        """Einen Lauf oder mehrere Varianten (gleiche Aufgabe, andere Gewichte) nacheinander starten."""
        from ..training import get_token

        plans = plans if isinstance(plans, list) else [plans]
        token = get_token()
        self.training_job = {"laeuft": True, "text": "startet …", "fehler": None}
        await self.broadcast(self.training_message())
        loop = asyncio.get_running_loop()
        gruppe = time.strftime("%Y%m%d-%H%M%S") if len(plans) > 1 else None
        mission = self.lab.missions.current()
        mid = mission["id"] if mission else None
        started, errors = [], []
        for i, plan in enumerate(plans):
            label = f"Variante {chr(65 + i)}" if gruppe else None

            def progress(text: str, label=label) -> None:
                self.training_job["text"] = f"{label}: {text}" if label else text
                loop.call_soon_threadsafe(lambda: spawn(self.broadcast(self.training_message())))

            try:
                run = await asyncio.to_thread(self.trainer.submit, plan, token, namespace, None, progress, gruppe, label)
                started.append(run)
                if self.lab.missions.link_run(plan, run, mid):
                    self._lab_changed()
            except Exception as exc:
                errors.append(f"{label + ': ' if label else ''}{exc}"[:300])
        if started and self.trainer.vorschlag and self.trainer.vorschlag.get("aufgabe") == plans[0].get("aufgabe"):
            self.trainer.vorschlag = None
        text = (f"{len(started)} Läufe gestartet" if len(started) > 1 else
                f"Job {started[0].get('job')} gestartet" if started else "fehlgeschlagen")
        self.training_job = {"laeuft": False, "text": text, "fehler": " · ".join(errors) or None}
        await self.broadcast(self.training_message())

    async def pull_model(self, model: str) -> None:
        job = self.pulls[model] = {"laeuft": True, "status": "startet …", "anteil": None, "fehler": None}
        self._voice_changed()

        def progress(status: str, frac: float | None) -> None:
            job["status"] = status
            job["anteil"] = round(frac, 3) if frac is not None else job["anteil"]
            self._voice_changed()

        try:
            await self.agent.local.pull(model, progress)
            job.update(laeuft=False, status="geladen", anteil=1.0)
        except Exception as exc:
            job.update(laeuft=False, fehler=f"{type(exc).__name__}: {exc}", status="fehlgeschlagen")
        self._voice_changed()
