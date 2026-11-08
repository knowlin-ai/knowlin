"""Die Lernschleife: am PC lernen, auf dem Parcours prüfen, weiterlernen – bis sie es kann oder die Zeit um ist.

Eine Runde = ein Lauf von `physics/lernen.py` (PPO am PC) mit einem Teil des Zeitbudgets. Danach prüft der Parcours-
Test das Ergebnis genau so wie jede andere Policy (drei Durchgänge, sichtbar unter Lernen → Parcours). Die nächste
Runde setzt auf dem **besten** bisher geprüften Stand auf – ein schlechterer Stand wird nie zur Grundlage.

Ohne Schleife ist es ein einzelner Lauf mit dem ganzen Budget (auch auf ebenem Boden ohne Parcours).
Kostenlos, deshalb darf auch Claude es starten (Werkzeug `training_kostenlos`). Die Ente selbst bewegt sich dabei
nicht: alles rechnet in eigenen, unsichtbaren MuJoCo-Welten.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Awaitable, Callable

from .aio import spawn

log = logging.getLogger(__name__)

MIN_BUDGET = 5            # Minuten
MAX_BUDGET = 600
MIN_RUNDE = 5
MAX_RUNDE = 60
VERSUCHE = 3              # Durchgänge pro Parcours-Prüfung
MAX_RUNDEN = 40
POLL_S = 2.0              # so oft wird der laufende Lauf nachgefragt


def _clamp(v: Any, lo: float, hi: float, default: float) -> float:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return default
    if x != x:
        return default
    return max(lo, min(hi, x))


def wertung(test: dict[str, Any]) -> tuple[int, int, int]:
    """Wie gut war ein Parcours-Test? Erst „im Ziel“, dann geschaffte Elemente, dann weniger Stürze."""
    return (int(test.get("im_ziel") or 0), sum(int(e.get("geschafft") or 0) for e in test.get("elemente") or []),
            -int(test.get("stuerze") or 0))


def runden_minuten(budget: float, wunsch: Any = None) -> float:
    """Länge einer Runde: ein Viertel des Budgets, 5–60 Minuten (höchstens das ganze Budget)."""
    r = _clamp(wunsch, MIN_RUNDE, MAX_RUNDE, max(MIN_RUNDE, min(MAX_RUNDE, budget / 4)))
    return round(min(budget, r), 1)


class LearnLoop:
    def __init__(self, trainer, lab, push: Callable[[], None], chat: Callable[[str], Awaitable[None]] | None = None,
                 note: Callable[[dict[str, Any]], None] | None = None) -> None:
        self.trainer = trainer          # physics.lernen.LocalTrainer
        self.lab = lab                  # mission.CourseLab
        self.push = push
        self.chat = chat
        self.note = note
        self.job: dict[str, Any] = {}
        self._task: asyncio.Task | None = None
        self._stop = False

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    # ── Start / Stopp ────────────────────────────────────────────────────
    async def start(self, body: dict[str, Any]) -> dict[str, Any]:
        from .physics import lernen as L

        if self.running or self.trainer.status().get("laeuft"):
            raise ValueError("Es lernt schon – erst den laufenden Lauf beenden.")
        ok, why = L.available()
        if not ok:
            raise ValueError(why)
        budget = round(_clamp(body.get("minuten"), MIN_BUDGET, MAX_BUDGET, 60), 1)
        schleife = bool(body.get("lernschleife", True))
        quelle = str(body.get("quelle") or "standard")
        L.aufloesen(self.trainer.root, quelle)          # früh und verständlich scheitern
        mission = self.lab.missions.current() or {}
        spec = mission.get("parcours") if body.get("parcours", True) else None
        if schleife and not spec:
            raise ValueError("Für die Lernschleife braucht es einen Parcours (Lernen → Parcours). Ohne Schleife lernt "
                             "sie auf ebenem Boden geradeaus.")
        runde = runden_minuten(budget, body.get("runde_minuten")) if schleife else budget
        geraet = str(body.get("geraet") or "auto")
        if geraet not in ("auto", "cpu", "gpu"):
            raise ValueError("Gerät: auto, cpu oder gpu")
        name = (self.lab.course().name if spec and self.lab.course() else "Ebener Boden")
        self._stop = False
        self.job = {
            "laeuft": True, "phase": "startet …", "schleife": schleife, "budget_minuten": budget,
            "runde_minuten": runde, "start": time.strftime("%Y-%m-%d %H:%M"), "t0": time.time(), "ende": None,
            "von": "claude" if body.get("von") == "claude" else "mensch",
            "begruendung": str(body.get("begruendung") or "")[:300], "quelle_start": quelle, "parcours": name,
            "auftrag": mission.get("id") if spec else None, "runden": [], "vorher": None, "bester": None,
            "geschafft": False, "fehler": None, "ergebnis": None, "geraet": geraet,
        }
        self._task = spawn(self._run(spec, quelle, budget, runde, schleife, name, geraet))
        self.push()
        return self.status()

    async def stop(self, warten: float = 0.0) -> dict[str, Any]:
        self._stop = True
        if self.job.get("laeuft"):
            self.job["phase"] = "hört auf – speichert den besten Stand …"
        try:
            self.lab.cancel()
        except Exception:
            pass
        await asyncio.to_thread(self.trainer.stop, warten)
        self.push()
        return self.status()

    def status(self) -> dict[str, Any]:
        j = dict(self.job)
        if j.get("laeuft") and j.get("t0"):
            j["verbraucht_minuten"] = round((time.time() - j["t0"]) / 60, 1)
        return j

    # ── die Schleife ─────────────────────────────────────────────────────
    async def _test(self, quelle: str) -> dict[str, Any] | None:
        for _ in range(30):                              # läuft gerade ein anderer Test? kurz warten
            try:
                return await self.lab.test(quelle, VERSUCHE, auto=True)
            except ValueError as exc:
                if "läuft schon" not in str(exc) or self._stop:
                    raise
            await asyncio.sleep(POLL_S)
        raise ValueError("Der Parcours-Test war die ganze Zeit belegt.")

    async def _run(self, spec, quelle: str, budget: float, runde: float, schleife: bool, name: str, geraet: str) -> None:
        j = self.job
        deadline = time.monotonic() + budget * 60
        best: dict[str, Any] | None = None
        try:
            # 1. vorher: wie gut kann es die Start-Policy schon?
            if schleife:
                j["phase"] = "prüft den Ausgangsstand auf dem Parcours …"
                self.push()
                t = await self._test(quelle)
                j["vorher"] = {"quelle": quelle, "im_ziel": t["im_ziel"], "versuche": t["versuche"], "test": t["id"]}
                best = {"quelle": quelle, "im_ziel": t["im_ziel"], "versuche": t["versuche"], "runde": 0,
                        "wertung": list(wertung(t))}
                j["bester"] = best
                if t["im_ziel"] >= t["versuche"]:
                    j["geschafft"] = True
                    j["phase"] = f"sie kann es schon – {t['im_ziel']} von {t['versuche']} im Ziel, nichts zu lernen"
                    return
            # 2. Runden
            n = 0
            while not self._stop and n < MAX_RUNDEN:
                rest = (deadline - time.monotonic()) / 60
                if rest < (1 if not schleife else min(MIN_RUNDE, runde) * 0.5):
                    break
                n += 1
                dauer = round(min(runde if schleife else budget, rest), 1)
                info: dict[str, Any] = {"runde": n, "von": quelle, "minuten": dauer, "lauf": None, "ergebnis": None,
                                        "faehigkeit": None, "test": None}
                j["runden"].append(info)
                j["phase"] = f"Runde {n}: lernt ({dauer:g} min) …" if schleife else f"lernt ({dauer:g} min) …"
                label = f"{name} · Runde {n}" if schleife else name
                st = await asyncio.to_thread(self.trainer.start, spec, quelle, dauer, label, None, geraet=geraet)
                info["lauf"] = st.get("id")
                self.push()
                while True:
                    await asyncio.sleep(POLL_S)
                    st = self.trainer.status()
                    self.push()
                    if not st.get("laeuft"):
                        break
                    if time.monotonic() > deadline + 120:          # Sicherheitsnetz: Budget weit überzogen
                        await asyncio.to_thread(self.trainer.stop, 0.0)
                info.update(ergebnis=st.get("ergebnis"), faehigkeit=(st.get("bester") or {}).get("faehigkeit"),
                            iterationen=st.get("iteration"), geraet=st.get("geraet"))
                if not st.get("ergebnis"):
                    j["fehler"] = st.get("fehler") or "Kein Ergebnis aus dieser Runde."
                    break
                j["ergebnis"] = st["ergebnis"]
                if not schleife:
                    break
                if self._stop:
                    break
                j["phase"] = f"Runde {n}: prüft auf dem Parcours …"
                self.push()
                t = await self._test(st["ergebnis"])
                info["test"] = {"im_ziel": t["im_ziel"], "versuche": t["versuche"], "id": t["id"]}
                info["test"]["elemente"] = wertung(t)[1]
                w = wertung(t)
                besser = best is None or w > tuple(best["wertung"])
                info["besser"] = besser
                if best is None or not besser:
                    info["warum"] = "neuer Bestwert" if besser else "nicht besser – weiter vom besten Stand"
                else:
                    alt = tuple(best["wertung"])
                    info["warum"] = ("mehr im Ziel" if w[0] > alt[0] else "weiter gekommen" if w[1] > alt[1]
                                     else "weniger Stürze")
                if besser:
                    best = {"quelle": st["ergebnis"], "im_ziel": t["im_ziel"], "versuche": t["versuche"], "runde": n,
                            "wertung": list(wertung(t))}
                    j["bester"] = best
                quelle = best["quelle"]                    # immer vom besten geprüften Stand weiter
                self.push()
                if t["im_ziel"] >= t["versuche"]:
                    j["geschafft"] = True
                    break
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.exception("Lernschleife")
            j["fehler"] = str(exc)[:300]
        finally:
            if not j.get("ende"):
                self._finish()

    def _finish(self) -> None:
        j = self.job
        j["laeuft"] = False
        j["ende"] = time.strftime("%Y-%m-%d %H:%M")
        j["verbraucht_minuten"] = round((time.time() - j.get("t0", time.time())) / 60, 1)
        best, vorher = j.get("bester"), j.get("vorher")
        if j.get("geschafft") and j.get("runden"):
            text = (f"Geschafft: Nach {len(j['runden'])} Runde{'n' if len(j['runden']) != 1 else ''} läuft sie "
                    f"{best['im_ziel']} von {best['versuche']} Mal durch den Parcours „{j['parcours']}“")
            text += f" (vorher {vorher['im_ziel']} von {vorher['versuche']})." if vorher else "."
        elif j.get("geschafft"):
            text = j["phase"][:1].upper() + j["phase"][1:] + "."
        elif j.get("fehler") and not j.get("ergebnis"):
            text = f"Das Lernen am PC ist fehlgeschlagen: {j['fehler']}"
        elif j.get("schleife") and best and vorher:
            gain = best["im_ziel"] - vorher["im_ziel"]
            nr = len(j["runden"])
            text = (f"Die Zeit ist um ({j['verbraucht_minuten']:g} min, {nr} Runde{'n' if nr != 1 else ''}). Bester Stand: "
                    f"{best['im_ziel']} von {best['versuche']} im Ziel (vorher {vorher['im_ziel']})."
                    + (" Es hat noch nicht geholfen – längere Runden oder eine leichtere Stelle zum Üben probieren."
                       if gain <= 0 else " Weiterlernen setzt auf diesem Stand auf."))
        else:
            text = "Fertig gelernt – das Ergebnis steht unter Lernen → Training → Dieser PC und im Parcours zur Auswahl."
        if self._stop and not j.get("geschafft"):
            text = "Lernen beendet – " + text[0].lower() + text[1:]
        j["phase"] = "fertig" if not j.get("fehler") or j.get("ergebnis") else "fehlgeschlagen"
        j["fazit"] = text
        if self.note:
            try:
                self.note({"type": "training", "message": text})
            except Exception:
                pass
        self.push()
        if self.chat:
            spawn(self.chat(text))
