"""Zugang zu Claude, dessen SDK im Hintergrund lädt (seit 0.52.1).

`import anthropic` lädt Hunderte Dateien (pydantic-Modelle für jede Antwortart). Unter Windows prüft der Virenschutz
jede davon beim ersten Laden – auf dem Laptop des Maintainers dauerte der Start deshalb 40 bis 140 s, alle in
`brain/agent.py` beim Import (Startbeobachter, 21.–23.11.). Jetzt lädt ein Hintergrund-Thread das Paket, der Start geht
weiter, und erst ein Aufruf an Claude wartet – bis dahin ist das SDK längst da.

Nach außen verhält sich `ClaudeZugang` wie `anthropic.AsyncAnthropic`, soweit Knowlin es nutzt: `messages.create(...)`.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from typing import Any

log = logging.getLogger(__name__)


class ClaudeZugang:
    def __init__(self, api_key: str) -> None:
        self._fertig = threading.Event()
        self._client: Any = None
        self.fehler: str | None = None
        self.sekunden: float | None = None
        threading.Thread(target=self._laden, args=(api_key,), name="claude-sdk", daemon=True).start()

    def _laden(self, api_key: str) -> None:
        t0 = time.monotonic()
        try:
            import anthropic

            self._client = anthropic.AsyncAnthropic(api_key=api_key)
        except ImportError:
            self.fehler = "Python-Paket 'anthropic' fehlt (pip install anthropic)"
        except Exception as exc:  # noqa: BLE001 – der Start darf daran nie scheitern
            self.fehler = f"Claude-Zugang: {type(exc).__name__}: {exc}"
        finally:
            self.sekunden = time.monotonic() - t0
            self._fertig.set()
            if self.sekunden > 5:
                log.info("Claude-SDK im Hintergrund geladen nach %.1f s", self.sekunden)

    @property
    def geladen(self) -> bool:
        return self._fertig.is_set()

    async def bereit(self) -> Any:
        """Der echte Client – wartet, falls das SDK noch lädt (ohne die Ereignisschleife zu blockieren)."""
        if not self._fertig.is_set():
            await asyncio.to_thread(self._fertig.wait)
        if self._client is None:
            raise RuntimeError(self.fehler or "Claude-Zugang nicht verfügbar")
        return self._client

    @property
    def messages(self) -> _Nachrichten:
        return _Nachrichten(self)


class _Nachrichten:
    def __init__(self, zugang: ClaudeZugang) -> None:
        self._zugang = zugang

    async def create(self, *args: Any, **kwargs: Any) -> Any:
        client = await self._zugang.bereit()
        return await client.messages.create(*args, **kwargs)
