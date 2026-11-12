"""Knowlets (seit 0.38.5): Verkörperung, Tricks und Tänze als Paket packen, prüfen, übernehmen und auf Hugging Face teilen.

Nur am PC (`remote.PC_ONLY`). Ein geladenes Paket wird erst geprüft und gezeigt; übernommen wird nur, was im Dialog
ausgewählt ist. Bevor ein Knowlet den Charakter einer Verkörperung ersetzt, sichert Knowlin die bisherige Verkörperung als Knowlet
im Datenordner (`knowlets/`), damit sich das rückgängig machen lässt.
"""

from __future__ import annotations

import secrets
import time
from asyncio import to_thread
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

from ... import __version__
from ... import knowlet_hub as H
from ... import knowlets as K
from ... import settings as S
from ...figuren import FIGUR_KEYS, FIGUREN, figur
from ..runtime import Runtime

OFFEN_S = 1800          # geprüfte, noch nicht übernommene Pakete verfallen nach 30 Minuten
MAX_OFFEN = 8


def register(app: FastAPI, runtime: Runtime) -> None:
    offen: dict[str, tuple[float, dict[str, Any]]] = {}

    def ordner():
        p = S.settings_path().parent / "knowlets"
        p.mkdir(parents=True, exist_ok=True)
        return p

    def figur_werte(modul: str) -> dict[str, Any]:
        if modul == runtime.config.modul:
            return {k: getattr(runtime.config, k) for k in FIGUR_KEYS if hasattr(runtime.config, k)}
        return runtime.figuren.profil(modul)

    def tricks_von(modul: str) -> dict[str, dict[str, Any]]:
        mem = runtime.memory
        if mem is None:
            return {}
        if modul == mem.figur:
            return dict(mem.data.get("tricks", {}))
        return dict(mem.data.get("tricks_je_figur", {}).get(modul, {}))

    def packe(b: dict[str, Any]) -> tuple[bytes, dict[str, Any]]:
        modul = b.get("modul") if b.get("modul") in K.koerper_ids() else runtime.config.modul
        tricks = tricks_von(modul)
        wahl_t = {n: tricks[n] for n in b.get("tricks") or [] if n in tricks}
        wahl_c = {n: c for n in b.get("taenze") or [] if (c := runtime.choreos.hole(n))}
        from ...werkbank_auftrag import eigene

        alle_a = eigene()
        wahl_a = {n: alle_a[n] for n in b.get("auftraege") or [] if n in alle_a}
        daten = K.packe(titel=b.get("titel") or "", beschreibung=b.get("beschreibung") or "",
                        urheber=b.get("urheber") or "", lizenz=b.get("lizenz") or "CC-BY-4.0", modul=modul,
                        figur=figur_werte(modul) if b.get("figur") else None, tricks=wahl_t, taenze=wahl_c,
                        version=__version__, auftraege=wahl_a)
        return daten, K.pruefe(daten)["steckbrief"]

    def merke(paket: dict[str, Any]) -> dict[str, Any]:
        jetzt = time.monotonic()
        for k in [k for k, (t, _) in offen.items() if jetzt - t > OFFEN_S]:
            offen.pop(k, None)
        while len(offen) >= MAX_OFFEN:
            offen.pop(next(iter(offen)))
        pid = secrets.token_urlsafe(9)
        offen[pid] = (jetzt, paket)
        modul = paket["steckbrief"]["fuer"]
        return {"ok": True, "id": pid, "ziel": {"modul": modul, "figur": figur_werte(modul).get("duck_name")
                                                 or figur(modul)["name"]},
                **K.vorschau(paket, set(tricks_von(modul)), {c["name"] for c in runtime.choreos.liste()})}

    def fehler(exc: Exception, code: int = 400) -> JSONResponse:
        return JSONResponse({"ok": False, "fehler": str(exc)}, status_code=code)

    @app.get("/api/knowlets")
    async def knowlets_uebersicht() -> JSONResponse:
        from ... import training

        figuren = []
        module = [*FIGUREN, *([runtime.config.modul] if runtime.config.modul not in FIGUREN else [])]   # + Erweiterung
        for modul in module:
            f = figur(modul)
            w = figur_werte(modul)
            figuren.append({"modul": modul, "name": w.get("duck_name") or f["name"], "koerper": f["art"],
                            "aktiv": modul == runtime.config.modul, "tricks": sorted(tricks_von(modul))})
        try:
            token = bool(await to_thread(training.get_token))
        except Exception:
            token = False
        gesichert = sorted((p.name for p in ordner().glob(f"*{K.ENDUNG}")), reverse=True)[:20]
        from ...werkbank_auftrag import eigene

        return JSONResponse({"figuren": figuren, "taenze": [c["name"] for c in runtime.choreos.liste()],
                             "auftraege": [{"id": k, "titel": v["titel"]} for k, v in eigene().items()],
                             "lizenzen": list(K.LIZENZEN), "hub": {"schluessel": token}, "gesichert": gesichert})

    @app.post("/api/knowlets/packen")
    async def knowlets_packen(request: Request):
        try:
            daten, st = packe(await request.json())
        except K.KnowletFehler as exc:
            return fehler(exc)
        datei = f"{K._dateiname(st['name'])}{K.ENDUNG}"
        return Response(daten, media_type="application/zip",
                        headers={"Content-Disposition": f'attachment; filename="{datei}"'})

    @app.post("/api/knowlets/pruefen")
    async def knowlets_pruefen(request: Request) -> JSONResponse:
        daten = await request.body()
        try:
            return JSONResponse(merke(K.pruefe(daten)))
        except K.KnowletFehler as exc:
            return fehler(exc)

    @app.post("/api/knowlets/gesichert/{datei}")
    async def knowlets_sicherung_laden(datei: str) -> JSONResponse:
        p = ordner() / datei
        if p.parent != ordner() or not p.is_file() or p.suffix != K.ENDUNG:
            return fehler(K.KnowletFehler("Diese Sicherung gibt es nicht."), 404)
        try:
            return JSONResponse(merke(K.pruefe(p.read_bytes())))
        except K.KnowletFehler as exc:
            return fehler(exc)

    @app.post("/api/knowlets/uebernehmen")
    async def knowlets_uebernehmen(request: Request) -> JSONResponse:
        b = await request.json()
        eintrag = offen.get(str(b.get("id") or ""))
        if eintrag is None:
            return fehler(K.KnowletFehler("Das Paket ist nicht mehr da – bitte noch einmal laden."), 404)
        paket = eintrag[1]
        modul = paket["steckbrief"]["fuer"]
        quelle = paket["steckbrief"]["name"]
        getan: list[str] = []
        if b.get("figur") and paket["figur"]:
            # vorher sichern: die bisherige Verkörperung als Knowlet im Datenordner
            alt = figur_werte(modul)
            name = alt.get("duck_name") or figur(modul)["name"]
            sicher = K.packe(titel=f"{name} vor {quelle}"[:40], beschreibung="Automatische Sicherung vor dem Übernehmen",
                             modul=modul, figur=alt, version=__version__)
            (ordner() / f"sicherung-{K._dateiname(name)}-{time.strftime('%Y%m%d-%H%M%S')}{K.ENDUNG}").write_bytes(sicher)
            werte = {k: v for k, v in paket["figur"].items() if k in K.FIGUR_TEILEN}
            if modul == runtime.config.modul:
                await runtime.apply_settings(werte)
            else:
                runtime.figuren.setze(modul, werte)
            getan.append(f"Charakter von {name} → {paket['figur'].get('duck_name') or name}")
        mem = runtime.memory
        wahl = [n for n in b.get("tricks") or [] if n in paket["tricks"]]
        if wahl and mem is None:
            return fehler(K.KnowletFehler("Tricks brauchen das Gedächtnis – es ist ausgeschaltet."))
        for n in wahl:
            t = paket["tricks"][n]
            ziel = mem.data["tricks"] if modul == mem.figur else mem.data.setdefault("tricks_je_figur", {}).setdefault(modul, {})
            frei = K.freier_name(n, set(ziel))
            if modul == mem.figur:
                frei = mem.remember_trick(frei, t["keyframes"], t["loops"], t["beschreibung"])
            else:
                ziel[frei] = {"keyframes": t["keyframes"], "loops": t["loops"], "beschreibung": t["beschreibung"],
                              "erstellt": time.strftime("%Y-%m-%dT%H:%M:%S"), "benutzt": 0, "version": 1}
            ziel[frei]["herkunft"] = f"Knowlet {quelle}"         # am echten Roboter erst nach einer Probe im Simulator
            ziel[frei]["probe"] = False
            getan.append(f"Trick {frei}")
        if wahl:
            mem.save()
        belegt = {c["name"] for c in runtime.choreos.liste()}
        for n in [n for n in b.get("taenze") or [] if n in paket["taenze"]]:
            frei = K.freier_name(n, belegt)
            try:
                runtime.choreos.speichere(frei, paket["taenze"][n])
            except ValueError as exc:
                return fehler(exc)
            belegt.add(frei)
            getan.append(f"Tanz {frei}")
        if b.get("auftraege"):                    # Werkbank-Aufträge (seit 0.38.54): geprüft gemerkt, nie Code
            from ...werkbank_auftrag import speichern

            for n in [n for n in b["auftraege"] if n in paket.get("auftraege", {})]:
                k, grund = speichern(paket["auftraege"][n])
                if k is None:
                    return fehler(K.KnowletFehler(grund))
                getan.append(f"Auftrag {paket['auftraege'][n]['titel']}")
        if not getan:
            return fehler(K.KnowletFehler("Nichts ausgewählt."))
        offen.pop(str(b.get("id")), None)
        if runtime.memory is not None:
            runtime.memory.log_event("Knowlet", f"{quelle}: " + ", ".join(getan))
        return JSONResponse({"ok": True, "uebernommen": getan})

    # ── Hugging Face ─────────────────────────────────────────────────────
    @app.get("/api/knowlets/hub/suche")
    async def knowlets_hub_suche(q: str = "") -> JSONResponse:
        try:
            return JSONResponse({"ok": True, "treffer": await to_thread(H.suche, q)})
        except Exception as exc:
            return JSONResponse({"ok": False, "fehler": f"Hugging Face nicht erreichbar ({type(exc).__name__})"},
                                status_code=502)

    @app.post("/api/knowlets/hub/laden")
    async def knowlets_hub_laden(request: Request) -> JSONResponse:
        b = await request.json()
        try:
            datei, daten = await to_thread(H.lade, str(b.get("repo") or ""), str(b.get("datei") or ""))
            out = merke(K.pruefe(daten))
        except K.KnowletFehler as exc:
            return fehler(exc)
        except Exception as exc:
            return JSONResponse({"ok": False, "fehler": f"Hugging Face nicht erreichbar ({type(exc).__name__})"},
                                status_code=502)
        return JSONResponse({**out, "quelle": {"repo": b.get("repo"), "datei": datei}})

    @app.post("/api/knowlets/hub/teilen")
    async def knowlets_hub_teilen(request: Request) -> JSONResponse:
        from ... import training

        b = await request.json()
        if b.get("bestaetigt") is not True:                       # zweiter Klick in der Oberfläche
            return fehler(K.KnowletFehler("Bitte das Hochladen bestätigen."))
        token = await to_thread(training.get_token)
        if not token:
            return fehler(K.KnowletFehler("Erst den Hugging-Face-Schlüssel hinterlegen (Lernen → Training)."))
        try:
            daten, st = packe(b)
            out = await to_thread(lambda: H.teile(daten, st, st["fuer"], token, slug=str(b.get("slug") or st["name"]),
                                                  oeffentlich=bool(b.get("oeffentlich"))))
        except K.KnowletFehler as exc:
            return fehler(exc)
        except Exception as exc:
            return JSONResponse({"ok": False, "fehler": f"Hochladen ging nicht ({type(exc).__name__})"}, status_code=502)
        return JSONResponse({"ok": True, **out})
