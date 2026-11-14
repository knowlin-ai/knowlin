"""Stack-chan im Simulator (seit 0.38.58): ein Schreibtisch-Roboter mit Gesicht.

Stack-chan ist ein offenes Projekt der Community (Apache-2.0, https://github.com/stack-chan/stack-chan), seit 2026 auch
als Bausatz von M5Stack: ein kleiner Würfel mit Bildschirm als Kopf (M5Stack CoreS3), darunter zwei Servos – einer dreht
den Kopf, einer nickt –, dazu Kamera, zwei Mikrofone und ein Lautsprecher. Er hat **keine Beine und keinen Arm**: Er
zeigt, was er meint, mit Kopf und Gesicht. In der 3D-Ansicht (`static/stackchan3d.js`) seit 0.38.61 mit Gehäuse und
Füßen aus den offenen Gehäusedaten der Community; Bildschirm und Gesicht zeichnet Knowlin.

Er steht wie Reachy als Tischroboter auf dem Couchtisch (`TischPlatz`), fällt nicht um und schiebt nichts. Das Gesicht
meldet er als `state().gesicht`: welches Gefühl gerade zu sehen ist, wie weit der Mund offen ist, ob er wach ist und ob
er gerade zuhört oder nachdenkt. Not-Aus macht ihn wie jeden Körper stromlos – der Kopf sinkt, die Augen gehen zu.

Grenzen seit 0.38.62 nach M5Stacks Angaben zum StackChan (Funktionsabgleich, Maintainer: „Ok“): Drehen ist am echten
Gerät endlos – im Simulator bis ±170°; Nicken hat 80° Spielraum, fast nur nach oben (die abgerundete Unterkante der
Schale gibt den Platz frei), nach unten 10°. Dazu wie beim Original: Berührung oben auf dem Kopf (streicheln → froh,
schütteln → schwindelig), nach fünf Minuten ohne Ansprache schläft er ein, und die LEDs zeigen grün beim Zuhören und
blau beim Sprechen (state().gesicht.led). Der echte Stack-chan ist noch nicht angebunden.
"""

from __future__ import annotations

import math
from typing import Any

from ..api import DuckState, Head, IntentResult, Perception, Twist
from .sim import SimBackend
from .tischplatz import STANDARD_FLAECHE, TischPlatz

EIGENSCHAFTEN = frozenset({"kopf", "gesicht", "beruehrung", "kamera", "mikrofon", "lautsprecher"})
KOPF_DREH = math.radians(170)            # echt: endlos drehbar
KOPF_HOCH = math.radians(80)             # nicken nach oben (pitch negativ)
KOPF_RUNTER = math.radians(10)           # nicken nach unten (pitch positiv)
SCHLAF_NICKEN = KOPF_RUNTER              # Kopf gesenkt, wenn er schläft oder stromlos ist
SCHLAF_NACH = 300.0                      # Sekunden ohne Ansprache, dann schläft er ein (wie das Original)
FUSS_M = 0.03                           # Fuß ≈ 5,5 cm im Quadrat
OHNE_BEINE = "Stack-chan hat keine Beine und keinen Arm – er zeigt es mit Kopf und Gesicht"

# Gefühle (Namen aus motion/choreografie.EMOTIONS) → Ausdruck im Gesicht. Unbekannte zeigen das ruhige Gesicht.
AUSDRUECKE = ("ruhig", "froh", "traurig", "ueberrascht", "wuetend", "muede", "neugierig", "verlegen", "schwindelig")
_GEFUEHL: dict[str, str] = {
    **dict.fromkeys(("freude", "begeistert", "stolz", "erleichtert", "lachen", "begruessen", "jawohl", "jep", "traellern",
                     "aufgeregt", "hibbeln", "ja", "nicken"), "froh"),
    **dict.fromkeys(("traurig", "betruebt", "am_boden", "seufzen", "einfuehlsam"), "traurig"),
    **dict.fromkeys(("ueberrascht", "staunen", "erschrecken", "was_was", "aufhorchen", "niesen", "schluckauf"),
                    "ueberrascht"),
    **dict.fromkeys(("wuetend", "frustriert", "trotzig", "grummelig", "ungeduldig", "naeaeae", "wer_sagt_das"), "wuetend"),
    **dict.fromkeys(("muede", "gaehnen", "doesen", "tot_stellen"), "muede"),
    **dict.fromkeys(("neugierig", "umherspaehen", "mustern", "himmel_gucken", "hmm"), "neugierig"),
    **dict.fromkeys(("verlegen", "stolpern"), "verlegen"),
    **dict.fromkeys(("schwindelig", "verwirrt"), "schwindelig"),
}


def ausdruck_aus(gefuehl: str) -> str:
    """Name eines Gefühls → Ausdruck im Gesicht (einer aus AUSDRUECKE)."""
    return _GEFUEHL.get(str(gefuehl or "").strip().lower(), "ruhig")


def kopf_lage(head: Head) -> dict[str, float]:
    """Kopfbefehl (Gelenke der Ente) → Drehen und Nicken von Stack-chan, begrenzt auf das, was er sicher kann."""
    pitch = max(-KOPF_HOCH, min(KOPF_RUNTER, head.head_pitch - head.neck_pitch * 0.6))
    yaw = max(-KOPF_DREH, min(KOPF_DREH, head.head_yaw))
    return {"yaw": round(yaw, 4), "pitch": round(pitch, 4)}


class StackChanSim(TischPlatz, SimBackend):
    """Stack-chan im Simulator: gleiches Wohnzimmer, steht auf dem Couchtisch, Kopf und Gesicht statt Beinen."""

    koerper_art = "stackchan"
    platz_name = "Stack-chan"
    fuss_m = FUSS_M

    def __init__(self, realtime: bool = True, seed: int | None = None) -> None:
        super().__init__(realtime=realtime, seed=seed)
        self.stand_z = 0.0
        self.standflaeche = ""
        self._ausdruck = "ruhig"
        self._ausdruck_bis = 0.0
        self._gespraech: str | None = None
        self._gespraech_bis = 0.0
        self._angesprochen = 0.0                 # letzte Ansprache (Gespräch, Gefühl, Berührung, Befehl)
        self._beruehrt: str | None = None
        self._beruehrt_ab = 0.0
        self.platzieren(STANDARD_FLAECHE)

    # ── Körper ───────────────────────────────────────────────────────────
    def eigenschaften(self) -> frozenset[str]:
        return EIGENSCHAFTEN | {"simulator", "zuruecksetzen"}

    def skills(self) -> list[str]:
        return []

    def gespraech(self, zustand: str | None, sekunden: float = 4.0) -> None:
        """Zuhören oder Nachdenken im Gesicht zeigen (wie Reachy mit den Antennen)."""
        self._gespraech = zustand if zustand in ("zuhoeren", "denkt") else None
        self._gespraech_bis = self.t + (max(0.5, min(30.0, sekunden)) if zustand == "zuhoeren" else 3600.0)
        if self._gespraech:
            self._angesprochen = self.t

    def schlaeft(self) -> bool:
        """Nach fünf Minuten ohne Ansprache eingeschlafen (Augen zu, Kopf gesenkt) – jede Ansprache weckt ihn."""
        return self.powered and not self.sitting and self.t - self._angesprochen >= SCHLAF_NACH

    def beruehren(self, art: str) -> IntentResult:
        """Berührung oben auf dem Kopf: „streicheln“ → froh, Kopf kurz hoch; „schuetteln“ → schwindelig, Kopf wackelt."""
        if art not in ("streicheln", "schuetteln"):
            return IntentResult(False, "Nur „streicheln“ oder „schuetteln“")
        if not self.powered:
            return IntentResult(False, "Stack-chan ist aus – nach dem Not-Aus spürt er nichts")
        self._angesprochen = self.t
        self._beruehrt, self._beruehrt_ab = art, self.t
        self.gefuehl_zeigen("freude" if art == "streicheln" else "schwindelig", 2.0 if art == "streicheln" else 2.6)
        return IntentResult(True, "freut sich" if art == "streicheln" else "ist schwindelig")

    def gefuehl_zeigen(self, gefuehl: str, sekunden: float = 2.5) -> str:
        """Ein Gefühl für eine Weile im Gesicht zeigen; liefert den Ausdruck."""
        self._angesprochen = self.t
        self._ausdruck = ausdruck_aus(gefuehl)
        self._ausdruck_bis = self.t + max(0.5, min(15.0, float(sekunden) + 0.5))
        return self._ausdruck

    async def sound(self, tag: str) -> IntentResult:
        return IntentResult(False, "Stack-chan hat keine Entenlaute – er spricht mit seiner Stimme")

    async def do(self, skill: str) -> IntentResult:
        self._angesprochen = self.t
        if skill == "sit_toggle":
            return await (self.init() if self.sitting else self.rest())
        return IntentResult(False, OHNE_BEINE)

    async def move(self, twist: Twist) -> None:
        self.requested = Twist(0.0, 0.0, 0.0)               # steht fest; Drehen geht nur mit dem Kopf
        self._last_move = self.t
        if not twist.is_zero(0.01):
            self.limited_by = [OHNE_BEINE]

    def _step_base(self, dt: float) -> None:
        x, y, yaw = self.x, self.y, self.yaw
        super()._step_base(dt)
        self.x, self.y, self.yaw = x, y, yaw                # bewegt sich nicht von der Stelle
        self.applied = Twist(0.0, 0.0, 0.0)
        self.gait_phase = 0.0

    def _update_tof(self) -> None:
        self._tof, self._points, self._sectors = [], [], {}  # kein Tiefensensor; Sehen über die Kamera

    def _fall(self, why: str) -> None:                       # steht fest – fällt nicht um
        return None

    def gesicht(self) -> dict[str, Any]:
        if self.mouth_now > 0.05:                           # spricht gerade – zählt als Ansprache
            self._angesprochen = self.t
        wach = self.powered and not self.sitting and not self.schlaeft()
        if self.t >= self._ausdruck_bis:
            self._ausdruck = "ruhig"
        if self._gespraech == "zuhoeren" and self.t >= self._gespraech_bis:
            self._gespraech = None
        spricht = wach and self.mouth_now > 0.02
        led = "gruen" if wach and self._gespraech == "zuhoeren" else "blau" if spricht else None
        zustand = self._gespraech if wach else "schlaeft" if self.schlaeft() else None
        return {"ausdruck": self._ausdruck if wach else "muede", "mund": round(self.mouth_now if wach else 0.0, 3),
                "wach": wach, "zustand": zustand, "led": led}

    def _beruehrt_lage(self, lage: dict[str, float]) -> dict[str, float]:
        """Kurz nach einer Berührung: Kopf hebt sich (streicheln) oder wackelt (schütteln)."""
        dt = self.t - self._beruehrt_ab
        if self._beruehrt == "streicheln" and dt < 1.2:
            lage["pitch"] = round(max(-KOPF_HOCH, lage["pitch"] - math.radians(14) * math.sin(math.pi * dt / 1.2)), 4)
        elif self._beruehrt == "schuetteln" and dt < 1.8:
            lage["yaw"] = round(lage["yaw"] + math.radians(16) * math.sin(2 * math.pi * 3 * dt) * (1 - dt / 1.8), 4)
        return lage

    def state(self) -> DuckState:
        st = super().state()
        st.koerper = self.koerper_art
        st.battery = None
        st.gait_phase = 0.0
        st.perception = Perception(objects=st.perception.objects, source="sim")
        st.gesicht = self.gesicht()
        if self.sitting or not self.powered or st.gesicht["zustand"] == "schlaeft":
            st.kopf_lage = {"yaw": 0.0, "pitch": round(SCHLAF_NICKEN, 4)}
        else:
            st.kopf_lage = self._beruehrt_lage(kopf_lage(st.head))
        st.stand_z, st.standflaeche = round(self.stand_z, 4), self.standflaeche
        return st

    def fassung(self, skill: str) -> dict[str, str]:
        return {"fassung": "Stack-chan im Simulator von Knowlin – Gehäuse aus den offenen Daten der Community, Gesicht von Knowlin"}
