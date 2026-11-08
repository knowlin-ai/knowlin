"""Gefühle der Ente – aus dem, was passiert, nicht aus fehlender Aufmerksamkeit.

Die Ente bewertet Ereignisse (Erfolg, Missgeschick, Schreck, was der Mensch sagt)
und hat daraus eine Stimmung, die mit der Zeit von selbst abklingt:

* **Freude** steigt bei Erfolgen (Ball getroffen, Socke erwischt, Ziel erreicht,
  Lob) – nach vorheriger Mühe als Erleichterung.
* **Frust** steigt bei wiederholtem Scheitern (daneben, blockiert, nicht gefunden,
  abgelehnt, mehrfach angestoßen) und sinkt bei Erfolg.
* **Schreck** bei Sturz und Anstoßen, klingt schnell ab.
* **Mitgefühl**, wenn der Mensch traurig, müde oder gestresst klingt: dann ruhig,
  sanft und ohne Albernheiten.

Was es bewusst NICHT gibt: Traurigkeit oder Ärger, weil sich niemand kümmert,
Schmollen, Beleidigtsein, Betteln um Aufmerksamkeit. Ohne Ereignisse wird die Ente
einfach ausgeglichen.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any

PRAISE = re.compile(r"\b(gut gemacht|super|toll|klasse|prima|bravo|brav|spitze|stark|genial|wunderbar|perfekt|"
                    r"gut so|sehr gut|cool|großartig|grossartig|wow|ich hab dich lieb|du bist (so )?(süß|suess|toll|lieb))\b")
USER_JOY = re.compile(r"\b(juhu|yeah|hurra|jippie|endlich wochenende|ich freu mich|freue mich|geschafft)\b")
USER_LOW = re.compile(r"\b(traurig|müde|muede|erschöpft|erschoepft|gestresst|stress|schlechter tag|mies|"
                      r"geht mir (nicht gut|schlecht)|krank|kopfschmerzen|einsam|überfordert|ueberfordert|frustriert)\b")
USER_SCOLD = re.compile(r"\b(falsch|doof|blöd|bloed|dumm|schlecht gemacht|nicht so|das war nichts|nein,? nicht)\b")

FAIL_WORDS = ("blockiert", "nicht gefunden", "abgelehnt", "Zeitlimit", "Fehler")
SUCCESS_WORDS = ("angekommen", "ausgeführt", "gelaufen", "gedreht", "umgeschaut")


@dataclass
class Feeling:
    name: str          # was die Oberfläche und Claude sehen
    reason: str        # warum
    valence: float     # -1 frustriert … +1 freudig
    intensity: float   # 0 … 1


class Mood:
    def __init__(self) -> None:
        self.joy = 0.0
        self.frust = 0.0
        self.shock = 0.0
        self.empathy = 0.0       # Sekunden, die das Mitgefühl noch anhält
        self.reason = ""
        self.reason_age = 0.0
        self.misses_in_row = 0

    # ── Zeit ──────────────────────────────────────────────────────────────
    def update(self, dt: float) -> None:
        self.joy *= math.exp(-dt / 25.0)
        self.frust *= math.exp(-dt / 30.0)
        self.shock *= math.exp(-dt / 3.5)
        self.empathy = max(0.0, self.empathy - dt)
        self.reason_age += dt
        if self.reason_age > 45 and max(self.joy, self.frust) < 0.15:
            self.reason = ""

    def _because(self, text: str) -> None:
        self.reason = text
        self.reason_age = 0.0

    # ── Lage ──────────────────────────────────────────────────────────────
    @property
    def empathic(self) -> bool:
        return self.empathy > 0

    def feeling(self) -> Feeling:
        valence = max(-1.0, min(1.0, self.joy - self.frust))
        if self.empathic:
            return Feeling("mitfühlend", self.reason or "du klingst bedrückt", valence, 0.6)
        if self.shock > 0.5:
            return Feeling("erschrocken", self.reason, valence, self.shock)
        if self.frust > 0.55 and self.frust > self.joy:
            return Feeling("frustriert", self.reason, valence, self.frust)
        if self.frust > 0.3 and self.frust > self.joy:
            return Feeling("angestrengt", self.reason, valence, self.frust)
        if self.joy > 0.6:
            return Feeling("begeistert", self.reason, valence, self.joy)
        if self.joy > 0.25:
            return Feeling("fröhlich", self.reason, valence, self.joy)
        return Feeling("ausgeglichen", "", valence, 0.0)

    def snapshot(self) -> dict[str, Any]:
        f = self.feeling()
        return {"name": f.name, "grund": f.reason, "valenz": round(f.valence, 3), "intensitaet": round(f.intensity, 3),
                "freude": round(self.joy, 3), "frust": round(self.frust, 3), "schreck": round(self.shock, 3),
                "mitgefuehl": self.empathic}

    # ── Bewertung von Ereignissen → vielleicht ein Ausdruck ──────────────
    def appraise(self, event: dict[str, Any]) -> str | None:
        kind = event.get("type")
        msg = str(event.get("message") or event.get("result") or "")
        if event.get("kollision"):
            # Kollisionsmodus ist Spiel: ein kurzes „Huch“ (Schreck klingt in Sekunden ab), aber kein Frust, kein
            # Grund, der hängen bleibt – sie denkt nicht, dass man sie ärgert
            if kind in ("fall", "bump"):
                self.shock = max(self.shock, 0.6 if kind == "fall" else 0.4)
            return None
        if kind == "kick":
            relief = self.frust > 0.3
            self.joy = min(1.0, self.joy + 0.55 + (0.2 if relief else 0.0))
            self.frust *= 0.25
            self.misses_in_row = 0
            self._because("endlich getroffen!" if relief else "Ball getroffen")
            return "begeistert" if self.joy > 0.6 else "freude"
        if kind == "pick":
            relief = self.frust > 0.3
            self.joy = min(1.0, self.joy + 0.4)
            self.frust *= 0.3
            self.misses_in_row = 0
            self._because(f"{event.get('item', 'etwas')} erwischt")
            return "erleichtert" if relief else "stolz"
        if kind in ("kick_miss", "pick_miss"):
            self.misses_in_row += 1
            self.frust = min(1.0, self.frust + 0.3 + 0.1 * (self.misses_in_row - 1))
            self._because("schon wieder daneben" if self.misses_in_row > 1 else "daneben")
            return "frustriert" if self.frust > 0.55 else None
        if kind == "bump":
            self.shock = max(self.shock, 0.6)
            self.frust = min(1.0, self.frust + 0.15)
            self._because(f"gegen {event.get('what', 'etwas')} gestoßen")
            return "frustriert" if self.frust > 0.65 else None
        if kind == "fall":
            self.shock = 1.0
            self.frust = min(1.0, self.frust + 0.2)
            self._because("umgefallen")
            return None
        if kind == "recover":
            self._because("wieder auf den Füßen")
            return "erleichtert"
        if kind == "behavior_end":
            if any(w in msg for w in FAIL_WORDS):
                self.frust = min(1.0, self.frust + 0.3)
                self._because(msg.split(":")[0] if ":" in msg else msg)
                return "frustriert" if self.frust > 0.55 else None
            if any(w in msg for w in SUCCESS_WORDS):
                if self.frust > 0.4:
                    self.frust *= 0.4
                    self.joy = min(1.0, self.joy + 0.3)
                    self._because("hat doch noch geklappt")
                    return "erleichtert"
                self.joy = min(1.0, self.joy + (0.15 if "angekommen" in msg else 0.05))
        return None

    def appraise_text(self, text: str) -> str | None:
        """Was der Mensch sagt. Mitgefühl geht vor allem anderen."""
        low = text.lower()
        if USER_LOW.search(low):
            self.empathy = 120.0
            self.frust *= 0.5
            self._because("du klingst bedrückt")
            return "einfuehlsam"
        if PRAISE.search(low):
            self.joy = min(1.0, self.joy + 0.5)
            self.frust *= 0.5
            self._because("gelobt worden")
            return "stolz"
        if USER_JOY.search(low):
            self.joy = min(1.0, self.joy + 0.35)
            self._because("freut sich mit dir")
            return "begeistert"
        if USER_SCOLD.search(low):
            self.joy *= 0.7
            self._because("hat es nicht richtig gemacht")
            return "verlegen"
        return None
