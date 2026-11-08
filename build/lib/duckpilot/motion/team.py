"""Teamarbeit der Enten (seit 0.37.4, Wunsch des Maintainers): Die Hauptente bittet die anderen um Hilfe.

„Kann meine Ente den anderen Enten Sachen erzählen und sie um Hilfe bitten? Z. B. dass bei mehreren Gegenständen die
anderen helfen, sie von A nach B zu transportieren – oder beim Suchen helfen, und wer sie gefunden hat zuerst, meldet
sich.“

Zwei Aufträge, die der Schwarm (`motion/schwarm.py`) für die Begleitenten ausführt:

- **Aufräumen** – Dinge zu einem Ziel bringen (Sofa, gemerkter Ort, zu mir). Jede Ente nimmt sich das ihr nächste
  freie Ding (keine nimmt eines, das schon eine andere trägt), trägt es hin, legt es ab, meldet sich und holt das
  nächste. Kommt eine nicht heran, gibt sie das Ding frei und sagt es.
- **Suchen** – jede Ente sucht in ihrem Teil des Zimmers. Wer das Gesuchte zuerst sieht, ruft „Gefunden!“ mit eigener
  Stimme; die anderen kommen gucken, die Finderin bringt es zur Hauptente.

Die Begleitenten kennen die Möbel direkt (wie im Simulator üblich) und planen ihre Wege mit derselben Rasterkarte und
A* wie die Hauptente (`motion/karte.py`). Not-Aus gilt wie immer: Der Schwarm hält dann alle an.
"""

from __future__ import annotations

import math
from typing import Any

from ..api import Head, Pose, Twist
from .karte import ZELLE, Karte, zelle

AUFHEBBAR = ("sock", "block", "baustein", "figur")
GREIF_M = 0.085 + 0.06          # vom Rumpf bis vor den Schnabel (wie SimBackend._pick_or_drop)
FEST_S = 10.0                   # so lange ohne Fortschritt = kommt nicht heran
ABLAGE_M = 0.3                  # wie nah am Ziel ein Ding als „aufgeräumt“ gilt
SUCHE_S = 90.0


def karte_aus_welt(welt: Any) -> Karte:
    """Rasterkarte aus den bekannten Möbeln und Wänden (die Begleitenten „wissen“, wo alles steht)."""
    k = Karte()
    w, d = welt.width / 2, welt.depth / 2
    i0, i1 = zelle(-w, -d), zelle(w, d)
    for i in range(i0[0] - 1, i1[0] + 2):
        for j in range(i0[1] - 1, i1[1] + 2):
            x, y = (i + 0.5) * ZELLE, (j + 0.5) * ZELLE
            k.zellen[(i, j)] = 3.0 if welt.collide(x, y, 0.001) else -3.0
    k.messungen = 1
    return k


def _winkel(a: float) -> float:
    return (a + math.pi) % (2 * math.pi) - math.pi


class Auftrag:
    """Gemeinsames für Aufräumen und Suchen: Wege planen und ablaufen, melden."""

    art = "auftrag"

    def __init__(self, schwarm: Any) -> None:
        self.sw = schwarm
        self.welt = schwarm.haupt.world_model
        self.karte = karte_aus_welt(self.welt)
        self.t0 = schwarm.t
        self.fertig = False
        self.ergebnis = ""
        self.lage: dict[int, dict[str, Any]] = {}       # Nummer → Zustand der Helferin
        self.meldungen: list[str] = []

    def melden(self, e: Any | None, text: str, laut: str = "chirp") -> None:
        self.meldungen.append(text)
        if e is not None:
            self.sw.haupt.emit("sound", tag=laut, ente=e.ente_name, klang=list(e.klang),
                           x=round(e.x, 2), y=round(e.y, 2))
        self.sw.haupt.emit("schwarm", message=text)

    def meiden(self, e: Any, ziel: tuple[float, float]) -> set[tuple[int, int]]:
        """Zellen um liegende Dinge, um die sie herumgeht (seit 0.37.5, Hinweis aus dem Test: „die Enten schieben die
        Gegenstände am Zielort wieder vor sich her“) – außer dem Ding, das sie holt, und rund um ihr eigenes Ziel."""
        ziel_ding = self.lage.get(e.nummer, {}).get("ding")
        aus: set[tuple[int, int]] = set()
        r = 2                                             # ≈ Ente + Ding: 10 cm um die Mitte
        for i in self.welt.items:
            if i.held or i.name == ziel_ding or i.kind == "ball":
                continue
            c = zelle(i.x, i.y)
            for di in range(-r, r + 1):
                for dj in range(-r, r + 1):
                    if di * di + dj * dj <= r * r:
                        aus.add((c[0] + di, c[1] + dj))
        frei = zelle(*ziel)
        return {c for c in aus if (c[0] - frei[0]) ** 2 + (c[1] - frei[1]) ** 2 > 4}

    def weg(self, e: Any, ziel: tuple[float, float]) -> list[tuple[float, float]]:
        r = self.karte.route((e.x, e.y), ziel, meiden=self.meiden(e, ziel))
        if r is None:
            r = self.karte.route((e.x, e.y), ziel)        # eingekeilt: dann eben ohne Rücksicht auf die Dinge
        return list(r) if r else [ziel]

    def laufen(self, e: Any, s: dict[str, Any], kopf: float = 0.0):
        """Den geplanten Weg ablaufen. → (twist, head, pose, mund) oder None, wenn angekommen."""
        while s["weg"] and math.hypot(s["weg"][0][0] - e.x, s["weg"][0][1] - e.y) < 0.07:
            s["weg"].pop(0)
        if not s["weg"]:
            return None
        tx, ty = s["weg"][0]
        fehler = _winkel(math.atan2(ty - e.y, tx - e.x) - e.yaw)
        dist = math.hypot(tx - e.x, ty - e.y)
        vmax = 0.1 if len(s["weg"]) == 1 and dist < 0.3 else 0.18     # am Ziel vorsichtig
        vx = vmax * min(1.0, dist / 0.25 + 0.3) * max(0.0, math.cos(fehler)) if abs(fehler) < 0.9 else 0.0
        return Twist(vx, 0.0, max(-1.0, min(1.0, 2.4 * fehler))), Head(0.0, 0.1, kopf, 0.0), Pose(), 0.0

    def fortschritt(self, e: Any, s: dict[str, Any], ziel: tuple[float, float]) -> bool:
        """False, wenn sie seit FEST_S Sekunden nicht näher kommt."""
        d = math.hypot(ziel[0] - e.x, ziel[1] - e.y)
        if d < s.get("best", math.inf) - 0.03:
            s["best"], s["best_t"] = d, self.sw.t
        return self.sw.t - s.get("best_t", self.sw.t) < FEST_S

    def regel(self, e: Any):
        raise NotImplementedError

    def zustand(self) -> dict[str, Any]:
        return {"art": self.art, "fertig": self.fertig, "ergebnis": self.ergebnis, "meldungen": self.meldungen[-6:]}


class Aufraeumen(Auftrag):
    """Dinge von A nach B tragen – alle helfen mit."""

    art = "aufraeumen"

    def __init__(self, schwarm: Any, ziel: tuple[float, float], ziel_name: str, arten: tuple[str, ...] = AUFHEBBAR,
                 haupt_nimmt: str | None = None, nur: set[str] | None = None, still: bool = False) -> None:
        super().__init__(schwarm)
        self.ziel, self.ziel_name = self.freier_platz(ziel), ziel_name
        self.arten = arten
        self.nur = nur                                   # nur diese Dinge (z. B. das Gefundene)
        self.vergeben: dict[str, str] = {}               # Ding → wer es holt („haupt“ oder Ententenkennung)
        self.unerreichbar: set[str] = set()
        self.gebracht: list[str] = []
        if haupt_nimmt:
            self.vergeben[haupt_nimmt] = "haupt"
        if still:
            self.melden = lambda *a, **k: None           # type: ignore[method-assign]
        offen = [i.name for i in self.offen()]
        self.melden(None, f"Helft mir aufräumen: {len(offen)} {'Ding' if len(offen) == 1 else 'Dinge'} zu {ziel_name}!"
                    if offen else f"Hier ist schon alles bei {ziel_name}.")
        if not offen:
            self.fertig, self.ergebnis = True, "schon aufgeräumt"

    def freier_platz(self, p: tuple[float, float]) -> tuple[float, float]:
        """Ablageplatz: das Ziel selbst oder – steht dort ein Möbel – davor, Richtung Raummitte."""
        x, y = p
        for _ in range(60):
            if self.welt.collide(x, y, 0.16) is None:
                return (x, y)
            d = math.hypot(x, y) or 1.0
            x, y = x - x / d * 0.03, y - y / d * 0.03
        return p

    def offen(self) -> list[Any]:
        return [i for i in self.welt.items
                if i.kind in self.arten and not i.held and i.name not in self.unerreichbar
                and i.name not in self.gebracht                # einmal gebracht bleibt gebracht
                and (self.nur is None or i.name in self.nur)
                and math.hypot(i.x - self.ziel[0], i.y - self.ziel[1]) > ABLAGE_M]

    def ablage(self, e: Any) -> tuple[float, float]:
        """Jede Ente legt an ihrem eigenen Fleck ab (nicht alle auf denselben Haufen)."""
        a = e.nummer * 1.6
        x, y = self.ziel[0] + 0.12 * math.cos(a), self.ziel[1] + 0.12 * math.sin(a)
        return (x, y) if self.welt.collide(x, y, 0.1) is None else self.ziel

    def ablage_stand(self, e: Any) -> tuple[float, float]:
        """Wo sie stehen bleibt, damit das Ding (es fällt ≈ 15 cm vor ihr hin) genau auf ihrem Ablagefleck landet."""
        ax, ay = self.ablage(e)
        dx, dy = ax - e.x, ay - e.y
        d = math.hypot(dx, dy) or 1.0
        x, y = ax - dx / d * 0.15, ay - dy / d * 0.15
        return (x, y) if self.welt.collide(x, y, 0.1) is None else (ax, ay)

    def regel(self, e: Any):
        s = self.lage.setdefault(e.nummer, {"phase": "frei"})
        if e.holding and s["phase"] != "tragen":
            s.update(phase="tragen", ding=e.holding, weg=self.weg(e, self.ablage_stand(e)), best=math.inf,
                     best_t=self.sw.t)
        if s["phase"] == "frei":
            if not self.haupt_traegt():                   # hat die Hauptente ihr Ding nicht hingebracht: übernehmen
                for name in [n for n, wer in self.vergeben.items() if wer == "haupt"]:
                    del self.vergeben[name]
            frei = [i for i in self.offen() if i.name not in self.vergeben]
            if not frei and self.nacharbeiten(e):
                frei = [i for i in self.offen() if i.name not in self.vergeben]
            if not frei:
                if not any(v["phase"] in ("hin", "tragen", "zurueck") for v in self.lage.values()) \
                        and not self.haupt_traegt():
                    self.abschliessen()
                return Twist(), Head(0.0, 0.05, 0.0, 0.0), Pose(), 0.0
            ding = min(frei, key=lambda i: math.hypot(i.x - e.x, i.y - e.y))
            self.vergeben[ding.name] = e.kennung
            s.update(phase="hin", ding=ding.name, weg=self.weg(e, (ding.x, ding.y)), best=math.inf, best_t=self.sw.t)
            self.melden(e, f"{e.ente_name}: Ich hole {ding.name}!")
        ding = next((i for i in self.welt.items if i.name == s.get("ding")), None)
        if s["phase"] == "hin":
            if ding is None or (ding.held and e.holding != ding.name):
                s["phase"] = "frei"
                return Twist(), None, None, None
            ux, uy = ding.x - e.x, ding.y - e.y
            d = math.hypot(ux, uy) or 1.0
            stand = (ding.x - ux / d * GREIF_M, ding.y - uy / d * GREIF_M)
            if d < GREIF_M + 0.1:                          # davor: ausrichten, heranrücken, dann aufheben
                fehler = _winkel(math.atan2(uy, ux) - e.yaw)
                if not self.fortschritt(e, s, (ding.x, ding.y)):
                    s["weg"] = []
                if abs(fehler) > 0.2 or d > GREIF_M + 0.02:
                    vx = 0.07 if d > GREIF_M + 0.01 and abs(fehler) < 0.4 else (-0.04 if d < GREIF_M - 0.03 else 0.0)
                    return Twist(vx, 0.0, max(-0.8, min(0.8, 2.0 * fehler))), Head(0.0, 0.4, 0.0, 0.0), Pose(), 0.0
                e._pick_or_drop()
                if e.holding != ding.name:                 # das Falsche erwischt oder daneben
                    if e.holding:
                        e._pick_or_drop()
                    s["best_t"] = self.sw.t - FEST_S / 2   # nicht ewig probieren
                    return Twist(-0.05, 0.0, 0.0), Head(0.0, 0.3, 0.0, 0.0), Pose(), 0.0
                s.update(phase="tragen", weg=self.weg(e, self.ablage_stand(e)), best=math.inf, best_t=self.sw.t)
                return Twist(), Head(0.0, -0.05, 0.0, 0.0), Pose(), 0.0
            if not self.fortschritt(e, s, (ding.x, ding.y)):
                self.unerreichbar.add(ding.name)
                self.vergeben.pop(ding.name, None)
                s["phase"] = "frei"
                self.melden(e, f"{e.ente_name}: Ich komme nicht an {ding.name} heran.", "inquire")
                return Twist(), None, None, None
            if not s["weg"] or math.hypot(s["weg"][-1][0] - stand[0], s["weg"][-1][1] - stand[1]) > 0.1:
                s["weg"] = self.weg(e, stand)
            cmd = self.laufen(e, s)
            return cmd or (Twist(), Head(0.0, 0.3, 0.0, 0.0), Pose(), 0.0)
        if s["phase"] == "tragen":
            ablage = self.ablage(e)
            if s["weg"]:                                   # zum Ablagefleck schauen, bevor sie ablegt
                pass
            elif abs(_winkel(math.atan2(ablage[1] - e.y, ablage[0] - e.x) - e.yaw)) > 0.25 and \
                    math.hypot(ablage[0] - e.x, ablage[1] - e.y) > 0.05:
                fehler = _winkel(math.atan2(ablage[1] - e.y, ablage[0] - e.x) - e.yaw)
                return Twist(0.0, 0.0, max(-0.9, min(0.9, 2.2 * fehler))), Head(0.0, 0.2, 0.0, 0.0), Pose(), 0.0
            cmd = self.laufen(e, s, kopf=0.0)
            if cmd is not None and self.fortschritt(e, s, ablage):
                return cmd[0], Head(0.0, -0.05, 0.0, 0.0), cmd[2], cmd[3]
            name = e.holding
            if name:
                e._pick_or_drop()                          # ablegen (auch wenn sie nicht ganz hinkam)
            angekommen = math.hypot(ablage[0] - e.x, ablage[1] - e.y) < ABLAGE_M + 0.15
            if name and angekommen:
                self.gebracht.append(name)
                self.melden(e, f"{e.ente_name}: {name} ist bei {self.ziel_name}!", "greet")
            elif name:
                self.unerreichbar.add(name)
                self.melden(e, f"{e.ente_name}: Ich komme mit {name} nicht durch.", "inquire")
            self.vergeben.pop(name or "", None)
            s.update(phase="zurueck", bis=self.sw.t + 1.2)   # erst rückwärts weg vom Abgelegten, dann umdrehen
            return Twist(), Head(0.0, 0.05, 0.0, 0.0), Pose(), 0.0
        if s["phase"] == "zurueck":
            if self.sw.t < s["bis"]:
                return Twist(-0.1, 0.0, 0.0), Head(0.0, 0.25, 0.0, 0.0), Pose(), 0.0
            s["phase"] = "frei"
            return Twist(), Head(0.0, 0.05, 0.0, 0.0), Pose(), 0.0
        return None

    NACHARBEIT_MAX = 2

    def nacharbeiten(self, e: Any) -> bool:
        """Ist etwas Gebrachtes weggerollt oder weggeschoben? Dann holt sie es noch einmal (je Ding höchstens 2×)."""
        if not hasattr(self, "nachgeholt"):
            self.nachgeholt: dict[str, int] = {}
        for i in self.welt.items:
            if i.name in self.gebracht and not i.held and \
                    math.hypot(i.x - self.ziel[0], i.y - self.ziel[1]) > ABLAGE_M + 0.15 and \
                    self.nachgeholt.get(i.name, 0) < self.NACHARBEIT_MAX:
                self.nachgeholt[i.name] = self.nachgeholt.get(i.name, 0) + 1
                self.gebracht.remove(i.name)
                self.melden(e, f"{e.ente_name}: {i.name} ist weggerollt – ich hole es zurück.", "inquire")
                return True
        return False

    def haupt_traegt(self) -> bool:
        """Holt die Hauptente gerade selbst noch etwas? (Dann ist das Team erst danach fertig.)"""
        cur = getattr(self.sw.engine, "current", None)
        return any(v == "haupt" for v in self.vergeben.values()) and cur is not None and \
            getattr(cur, "name", "") == "apportieren" and not cur.done

    def abschliessen(self) -> None:
        if self.fertig:
            return
        self.fertig = True
        n = sum(1 for i in self.welt.items if i.kind in self.arten and not i.held
                and (self.nur is None or i.name in self.nur)
                and (i.name in self.gebracht or math.hypot(i.x - self.ziel[0], i.y - self.ziel[1]) <= ABLAGE_M + 0.1))
        rest = sorted(self.unerreichbar)
        self.ergebnis = (f"Fertig: {n} {'Ding' if n == 1 else 'Dinge'} zu {self.ziel_name} gebracht"
                         + (f" – nicht erreicht: {', '.join(rest)}" if rest else "") + ".")
        self.melden(None, self.ergebnis)


class Suche(Auftrag):
    """Gemeinsam suchen: jede in ihrem Teil des Zimmers; wer es zuerst sieht, meldet sich und bringt es."""

    art = "suchen"

    def __init__(self, schwarm: Any, ding: str) -> None:
        super().__init__(schwarm)
        self.ding = ding.lower()
        self.finderin: Any = None
        self.fundort: tuple[float, float] | None = None
        self.melden(None, f"Helft mir suchen: {ding}!")
        n = max(1, len(schwarm.enten))
        w, d = self.welt.width / 2 - 0.3, self.welt.depth / 2 - 0.3
        # Suchpunkte im ganzen Zimmer, reihum verteilt – jede bekommt ihren Teil
        punkte = [(x, y) for x in (-w, -w / 3, w / 3, w) for y in (-d, 0.0, d)
                  if self.welt.collide(x, y, 0.16) is None]
        self.teile = {e.nummer: [p for k, p in enumerate(punkte) if k % n == idx] for idx, e in enumerate(schwarm.enten)}

    def _sieht(self, e: Any) -> Any:
        for o in e._visible_objects():
            if self.ding in str(o.get("name", "")).lower() or self.ding == o.get("art"):
                return next((i for i in self.welt.items if i.name == o["name"]), None)
        return None

    def haupt_sieht(self, objekte: list[dict[str, Any]]) -> None:
        """Die Hauptente hat es selbst entdeckt (ihre Wahrnehmung)."""
        if self.fundort is not None:
            return
        for o in objekte:
            if self.ding in str(o.get("name", "")).lower():
                i = next((x for x in self.welt.items if x.name == o["name"]), None)
                if i is not None:
                    self.fundort = (i.x, i.y)
                    self.fertig = True
                    self.ergebnis = f"Ich hab {i.name} selbst gefunden!"
                    self.melden(None, self.ergebnis, "greet")
                    return

    def regel(self, e: Any):
        s = self.lage.setdefault(e.nummer, {"phase": "suchen", "weg": [], "punkte": list(self.teile.get(e.nummer, []))})
        if self.sw.t - self.t0 > SUCHE_S and self.fundort is None:
            self.fertig, self.ergebnis = True, f"Keiner hat {self.ding} gefunden."
            self.melden(None, self.ergebnis, "inquire")
            return None
        if self.fundort is None:
            i = self._sieht(e)
            if i is not None:                              # gefunden – laut melden, mit eigener Stimme
                self.finderin, self.fundort = e, (i.x, i.y)
                naehe = self.ortsangabe(i.x, i.y)
                self.melden(e, f"{e.ente_name}: Gefunden – {i.name} liegt {naehe}!", "greet")
                if i.kind in AUFHEBBAR:                    # die Finderin trägt es – dieselbe Mechanik wie Aufräumen
                    self.bringen = Aufraeumen(self.sw, self.vor_der_hauptente(), "dir", (i.kind,), nur={i.name},
                                              still=True)
                else:
                    self.fertig, self.ergebnis = True, f"{e.ente_name} hat {i.name} gefunden."
            # weiter suchen: nächster Punkt, unterwegs umschauen
            if not s["weg"]:
                if not s["punkte"]:
                    s["punkte"] = list(self.teile.get(e.nummer, []))
                if s["punkte"]:
                    s["weg"] = self.weg(e, s["punkte"].pop(0))
            kopf = 0.6 * math.sin(self.sw.t * 1.3 + e.nummer)
            return self.laufen(e, s, kopf) or (Twist(0.0, 0.0, 0.6), Head(0.0, 0.1, kopf, 0.0), Pose(), 0.0)
        # gefunden: die Finderin bringt es (falls tragbar), die anderen kommen gucken
        if e is self.finderin and getattr(self, "bringen", None) is not None:
            self.bringen.ziel = self.vor_der_hauptente()
            cmd = self.bringen.regel(e)
            if self.bringen.gebracht or self.bringen.unerreichbar:
                self.fertig = True
                self.ergebnis = (f"{e.ente_name} hat {self.bringen.gebracht[0]} gefunden und dir gebracht."
                                 if self.bringen.gebracht else f"{e.ente_name} hat es gefunden, kommt aber nicht heran.")
                self.melden(e, self.ergebnis, "greet")
            return cmd
        if s.get("phase") != "gucken":
            fx, fy = self.fundort
            a = math.atan2(e.y - fy, e.x - fx)
            s.update(phase="gucken", weg=self.weg(e, (fx + 0.35 * math.cos(a), fy + 0.35 * math.sin(a))))
        cmd = self.laufen(e, s)
        if cmd is None:                                    # angekommen: hingucken
            fx, fy = self.fundort
            fehler = _winkel(math.atan2(fy - e.y, fx - e.x) - e.yaw)
            return Twist(0.0, 0.0, max(-0.8, min(0.8, 2.0 * fehler))), Head(0.0, 0.35, 0.0, 0.0), Pose(), 0.0
        return cmd

    def vor_der_hauptente(self) -> tuple[float, float]:
        h = self.sw.haupt
        return (h.x + 0.3 * math.cos(h.yaw), h.y + 0.3 * math.sin(h.yaw))

    def ortsangabe(self, x: float, y: float) -> str:
        moebel = sorted((math.hypot(m.x - x, m.y - y), m.name) for m in [*self.welt.boxes, *self.welt.cylinders])
        if moebel and moebel[0][0] < 0.9:
            n = moebel[0][1]
            return f"bei der {n}" if n.endswith("e") else f"beim {n}"
        return "mitten im Zimmer"
