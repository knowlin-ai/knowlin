"""Konformitätsprüfung der Körperschnittstelle (seit 0.38.35): Hält ein Körper die Pflichten ein?

Für jeden, der einen Körper für Knowlin baut – eingebaut oder als eigenes Paket. Geprüft wird nur über die öffentliche
Schnittstelle (`DuckBackend`), mit kurzen echten Wartezeiten; ein Simulator braucht dafür ≈ 3 s.

    python -m duckpilot.koerper_pruefung              # alle Körper mit Simulator
    python -m duckpilot.koerper_pruefung open_duck_mini

Am echten Roboter nur mit freier Umgebung und Hand am Not-Aus prüfen: Die Prüfung schaltet die Motoren ein und
fährt kurz an (mit der kleinsten erlaubten Geschwindigkeit, nie mit Gelenken).

Pflichten (P = muss, E = empfohlen):
- P1 Profil gültig, Fähigkeiten nur aus dem Wortschatz (`koerper.FAEHIGKEITEN`, `x-…`).
- P2 `eigenschaften()` ⊆ Profil ∪ Betrieb – der Körper behauptet nichts, was sein Profil nicht nennt.
- P3 `connect()` innerhalb von 5 s; `state()` wirft nie und meldet `connected`.
- P4 Zustand lässt sich als JSON senden, `koerper` = Profil.
- P5 Not-Aus: `relax()` gelingt, danach ist `powered` aus (≤ 1 s).
- P6 Stromlos bewegt sich nichts: `move()` nach `relax()` bewegt den Körper nicht.
- P7 Grenzen: Fortbewegung und Kopf bleiben in `api.LIMITS`, auch bei viel zu großen Befehlen.
- P8 Stopp hält an: nach `stop()` ist die Geschwindigkeit null (≤ 1 s) – ohne stromlos zu werden.
- P9 `close()` innerhalb von 5 s.
- E1 Unbekannter Skill und unbekannter Ton werden abgelehnt statt zu werfen.
"""

from __future__ import annotations

import asyncio
import json
import sys
from dataclasses import dataclass
from typing import Any

from . import koerper as K
from .api import LIMITS, Head, Twist

WARTEN_S = 1.0


@dataclass
class Ergebnis:
    pflicht: str
    ok: bool
    text: str

    def zeile(self) -> str:
        return f"{'✓' if self.ok else '✗'} {self.pflicht} {self.text}"


async def _bis(bedingung: Any, sek: float = WARTEN_S) -> bool:
    ende = asyncio.get_running_loop().time() + sek
    while asyncio.get_running_loop().time() < ende:
        if bedingung():
            return True
        await asyncio.sleep(0.05)
    return bool(bedingung())


def _in_grenzen(wert: float, key: str, toleranz: float = 1e-3) -> bool:
    lo, hi = LIMITS[key]
    return lo - toleranz <= wert <= hi + toleranz


async def pruefen(be: Any, profil: K.Koerper, echt: bool = False) -> list[Ergebnis]:
    """Alle Pflichten an einem gebauten (noch nicht verbundenen) Körper prüfen."""
    r: list[Ergebnis] = []
    f = profil.fehler()
    r.append(Ergebnis("P1", not f, "Profil gültig" if not f else "; ".join(f)))

    try:
        await asyncio.wait_for(be.connect(), 5.0)
        r.append(Ergebnis("P3", True, "verbindet sich"))
    except Exception as exc:  # noqa: BLE001
        r.append(Ergebnis("P3", False, f"connect(): {type(exc).__name__}: {exc}"))
        return r
    await asyncio.sleep(0.2)
    try:
        st = be.state()
        r.append(Ergebnis("P3", bool(st.connected), "meldet verbunden" if st.connected else
                          f"meldet nicht verbunden ({'; '.join(st.limited_by) or 'ohne Grund'})"))
    except Exception as exc:  # noqa: BLE001
        r.append(Ergebnis("P3", False, f"state(): {type(exc).__name__}: {exc}"))
        return r

    eig = set(be.eigenschaften())
    zuviel = sorted(eig - set(profil.faehigkeiten) - set(K.BETRIEB))
    r.append(Ergebnis("P2", not zuviel, "Eigenschaften passen zum Profil" if not zuviel else
                      f"nicht im Profil: {', '.join(zuviel)}"))
    try:
        json.dumps(st.to_dict(), default=str)
        ok = st.koerper == profil.koerper_zustand
        r.append(Ergebnis("P4", ok, "Zustand als JSON, Körper stimmt" if ok else
                          f"state().koerper = „{st.koerper}“, Profil sagt „{profil.koerper_zustand}“"))
    except Exception as exc:  # noqa: BLE001
        r.append(Ergebnis("P4", False, f"Zustand nicht als JSON: {exc}"))

    await be.init()
    await be.enable(True)
    await _bis(lambda: be.state().powered, 3.0)
    faehrt = eig & K.FORTBEWEGUNG
    if faehrt:
        # Viel zu großer Befehl → Grenzen
        zu_gross = Twist(5.0, 5.0, 5.0) if not echt else Twist(LIMITS["vx"][1] * 4, 0.0, 0.0)
        for _ in range(8):
            await be.move(zu_gross)
            await asyncio.sleep(0.05)
        t = be.state().twist
        ok = all(_in_grenzen(v, k) for v, k in ((t.vx, "vx"), (t.vy, "vy"), (t.vyaw, "vyaw")))
        r.append(Ergebnis("P7", ok, "Fortbewegung in den Grenzen" if ok else f"zu schnell: {t}"))
        res = await be.stop()
        await be.move(Twist())
        still = await _bis(lambda: be.state().twist.is_zero(0.02))
        r.append(Ergebnis("P8", bool(res.accepted) and still, "Stopp hält an" if still else
                          f"nach stop() noch {be.state().twist}"))
        r.append(Ergebnis("P8", be.state().powered, "Stopp lässt den Strom an" if be.state().powered else
                          "stop() hat stromlos gemacht – dafür ist relax() da"))
    if "kopf" in eig:
        await be.head(Head(9.0, 9.0, 9.0, 9.0))
        await asyncio.sleep(0.4)
        h = be.state().head
        ok = all(_in_grenzen(v, k, 0.02) for v, k in ((h.neck_pitch, "neck_pitch"), (h.head_pitch, "head_pitch"),
                                                     (h.head_yaw, "head_yaw"), (h.head_roll, "head_roll")))
        r.append(Ergebnis("P7", ok, "Kopf in den Grenzen" if ok else f"Kopf außerhalb: {h}"))

    res = await be.relax()
    aus = await _bis(lambda: not be.state().powered)
    r.append(Ergebnis("P5", bool(res.accepted) and aus, "Not-Aus macht stromlos" if aus else
                      f"nach relax() noch unter Strom ({res.reason or 'ohne Meldung'})"))
    if faehrt:
        for _ in range(6):
            await be.move(Twist(0.2, 0.0, 0.5))
            await asyncio.sleep(0.05)
        t = be.state().twist
        r.append(Ergebnis("P6", t.is_zero(0.02), "stromlos bewegt sich nichts" if t.is_zero(0.02) else
                          f"bewegt sich stromlos: {t}"))
    try:
        a = await be.do("gibt_es_nicht_42")
        b = await be.sound("gibt_es_nicht_42")
        r.append(Ergebnis("E1", not a.accepted and not b.accepted, "Unbekanntes wird abgelehnt"))
    except Exception as exc:  # noqa: BLE001
        r.append(Ergebnis("E1", False, f"wirft bei Unbekanntem: {type(exc).__name__}: {exc}"))
    try:
        await asyncio.wait_for(be.close(), 5.0)
        r.append(Ergebnis("P9", True, "schließt sauber"))
    except Exception as exc:  # noqa: BLE001
        r.append(Ergebnis("P9", False, f"close(): {type(exc).__name__}: {exc}"))
    return r


def bestanden(ergebnisse: list[Ergebnis]) -> bool:
    return all(e.ok for e in ergebnisse if e.pflicht.startswith("P"))


async def _sim_pruefen(profil: K.Koerper) -> list[Ergebnis]:
    from types import SimpleNamespace

    cfg = SimpleNamespace(backend="sim", modul=profil.id, sim_physik=False, koerper_optionen={},
                          reachy_adresse="http://localhost:8000", robot="", tof=None, head_signs=None, updater=None)
    return await pruefen(profil.bauen(cfg), profil)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    profile = [K.holen(i) for i in argv] if argv else [k for k in K.alle() if k.simulator]
    alles_ok = True
    for p in profile:
        if not p.simulator:
            print(f"{p.name} ({p.id}): kein Simulator – am echten Roboter mit pruefen(…, echt=True) prüfen")
            continue
        erg = asyncio.run(_sim_pruefen(p))
        ok = bestanden(erg)
        alles_ok &= ok
        print(f"{p.name} ({p.id}) – {'bestanden' if ok else 'NICHT bestanden'}")
        for e in erg:
            print("  " + e.zeile())
    for name, grund in K.abgelehnt().items():
        alles_ok = False
        print(f"Erweiterung „{name}“ abgelehnt: {grund}")
    return 0 if alles_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
