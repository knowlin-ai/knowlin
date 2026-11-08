"""Hindernissen ausweichen und sie umlaufen – für alle Modi (seit 0.33).

Bis 0.32 hat der Hindernis-Reflex nur gebremst: Stand etwas vor ihr, blieb die Ente davor stehen und lief bei
„Folg mir“, Laser, Hinlaufen oder Erkunden auf der Stelle dagegen. Jetzt sitzt zwischen jedem Verhalten (und der
Fahrhilfe von Hand) und den Beinen diese Schicht:

- **Kurzes Hindernisgedächtnis:** die ToF-Punkte der letzten Sekunden im Raum (`Perception.points`), damit sie ein
  Hindernis nicht vergisst, sobald es beim Drehen aus dem 45°-Blickfeld rutscht. Bodenpunkte zählen nicht.
- **Lenken statt nur bremsen:** Sie prüft Richtungen bis ±90° um die gewünschte Fahrtrichtung und nimmt die
  nächstgelegene freie. Ist voraus noch Platz, lenkt sie im Gehen; ist es eng, dreht sie auf der Stelle.
- **Festsitzen erkennen:** Will sie vorwärts und kommt 2,5 s lang keine 3 cm weiter, setzt sie kurz zurück und
  dreht zur freieren Seite.
- **Ohne Punkte** fällt sie auf die drei ToF-Sektoren zurück und dreht zur freieren Seite – so auch am echten
  Roboter, bis die Kopf-Kalibrierung dort geprüft ist (R1).
- **Anstoßen merken (seit 0.38.27, Odi O1):** Sieht sie nichts (keine Tiefenpunkte – Odi ohne Kamera, echte Open
  Duck, echte Microduck bis R1), merkt sie sich, wo sie festsaß, anstieß, fiel oder einen Ruck von vorn bekam
  (`state.ruck`, nicht von der Hand), zwei Minuten lang als kurze Wand, setzt weiter zurück und lenkt beim nächsten
  Anlauf daran vorbei. Mit Tiefenpunkten bleibt alles wie bisher.

Die Schicht ist reine Motorik: Sie kennt weder Gehirn noch einen bestimmten Körper, nur `DuckState` und `Twist`.
Sie greift nur in Vorwärtsfahrt ein; seitwärts, rückwärts und Drehen auf der Stelle lässt sie, wie sie sind.
Verhalten, die bewusst nah heran wollen (Annähern an den Ball), schalten sie wie bisher über `guard` ab.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from ..api import DuckState, Twist
from ..i18n import t

MEM_S = 4.0                # so lange bleiben ToF-Punkte im Gedächtnis
MEM_MAX = 1500             # höchstens so viele Rasterzellen
ZELLE = 0.03               # m – Raster des Gedächtnisses (ein Punkt je Zelle, der jüngste)
MEM_RANGE = 1.6            # m – weiter entfernte Punkte werden nicht gemerkt
MIN_Z, MAX_Z = 0.03, 0.40  # m – darunter Boden, darüber kann sie drunter durch
HALF_W = 0.11              # m – halbe Breite des Korridors (Ente ≈ 0,085 m Radius + Rand)
STEP = math.radians(15)    # Raster der geprüften Richtungen
MAX_ANGLE = math.radians(90)
TURN_GAIN = 1.8            # rad/s je rad Abweichung
TURN_MAX = 1.0             # rad/s – wie trainiert
TURN_IN_PLACE = 0.9        # rad/s – über der Totzone von Pollens Geh-Policy
HOLD_SIDE_S = 1.5          # so lange bleibt sie bei der gewählten Seite (kein Hin und Her)
STUCK_S = 2.5              # so lange ohne Fortschritt = festgesessen
STUCK_MOVE = 0.03          # m
BACK_S, BACK_V = 0.7, -0.10
BACK_BLIND_S = 1.6         # ohne Sensorpunkte weiter zurück (≈ 16 cm): sie sieht nicht, wie weit das Ding reicht
FREE_TURN_S = 0.9
SICHT = math.radians(30)   # so weit neben der Blickrichtung zählt eine Richtung als gesehen (ToF ±22,5° + Rand)
# Punkte nur aus Quellen, deren Blickneigung sicher stimmt. Am echten Roboter hängt sie an `head_signs`; eine
# falsche Kalibrierung macht Bodenpunkte zu Hindernissen. Dort bis zur Prüfung am Gerät (R1) nur die Sektoren,
# die den Boden selbst herausrechnen.
PUNKT_QUELLEN = frozenset({"sim"})
UMLAUF_S = 3.0             # so lange nach dem Ausweichen gilt: am Hindernis entlang, nicht zurückdrehen
UMLAUF_BLICK = math.radians(40)  # in diese Richtung (zur Drehseite) muss es frei sein, damit sie abbiegt
FLANKE_HINTEN, FLANKE_VORN, FLANKE_SEITE = -0.10, 0.18, 0.17   # m – Bereich neben ihr, in den sie nicht dreht
NAH, NAH_VX = 0.30, 0.13    # m, m/s – so nah an etwas geht sie höchstens so schnell (Anrempeln ohne Umfallen)
SPRUNG = 0.25              # m – größerer Sprung der Odometrie in einem Takt = neu gesetzt
UNGESEHEN = 0.30           # m – so viel Platz wird für ungesehene Richtungen höchstens angenommen
STOSS_S = 120.0            # so lange bleibt eine Stelle gemerkt, an der sie angestoßen ist
STOSS_VOR = 0.13           # m – so weit vor der Körpermitte liegt das, woran sie stieß (Brust/Schnabel)
STOSS_BREITE = (-0.10, -0.05, 0.0, 0.05, 0.10)   # m – quer dazu, so breit wie sie selbst
STOSS_MAX = 12             # höchstens so viele Stellen


@dataclass
class Entscheidung:
    twist: Twist
    note: str | None = None
    seite: int = 0          # +1 links, −1 rechts, 0 geradeaus


class Ausweicher:
    """Lenkt Vorwärtsfahrt um Hindernisse herum. Zustand: Punktgedächtnis, gewählte Seite, Festsitzen."""

    def __init__(self, stop: float = 0.16, look: float = 0.45) -> None:
        self._ziel: tuple[float, float, float] | None = None
        self.stop = stop
        self.look = look
        self.clock = 0.0
        self._pts: dict[tuple[int, int], tuple[float, float, float]] = {}   # Rasterzelle → (t, x, y)
        self._seite = 0
        self._seite_bis = 0.0
        self._stuck_ref: tuple[float, float, float] | None = None   # (t, x, y) seit wann vorwärts gewollt
        self._befreien_bis = 0.0
        self._befreien_start = 0.0
        self._pose: tuple[float, float] | None = None
        self._umlauf_bis = 0.0
        self._umlauf_vx = 0.12
        self._stoesse: list[tuple[float, list[tuple[float, float]]]] = []   # (t, Punkte in Weltkoordinaten)
        self._ruck_n: int | None = None
        self._back_s = BACK_S
        self._befreien_faellig = False      # nach gemeldetem Anstoß/Sturz: beim nächsten Vorwärts erst zurücksetzen

    # ── Gedächtnis ────────────────────────────────────────────────────────
    def merken(self, st: DuckState, dt: float) -> None:
        self.clock += dt
        now = self.clock
        if self._pose is not None and math.hypot(st.x - self._pose[0], st.y - self._pose[1]) > SPRUNG:
            self.vergessen()        # Odometrie neu gesetzt (Verbinden, Körperwechsel): alte Punkte passen nicht mehr
        self._pose = (st.x, st.y)
        if st.perception.source not in PUNKT_QUELLEN:
            return                  # echter Roboter: erst nach der Kopf-Kalibrierung (sonst Boden als Hindernis)
        for p in st.perception.points or ():
            if len(p) < 3 or not (MIN_Z <= p[2] <= MAX_Z):
                continue
            if math.hypot(p[0] - st.x, p[1] - st.y) > MEM_RANGE:
                continue
            self._pts[(round(p[0] / ZELLE), round(p[1] / ZELLE))] = (now, p[0], p[1])
        if len(self._pts) > MEM_MAX or int(now * 4) != int((now - dt) * 4):    # viermal je Sekunde aufräumen
            alt = sorted(self._pts.items(), key=lambda kv: kv[1][0])
            for k, (t, _, _) in alt:
                if now - t > MEM_S or len(self._pts) > MEM_MAX:
                    del self._pts[k]

    def umlauf_aktiv(self) -> bool:
        """Weicht sie gerade aus bzw. läuft um etwas herum? (Dann schaut die Engine in die Kurve.)"""
        return self.clock < self._umlauf_bis

    def arbeitet(self) -> bool:
        """Tastet sie sich gerade blind um eine Anstoß-Stelle herum? Dann ist der Umweg kein „kommt nicht weiter“."""
        return bool(self._stoesse) and self.clock < self._befreien_bis + 3.0

    @staticmethod
    def blind(st: DuckState, pts: dict | None = None) -> bool:
        """Ohne jede Tiefenwahrnehmung (keine Punkte, keine Sektoren) – nur dann merkt sie sich Anstoß-Stellen."""
        return not pts and not any(v is not None for v in (st.perception.sectors or {}).values())

    def vergessen(self) -> None:
        self._pts.clear()
        self._stoesse.clear()
        self._befreien_faellig = False
        self._stuck_ref = None
        self._befreien_bis = 0.0
        self._umlauf_bis = 0.0

    def _ziel_voraus(self, st: DuckState) -> bool:
        """Liegt das Kontaktziel grob voraus und nah? Dann zählt es nicht als Hindernis – auch nicht für die drei
        Sektoren am echten Roboter, die das Ziel nicht von einem Hindernis unterscheiden können."""
        if not self._ziel:
            return False
        zx, zy, r = self._ziel
        d = math.hypot(zx - st.x, zy - st.y)
        peil = abs(math.atan2(math.sin(math.atan2(zy - st.y, zx - st.x) - st.yaw),
                              math.cos(math.atan2(zy - st.y, zx - st.x) - st.yaw)))
        return d < self.look + r and peil < math.radians(35)

    def stoss_merken(self, st: DuckState) -> None:
        """Die Stelle vor ihr, an der sie hängen blieb, als kurze Wand quer zur Laufrichtung merken."""
        c, s = math.cos(st.yaw), math.sin(st.yaw)
        mx, my = st.x + STOSS_VOR * c, st.y + STOSS_VOR * s
        self._stoesse = [x for x in self._stoesse if self.clock - x[0] < STOSS_S][-(STOSS_MAX - 1):]
        self._stoesse.append((self.clock, [(mx - q * s, my + q * c) for q in STOSS_BREITE]))

    def angestossen(self, st: DuckState) -> bool:
        """Gemeldeter Anstoß („bump“) oder Sturz gegen etwas, während sie vorwärts ging: Stelle merken. Nicht, wenn
        das Ding voraus ihr Ziel ist (Ball schießen) – das will sie ja treffen."""
        if st.requested.vx <= 0.03 and st.twist.vx <= 0.03:
            return False
        if not self.blind(st, self._pts):
            return False            # sie sieht das Ding ohnehin (Punkte oder Sektoren) – das bewährte Umlaufen reicht
        if self._ziel_voraus(st):
            return False
        self.stoss_merken(st)
        self._befreien_faellig = True
        return True

    def stoesse(self) -> list[tuple[float, float]]:
        """Gemerkte Anstoß-Stellen (Weltkoordinaten) – für Tests und die Oberfläche."""
        return [p for t0, pts in self._stoesse if self.clock - t0 < STOSS_S for p in pts]

    def _koerper(self, st: DuckState) -> list[tuple[float, float]]:
        """Gemerkte Punkte im Körperrahmen (x vorwärts, y links) – ohne das Kontaktziel. Dazu die Anstoß-Stellen."""
        c, s = math.cos(st.yaw), math.sin(st.yaw)
        ziel = getattr(self, "_ziel", None)
        out = []
        for px, py in self.stoesse():
            dx, dy = px - st.x, py - st.y
            out.append((dx * c + dy * s, -dx * s + dy * c))
        for _, px, py in self._pts.values():
            if ziel and math.hypot(px - ziel[0], py - ziel[1]) < ziel[2]:
                continue
            dx, dy = px - st.x, py - st.y
            out.append((dx * c + dy * s, -dx * s + dy * c))
        return out

    def freiraum(self, pts: list[tuple[float, float]], winkel: float) -> float:
        """Wie weit ist in Richtung `winkel` (Körperrahmen) ein Korridor von 2·HALF_W frei? (m, höchstens 2·look)"""
        c, s = math.cos(winkel), math.sin(winkel)
        frei = 2 * self.look
        for x, y in pts:
            f = x * c + y * s
            if f <= 0:
                continue
            if abs(-x * s + y * c) < HALF_W:
                frei = min(frei, f)
        return frei

    # ── Lenken ────────────────────────────────────────────────────────────
    def lenken(self, st: DuckState, twist: Twist, *, hand: bool = False,
               ziel: tuple[float, float, float] | None = None) -> Entscheidung:
        """Vorwärtsfahrt `twist` um Hindernisse lenken. `hand` = Fahrhilfe beim Steuern von Hand (sanfter).
        `ziel` = (x, y, Radius) eines Dings, zu dem sie absichtlich hin will (Ball schießen, Annähern): Das ist kein
        Hindernis – sonst wiche sie genau dem aus, was sie treffen soll."""
        self._ziel = ziel
        now = self.clock
        if st.fallen or st.picked_up:
            self._stuck_ref = None
            return Entscheidung(twist)
        if twist.vx <= 0 and now < self._umlauf_bis and abs(twist.vyaw) > 0.05 and not hand:
            # Ein Verhalten mit Ziel will zurückdrehen – zum Hindernis hin. Dann am Hindernis entlang weitergehen,
            # bis die Richtung frei ist (sonst Hin und Her zwischen Ausweichen und Zurückdrehen).
            richtung = math.copysign(UMLAUF_BLICK, twist.vyaw)
            pts = self._koerper(st)
            if pts and self.freiraum(pts, richtung) < self.look:
                twist = Twist(min(self._umlauf_vx, NAH_VX), twist.vy, 0.0)
        elif (twist.vx > 0 and now < self._umlauf_bis and not hand and self._seite
              and twist.vyaw * self._seite < -0.05):
            # im Gehen zurück zur Hindernisseite lenken: erst, wenn es dort frei ist – bis dahin vorsichtig geradeaus
            pts = self._koerper(st)
            if pts and self.freiraum(pts, math.copysign(UMLAUF_BLICK, twist.vyaw)) < self.look:
                twist = Twist(min(twist.vx, NAH_VX), twist.vy, 0.0)
        if twist.vx <= 0:
            self._stuck_ref = None
            return Entscheidung(twist)

        # Festsitzen: vorwärts gewollt, aber nicht vorwärts gekommen
        if now < self._befreien_bis:
            seite = self._seite or 1
            if now - self._befreien_start < self._back_s:
                return Entscheidung(Twist(BACK_V, 0.0, 0.0), t("ausweichen.fest_zurueck"), seite)
            return Entscheidung(Twist(0.0, 0.0, seite * TURN_IN_PLACE), t("ausweichen.fest_drehen"), seite)
        ruck = st.ruck if isinstance(st.ruck, dict) else None
        n = int(ruck.get("n", 0)) if ruck else None
        neuer_ruck = (n is not None and self._ruck_n is not None and n > self._ruck_n
                      and ruck.get("quelle") != "Hand" and not self._ziel_voraus(st))
        self._ruck_n = n
        if self._stuck_ref is None or (math.hypot(st.x - self._stuck_ref[1], st.y - self._stuck_ref[2]) > STUCK_MOVE
                                       and not neuer_ruck):
            self._stuck_ref = (now, st.x, st.y)
        fest = now - self._stuck_ref[0] > STUCK_S
        if (fest or neuer_ruck or self._befreien_faellig) and not hand:
            if not self._ziel_voraus(st) and not self._befreien_faellig and self.blind(st, self._pts):
                self.stoss_merken(st)
            self._befreien_faellig = False
            pts = self._koerper(st)
            self._seite = 1 if self.freiraum(pts, math.radians(60)) >= self.freiraum(pts, -math.radians(60)) else -1
            self._back_s = BACK_BLIND_S if self.blind(st, self._pts) else BACK_S
            self._seite_bis = now + HOLD_SIDE_S + self._back_s + FREE_TURN_S
            self._befreien_start = now
            self._befreien_bis = now + self._back_s + FREE_TURN_S
            self._stuck_ref = None
            return Entscheidung(Twist(BACK_V, 0.0, 0.0), t("ausweichen.fest_zurueck"), self._seite)

        pts = self._koerper(st)
        if not pts:
            return self._sektoren(st, twist)
        return self._flanken(pts, self._entscheiden(st, twist, pts, hand))

    def bremsen(self, st: DuckState, twist: Twist, *, ziel: tuple[float, float, float] | None = None) -> Entscheidung:
        """Nur bremsen, nicht lenken – wie bis 0.32. Für den Schalter „Hindernissen ausweichen“ aus (Wunsch des Maintainers:
        das Umlaufen unter Verhalten an- und abschaltbar)."""
        self._stuck_ref = None
        self._ziel = ziel
        if st.fallen or st.picked_up or twist.vx <= 0:
            return Entscheidung(twist)
        if self._ziel_voraus(st):
            return Entscheidung(twist)
        pts = self._koerper(st)
        if pts:
            front = self.freiraum(pts, 0.0)
        else:
            sec = st.perception.sectors or {}
            front = sec.get("mitte")
            if front is None:
                seiten = [d for d in sec.values() if d is not None]
                front = min(seiten) * 1.6 if seiten else None
        if front is None or front >= self.look:
            return Entscheidung(twist)
        k = max(0.0, (front - self.stop) / (self.look - self.stop))
        vx = 0.0 if front <= self.stop else twist.vx * max(0.25, k)
        return Entscheidung(Twist(vx, twist.vy, twist.vyaw), t("ausweichen.gebremst", m=front), 0)

    def _flanken(self, pts: list[tuple[float, float]], e: Entscheidung) -> Entscheidung:
        """Neben ihr (außerhalb des Korridors voraus): nicht in eine Kante hineindrehen und nah dran langsam gehen."""
        tw = e.twist
        if tw.vx <= 0:
            return e
        links = rechts = False
        nah = 9.0
        for x, y in pts:
            nah = min(nah, math.hypot(x, y))
            if FLANKE_HINTEN < x < FLANKE_VORN and abs(y) < FLANKE_SEITE:
                links |= y > 0
                rechts |= y < 0
        vyaw = tw.vyaw
        if (vyaw > 0 and links) or (vyaw < 0 and rechts):
            vyaw = 0.0
        vx = min(tw.vx, NAH_VX) if nah < NAH else tw.vx
        if vyaw == tw.vyaw and vx == tw.vx:
            return e
        return Entscheidung(Twist(vx, tw.vy, vyaw), e.note or t("ausweichen.neben"), e.seite)

    def _entscheiden(self, st: DuckState, twist: Twist, pts: list[tuple[float, float]], hand: bool) -> Entscheidung:
        now = self.clock
        # gewünschte Richtung: was das Verhalten ohnehin lenken will (ein Zehntelsekunden-Vorgriff)
        wunsch = max(-MAX_ANGLE, min(MAX_ANGLE, twist.vyaw * 0.3))
        frei0 = self.freiraum(pts, wunsch)
        blick = getattr(st.head, "head_yaw", 0.0) or 0.0
        if frei0 >= self.look:
            return Entscheidung(twist)
        best, best_score = None, -1e9
        n = int(MAX_ANGLE / STEP)
        for i in range(-n, n + 1):
            w = wunsch + i * STEP
            if abs(w) > MAX_ANGLE + 1e-6:
                continue
            frei = self.freiraum(pts, w)
            if abs(w - blick) > SICHT:
                frei = min(frei, UNGESEHEN)   # dort hat sie gerade nicht hingeschaut – nicht blind hineinlaufen
            if frei <= self.stop + 0.05:
                continue
            score = min(frei, 1.5 * self.look) - 0.25 * abs(w - wunsch)
            seite = 1 if w > wunsch else -1 if w < wunsch else 0
            if seite and now < self._seite_bis and seite == self._seite:
                score += 0.08
            if score > best_score:
                best, best_score = w, score
        if best is None:
            # rundum zu: auf der Stelle zur freieren Seite drehen
            if now >= self._seite_bis or not self._seite:
                links = sum(self.freiraum(pts, a) for a in (0.5, 1.0, 1.5))
                rechts = sum(self.freiraum(pts, -a) for a in (0.5, 1.0, 1.5))
                self._seite = 1 if links >= rechts else -1
                self._seite_bis = now + HOLD_SIDE_S
            return Entscheidung(Twist(0.0, twist.vy, self._seite * TURN_IN_PLACE),
                                t("ausweichen.dreht_frei", m=frei0), self._seite)
        seite = 1 if best > wunsch else -1 if best < wunsch else 0
        if seite and (now >= self._seite_bis or seite != self._seite):
            self._seite, self._seite_bis = seite, now + HOLD_SIDE_S
        gain = TURN_GAIN * (0.5 if hand else 1.0)
        vyaw = max(-TURN_MAX, min(TURN_MAX, twist.vyaw + gain * (best - wunsch)))
        if frei0 <= self.stop:
            vx = 0.0                       # erst wegdrehen, dann weiter – immer zur einmal gewählten Seite
            drehen = self._seite if now < self._seite_bis and self._seite else (seite or 1)
            vyaw = drehen * max(TURN_IN_PLACE, abs(vyaw))
        else:
            k = (frei0 - self.stop) / (self.look - self.stop)
            vx = twist.vx * max(0.35, min(1.0, k))
        if not hand:
            self._umlauf_bis, self._umlauf_vx = now + UMLAUF_S, max(twist.vx, 0.12)
        if seite:
            note = t("ausweichen.weicht_aus", m=frei0, seite=t("seite.links" if seite > 0 else "seite.rechts"))
        else:
            note = t("ausweichen.gebremst", m=frei0)
        return Entscheidung(Twist(vx, twist.vy, vyaw), note, seite)

    def _sektoren(self, st: DuckState, twist: Twist) -> Entscheidung:
        """Rückfall ohne Punkte: drei ToF-Sektoren (Kopfrahmen) wie bis 0.32, aber zur freieren Seite drehen."""
        if self._ziel_voraus(st):
            return Entscheidung(twist)          # das Ding voraus ist das Ziel – das Verhalten hält selbst davor an
        sec = st.perception.sectors or {}
        front = sec.get("mitte")
        seiten = [d for d in sec.values() if d is not None]
        if front is None and seiten:
            front = min(seiten) * 1.6
        if front is None or front >= self.look:
            return Entscheidung(twist)
        links = sec.get("links") or 2 * self.look
        rechts = sec.get("rechts") or 2 * self.look
        seite = 1 if links >= rechts else -1
        if front <= self.stop:
            return Entscheidung(Twist(0.0, twist.vy, seite * TURN_IN_PLACE),
                                t("ausweichen.dreht_frei", m=front), seite)
        k = (front - self.stop) / (self.look - self.stop)
        vyaw = max(-TURN_MAX, min(TURN_MAX, twist.vyaw + seite * 0.6 * (1 - k)))
        return Entscheidung(Twist(twist.vx * max(0.25, k), twist.vy, vyaw),
                            t("ausweichen.gebremst", m=front), seite)
