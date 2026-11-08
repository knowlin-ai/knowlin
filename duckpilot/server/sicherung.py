"""Sicherungspunkte in der laufenden App (seit 0.38.24): anlegen, zurücksetzen, wiederherstellen – und danach die
laufenden Teile (Gedächtnis, Erfahrungsnetz, Akrobatik-Heft, Raum, Charakter) neu laden, damit nichts den
zurückgeholten Stand beim nächsten Speichern wieder überschreibt. Die Dateiarbeit macht `duckpilot.sicherungspunkte`.

Vor jedem Zurücksetzen und Wiederherstellen entsteht automatisch ein Sicherungspunkt – so lässt sich auch das
rückgängig machen."""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .. import settings as S
from ..config import Config
from ..figuren import FIGUR_KEYS, FIGUREN
from ..sicherungspunkte import BEREICHE, CHARAKTER_KEYS, SicherungFehler, Sicherungspunkte

if TYPE_CHECKING:
    from .runtime import Runtime

log = logging.getLogger(__name__)
_LEER = {"gedaechtnis": None, "erfahrung": {"knoten": {}, "kanten": {}}, "uebungen": {"uebungen": {}, "posen": {}},
         "taenze": {}}


class SicherungService:
    def __init__(self, rt: "Runtime") -> None:
        self.rt = rt

    @property
    def punkte(self) -> Sicherungspunkte:
        from ..brain.memory import default_path

        mem = getattr(self.rt.memory, "path", None) or self.rt.config.memory_path or default_path()
        return Sicherungspunkte(S.settings_path().parent, Path(mem))

    # ── Charakter je Verkörperung ─────────────────────────────────────────
    def _jetzt(self) -> dict[str, Any]:
        cfg = self.rt.config
        return {k: getattr(cfg, k) for k in FIGUR_KEYS if hasattr(cfg, k)}

    def charakter(self) -> dict[str, dict[str, Any]]:
        aktiv = self.rt.config.modul
        out = {}
        for modul in FIGUREN:
            p = self.rt.figuren.profil(modul, self._jetzt() if modul == aktiv else None)
            out[modul] = {k: p[k] for k in CHARAKTER_KEYS if k in p}
        return out

    async def _charakter_setzen(self, werte: dict[str, dict[str, Any]]) -> None:
        aktiv = self.rt.config.modul
        for modul, w in werte.items():
            if modul not in FIGUREN or not w:
                continue
            w = S.validate({k: v for k, v in w.items() if k in CHARAKTER_KEYS})
            if modul == aktiv:
                await self.rt.apply_settings(w)
            else:
                self.rt.figuren.setze(modul, w)

    @staticmethod
    def _charakter_start() -> dict[str, dict[str, Any]]:
        c = Config()
        grund = {"eigenschaften": None, "eigenstaendig": c.eigenstaendig, "idle_life": c.idle_life, "plaudern": c.plaudern}
        return {m: {**grund, **{k: v for k, v in f["start"].items() if k in ("energie", "humor")}} for m, f in FIGUREN.items()}

    # ── Übersicht ─────────────────────────────────────────────────────────
    def uebersicht(self) -> dict[str, Any]:
        jetzt = self.punkte.jetzt()
        jetzt["charakter"] = {"verkoerperungen": len(FIGUREN)}
        return {"bereiche": [{"id": b, **BEREICHE[b], "zahlen": jetzt.get(b, {})} for b in BEREICHE],
                "punkte": self.punkte.liste()}

    def _speichern_alles(self) -> None:
        """Was im Speicher liegt, erst auf die Platte – sonst fehlt Frisches im Sicherungspunkt."""
        try:
            if self.rt.memory is not None:
                self.rt.memory.save()
            self.rt.erfahrung.netz._dirty = True
            self.rt.erfahrung.netz.save()
            raum = getattr(self.rt, "_raum", None)
            if raum is not None:
                raum.geaendert_karte = True
                raum.speichern()
        except Exception:
            log.warning("Vor dem Sicherungspunkt speichern", exc_info=True)

    def anlegen(self, name: str = "", art: str = "hand") -> dict[str, Any]:
        self._speichern_alles()
        return self.punkte.anlegen(art, name, None, self.charakter())

    def vorher(self, name: str, bereiche: list[str]) -> dict[str, Any] | None:
        """Schneller Sicherungspunkt vor „Alles vergessen“ und Co. – scheitert er, geht das Vergessen trotzdem."""
        try:
            self._speichern_alles()
            return self.punkte.anlegen("vor-zuruecksetzen", name, bereiche, self.charakter())
        except Exception:
            log.warning("Sicherungspunkt vor dem Vergessen", exc_info=True)
            return None

    def taeglich(self) -> dict[str, Any] | None:
        try:                     # beim Start (im Hintergrund): die Dateien sind frisch, nichts erst speichern
            return self.punkte.taeglich(self.charakter())
        except Exception:
            log.warning("Täglicher Sicherungspunkt", exc_info=True)
            return None

    def _pruefen(self, bereiche: list[str]) -> list[str]:
        bereiche = [b for b in dict.fromkeys(bereiche or []) if b in BEREICHE]
        if not bereiche:
            raise SicherungFehler("Bitte mindestens einen Bereich wählen.")
        if "uebungen" in bereiche and (getattr(self.rt, "acro", None) and self.rt.acro.job.get("laeuft")):
            raise SicherungFehler("Gerade läuft eine Übung – erst beenden, dann die Übungen zurückholen.")
        return bereiche

    # ── Zurücksetzen / Wiederherstellen ──────────────────────────────────
    async def zuruecksetzen(self, bereiche: list[str]) -> dict[str, Any]:
        bereiche = self._pruefen(bereiche)
        self._speichern_alles()
        vorher = self.punkte.anlegen("vor-zuruecksetzen", "", bereiche, self.charakter())
        q = self.punkte.quellen
        for b in bereiche:
            if b == "charakter":
                await self._charakter_setzen(self._charakter_start())
                continue
            if b == "raum":
                self._raum_anhalten()
                for f in (q["daten"] / "raum").glob("*.json") if (q["daten"] / "raum").is_dir() else []:
                    if f.name.startswith(("karte-", "sichtungen-")):
                        f.write_text("{}", encoding="utf-8")
                continue
            ziel = q["gedaechtnis"] if b == "gedaechtnis" else q["daten"] / {
                "erfahrung": "erfahrung.json", "uebungen": "akrobatik.json", "taenze": "choreos.json"}[b]
            if b == "gedaechtnis":
                from ..brain.memory import Memory

                inhalt = {**Memory._empty(), "figur": self.rt.config.modul}
            else:
                inhalt = _LEER[b]
            ziel.parent.mkdir(parents=True, exist_ok=True)
            ziel.write_text(json.dumps(inhalt, ensure_ascii=False), encoding="utf-8")
        self._neu_laden(bereiche)
        log.info("Zurückgesetzt: %s (vorher gesichert als %s)", ", ".join(bereiche), vorher.get("id"))
        return {"vorher": vorher, "betroffen": bereiche}

    async def wiederherstellen(self, pid: str, bereiche: list[str] | None = None) -> dict[str, Any]:
        p = self.punkte
        d = p.pfad(pid)
        meta = next((x for x in p.liste() if x["id"] == d.name), {})
        bereiche = self._pruefen([b for b in (bereiche or meta.get("bereiche", [])) if b in meta.get("bereiche", [])])
        self._speichern_alles()
        vorher = p.anlegen("vor-wiederherstellen", "", bereiche, self.charakter())
        for b in bereiche:
            if b == "charakter":
                await self._charakter_setzen(p.charakter_im(pid))
                continue
            if b == "raum":
                self._raum_anhalten()
            for quelle, ziel in p.dateien_im(pid, b):
                ziel.parent.mkdir(parents=True, exist_ok=True)
                tmp = ziel.with_name(ziel.name + ".zurueck")
                shutil.copy2(quelle, tmp)
                tmp.replace(ziel)
        self._neu_laden(bereiche)
        log.info("Wiederhergestellt aus %s: %s", pid, ", ".join(bereiche))
        return {"vorher": vorher, "betroffen": bereiche, "aus": meta}

    def _raum_anhalten(self) -> None:
        raum = getattr(self.rt, "_raum", None)
        if raum is not None:
            try:
                raum.kartieren_stopp()
            except Exception:
                pass
            raum.speichern = lambda: None          # der alte Raum schreibt nichts mehr zurück
        self.rt._raum = None

    def _neu_laden(self, bereiche: list[str]) -> None:
        rt = self.rt
        if "gedaechtnis" in bereiche and rt.memory is not None:
            from ..brain.memory import Memory

            m = rt.memory
            m.data = Memory._empty()
            m.load()
            fig = rt.config.modul
            if m.data.get("figur") != fig:
                m.set_figur(fig)
            m.save()                                     # meldet den neuen Stand an Oberfläche und Gehirn
        if "erfahrung" in bereiche:
            netz = rt.erfahrung.netz
            netz.knoten.clear()
            netz.kanten.clear()
            netz.akt.clear()
            netz.neu.clear()
            netz.load()
            netz._dirty = False
        if "uebungen" in bereiche and getattr(rt, "acro", None) is not None:
            with rt.acro._book_lock:
                rt.acro.book = rt.acro._load()
        if "raum" in bereiche:
            self._raum_anhalten()
            if getattr(rt, "runner", None) is not None:
                rt.runner.raum = rt.raum                 # frisch aus den zurückgeholten Dateien
