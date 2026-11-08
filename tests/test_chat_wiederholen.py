"""Fund 6.11.2026 (beim Bilder-Machen): Riss die Verbindung genau beim Senden ab, ging die Nachricht still verloren.
Seitdem schickt der Browser Nachrichten ohne Echo nach dem Wiederverbinden erneut – mit derselben Kennung (cid); der
Server nimmt jede Kennung nur einmal."""

import asyncio

import pytest
from test_gui import tmp_settings, vault  # noqa: F401 – Fixtures

from duckpilot.config import load
from duckpilot.server.app import Runtime


@pytest.fixture()
def rt(tmp_settings, vault, tmp_path, monkeypatch):  # noqa: F811
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    return Runtime(load(memory_path=str(tmp_path / "mem.json")))


def test_gleiche_kennung_nur_einmal(rt):
    gesendet = []

    async def mitschreiben(msg):
        gesendet.append(msg)
    rt.broadcast = mitschreiben
    asyncio.run(rt.chat("Hallo", "text", "figur", "abc123"))
    asyncio.run(rt.chat("Hallo", "text", "figur", "abc123"))          # nach dem Wiederverbinden erneut geschickt
    echos = [m for m in gesendet if m.get("type") == "chat" and m.get("role") == "user"]
    assert len(echos) == 1 and echos[0]["cid"] == "abc123"


def test_ohne_kennung_wie_bisher(rt):
    gesendet = []

    async def mitschreiben(msg):
        gesendet.append(msg)
    rt.broadcast = mitschreiben
    asyncio.run(rt.chat("Hallo", "text"))
    asyncio.run(rt.chat("Hallo", "text"))
    assert len([m for m in gesendet if m.get("role") == "user"]) == 2
    assert all("cid" not in m for m in gesendet if m.get("role") == "user")


def test_browser_schickt_offene_nachrichten_nach_dem_wiederverbinden():
    from pathlib import Path

    app = (Path(__file__).resolve().parents[1] / "duckpilot" / "server" / "static" / "app.js").read_text(encoding="utf-8")
    assert "offeneChats.delete(m.cid)" in app and "for (const t of offeneChats.values())" in app
