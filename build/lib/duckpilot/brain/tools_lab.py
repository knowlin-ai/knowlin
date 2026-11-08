"""Werkzeuge der Trainingshalle (Knowlin Lab): Üben in der Physik, Training, Parcours (seit 0.38 aus tools.py).

Teil von `ToolRunner` (Mixin) – `self.engine`, `self.lab`, `self.trainer` usw. setzt der ToolRunner.
"""

from __future__ import annotations

from typing import Any

PRACTICE_TOOL = {
    "name": "bewegung_ueben",
    "description": (
        "Eine selbst komponierte Bewegung erst in der echten Physik üben, bevor die Ente sie zeigt: "
        "Pollens MuJoCo-Modell mit Pollens Geh-Policy spielt die Keyframes unsichtbar und schneller als Echtzeit "
        "durch und misst, ob sie umfällt, wie stark sie kippt, ob der Kopf folgt und ob man die Bewegung überhaupt sieht "
        "(sichtbar: ja/kaum). Urteil: sicher, wackelig, fällt um – mit Hinweisen. Die Ente bewegt sich dabei nicht; "
        "sag dem Menschen ehrlich, wenn etwas nur „kaum“ sichtbar ist. Keyframes wie bei choreography. "
        "Nutze es für neue, große oder schnelle Bewegungen und vor dem Speichern eines Tricks; bei „wackelig“ "
        "oder „fällt um“ verbessern und nochmal üben (höchstens drei Runden), dann mit choreography zeigen."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "keyframes": {"type": "array", "items": {"type": "object"}},
            "loops": {"type": "integer"},
            "title": {"type": "string"},
        },
        "required": ["keyframes"],
    },
}

TRAINING_TOOL = {
    "name": "training_vorschlagen",
    "description": (
        "Einen Trainingslauf für eine NEUE Fähigkeit vorschlagen (Pollens Reinforcement Learning auf Hugging Face Jobs, "
        "dauert Stunden und kostet Geld). Du legst nur einen Vorschlag auf die Seite Lernen → Training – starten muss der "
        "Mensch. Spar Rechenzeit: start_von „pollen“ setzt auf Pollens geteiltem Trainingsstand auf (gleiche Aufgabe: "
        "weitertrainieren, gleiche Familie: Warmstart) und braucht oft nur 500–1500 Iterationen; „lauf:<id>“ trainiert "
        "einen eigenen früheren Lauf weiter. Belohnungsgewichte als anpassungen {\"env.rewards.foot_clearance.weight\": 1.5}; "
        "bis zu zwei varianten (andere Gewichte) laufen parallel, der Parcours entscheidet. bei_stillstand „abbrechen“ "
        "spart Geld, wenn sich die Belohnung nicht mehr verbessert (der letzte Zwischenstand wird exportiert). "
        "Für Bewegungen aus Kopf, Körper und Fahrbefehlen reicht choreography + bewegung_ueben. "
        "Pollens Stände gibt es für: {pollen}. Aufgaben: {tasks}."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "aufgabe": {"type": "string"},
            "iterationen": {"type": "integer"},
            "anpassungen": {"type": "object", "description": "tyro-Optionen → Zahl/true/false"},
            "varianten": {"type": "array", "items": {"type": "object"}, "description": "bis zu 2 weitere Anpassungs-Sätze"},
            "start_von": {"type": "string", "description": "„pollen“, „lauf:<id>“ oder leer = von vorn"},
            "grafikkarte": {"type": "string"},
            "max_stunden": {"type": "integer", "description": "1–12, begrenzt die Kosten"},
            "bei_stillstand": {"type": "string", "enum": ["weiter", "abbrechen"]},
            "begruendung": {"type": "string"},
        },
        "required": ["aufgabe", "begruendung"],
    },
}

FREE_TRAINING_TOOL = {
    "name": "training_kostenlos",
    "description": (
        "Ein KOSTENLOSES Training selbst starten (das darfst du – bezahlte nur vorschlagen). anbieter „pc“: auf diesem PC "
        "(Physik auf dem Prozessor, Lernen auf der Grafikkarte), baut auf Pollens Geh-Programm auf und lernt den aktuellen "
        "Parcours; minuten = Zeitbudget (15–600); lernschleife=true prüft nach jedem Abschnitt auf dem Parcours und macht "
        "weiter, bis sie es schafft oder die Zeit um ist. anbieter „kaggle“: Pollens Original-Training auf einer "
        "geschenkten NVIDIA-Karte (aufgabe, iterationen, start_von „pollen“, max_stunden 1–11). Erklär dem Menschen kurz, "
        "was du startest und wie lange es dauert."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "anbieter": {"type": "string", "enum": ["pc", "kaggle"]},
            "minuten": {"type": "integer"},
            "lernschleife": {"type": "boolean"},
            "aufgabe": {"type": "string"},
            "iterationen": {"type": "integer"},
            "start_von": {"type": "string"},
            "max_stunden": {"type": "integer"},
            "begruendung": {"type": "string"},
        },
        "required": ["anbieter"],
    },
}

TRAINING_REVIEW_TOOL = {
    "name": "training_auswerten",
    "description": (
        "Lernkurve eines Trainingslaufs auswerten: Fortschritt, Belohnung (Start, jetzt, bestes), Trend, Stillstand, "
        "Sekunden pro Iteration, Restzeit, jeder Belohnungsterm mit Veränderung seit der Laufmitte und die Abbruchgründe "
        "(z. B. wie oft sie umfällt). Ohne lauf: der neueste. Nutze es, um zu erklären, was hakt, und um gezielt andere "
        "Gewichte oder ein Weitertrainieren vorzuschlagen."
    ),
    "input_schema": {"type": "object", "properties": {"lauf": {"type": "string"}}},
}

PARCOURS_BUILD_TOOL = {
    "name": "parcours_bauen",
    "description": (
        "Einen Hindernisparcours in der echten Physik (MuJoCo) aufbauen – für einen Auftrag wie „die Ente soll Rampe "
        "und Stufen schaffen“. Die Bahn ist 50 cm breit und gerade, Elemente folgen in der angegebenen Reihenfolge "
        "(höchstens 8, zusammen höchstens 8 m). Elemente mit Parametern (Zentimeter): "
        "rampe {hoehe_cm 1–10, laenge_cm 20–100, plateau_cm}, stufen {anzahl 1–4, hoehe_cm 0.5–6, tiefe_cm 8–30, plateau_cm}, "
        "schwelle {hoehe_cm 0.5–4, tiefe_cm}, uneben {hoehe_cm 0.5–3, laenge_cm 30–150}, "
        "slalom {anzahl 2–6, abstand_cm 25–80, versatz_cm 11–25}, engstelle {breite_cm 15–40, laenge_cm 10–80}. "
        "Die Microduck ist 25 cm groß und etwa 15 cm breit; Richtwerte für Pollens Geh-Policy: Rampen bis etwa 12°, "
        "Stufen und Schwellen bis 2–2,5 cm. Was darüber liegt, ist ein Ziel fürs Training. "
        "Danach mit parcours_testen prüfen."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "ziel": {"type": "string", "description": "Was die Ente am Ende können soll, ein Satz"},
            "name": {"type": "string"},
            "elemente": {"type": "array", "items": {"type": "object"},
                         "description": "z. B. [{\"art\": \"rampe\", \"hoehe_cm\": 4}, {\"art\": \"slalom\", \"anzahl\": 3}]"},
        },
        "required": ["elemente"],
    },
}

PARCOURS_TEST_TOOL = {
    "name": "parcours_testen",
    "description": (
        "Eine Geh-Policy mehrmals durch den aktuellen Parcours laufen lassen (unsichtbar, schneller als Echtzeit, "
        "Versuch 1 genau, weitere mit etwas anderer Reibung und Startlage). Ergebnis pro Element: geschafft, gestürzt, "
        "steckt fest, Stange ausgelassen – und wie viele Versuche im Ziel sind. policy: „standard“ (Pollens Geh-Policy) "
        "oder „lauf:<id>“ (fertiges eigenes Training). Scheitert die Standard-Policy an einem Element, schlage mit "
        "training_vorschlagen einen passenden Lauf vor (z. B. Mjlab-Velocity-Rough-MicroDuck für Stufen und Schrägen) "
        "und erkläre, woran es lag. Die Aufzeichnung kann der Mensch unter Lernen → Parcours in 3D ansehen."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "policy": {"type": "string"},
            "versuche": {"type": "integer", "description": "1–5, Standard 3"},
        },
    },
}


def _num(d: dict[str, Any], key: str, default: float) -> float:
    from .tools import _num as num

    return num(d, key, default)


class LabWerkzeuge:
    async def _parcours(self, name: str, a: dict[str, Any]) -> dict[str, Any]:
        if self.lab is None:
            return {"ok": False, "fehler": "Der Parcours braucht die echte Physik (Einstellungen → Körper)."}
        if name == "parcours_bauen":
            spec = {"name": a.get("name") or "Parcours", "elemente": a.get("elemente") or []}
            return {"ok": True, **self.lab.build(spec, a.get("ziel"))}
        quelle = str(a.get("policy") or "standard").strip()
        versuche = max(1, min(5, int(_num(a, "versuche", 3))))
        test = await self.lab.test(quelle, versuche)
        return {"ok": True, **{k: test[k] for k in ("policy", "versuche", "im_ziel", "urteil", "elemente", "stuerze",
                                                     "max_neigung_grad", "zeit_s", "ende", "hinweise", "rechenzeit_s")}}

    async def _practice(self, a: dict[str, Any]) -> dict[str, Any]:
        if self.practice is None:
            return {"ok": False, "fehler": "Die Physik zum Üben ist nicht eingerichtet (Einstellungen → Körper)."}
        import asyncio

        from ..physics.practice import rehearse

        spec = list(a.get("keyframes") or [])
        if not spec:
            return {"ok": False, "fehler": "Keine Keyframes"}
        loops = max(1, min(20, int(_num(a, "loops", 1))))

        def run():
            from ..physics.core import PhysicsCore

            if self._practice_core is None:
                self._practice_core = PhysicsCore(None)
            return rehearse(self.practice, spec, loops, core=self._practice_core)

        res = await asyncio.to_thread(run)
        title = str(a.get("title") or "Bewegung")[:40]
        self.practice_log.append({"titel": title, **{k: res[k] for k in ("urteil", "max_neigung_grad", "umgefallen_bei_s")}})
        del self.practice_log[:-20]
        self.engine.note({"type": "practice", "message": f"Geübt: {title} – {res['urteil']}"})
        return {"ok": True, **res}
