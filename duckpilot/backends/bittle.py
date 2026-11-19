"""Bittle X im Simulator (seit 0.38.59): Petois kleiner Roboterhund.

Bittle X ist ein offener Lern-Roboterhund von Petoi (Software OpenCat unter MIT-Lizenz): etwa 19 × 15 × 11 cm, 270 bis
350 g, neun Gelenke – je Bein Schulter und Knie, dazu ein Gelenk im Hals, das den Kopf seitlich dreht. Auf dem ESP32-Board
sitzen ein Lagesensor und ein Modul für Sprachbefehle; ein Summer spielt Melodien, sprechen kann er nicht. Es gibt ihn
auch mit Greifarm (kommt später).

Hier läuft er im einfachen Simulator wie die Enten: laufen, drehen, sitzen, er fällt bei einem harten Stoß um und steht
nach dem Stopp-Fenster wieder auf (dieselben Regeln wie überall, nie hochgehoben). Er hat keinen Schnabel, keinen
Tiefensensor und keine eigene Stimme – Knowlin spricht für ihn. Gezeichnet wird er in der 3D-Ansicht selbst
(`static/bittle3d.js`), ohne Dateien von Petoi. Der Kopf dreht nur seitlich (±70°), nicken kann er mit dem Körper.

Seit 0.38.65 („Bello wie das Original“) hat die Figur die Maße aus Petois offenem Simulationsmodell (nur die Zahlen) und
läuft in drei Gangarten (`GANGARTEN`: Krabbeln, Traben, Hoppeln) – umgeschaltet über das skill-Werkzeug, gültig bis zur
nächsten Wahl, mit eigener Höchstgeschwindigkeit. Dazu Bewegungen nach Petois Kürzeln, die ihn mitnehmen (`UNTERWEGS`).

Der echte Bittle X ist noch nicht angebunden; geplant ist Petois serielles Protokoll (OpenCat, über USB oder Bluetooth).
"""

from __future__ import annotations

import math

from ..api import DuckState, Head, IntentResult, Perception, Twist
from .sim import SimBackend

EIGENSCHAFTEN = frozenset({"beine", "kopf", "mikrofon"})
KOPF_DREH = math.radians(70)
# Bellos Tricks (seit 0.38.61, nach dem Abgleich mit Petois eingebauten Tricks; Maintainer: „Ja und weiter“):
# Name → (Titel, Dauer in s, kurze Beschreibung). Gezeichnet in static/bittle3d.js, Kacheln auf der Trickseite.
# Salto und Handstand gibt es nur im Simulator – am echten Hund kämen sie erst nach eigener Prüfung dazu.
TRICKS: dict[str, tuple[str, float, str]] = {
    "pfote": ("Pfote geben", 2.6, "setzt sich und winkt mit der Pfote"),
    "strecken": ("Strecken", 2.8, "streckt die Vorderbeine weit nach vorn"),
    "verbeugen": ("Verbeugen", 2.4, "vorn tief, Po hoch – die Spielaufforderung"),
    "liegestuetze": ("Liegestütze", 4.2, "drei Liegestütze auf den Vorderbeinen"),
    "platz": ("Platz", 3.6, "legt sich hin und ruht kurz"),
    "tot_stellen": ("Tot stellen", 3.6, "kippt auf die Seite und bleibt liegen"),
    "boxen": ("Boxen", 3.2, "sitzt und boxt mit beiden Vorderpfoten"),
    "umschauen": ("Umschauen", 3.0, "dreht den Kopf nach links und rechts"),
    "handstand": ("Handstand", 3.4, "auf die Vorderbeine – nur im Simulator"),
    "salto": ("Rückwärtssalto", 2.4, "ein Salto rückwärts – nur im Simulator"),
    # Seit 0.38.64 (Maintainer: „mach männchen“ ging nicht; Abgleich mit Petois OpenCat-Fähigkeiten, MIT):
    "maennchen": ("Männchen", 3.4, "setzt sich auf und hebt beide Vorderpfoten"),  # Petoi „hu“
    "high_five": ("High five", 2.8, "sitzt und hält dir die Pfote hoch hin"),  # Petoi „fiv“
    "jubeln": ("Jubeln", 3.2, "sitzt aufrecht und winkt mit beiden Pfoten"),  # Petoi „chr“
    "nicken": ("Nicken", 2.2, "nickt ein paarmal mit dem Kopf"),  # Petoi „nd“
    "schnueffeln": ("Schnüffeln", 3.4, "schnüffelt mit gesenktem Kopf hin und her"),  # Petoi „snf“
    "kratzen": ("Kratzen", 3.0, "sitzt und kratzt sich mit dem Hinterbein"),  # Petoi „scrh“
    "graben": ("Graben", 3.4, "buddelt mit den Vorderpfoten"),  # Petoi „dg“
    "kicken": ("Auskeilen", 2.4, "tritt mit einem Hinterbein nach hinten"),  # Petoi „kc“
    "springen": ("Springen", 2.0, "geht in die Hocke und hüpft hoch"),  # Petoi „jmp“
    "tisch": ("Tisch", 3.0, "steht mit ganz geraden Beinen still wie ein Tisch"),  # Petoi „tbl“
    "schlafen": ("Schlafen", 5.0, "legt sich hin und lässt den Kopf sinken"),  # Petoi „zz“
    "frontsalto": ("Vorwärtssalto", 2.4, "ein Salto vorwärts – nur im Simulator"),  # Petoi „ff“
    # Seit 0.38.65 („Bello wie das Original“): Bewegungen nach Petois Kürzeln, die ihn mitnehmen oder auf der Stelle laufen
    "rueckwaerts": ("Rückwärts", 3.0, "trabt ein Stück rückwärts"),  # Petoi „bk“
    "auf_der_stelle": ("Auf der Stelle", 3.0, "trabt auf der Stelle, ohne loszulaufen"),  # Petoi „vt“
    "moonwalk": ("Moonwalk", 4.0, "gleitet rückwärts, während die Beine vorwärts laufen"),  # Petoi „mw“
    "umarmen": ("Umarmen", 3.4, "setzt sich auf und schließt die Vorderpfoten wie zu einer Umarmung"),  # Petoi „hg“
    "komm_her": ("Komm her", 3.0, "sitzt und winkt dich mit der Pfote heran"),  # Petoi „cmh“
    "rollen": ("Rollen", 3.2, "rollt einmal über die Seite und steht wieder auf"),  # Petoi „rl“
}
# Tricks, die ihn ein Stück mitnehmen: Name → (Geschwindigkeit vorwärts in m/s, von, bis – Anteil der Trickdauer)
UNTERWEGS: dict[str, tuple[float, float, float]] = {
    "rueckwaerts": (-0.08, 0.1, 0.9),
    "moonwalk": (-0.05, 0.12, 0.88),
}
# Gangarten (seit 0.38.65, nach Petois Gangarten): Name → (Titel, höchste Geschwindigkeit vorwärts in m/s, Schritt-Takt
# im Verhältnis zum Traben, kurze Beschreibung). Die Geschwindigkeiten sind für den Simulator geschätzt, nicht gemessen.
# Umschalten über das skill-Werkzeug („krabbeln“), die Kacheln auf der Trickseite oder per Zuruf; gilt, bis eine andere
# gewählt wird. Die 3D-Ansicht setzt die Beine je Gangart anders (static/bittle3d.js GANGARTEN).
GANGARTEN: dict[str, tuple[str, float, float, str]] = {
    "krabbeln": ("Krabbeln", 0.06, 0.6, "tief am Boden, ein Bein nach dem anderen"),  # Petoi „cr“
    "traben": ("Traben", 0.18, 1.0, "diagonale Beinpaare im Wechsel – seine Grundgangart"),  # Petoi „tr“
    "hoppeln": ("Hoppeln", 0.25, 1.15, "Vorder- und Hinterbeine im Wechsel, wie ein Hase"),  # Petoi „bd“
}
GRUND_GANGART = "traben"
# Gelernte Gangart (seit 0.43, `physics/bello.py`): im MuJoCo-Modell mit einer Evolutionsstrategie gelernt, hier gezeigt.
# Tempo und Takt kommen aus dem Lernergebnis; die Handgangart „traben“ läuft mit 2 Schrittzyklen je Sekunde.
GELERNT = "gelernt"
HAND_TAKT_HZ = 2.0
OHNE = "Bello ist ein Hund ohne Schnabel – aufheben, Purzelbaum und Pollens Tricks gehen nicht; seine eigenen Tricks schon"


def kopf_lage(head: Head) -> dict[str, float]:
    """Kopfbefehl → Bittles Halsgelenk: nur seitlich drehen. Nicken zeigt die 3D-Ansicht mit dem Vorderkörper."""
    return {"yaw": round(max(-KOPF_DREH, min(KOPF_DREH, head.head_yaw)), 4),
            "pitch": round(max(-0.35, min(0.35, head.head_pitch - head.neck_pitch * 0.6)), 4)}


class BittleSim(SimBackend):
    """Bittle X im einfachen Simulator: gleiches Wohnzimmer, läuft auf vier Beinen."""

    koerper_art = "bittle"

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.extra_skills = {name: dauer for name, (_, dauer, _) in TRICKS.items()}
        self.gangart = GRUND_GANGART
        self._tanz: tuple[str, float] | None = None      # Tanzschritt (seit 0.43): Trick, bis wann wiederholen
        self.gelernt: dict | None = None                  # gelernte Gangart (seit 0.43): {parameter, tempo}

    def gelernt_setzen(self, gang: dict | None) -> None:
        """Gelernte Gangart übernehmen (oder vergessen – dann zurück zum Traben)."""
        ok = isinstance(gang, dict) and isinstance(gang.get("parameter"), dict) and isinstance(gang.get("tempo"), (int, float))
        self.gelernt = {"parameter": dict(gang["parameter"]), "tempo": max(0.02, min(0.36, float(gang["tempo"])))} if ok else None
        if self.gelernt is None and self.gangart == GELERNT:
            self.gangart = GRUND_GANGART

    def trick_titel(self) -> dict[str, str]:
        """Für das skill-Werkzeug: was die eigenen Tricks bedeuten (statt „vom Hub geladen“)."""
        titel = {name: f"{t} – {text}" for name, (t, _, text) in TRICKS.items()}
        titel.update({name: f"Gangart {t} – {text}" for name, (t, _, _, text) in GANGARTEN.items()})
        if self.gelernt:
            titel[GELERNT] = "Gangart Gelernt – im Physikmodell selbst gelernt (Lernen → Bello lernt laufen)"
        return titel

    def eigenschaften(self) -> frozenset[str]:
        return EIGENSCHAFTEN | {"simulator", "zuruecksetzen"}

    def skills(self) -> list[str]:
        return ["sit_toggle", *TRICKS, *GANGARTEN, *([GELERNT] if self.gelernt else [])]

    async def do(self, skill: str) -> IntentResult:
        if skill == GELERNT:
            if not self.gelernt:
                return IntentResult(False, "Bello hat noch keine Gangart gelernt – unter Tricks → „Bello lernt laufen“")
            self.gangart = GELERNT
            self.emit("gangart", gangart=GELERNT, message="Gangart: Gelernt")
            return IntentResult(True, "Gangart Gelernt")
        if skill in GANGARTEN:                         # Gangart wechseln: sofort, auch im Sitzen – gilt beim nächsten Laufen
            self.gangart = skill
            self.emit("gangart", gangart=skill, message=f"Gangart: {GANGARTEN[skill][0]}")
            return IntentResult(True, f"Gangart {GANGARTEN[skill][0]}")
        if skill != "sit_toggle" and skill not in TRICKS:
            return IntentResult(False, OHNE)
        return await super().do(skill)

    # ── Tanzen (seit 0.43, Bauart „vierbeiner“): Tanzschritte sind Tricks am Platz, wiederholt bis zum Schrittende ──
    async def tanz_schritt(self, name: str, sekunden: float, bpm: float) -> IntentResult:
        if name not in TRICKS or name in UNTERWEGS or name in ("salto", "frontsalto", "handstand", "rollen", "tot_stellen"):
            return IntentResult(False, f"„{name}“ tanzt Bello nicht")
        if self.skill in TRICKS:                          # der vorige Tanzschritt darf gehen
            self.skill = None
        r = await self.do(name)
        self._tanz = (name, self.t + max(0.5, float(sekunden))) if r.accepted else None
        return r

    def tanz_ende(self) -> None:
        self._tanz = None

    def _step_skill(self, dt: float) -> None:
        super()._step_skill(dt)
        if self._tanz is None:
            return
        name, bis = self._tanz
        if self.fallen or not self.powered or self.t >= bis:
            self._tanz = None
        elif self.skill is None and bis - self.t > 0.6 * TRICKS[name][1]:
            self._start_skill(name)                       # noch Zeit: den Trick noch einmal

    async def move(self, twist: Twist) -> None:
        """Wie überall, nur so schnell, wie die gewählte Gangart läuft (rückwärts höchstens halb so schnell)."""
        vmax = self.gelernt["tempo"] if self.gangart == GELERNT and self.gelernt else GANGARTEN[self.gangart][1]
        t = twist.clamped()
        await super().move(Twist(max(-vmax / 2, min(vmax, t.vx)), max(-vmax / 2, min(vmax / 2, t.vy)), t.vyaw))

    def _skill_twist(self) -> Twist | None:
        if self.skill in UNTERWEGS:
            v, von, bis = UNTERWEGS[self.skill]
            p = self._skill_progress()
            return Twist(v if von < p < bis else 0.0, 0.0, 0.0)
        return super()._skill_twist()

    def _schritt_takt(self) -> float:
        if self.gangart == GELERNT and self.gelernt:
            return float(self.gelernt["parameter"].get("takt_hz", HAND_TAKT_HZ)) / HAND_TAKT_HZ
        return GANGARTEN[self.gangart][2]

    async def sound(self, tag: str) -> IntentResult:
        return IntentResult(False, "Bello hat keine Entenlaute – Knowlin spricht für ihn")

    def _pick_or_drop(self) -> None:                   # kein Schnabel
        return None

    def _update_tof(self) -> None:
        self._tof, self._points, self._sectors = [], [], {}   # kein Tiefensensor

    def state(self) -> DuckState:
        st = super().state()
        st.koerper = self.koerper_art
        st.gangart = self.gangart
        if self.gangart == GELERNT and self.gelernt:          # die 3D-Ansicht setzt die Beine danach (bittle3d.js)
            p = self.gelernt["parameter"]
            st.gang_form = {k: round(float(p.get(k, 0.0)), 4) for k in ("schritt", "hub", "luft", "ducken")}
        st.holding = None
        st.perception = Perception(objects=st.perception.objects, source="sim")
        ruhig = self.sitting or not self.powered or (self.skill in TRICKS and self.skill != "umschauen")
        st.kopf_lage = {"yaw": 0.0, "pitch": 0.0} if ruhig else kopf_lage(st.head)
        return st

    def fassung(self, skill: str) -> dict[str, str]:
        return {"fassung": "Bittle X im einfachen Simulator von Knowlin – gezeichnete Bewegung, ohne Modell von Petoi"}
