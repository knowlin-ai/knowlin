"""Stimme der Verkörperung (und Knowlins eigene): Motoren, Stimmen, Installation, Entwerfen je Körper."""

from __future__ import annotations

import asyncio
import json
import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ...aio import spawn
from ..runtime import (
    Runtime,
    _json_default,
)

log = logging.getLogger(__name__)

# Probetext je Körper, wenn die Oberfläche keinen schickt (Reachy ist keine Ente: kein Quaken)
PROBE = {
    "duckpilot": "*quak quak* Hallo, ich bin {name}! So klinge ich jetzt. Gefällt dir meine Stimme?",
    "open_duck_mini": "*quak* Hallo, ich bin {name}! Selbst gebaut und startklar. Gefällt dir meine Stimme?",
    "reachy_mini": "Hallo, ich bin {name}. So klinge ich jetzt. Gefällt dir meine Stimme?",
}


def probetext(modul: str, name: str) -> str:
    from ...voice.tts import STANDARD_NAME

    return PROBE.get(modul, PROBE["duckpilot"]).format(name=(name or "").strip() or STANDARD_NAME.get(modul, "Quacki"))


def register(app: FastAPI, runtime: Runtime) -> None:
    # ── Stimme der Ente ──────────────────────────────────────────────────
    @app.get("/api/stimme")
    async def get_voice() -> JSONResponse:
        await asyncio.to_thread(runtime.gpus)
        from ...figuren import FIGUR_KEYS, FIGUREN

        msg = runtime.voice_message()
        # Stimmen gehören Verkörperungen (seit 0.38.6): wer welche entworfene Stimme nutzt – fürs Zuweisen in der Oberfläche
        jetzt = {k: getattr(runtime.config, k) for k in FIGUR_KEYS if hasattr(runtime.config, k)}
        msg["figuren"] = [{"modul": m, "name": (jetzt if m == runtime.config.modul else runtime.figuren.profil(m)).get("duck_name")
                           or f["name"], "koerper": f["art"], "ente": f.get("ente", True), "aktiv": m == runtime.config.modul,
                           "stimme_qwen": (jetzt if m == runtime.config.modul else runtime.figuren.profil(m)).get("stimme_qwen", "")}
                          for m, f in FIGUREN.items()]
        return JSONResponse(json.loads(json.dumps(msg, default=_json_default)))

    @app.get("/api/stimme/clip/{cid}.wav")
    async def voice_clip(cid: str):
        from fastapi.responses import Response

        try:
            audio = await runtime.speaker.clip(cid)
        except KeyError:
            return JSONResponse({"fehler": "unbekannt"}, status_code=404)
        except Exception as exc:
            return JSONResponse({"fehler": f"{type(exc).__name__}: {exc}"}, status_code=503)
        return Response(audio.wav, media_type="audio/wav", headers={"Cache-Control": "no-store",
                                                                    "X-Rechenzeit": str(audio.rechenzeit)})

    @app.post("/api/stimme/probe")
    async def voice_probe(request: Request) -> JSONResponse:
        body = await request.json()
        if body.get("fuer") == "kopf":         # Knowlins eigene Stimme (seit 0.38.10)
            name = runtime.config.kopf_name or "Knowlin"
            text = str(body.get("text") or f"Ich bin {name}. So klinge ich.")[:300]
            return JSONResponse({"ok": True, "sprache": runtime.speaker.prepare_kopf(text), "text": text})
        name = runtime.config.duck_name
        text = str(body.get("text") or probetext(runtime.config.modul, name))[:300]
        plan = runtime.speaker.prepare(text, str(body.get("stimmung") or "fröhlich"), runtime.config.goofy,
                                       runtime.config.energie)
        return JSONResponse({"ok": True, "sprache": plan, "text": text})

    @app.post("/api/stimme/laden")
    async def voice_download(request: Request) -> JSONResponse:
        body = await request.json()
        vid = str(body.get("stimme", ""))
        from ...voice.tts import PIPER_VOICES

        if vid not in PIPER_VOICES:
            return JSONResponse({"ok": False, "fehler": "unbekannte Stimme"}, status_code=400)
        spawn(runtime.speaker.download_piper(vid))
        return JSONResponse({"ok": True})

    @app.post("/api/stimme/installieren")
    async def voice_install(request: Request) -> JSONResponse:
        body = await request.json()
        paket, gpu = str(body.get("paket", "")), str(body.get("gpu", "cpu"))
        from ...voice.install import GPUS, PAKETE

        if paket not in PAKETE or gpu not in GPUS:
            return JSONResponse({"ok": False, "fehler": "unbekanntes Paket oder Grafikkarte"}, status_code=400)
        if runtime.installer.running():
            return JSONResponse({"ok": False, "fehler": "Es läuft schon eine Installation."}, status_code=409)
        spawn(runtime.install(paket, gpu))
        return JSONResponse({"ok": True})

    @app.post("/api/stimme/entwerfen")
    async def voice_design(request: Request) -> JSONResponse:
        body = await request.json()
        text = str(body.get("beschreibung", ""))
        if len(text.strip()) < 10:
            return JSONResponse({"ok": False, "fehler": "Beschreib die Stimme in ein, zwei Sätzen."}, status_code=400)
        if not runtime.speaker.synth.qwen.installed():
            return JSONResponse({"ok": False, "fehler": "Qwen3-TTS ist noch nicht installiert."}, status_code=400)
        kopf = body.get("fuer") == "kopf"
        name = (runtime.config.kopf_name or "Knowlin") if kopf else runtime.config.duck_name
        # Der Probesatz der Fassungen passt zum Körper: Reachy und Knowlin sagen nichts von einer Ente (5.11.)
        spawn(runtime.speaker.design(text, name, int(body.get("fassungen") or 3), "kopf" if kopf else runtime.config.modul))
        return JSONResponse({"ok": True})

    @app.post("/api/stimme/uebernehmen")
    async def voice_adopt(request: Request) -> JSONResponse:
        body = await request.json()
        try:
            vid = runtime.speaker.adopt(str(body.get("fassung", "")), str(body.get("name", "")))
            if body.get("fuer") == "kopf":
                await runtime.apply_settings({"kopf_stimme_qwen": vid, "kopf_stimme_motor": "qwen"})
            else:
                await runtime.apply_settings({"stimme_qwen": vid, "stimme_motor": "qwen"})
        except (KeyError, ValueError) as exc:
            return JSONResponse({"ok": False, "fehler": str(exc).strip("'")}, status_code=400)
        return JSONResponse({"ok": True, "stimme": vid})

    @app.delete("/api/stimme/qwen/{vid}")
    async def voice_delete(vid: str) -> JSONResponse:
        try:
            runtime.speaker.delete_voice(vid)
            if runtime.config.stimme_qwen == vid:
                await runtime.apply_settings({"stimme_qwen": ""})
            if runtime.config.kopf_stimme_qwen == vid:
                await runtime.apply_settings({"kopf_stimme_qwen": "", "kopf_stimme_motor": "piper"})
        except ValueError as exc:
            return JSONResponse({"ok": False, "fehler": str(exc)}, status_code=400)
        return JSONResponse({"ok": True})
