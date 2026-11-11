"""Laufzeit, Bereich Reachy Mini (seit 0.38.2): Pollens 3D-Modell und Bewegungsbibliotheken nachladen, abspielen.

Teil der Klasse `Runtime` (server/runtime.py), ausgelagert wie `runtime_lab.py`. Schicht: Verbindung. Lädt nichts,
solange Reachy Mini nicht der Körper ist – erst beim Zuweisen (oder per Knopf unter Einstellungen → Körper).
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from typing import Any

from .. import settings as S
from ..aio import spawn

log = logging.getLogger(__name__)


class PollenAdapter:
    """Was das Gehirn von Pollens Bibliotheken sieht (`ToolRunner.pollen`) – ohne den Körper zu kennen."""

    def __init__(self, rt: "ReachyTeil") -> None:
        self.rt = rt

    def liste(self) -> list[dict[str, Any]]:
        return self.rt.reachy_bewegungen.liste()

    async def spielen(self, name: str) -> dict[str, Any]:
        return await self.rt.reachy_spielen(name)


# Reachys eigener Leerlauf (seit 0.38.3): ab und zu eine ruhige Bewegung aus Pollens Bibliothek statt Entengesten
LEERLAUF_STAEMME = ("attentive", "curious", "serenity", "thoughtful", "inquiring", "calming", "boredom", "understanding")
LEERLAUF_S = (90.0, 240.0)


class ReachyTeil:
    """Mischklasse für `Runtime` – nicht allein benutzbar."""

    async def _reachy_leerlauf(self) -> None:
        """Reachy zeigt im Leerlauf von sich aus kleine Regungen – nie mitten in etwas, nie nach einem Not-Aus."""
        rng = random.Random()
        while True:
            await asyncio.sleep(rng.uniform(*LEERLAUF_S))
            try:
                if not (self.ist_reachy() and self.config.idle_life) or self.engine.busy():
                    continue
                if self.engine.notaus_gesperrt() or self.engine.still or (self.alltag.on and self.alltag.mode == "ruhe"):
                    continue
                st = self.backend.state()
                if not st.powered or st.sitting or st.mouth > 0.05:
                    continue
                ruhig = [x["name"] for x in self.reachy_bewegungen.liste()
                         if x["art"] == "emotionen" and x["name"].rstrip("0123456789").rstrip("_") in LEERLAUF_STAEMME]
                if ruhig:
                    await self.reachy_spielen(rng.choice(ruhig), ton=False)   # im Leerlauf leise
            except Exception:  # noqa: BLE001 – Leerlauf darf nie etwas anderes stören
                log.debug("Reachy-Leerlauf", exc_info=True)

    async def _reachy_begruessen(self) -> None:
        """Begrüßung beim Aufwecken (seit 0.38.13, wie Pollens App „Reachy Mini Greetings“): Antennen hoch, Kopf heben,
        nicken, kurz zur Seite schauen – und ein kurzer Satz mit Tageszeit, deinem Namen und seinem. Nur beim Aufwecken
        (`koerper_betreten`, Körperwechsel), abschaltbar (`reachy_begruessung`). Während der Not-Aus-Sperre nur der Satz,
        keine Bewegung."""
        from .. import i18n
        from ..motion.reachy_tanz import begruessung, begruessung_text

        if not self.config.reachy_begruessung:
            return
        for _ in range(40):                                # erst ganz aufwachen lassen (Pollens Aufwachen läuft)
            st = self.backend.state()
            if st.powered and not st.sitting and not st.skill:
                break
            await asyncio.sleep(0.1)
        if not self.engine.notaus_gesperrt() and not self.engine.still and not self.engine.busy():
            self.engine.run(begruessung())
        if self.config.tts:
            stunde = time.localtime().tm_hour
            await self._duck_says(begruessung_text(self.config.duck_name, self.config.nutzer_name, stunde, i18n.t))

    def _reachy_einrichten(self) -> None:
        from ..modell.reachy import ReachyModellStore
        from ..modell.reachy_bewegungen import ReachyBewegungen

        root = S.settings_path().parent
        self.reachy_modell = ReachyModellStore(root)
        self.reachy_bewegungen = ReachyBewegungen(root)
        self._reachy_lade_job: dict[str, Any] = {}

    def ist_reachy(self) -> bool:
        return getattr(self.backend, "koerper_art", "") == "reachy_mini"

    def reachy_message(self) -> dict[str, Any]:
        return {"type": "reachy", "modell": self.reachy_modell.status(), "bewegungen": self.reachy_bewegungen.status()}

    def reachy_beim_zuweisen(self) -> None:
        """Reachy Mini ist jetzt der Körper: fehlt Modell oder Bibliothek, im Hintergrund holen (nie offline)."""
        if self.ist_reachy():                                  # Gefühle manchmal mit Pollens Aufnahmen (seit 0.38.10)
            self.engine.pollen_gefuehl = self._reachy_gefuehl
        if not self.ist_reachy() or self._reachy_lade_job.get("laeuft"):
            return
        if self.reachy_modell.missing() or not self.reachy_bewegungen.da():
            self._tasks.append(asyncio.create_task(self.reachy_laden(), name="reachy-laden"))

    def _reachy_gefuehl(self, staemme: tuple[str, ...]) -> bool:
        """Eine passende Aufnahme aus Pollens Bibliothek starten (mit Ton) – False, wenn keine da ist."""
        if not self.ist_reachy():
            return False
        namen = [x["name"] for x in self.reachy_bewegungen.liste()
                 if x["art"] == "emotionen" and x["name"].rstrip("0123456789").rstrip("_") in staemme]
        if not namen:
            return False
        spawn(self.reachy_spielen(random.choice(namen)))
        return True

    async def reachy_laden(self, force: bool = False, was: tuple[str, ...] = ("modell", "bewegungen")) -> None:
        from ..modell.reachy import offline

        job = self._reachy_lade_job
        if job.get("laeuft"):
            return
        if offline():
            return
        job.update({"laeuft": True, "fehler": None})
        loop = asyncio.get_running_loop()

        def progress(store: Any):
            def melde(text: str) -> None:
                store.job = {"laeuft": True, "text": text, "fehler": None}
                loop.call_soon_threadsafe(lambda: spawn(self.broadcast(self.reachy_message())))
            return melde

        for name, store in (("modell", self.reachy_modell), ("bewegungen", self.reachy_bewegungen)):
            if name not in was:
                continue
            store.job = {"laeuft": True, "text": "startet …", "fehler": None}
            await self.broadcast(self.reachy_message())
            try:
                res = await asyncio.to_thread(store.ensure, progress(store), force)
                store.job = {"laeuft": False, "fehler": None, "text": "fertig" if res else "schon da"}
                if name == "modell" and res:                   # Kopfprüfung jetzt mit Pollens Geometrie (0.38.10)
                    from ..backends.reachy_kinematik import geometrie_neu_laden

                    geometrie_neu_laden()
            except Exception as exc:  # noqa: BLE001 – Laden darf nie den Rest stören
                from ..fehlerort import einordnen

                log.warning("Pollens Reachy-%s nicht geladen: %s", name, exc)
                store.job = {"laeuft": False, "text": "fehlgeschlagen", "fehler": einordnen(exc, "GitHub" if name == "modell" else "Hugging Face")}
            await self.broadcast(self.reachy_message())
        job["laeuft"] = False

    # ── Pollens Apps (seit 0.38.19) ────────────────────────────────────────
    def _reachy_apps(self) -> Any:
        """Pollens App-Verwaltung des echten Reachy (über den Daemon) – im Simulator gibt es keine."""
        return getattr(self.backend, "apps", None) if self.ist_reachy() else None

    async def reachy_apps(self, katalog: bool = False) -> dict[str, Any]:
        apps = self._reachy_apps()
        if apps is None:
            return {"ok": False, "verfuegbar": False,
                    "fehler": "Pollens Apps laufen auf dem echten Reachy Mini – im Simulator gibt es sie nicht"}
        try:
            laeuft = await apps.status()
            daten: dict[str, Any] = {"ok": True, "verfuegbar": True, "laeuft": laeuft,
                                     "installiert": await apps.installiert()}
            if katalog:
                daten["katalog"] = await apps.katalog()
            return daten
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "verfuegbar": True, "fehler": f"Pollens Daemon antwortet nicht: {exc}"}

    async def reachy_app_starten(self, name: str) -> dict[str, Any]:
        """Eine installierte App starten – nie während der Not-Aus-Sperre, nie mitten in einer eigenen Bewegung."""
        apps = self._reachy_apps()
        if apps is None:
            return {"ok": False, "fehler": "Pollens Apps laufen nur auf dem echten Reachy Mini"}
        if self.engine.notaus_gesperrt():
            return {"ok": False, "fehler": "Nach dem Not-Aus noch gesperrt – kurz warten"}
        if self.engine.busy():
            return {"ok": False, "fehler": "Reachy ist gerade beschäftigt – erst fertig machen lassen"}
        try:
            if name not in {a["name"] for a in await apps.installiert()}:
                return {"ok": False, "fehler": f"„{name}“ ist auf dem Reachy nicht installiert"}
            res = await apps.starten(name)
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "fehler": f"Pollens Daemon startet sie nicht: {exc}"}
        self.engine.note({"type": "behavior_start", "name": f"Pollens App {name}"})
        await self.broadcast({"type": "reachy_app", "laeuft": res})
        return {"ok": True, "laeuft": res}

    async def reachy_app_stoppen(self) -> dict[str, Any]:
        apps = self._reachy_apps()
        if apps is None:
            return {"ok": False, "fehler": "Es läuft keine App von Pollen"}
        try:
            await apps.stoppen()
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "fehler": f"Pollens Daemon hält sie nicht an: {exc}"}
        await self.broadcast({"type": "reachy_app", "laeuft": None})
        return {"ok": True}

    async def reachy_app_installieren(self, name: str) -> dict[str, Any]:
        apps = self._reachy_apps()
        if apps is None:
            return {"ok": False, "fehler": "Pollens Apps laufen nur auf dem echten Reachy Mini"}
        try:
            return {"ok": True, "auftrag": await apps.installieren(name)}
        except ValueError as exc:
            return {"ok": False, "fehler": str(exc)}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "fehler": f"Pollens Daemon installiert sie nicht: {exc}"}

    async def reachy_app_auftrag(self, job: str) -> dict[str, Any]:
        apps = self._reachy_apps()
        if apps is None:
            return {"ok": False, "fehler": "kein Reachy"}
        try:
            return {"ok": True, **await apps.auftrag(job)}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "fehler": str(exc)}

    async def reachy_spielen(self, name: str, ton: bool = True) -> dict[str, Any]:
        """Eine von Pollens Aufnahmen abspielen. Im Simulator kommt der Ton aus dem Browser, am Roboter von ihm selbst."""
        if not self.ist_reachy():
            return {"ok": False, "fehler": "Pollens Bewegungen gibt es nur für Reachy Mini"}
        if name in ("zufall", "zufall_emotion", "zufall_tanz"):      # Schnellbefehl „Ein Gefühl von Pollen“
            art = "taenze" if name == "zufall_tanz" else "emotionen"
            kandidaten = [x["name"] for x in self.reachy_bewegungen.liste() if x["art"] == art]
            name = random.choice(kandidaten) if kandidaten else name
        a = self.reachy_bewegungen.get(name)
        if a is None:
            if not self.reachy_bewegungen.da():
                return {"ok": False, "fehler": "Pollens Bewegungen sind noch nicht geladen (Einstellungen → Körper)"}
            return {"ok": False, "fehler": f"„{name}“ gibt es nicht", "beispiele": [x["name"] for x in self.reachy_bewegungen.liste()[:12]]}
        res = await self.backend.pollen_bewegung(a)
        if res.accepted and ton and a.ton and self.backend.state().backend == "sim":
            await self.broadcast({"type": "reachy_ton", "url": f"/api/reachy/ton/{a.art}/{a.ton}", "name": a.name})
        if res.accepted:
            self.engine.note({"type": "behavior_start", "name": f"Pollens {a.name}"})
        return {"ok": res.accepted, "gestartet" if res.accepted else "fehler": res.reason, "dauer_s": round(a.dauer, 1)}
