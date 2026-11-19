"""„Ente sagt“ (seit 0.44, Fahrplan „Spiele“) – wie „Simon sagt“, mit Handzeichen.

Knowlin sagt ein Handzeichen an. Kommt davor „<Name> sagt“, macht man es nach; sonst nicht. Erkannt wird das Zeichen im
Browser – mit Handerkennung aus der Webcam (`static/hand.js`, Schere/Stein/Papier) oder angetippt. Hierher kommt nur
ein Wort (`stein`, `schere`, `papier`, `keine`), nie ein Bild.

Regeln: Mit „sagt“ ist richtig, wer genau das Zeichen zeigt. Ohne „sagt“ ist richtig, wer es **nicht** zeigt. Wer zu spät
antwortet, hat keine Hand gezeigt. Drei Leben; je drei Punkte wird die Zeit etwas knapper. Reine Logik – die Route
(`server/routes/spiel.py`) sagt an und lässt den Körper sich freuen.
"""

from __future__ import annotations

import random
import time
from typing import Any, Callable

ZEICHEN: dict[str, str] = {
    "stein": "Zeig eine Faust",
    "schere": "Zeig die Schere",
    "papier": "Zeig die offene Hand",
    "keine": "Nimm die Hand weg",
}
LEBEN = 3
FRIST_S, FRIST_MIN_S, KNAPPER_S = 4.0, 2.4, 0.25
SAGT_ANTEIL = 0.7
SPAET_S = 1.5             # so lange nach der Frist zählt eine Antwort noch (Netz, langsamer Rechner)

LOB = ("Richtig!", "Genau so!", "Gut aufgepasst!", "Stark!")
REINGELEGT = ("Reingelegt – ich hab nicht „{wer} sagt“ gesagt!", "Ha! Ohne „{wer} sagt“ gilt das nicht.")
FALSCH = ("Das war nicht das Zeichen.", "Knapp daneben.")


class EnteSagt:
    def __init__(self, wer: str = "Ente", seed: int | None = None, uhr: Callable[[], float] = time.monotonic) -> None:
        self.wer = (wer or "Ente").strip() or "Ente"
        self.rng = random.Random(seed)
        self.uhr = uhr
        self.punkte = 0
        self.leben = LEBEN
        self.runde: dict[str, Any] | None = None
        self.vorher = "keine"

    @property
    def frist(self) -> float:
        return max(FRIST_MIN_S, FRIST_S - KNAPPER_S * (self.punkte // 3))

    @property
    def vorbei(self) -> bool:
        return self.leben <= 0

    def naechste(self) -> dict[str, Any]:
        """Neue Ansage – nie das Zeichen, das die Hand gerade schon zeigt (sonst wäre „nicht nachmachen“ unmöglich)."""
        if self.vorbei:
            raise ValueError("Das Spiel ist vorbei.")
        wahl = [z for z in ZEICHEN if z != self.vorher]
        zeichen = self.rng.choice(wahl)
        sagt = self.rng.random() < SAGT_ANTEIL
        text = f"{self.wer} sagt: {ZEICHEN[zeichen]}!" if sagt else f"{ZEICHEN[zeichen]}!"
        self.runde = {"zeichen": zeichen, "sagt": sagt, "text": text, "ab": self.uhr(), "frist_s": self.frist}
        return {k: self.runde[k] for k in ("text", "frist_s", "sagt")} | {"nr": self.punkte + LEBEN - self.leben + 1}

    def antwort(self, gezeigt: str | None) -> dict[str, Any]:
        """Was gezeigt wurde (`None` = nichts erkannt). Zu spät zählt als „keine“."""
        if self.runde is None:
            raise ValueError("Gerade läuft keine Runde.")
        r, self.runde = self.runde, None
        if self.uhr() - r["ab"] > r["frist_s"] + SPAET_S:
            gezeigt = "keine"
        gezeigt = gezeigt if gezeigt in ZEICHEN else "keine"
        richtig = gezeigt == r["zeichen"] if r["sagt"] else gezeigt != r["zeichen"]
        self.vorher = gezeigt                                # so steht die Hand jetzt
        if richtig:
            self.punkte += 1
            satz = self.rng.choice(LOB)
        else:
            self.leben -= 1
            satz = self.rng.choice(REINGELEGT if not r["sagt"] else FALSCH).format(wer=self.wer)
        if self.vorbei:
            satz += f" Spiel vorbei – {self.punkte} Punkt{'' if self.punkte == 1 else 'e'}."
        return {"richtig": richtig, "satz": satz, "punkte": self.punkte, "leben": self.leben, "vorbei": self.vorbei,
                "gefragt": r["zeichen"], "sagt": r["sagt"], "gezeigt": gezeigt}

    def stand(self) -> dict[str, Any]:
        return {"punkte": self.punkte, "leben": self.leben, "vorbei": self.vorbei, "wer": self.wer,
                "runde": None if self.runde is None else {k: self.runde[k] for k in ("text", "frist_s", "sagt")}}
