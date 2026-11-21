"""Aufmerksamkeit suchen (seit 0.50): nach langer Stille vorsichtig zu dir, Kopf hoch – nie drängend."""

from __future__ import annotations

import asyncio
import math
import time

import pytest
from helpers import run_for
from test_eigenstaendig import _wach, tmp_settings, vault  # noqa: F401 – Fixtures

from duckpilot.config import load
from duckpilot.motion import eigenstaendig as E
from duckpilot.motion.aufmerksamkeit import SPEED, AufmerksamkeitSuchen, haltepunkt
from duckpilot.server import runtime_eigenstaendig as RE
from duckpilot.server.app import Runtime


@pytest.fixture()
def rt(tmp_settings, vault, tmp_path, monkeypatch):  # noqa: F811
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    r = Runtime(load(memory_path=str(tmp_path / "mem.json")))
    r.backend._task = object()
    return r


def test_haltepunkt_mit_abstand():
    assert haltepunkt((0, 0), (2, 0)) == (1.5, 0.0)
    assert haltepunkt((0, 0), (0.3, 0)) == (0, 0)                 # schon nah: bleibt stehen


def test_angebot_nur_mit_haltepunkt_und_nie_am_echten_roboter():
    lage = E.Lage(eigenschaften=frozenset({"beine", "kopf"}), zu_dir=(1.0, 0.5))
    arten = {b.art: b for b in E.angebot(lage, 0.5, 0.5)}
    assert "aufmerksamkeit" in arten and arten["aufmerksamkeit"].ort and arten["aufmerksamkeit"].satz is None
    assert "aufmerksamkeit" not in {b.art for b in E.angebot(E.Lage(eigenschaften=frozenset({"beine"})), 0.5, 0.5)}
    echt = E.Lage(eigenschaften=frozenset({"beine"}), zu_dir=(1.0, 0.5), echt=True)
    assert "aufmerksamkeit" not in {b.art for b in E.angebot(echt, 0.5, 0.5)}
    ohne_beine = E.Lage(eigenschaften=frozenset({"kopf"}), zu_dir=(1.0, 0.5))
    assert "aufmerksamkeit" not in {b.art for b in E.angebot(ohne_beine, 0.5, 0.5)}


def test_erst_nach_langer_stille_mit_offenem_fenster_und_nicht_zu_oft(rt):
    async def go():
        await _wach(rt)
        jetzt = time.monotonic()
        assert rt.aufmerksamkeit_ziel(jetzt) is None                    # kein Fenster meldet, wo du sitzt
        rt.betrachter_setzen({"x": 1.4, "y": 0.0})
        assert rt.aufmerksamkeit_ziel(jetzt) is None                    # gerade erst Kontakt
        spaeter = rt.engine.kontakt_at + RE.AUFMERKSAMKEIT_STILLE_S + 1
        rt.betrachter = (*rt.betrachter[:2], spaeter)
        ziel = rt.aufmerksamkeit_ziel(spaeter)
        assert ziel is not None
        st = rt.backend.state()
        assert abs(math.hypot(1.4 - ziel[0], 0.0 - ziel[1]) - 0.5) < 0.01   # 50 cm vor dir
        rt.config.aufmerksamkeit = False
        assert rt.aufmerksamkeit_ziel(spaeter) is None                  # ausgeschaltet
        rt.config.aufmerksamkeit = True
        rt._aufmerksamkeit_zuletzt = spaeter - 60
        assert rt.aufmerksamkeit_ziel(spaeter) is None                  # eben erst – Nähe drängt nie
        rt.betrachter_setzen({"x": "x", "y": 1})                        # Unsinn wird übergangen
        rt.betrachter_setzen({"x": 99, "y": -99})                       # in den Raum geklemmt
        assert abs(rt.betrachter[0]) < rt.backend.world_model.width / 2
        return st

    asyncio.run(go())


def test_sie_kommt_langsam_schaut_hoch_und_spricht_nicht(rt):
    async def go():
        gesendet = await _wach(rt)
        st0 = rt.backend.state()
        ziel = (st0.x + 0.6, st0.y)
        sprechen = []
        rt._duck_says = lambda text: sprechen.append(text)
        b = AufmerksamkeitSuchen(ziel, laut=True)
        rt.engine.run(b)
        await run_for(rt.backend, rt.engine, 3.0)
        st3 = rt.backend.state()
        schnellste = math.hypot(st3.x - st0.x, st3.y - st0.y) / 3.0          # mittleres Tempo der ersten 3 s
        for _ in range(30):
            await run_for(rt.backend, rt.engine, 1.0)
            if b.done:
                break
        return b, rt.backend.state(), gesendet, sprechen, ziel, schnellste

    b, st, gesendet, sprechen, ziel, schnellste = asyncio.run(go())
    assert b.done and b.result == "schaut zu dir hoch", b.result
    assert math.hypot(st.x - ziel[0], st.y - ziel[1]) < 0.15
    assert not sprechen and 0.01 < schnellste <= SPEED + 0.02


def test_not_aus_beendet_es(rt):
    async def go():
        await _wach(rt)
        st0 = rt.backend.state()
        b = AufmerksamkeitSuchen((st0.x + 1.0, st0.y))
        rt.engine.run(b)
        await run_for(rt.backend, rt.engine, 1.0)
        await rt.engine.not_aus("Not-Aus")
        await run_for(rt.backend, rt.engine, 0.5)
        return b, rt.engine.current, rt.eigenstaendig_sperre()

    b, aktuell, sperre = asyncio.run(go())
    assert aktuell is not b and sperre and "Not-Aus" in sperre
