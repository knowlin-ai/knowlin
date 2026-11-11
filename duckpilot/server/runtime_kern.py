"""Laufzeit, Bereich Kern: Claude-Schlüssel, Handy-Fernbedienung/Tailscale und Stimme.

Teil der Klasse `Runtime` (server/runtime.py), ausgelagert nach Bereichen, damit runtime.py überschaubar bleibt.
Schicht: Verbindung (fachlich Kern, das Gehirn; siehe duckpilot/schichten.py). Die Methoden greifen auf Felder von `Runtime` zu (self.config, self.broadcast …).
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import sys
import time
from typing import Any

from .. import settings as S
from ..aio import spawn

log = logging.getLogger(__name__)

VOICE_KEYS = {"stimme_motor", "stimme_piper", "stimme_qwen", "qwen_qualitaet", "qwen_geduldig", "entenhaft", "entenlaute",
              "tts"}


def _json_default(o: Any) -> Any:
    """NaN/Unendlich → null, alles Unbekannte als Text (für json.dumps an die Fenster)."""
    if isinstance(o, float) and (math.isnan(o) or math.isinf(o)):
        return None
    return str(o)


class KernTeil:
    """Mischklasse für `Runtime` – nicht allein benutzbar."""

    async def set_key(self, key: str) -> dict[str, Any]:
        key = S.check_key_format(key)
        S.set_vault_key(key)
        self.config.api_key, self.config.key_source = key, "tresor"
        self._new_agent()
        await self.broadcast(self.init_message())
        return self.key_status()

    async def delete_key(self) -> dict[str, Any]:
        S.delete_vault_key()
        # Was jetzt noch gilt: Umgebungsvariable oder .env
        from ..config import load

        fallback = load(use_user_settings=False)
        self.config.api_key, self.config.key_source = fallback.api_key, fallback.key_source
        self._new_agent()
        await self.broadcast(self.init_message())
        return self.key_status()

    async def test_key(self) -> dict[str, Any]:
        if not self.config.api_key:
            return {"ok": False, "meldung": "Kein Schlüssel hinterlegt."}
        try:
            import anthropic

            client = anthropic.AsyncAnthropic(api_key=self.config.api_key)
            t0 = time.monotonic()
            await client.messages.create(model=self.config.model, max_tokens=5,
                                         messages=[{"role": "user", "content": "Sag nur: Quak"}])
            return {"ok": True, "meldung": f"Claude antwortet ({self.config.model}, {time.monotonic() - t0:.1f} s)."}
        except Exception as exc:
            name = type(exc).__name__
            text = {
                "AuthenticationError": "Der Schlüssel wird abgelehnt – bitte neu kopieren.",
                "PermissionDeniedError": "Der Schlüssel hat keinen Zugriff auf dieses Modell.",
                "NotFoundError": "Dieses Modell kennt die API nicht.",
                "RateLimitError": "Gerade zu viele Anfragen – gleich noch einmal versuchen.",
                "APIConnectionError": "Keine Verbindung zu Anthropic – Internet prüfen.",
            }.get(name, f"{name}: {exc}")
            return {"ok": False, "meldung": text}

    def key_status(self) -> dict[str, Any]:
        cfg = self.config
        return {
            "gesetzt": bool(cfg.api_key),
            "quelle": cfg.key_source,
            "hinweis": S.key_hint(cfg.api_key),
            "tresor": S.vault_available(),
            "tresor_name": S.vault_name(),
            "umgebung_auch": bool(os.environ.get("ANTHROPIC_API_KEY")) and cfg.key_source == "tresor",
        }

    # ── Handy-Fernbedienung ───────────────────────────────────────────────
    def remote_message(self, with_qr: bool = False) -> dict[str, Any]:
        from ..desktop import autostart_enabled

        st = self.remote.status(self.remote_listener.listening, self.remote_listener.error)
        st["name"] = (f"http://{self.remote_listener.ansage.name}:{self.remote.port}"      # knowlin.local (0.38.28)
                      if self.remote_listener.ansage.name else None)
        st["autostart"] = autostart_enabled()
        st["autostart_moeglich"] = sys.platform == "win32"
        base = st["tailscale"]["adresse"] if st["tailscale"]["an"] and st["tailscale"]["adresse"] else (
            st["adressen"][0] if st["adressen"] else None)
        if with_qr and st["code"] and base:
            from ..qr import rows

            link = f"{base}/koppeln?c={st['code']['code']}"
            st["code"] = {**st["code"], "link": link, "qr": rows(link)}
        elif st["code"]:
            st["code"] = {"gueltig_bis": st["code"]["gueltig_bis"]}
        return st

    async def set_tailscale(self, on: bool) -> dict[str, Any]:
        """Tailscale Serve für duckpilot ein- oder ausschalten (https im eigenen Tailnet, auch unterwegs)."""
        from .. import tailscale as TS

        if not on:
            res = await asyncio.to_thread(TS.serve_off)
            self.remote.set_tailscale(False)
            await self.kick_remote_clients()
            return res
        if not self.remote.enabled:
            raise ValueError("Erst „Vom Handy aus bedienen“ einschalten")
        st = await asyncio.to_thread(TS.status, True)
        if not st["installiert"]:
            raise ValueError("Tailscale ist auf diesem PC nicht installiert – von tailscale.com laden, anmelden, dann hier einrichten.")
        if not st["laeuft"] or not st["name"]:
            raise ValueError(st.get("fehler") or "Tailscale ist nicht angemeldet.")
        res = await asyncio.to_thread(TS.serve_on, self.config.port)
        if res.get("ok"):
            self.remote.set_tailscale(True, st["name"])
        return res

    async def set_remote(self, an: bool | None = None, port: int | None = None) -> None:
        if port is not None and port != self.remote.port:
            if port == self.config.port:
                raise ValueError("Das ist schon der Port der Oberfläche am PC")
            self.remote.set_port(port)
        if an is not None:
            self.remote.set_enabled(an)
        if self.remote.enabled and self.app is not None:
            if not self.remote_listener.listening or self.remote_listener.port != self.remote.port:
                await self.remote_listener.start(self.app, self.remote.port)
        else:
            await self.remote_listener.stop()
            await self.kick_remote_clients()
            from ..desktop import autostart_enabled, set_autostart

            if an is False and autostart_enabled():
                await asyncio.to_thread(set_autostart, False)   # ohne Fernbedienung hat der Hintergrundstart keinen Sinn
            if an is False and self.remote.data.get("tailscale"):
                await self.set_tailscale(False)

    async def broadcast_local(self, message: dict[str, Any]) -> None:
        """Nur an die Fenster am PC – Geräteliste und Adressen gehen Handys nichts an."""
        message = self._lokal(message)
        text = json.dumps(message, ensure_ascii=False, default=_json_default)
        await asyncio.gather(*(self.send_to(ws, text) for ws in list(self.clients)
                               if getattr(ws, "fern_geraet", None) is None))

    async def kick_remote_clients(self, device_id: str | None = None) -> None:
        """Verbindungen von Handys trennen (alle oder nur die eines Geräts)."""
        for ws in list(self.clients):
            dev = getattr(ws, "fern_geraet", None)
            if dev is None or (device_id is not None and dev != device_id):
                continue
            self.clients.discard(ws)
            try:
                await ws.close(code=4401)
            except Exception:
                pass

    def _voice_changed(self) -> None:
        """Stimme/Installation hat sich geändert – gebündelt an die Browser melden."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        if self._voice_push is not None:
            return
        self._voice_push = loop.call_later(0.25, self._push_voice)

    def _push_voice(self) -> None:
        self._voice_push = None
        spawn(self.broadcast(self.voice_message()))
        spawn(self.broadcast(self.physik_message()))

    def gpus(self) -> list[str]:
        if self._gpus is None:
            from ..voice.install import detect_gpus

            self._gpus = detect_gpus()
        return self._gpus

    def voice_message(self) -> dict[str, Any]:
        from ..voice import describe
        from ..voice import install as I

        gpus = self._gpus or []
        info = self.speaker.info()
        # Vorlagen und Entwurf je Körper (Hinweis aus dem Test 5.11.) – „kopf“ für Knowlins eigene Stimme
        info["qwen"] = {**info.get("qwen", {}), "modul": self.config.modul,
                        "vorlagen": describe.vorlagen(self.config.modul), "vorlagen_kopf": describe.vorlagen("kopf"),
                        "entwurf": describe.entwurf(self.config.modul, self.config.duck_name)}
        return {
            "type": "stimme", **info,
            "installation": self.installer.jobs,
            "pakete": {k: {**v, "installiert": I.installed(k) if not self.installer.running() else None}
                       for k, v in I.PAKETE.items()},
            "grafikkarten": gpus, "gpu_vorschlag": I.suggest_gpu(gpus),
            # für welches Gerät PyTorch gebaut ist (seit 0.38.40) – „cpu“ trotz Grafikkarte → neu einrichten anbieten
            "pytorch": I.torch_bau() if not self.installer.running() else None,
            "ollama": self.pulls,
            "werte": {k: getattr(self.config, k) for k in (*sorted(VOICE_KEYS), "plaudern", "gehirn", "lokal_modell",
                                                           "lokal_adresse")},
            # Knowlins eigene Stimme (seit 0.38.10) – die Stimmen-Seite zeigt sie, wenn sie im Kopf geöffnet wird
            "kopf": {"motor": self.speaker.kopf_motor(), "stimme_motor": self.config.kopf_stimme_motor,
                     "stimme_piper": self.config.kopf_stimme_piper, "stimme_qwen": self.config.kopf_stimme_qwen},
        }

    async def install(self, paket: str, gpu: str) -> None:
        """Installieren – bei Piper gleich die gewählte Stimme mitladen, damit sie sofort spricht."""
        if paket in ("qwen", "lernen"):
            # PyTorch wird ersetzt: unter Windows hält der laufende Qwen-Arbeiter dessen DLLs fest (seit 0.38.40)
            qwen = getattr(getattr(self.speaker, "synth", None), "qwen", None)
            if qwen is not None and hasattr(qwen, "beenden"):
                qwen.beenden()
        job = await self.installer.install(paket, gpu)
        if paket in ("physik", "bam") and job.get("fertig"):
            self._wire_practice()
            await self.broadcast(self.physik_message())
        if paket == "lernen":
            self._lernen_changed()
        if paket == "piper" and job.get("fertig") and not self.speaker.synth.piper.has_voice(self.config.stimme_piper):
            await self.speaker.download_piper(self.config.stimme_piper)

    # ── Kamera, Pflege, Training ─────────────────────────────────────────
