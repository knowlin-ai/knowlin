"""SO-101 im Simulator (seit 0.38.47, Etappe G5 aus dem Konzept „Knowlins Kopf“).

Ein Arm ohne Kopf, ohne Beine und ohne Stimme: Er steht fest auf seiner eigenen Werkbank (seit 0.38.48, `werkbank.py`) und bewegt
sechs Gelenke (`duckpilot/arm.py`). Gezeigt wird, dass derselbe Kopf mit einem ganz anderen Körper zurechtkommt – der
Aktionskatalog handelt „grüßen“ hier als Winken aus, nicht als Nicken.

Kinematik ohne Physik, wie bei Reachy: Haltungen werden in der angegebenen Zeit linear angefahren. Not-Aus: Motoren aus,
der Arm sackt in die Ruhelage (nur fürs Bild); bewegt wird erst wieder nach dem Aufwecken.
Am echten SO-101 übernimmt das Profil „lerobot“ (`backends/lerobot.py`).
"""

from __future__ import annotations

import math
from typing import Any

from .. import arm as A
from ..api import DuckState, Head, IntentResult, Perception, Pose, Twist
from ..werkbank_auftrag import planen, pruefen
from .sim import SimBackend
from .tischplatz import TischPlatz
from .werkbank import OFFEN_LAESST_FALLEN, SOCKEL_VOR_KANTE, WERKBANK, Werkbank
from .werkbank_spiel import TicTacToe
from .world import Box

EIGENSCHAFTEN = frozenset({"arm", "greifer", "simulator", "zuruecksetzen"})
OHNE = "Der SO-101 ist ein Arm – er hat keine Beine, keinen Kopf und keine Stimme"
SACKEN_S = 1.2                # so lange sackt der Arm nach dem Not-Aus in die Ruhelage


class So101Sim(TischPlatz, SimBackend):
    koerper_art = "so101"
    platz_name = "Der SO-101"
    fuss_m = 0.06
    standard_flaeche = WERKBANK["name"]                     # eigene Werkbank (seit 0.38.48)

    def __init__(self, realtime: bool = True, seed: int | None = None) -> None:
        super().__init__(realtime=realtime, seed=seed)
        self.gelenke: dict[str, float] = dict(A.POSEN["ruhe"])        # Grad
        self._von: dict[str, float] = dict(self.gelenke)
        self._ziel: dict[str, float] = dict(self.gelenke)
        self._dauer = 0.0
        self._zeit = 0.0
        self._folge: list[tuple[dict[str, float], float, str | None]] = []
        self._bei_ankunft: str | None = None
        self.geste_name: str | None = None
        self.werkbank = Werkbank()
        self.auftrag: dict[str, Any] | None = None      # Aufräumen, Sortieren, Turm … (seit 0.38.54)
        self.auftrag_ende: str | None = None
        if not any(b.name == WERKBANK["name"] for b in self.world_model.boxes):
            self.world_model.boxes.append(Box(**{k: WERKBANK[k] for k in ("name", "x", "y", "sx", "sy", "h", "color")}))
        self.sitting = True                                             # beginnt in der Ruhelage, Motoren aus
        self.powered = False
        self.enabled = False
        self.platzieren(self.standard_flaeche)

    # ── Körper ───────────────────────────────────────────────────────────
    def eigenschaften(self) -> frozenset[str]:
        return EIGENSCHAFTEN

    def skills(self) -> list[str]:
        return []

    # ── Platz: immer an der eigenen Werkbank, Sockel hinten, Blick über die Werkbank ─────
    def platz_pruefen(self, flaeche: str) -> str | None:
        if str(flaeche or "").strip().lower() != WERKBANK["name"].lower():
            return "Ari bleibt an seiner Werkbank – dort liegen seine Würfel und Kisten."
        return None

    def platzieren(self, flaeche: str) -> tuple[bool, str]:
        grund = self.platz_pruefen(flaeche)
        if grund is not None:
            return False, grund
        w = WERKBANK
        self.stand_z, self.standflaeche = float(w["h"]), w["name"]
        self._ente_setzen(w["x"] - w["sx"] / 2 + SOCKEL_VOR_KANTE, w["y"], 0.0)
        return True, f"Ari steht an seiner {w['name']}"

    def szene_zuruecksetzen(self, ente: bool = True) -> dict[str, Any]:
        out = super().szene_zuruecksetzen(ente=ente)
        self.werkbank.zuruecksetzen()
        out["dinge"] = [*out.get("dinge", []), *self.werkbank.namen()["dinge"]]
        return out

    def fassung(self, skill: str) -> dict[str, str]:
        return {"fassung": "SO-101 im Simulator von Knowlin – Kinematik ohne Physik, Modell von TheRobotStudio"}

    # ── Bewegung ─────────────────────────────────────────────────────────
    def _anfahren(self, ziel: dict[str, float], sekunden: float) -> None:
        self._von = dict(self.gelenke)
        self._ziel = {**self.gelenke, **ziel}
        self._dauer = max(0.05, float(sekunden))
        self._zeit = 0.0

    def _step_actuators(self, dt: float) -> None:
        if self._zeit < self._dauer:
            self._zeit = min(self._dauer, self._zeit + dt)
            a = self._zeit / self._dauer
            a = a * a * (3 - 2 * a)                                     # weich anfahren und abbremsen
            self.gelenke = {g: self._von[g] + (self._ziel[g] - self._von[g]) * a for g in A.GELENKE}
            if self.werkbank.haelt and self.gelenke["gripper"] > OFFEN_LAESST_FALLEN:
                self.werkbank.fallen_lassen(self.gelenke)              # Greifer geht auf: es fällt
            if self._zeit >= self._dauer and self._bei_ankunft:
                aktion, self._bei_ankunft = self._bei_ankunft, None
                self.werkbank.ausfuehren(aktion, self.gelenke)
        elif self._folge:
            haltung, s, aktion = self._folge.pop(0)
            self._anfahren(haltung, s)
            self._bei_ankunft = aktion
        else:
            self.geste_name = None
            if self.auftrag is not None:
                self._auftrag_weiter()

    def _step_base(self, dt: float) -> None:
        self.applied = Twist()                                          # steht fest
        self.gait_phase = 0.0

    def _update_tof(self) -> None:
        self._tof, self._points, self._sectors = [], [], {}

    def _fall(self, why: str) -> None:                                  # steht fest – fällt nicht um
        return None

    async def haltung(self, gelenke: dict[str, Any], sekunden: float = 1.0) -> IntentResult:
        """Gelenke in Grad (Namen wie in `arm.GELENKE`, auch deutsch) in `sekunden` anfahren."""
        self._auftrag_abbrechen("eine Haltung von Hand")
        if not self.powered:
            return IntentResult(False, "Motoren sind aus – erst aufwecken")
        ziel, unbekannt = A.begrenzen(gelenke)
        if unbekannt:
            return IntentResult(False, f"Gelenk unbekannt: {', '.join(unbekannt)} – bekannt: {', '.join(A.GELENKE)}")
        self._folge, self.geste_name, self._bei_ankunft = [], None, None
        self.sitting = False
        self._anfahren(ziel, max(0.3, min(10.0, float(sekunden))))
        return IntentResult(True, f"fährt {len(ziel)} Gelenke in {self._dauer:.1f} s an")

    async def geste(self, name: str) -> IntentResult:
        self._auftrag_abbrechen("eine Geste")
        if name not in A.GESTEN:
            return IntentResult(False, f"Geste unbekannt – bekannt: {', '.join(A.GESTEN)}")
        if not self.powered:
            return IntentResult(False, "Motoren sind aus – erst aufwecken")
        self._folgen([(dict(h), s, None) for h, s in A.GESTEN[name]], name)
        self.sitting = name == "ruhe"
        return IntentResult(True, f"{name} ({A.dauer(name):.1f} s)")

    def _folgen(self, folge: list[tuple[dict[str, float], float, str | None]], name: str) -> None:
        self._folge = folge[1:]
        self._anfahren(folge[0][0], folge[0][1])
        self._bei_ankunft = folge[0][2]
        self.geste_name = name

    # ── Greifen und Ablegen an der Werkbank (seit 0.38.48) ───────────────
    async def greifen(self, ding: str) -> IntentResult:
        self._auftrag_abbrechen("Greifen von Hand")
        if not self.powered:
            return IntentResult(False, "Motoren sind aus – erst aufwecken")
        plan, grund = self.werkbank.greifen_plan(ding)
        if plan is None:
            return IntentResult(False, grund)
        self.sitting = False
        self._folgen(plan, "greifen")
        d = self.werkbank.ding(ding)
        return IntentResult(True, f"greift {d.get('akk') or d['name'] if d else ding} ({sum(s for _, s, _ in plan):.1f} s)")

    async def ablegen(self, ziel: str) -> IntentResult:
        self._auftrag_abbrechen("Ablegen von Hand")
        if not self.powered:
            return IntentResult(False, "Motoren sind aus – erst aufwecken")
        plan, grund = self.werkbank.ablegen_plan(ziel)
        if plan is None:
            return IntentResult(False, grund)
        self.sitting = False
        self._folgen(plan, "ablegen")
        return IntentResult(True, f"legt {self.werkbank.haelt} ab ({sum(s for _, s, _ in plan):.1f} s)")

    # ── Aufträge: mehrere Griffe nacheinander (seit 0.38.54, `werkbank_auftrag.py`) ──────────
    async def auftrag_starten(self, auftrag: dict[str, Any]) -> IntentResult:
        geprueft, grund = pruefen(auftrag)
        if geprueft is None:
            return IntentResult(False, grund)
        if not self.powered:
            return IntentResult(False, "Motoren sind aus – erst aufwecken")
        if self.werkbank.spiel is not None and geprueft["titel"] != "Tic-Tac-Toe":
            return IntentResult(False, "Gerade läuft Tic-Tac-Toe – erst „Spiel beenden“.")
        schritte, grund = planen(geprueft, self.werkbank)
        if not schritte:
            return IntentResult(False, grund)
        self._auftrag_abbrechen("ein neuer Auftrag")
        self._folge, self.geste_name, self._bei_ankunft = [], None, None
        griffe = sum(1 for art, _ in schritte if art == "greifen")
        self.auftrag = {"titel": geprueft["titel"], "schritte": schritte, "griffe": griffe}
        self.auftrag_ende = None
        self.sitting = False
        self._dauer = self._zeit = 0.0                                  # gleich im nächsten Takt beginnen
        return IntentResult(True, f"{geprueft['titel']}: {griffe} {'Griff' if griffe == 1 else 'Griffe'}")

    def _auftrag_weiter(self) -> None:
        a = self.auftrag
        if a is None:
            return
        if not a["schritte"]:
            self.auftrag, self.auftrag_ende = None, f"{a['titel']} – fertig"
            if a.get("spiel_feld") and self.werkbank.spiel is not None:          # Aris Zug ist gesetzt
                self.auftrag_ende = self.werkbank.spiel.ari_gesetzt(a["spiel_feld"], True)
            return
        art, ziel = a["schritte"].pop(0)
        plan, grund = (self.werkbank.greifen_plan(ziel) if art == "greifen" else self.werkbank.ablegen_plan(ziel))
        if plan is None:
            self.auftrag, self.auftrag_ende = None, f"{a['titel']} abgebrochen – {grund}"
            if a.get("spiel_feld") and self.werkbank.spiel is not None:
                self.werkbank.spiel.ari_gesetzt(a["spiel_feld"], False)
            return
        self._folgen(plan, art)

    def _auftrag_abbrechen(self, wodurch: str) -> None:
        if self.auftrag is not None:
            self.auftrag_ende = f"{self.auftrag['titel']} abgebrochen ({wodurch})"
            if self.auftrag.get("spiel_feld") and self.werkbank.spiel is not None:
                self.werkbank.spiel.ari_gesetzt(self.auftrag["spiel_feld"], False)
            self.auftrag = None

    # ── Tic-Tac-Toe (seit 0.38.54, `werkbank_spiel.py`) ──────────────────
    async def spiel_aktion(self, aktion: str, feld: int | None = None) -> IntentResult:
        if aktion == "start":
            self._auftrag_abbrechen("ein neues Spiel")
            self.werkbank.zuruecksetzen()
            self.werkbank.spiel = TicTacToe(self.werkbank)
            self.auftrag_ende = None
            return IntentResult(True, "Tic-Tac-Toe: du fängst an – klick ein Feld oder sag „Feld 5“.")
        if aktion == "ende":
            self._auftrag_abbrechen("Spiel beendet")
            self.werkbank.zuruecksetzen()
            return IntentResult(True, "Spiel beendet, die Werkbank ist wieder aufgeräumt.")
        spiel = self.werkbank.spiel
        if spiel is None:
            return IntentResult(False, "Es läuft kein Spiel – erst „Tic-Tac-Toe“ starten.")
        if not self.powered:
            return IntentResult(False, "Motoren sind aus – erst aufwecken")
        nr_ari, text = spiel.zug_mensch(int(feld or 0))
        if nr_ari is None:
            return IntentResult(spiel.ergebnis is not None, text)
        stein = spiel.stein_fuer_ari()
        r = await self.auftrag_starten({"titel": "Tic-Tac-Toe", "regel": "schritte",
                                        "schritte": [{"ding": stein, "ziel": f"Feld {nr_ari}"}]})
        if not r.accepted:
            spiel.ari_gesetzt(nr_ari, False)
            return IntentResult(False, r.reason)
        self.auftrag["spiel_feld"] = nr_ari
        return IntentResult(True, f"{text} Ari überlegt …")

    def beschaeftigt(self) -> bool:
        """Für die Eigeninitiative: Der Arm arbeitet gerade (Auftrag oder Bewegung)."""
        return self.auftrag is not None or bool(self._folge) or self._zeit < self._dauer

    # ── Intents, die ein Arm nicht hat ───────────────────────────────────
    async def move(self, twist: Twist) -> None:
        self.requested = Twist()
        if abs(twist.vx) > 0.01 or abs(twist.vy) > 0.01 or abs(twist.vyaw) > 0.01:
            self.limited_by = [OHNE]

    async def head(self, head: Head) -> None:
        return None

    async def mouth(self, open_: float) -> None:
        return None

    async def pose(self, pose: Pose, active: bool = True) -> None:
        return None

    async def do(self, skill: str) -> IntentResult:
        return IntentResult(False, OHNE)

    async def sound(self, tag: str) -> IntentResult:
        return IntentResult(False, "Der SO-101 hat keine eigenen Laute – Knowlin spricht über den PC")

    # ── Wach, Ruhe, Not-Aus ──────────────────────────────────────────────
    async def init(self) -> IntentResult:
        if self.powered and not self.sitting:
            return IntentResult(True, "ist schon bereit")
        self.powered = self.enabled = True
        await self.geste("bereit")
        return IntentResult(True, "Motoren an, Arm bereit")

    async def enable(self, on: bool) -> IntentResult:
        if on and not self.powered:
            return await self.init()
        self.enabled = bool(on) and self.powered
        return IntentResult(True)

    async def rest(self) -> IntentResult:
        if not self.powered:
            return IntentResult(True, "ist schon aus")
        await self.geste("ruhe")
        self.enabled = False
        return IntentResult(True, "legt sich in die Ruhelage")

    async def stop(self) -> IntentResult:
        self._auftrag_abbrechen("Stopp")
        self._folge, self.geste_name, self._bei_ankunft = [], None, None
        self._von = self._ziel = dict(self.gelenke)
        self._dauer = self._zeit = 0.0
        self.requested = Twist()
        return IntentResult(True)

    def lahm(self) -> None:
        """Not-Aus: Motoren sofort aus; ohne Kraft sackt der Arm in die Ruhelage (nur fürs Bild)."""
        self.powered = self.enabled = False
        self._auftrag_abbrechen("Not-Aus")
        self._folge, self.geste_name, self._bei_ankunft = [], None, None
        self.werkbank.fallen_lassen(self.gelenke)                      # ohne Kraft hält der Greifer nichts
        self._anfahren(A.POSEN["ruhe"], SACKEN_S)
        self.sitting = True

    async def relax(self) -> IntentResult:
        self.lahm()
        return IntentResult(True, "stromlos")

    # ── Zustand ──────────────────────────────────────────────────────────
    def state(self) -> DuckState:
        st = super().state()
        st.koerper = self.koerper_art
        st.battery = None
        st.gait_phase = 0.0
        st.perception = Perception(objects=st.perception.objects, source="sim")
        rad = [round(math.radians(self.gelenke[g]), 4) for g in A.GELENKE]
        st.joints = rad
        st.display_joints = rad
        st.skill = None                                                 # Gesten sind keine Skills (keine Anzeige „geste:…“)
        st.stand_z, st.standflaeche = round(self.stand_z, 4), self.standflaeche
        st.holding = self.werkbank.haelt
        st.werkbank = {**self.werkbank.als_dict(), "auftrag_ende": self.auftrag_ende,
                       "auftrag": None if self.auftrag is None else {          # gezählt in Griffen: „2/5“
                           "titel": self.auftrag["titel"], "gesamt": self.auftrag["griffe"],
                           "erledigt": self.auftrag["griffe"] - sum(1 for s in self.auftrag["schritte"] if s[0] == "greifen")}}
        return st
