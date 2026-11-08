"""Hindernissen ausweichen und sie umlaufen – in allen Modi (0.33, Wunsch des Maintainers vom 1.11.2026:
„nicht hängenbleiben oder dagegenlaufen, sondern ausweichen, es umlaufen – Folg mir, Laser, manuelle Steuerung,
Erkunden …“)."""

import asyncio
import math

from helpers import make

from duckpilot.api import DuckState, Perception, Twist
from duckpilot.motion import behaviors as B
from duckpilot.motion.ausweichen import BACK_BLIND_S, BACK_V, STUCK_S, Ausweicher


async def _lauf(sim, eng, sekunden, *, laser=None, person=None, bis=None):
    """Takten und mitzählen, ob sie je in einem Möbel steckt oder umfällt."""
    kontakt = 0
    for i in range(int(sekunden * 20)):
        if laser and i % 20 == 0:
            sim.set_laser(*laser)
        if person and i % 20 == 0:
            sim.world_model.set_person(*person)
        await eng.tick(0.05)
        await asyncio.sleep(0)
        sim.step(0.025)
        sim.step(0.025)
        if sim.world_model.collide(sim.x, sim.y, 0.085):
            kontakt += 1
        if sim.fallen or (bis and bis()):
            break
    return kontakt


def test_walks_around_furniture_from_many_angles():
    """Geradeaus gegen Regal, Kiste, Sofa, Hocker und Wände: nie im Möbel, nie umgefallen, immer weitergekommen."""
    async def go(x, y, yaw):
        sim, eng = await make()
        sim.x, sim.y, sim.yaw = x, y, yaw
        eng.ausweicher.vergessen()
        x0, y0 = x, y
        weg = 0.0
        eng.run(B.TimedMove(Twist(0.22, 0, 0), 8.0))
        kontakt = 0
        for _ in range(160):
            px, py = sim.x, sim.y
            kontakt += await _lauf(sim, eng, 0.05)
            weg += math.hypot(sim.x - px, sim.y - py)
        assert kontakt == 0 and not sim.fallen, (x0, y0, yaw)
        assert weg > 0.6, (x0, y0, yaw, weg)            # nicht davor stehen geblieben

    for start in [(1.0, -0.6, 0.0), (1.0, -0.6, 0.5), (1.2, -0.2, -0.8), (-0.6, -0.75, math.pi),
                  (-0.2, 0.6, math.pi / 2), (0.6, -1.0, 0.5), (1.5, 0.6, 1.0)]:
        asyncio.run(go(*start))


def test_goto_finds_its_way_around_the_coffee_table():
    """Hinlaufen zu einem Punkt hinter dem Couchtisch und hinter der Kiste – in 12 festen Varianten (Zufall im Leerlauf
    davor, also Kopfhaltung und Blick). Bekannte Grenze (gemessen 1.11.): An der Kistenecke, die der Tiefensensor nie
    gesehen hat, stößt sie selten an – hier 2 von 12, im einfachen Simulator fällt sie dabei. Besser mit der Karte (0.37).
    Der Test hält diese Quote fest, damit sie nicht schlechter wird."""
    async def go(seed, start, ziel, zufall):
        sim, eng = await make(seed=seed, zufall=zufall)
        sim.x, sim.y, sim.yaw = start
        eng.ausweicher.vergessen()
        eng.run(B.GoTo(*ziel))
        kontakt = await _lauf(sim, eng, 40, bis=lambda: not eng.busy())
        enden = [e.get("result") for e in eng.events if e["type"] == "behavior_end"]
        return kontakt == 0 and not sim.fallen and bool(enden) and enden[-1] == "angekommen"

    gut = [asyncio.run(go(seed, start, ziel, z)) for seed in (1, 2)
           for start, ziel in (((0.15, 0.25, 0.0), (0.95, 0.25)), ((-0.6, -0.75, math.pi), (-1.6, -0.75)))
           for z in (1, 2, 3)]
    assert sum(gut) >= 10, gut
    assert all(gut[:3]) and all(gut[6:9]), "hinter den Couchtisch muss sie immer kommen"


def test_laser_and_follow_me_go_around_a_corner():
    async def laser():
        sim, eng = await make()
        sim.x, sim.y, sim.yaw = 0.15, 0.0, 0.0
        eng.ausweicher.vergessen()
        eng.run(B.FollowLaser(60))
        kontakt = await _lauf(sim, eng, 30, laser=(1.0, 0.2), bis=lambda: math.hypot(1.0 - sim.x, 0.2 - sim.y) < 0.3)
        assert kontakt == 0 and not sim.fallen and math.hypot(1.0 - sim.x, 0.2 - sim.y) < 0.3

    async def mensch():
        sim, eng = await make()
        sim.x, sim.y, sim.yaw = 0.15, 0.0, 0.0
        eng.ausweicher.vergessen()
        eng.run(B.FollowMe(60))
        kontakt = await _lauf(sim, eng, 30, person=(1.4, 0.15),
                              bis=lambda: math.hypot(1.4 - sim.x, 0.15 - sim.y) < 0.8)
        assert kontakt == 0 and not sim.fallen and math.hypot(1.4 - sim.x, 0.15 - sim.y) < 0.8

    asyncio.run(laser())
    asyncio.run(mensch())


def test_explore_never_ends_up_inside_furniture():
    async def go(seed):
        sim, eng = await make(seed=seed)
        eng.run(B.Explore(40))
        kontakt = await _lauf(sim, eng, 30)
        assert kontakt == 0 and not sim.fallen
    for seed in (1, 2):
        asyncio.run(go(seed))


def _state(x=0.0, y=0.0, yaw=0.0, punkte=(), quelle="sim", sektoren=None):
    return DuckState(x=x, y=y, yaw=yaw, perception=Perception(points=[list(p) for p in punkte], source=quelle,
                                                                sectors=sektoren or {}))


def test_wall_straight_ahead_turns_instead_of_pushing():
    aw = Ausweicher()
    wand = [(0.15, dy / 100, 0.1) for dy in range(-30, 31, 3)]           # Wand 15 cm voraus
    st = _state(punkte=wand)
    aw.merken(st, 0.05)
    e = aw.lenken(st, Twist(0.2, 0, 0))
    assert e.twist.vx == 0.0 and abs(e.twist.vyaw) >= 0.8 and e.seite != 0


def test_obstacle_ahead_left_steers_right_while_walking():
    aw = Ausweicher()
    kiste = [(0.35, dy / 100, 0.1) for dy in range(-5, 25, 2)]          # links vorn, rechts frei
    st = _state(punkte=kiste)
    aw.merken(st, 0.05)
    e = aw.lenken(st, Twist(0.2, 0, 0))
    assert e.twist.vx > 0 and e.twist.vyaw < -0.1 and e.seite == -1


def test_memory_keeps_points_after_turning_away_and_forgets_later():
    aw = Ausweicher()
    aw.merken(_state(punkte=[(0.3, 0.0, 0.1)]), 0.05)
    st = _state()                                                      # ToF sieht gerade nichts
    for _ in range(20):
        aw.merken(st, 0.05)
    assert aw.freiraum(aw._koerper(st), 0.0) < 0.35                     # noch gemerkt (1 s später)
    for _ in range(80):
        aw.merken(st, 0.05)
    assert aw.freiraum(aw._koerper(st), 0.0) > 0.8                      # nach > 4 s vergessen


def test_floor_points_and_odometry_jumps_do_not_count():
    aw = Ausweicher()
    aw.merken(_state(punkte=[(0.2, 0.0, 0.0), (0.2, 0.05, 0.01)]), 0.05)   # Boden
    assert not aw._pts
    aw.merken(_state(punkte=[(0.2, 0.0, 0.1)]), 0.05)
    assert aw._pts
    aw.merken(_state(x=1.0), 0.05)                                     # Odometrie neu gesetzt
    assert not aw._pts


def test_real_robot_uses_sectors_until_head_is_calibrated():
    """Am echten Roboter hängen die Punkte an der Kopf-Kalibrierung – bis R1 nur die Sektoren (Boden herausgerechnet)."""
    aw = Ausweicher()
    st = _state(punkte=[(0.2, 0.0, 0.1)], quelle="tofd", sektoren={"links": 0.9, "mitte": 0.12, "rechts": 0.3})
    aw.merken(st, 0.05)
    assert not aw._pts
    e = aw.lenken(st, Twist(0.2, 0, 0))
    assert e.twist.vx == 0.0 and e.twist.vyaw > 0                      # zur freieren Seite (links)


def test_stuck_backs_up_and_turns_free():
    aw = Ausweicher()
    st = _state()
    e = None
    for _ in range(int(STUCK_S / 0.05) + 3):
        aw.merken(st, 0.05)
        e = aw.lenken(st, Twist(0.2, 0, 0))
    assert e.twist.vx == BACK_V and "Festgesessen" in e.note
    for _ in range(int((BACK_BLIND_S + 0.3) / 0.05)):         # ohne jede Tiefe setzt sie weiter zurück (0.38.27)
        aw.merken(st, 0.05)
        e = aw.lenken(st, Twist(0.2, 0, 0))
    assert e.twist.vx == 0.0 and abs(e.twist.vyaw) > 0.5


def test_manual_driving_gets_help_but_no_surprise_reversing():
    aw = Ausweicher()
    st = _state()
    for _ in range(int(STUCK_S / 0.05) + 10):
        aw.merken(st, 0.05)
        e = aw.lenken(st, Twist(0.2, 0, 0), hand=True)
    assert e.twist.vx >= 0                                             # von Hand nie von selbst rückwärts
    wand = [(0.15, dy / 100, 0.1) for dy in range(-30, 31, 3)]
    st = _state(punkte=wand)
    aw.merken(st, 0.05)
    assert aw.lenken(st, Twist(0.2, 0, 0), hand=True).twist.vx == 0.0  # aber nicht in die Wand


def test_switch_off_only_brakes_like_before():
    """Wunsch des Maintainers (1.11.): Ausweichen unter Verhalten abschaltbar. Aus = nur bremsen wie bis 0.32, nie lenken."""
    aw = Ausweicher()
    kiste = [(0.30, dy / 100, 0.1) for dy in range(-5, 25, 2)]
    st = _state(punkte=kiste)
    aw.merken(st, 0.05)
    e = aw.bremsen(st, Twist(0.2, 0, 0.1))
    assert 0 < e.twist.vx < 0.2 and e.twist.vyaw == 0.1 and e.seite == 0
    wand = [(0.12, dy / 100, 0.1) for dy in range(-30, 31, 3)]
    st = _state(punkte=wand)
    aw.merken(st, 0.05)
    assert aw.bremsen(st, Twist(0.2, 0, 0)).twist == Twist(0.0, 0, 0)


def test_switch_reaches_the_engine():
    async def go():
        sim, eng = await make()
        assert eng.config.ausweichen
        eng.config.ausweichen = False
        sim.x, sim.y, sim.yaw = 1.0, -0.6, 0.0
        eng.ausweicher.vergessen()
        eng.run(B.TimedMove(Twist(0.22, 0, 0), 4.0))
        yaw0 = sim.yaw
        await _lauf(sim, eng, 4)
        assert abs(sim.yaw - yaw0) < 0.2                  # nicht abgebogen – nur gebremst
    asyncio.run(go())


def test_target_of_the_task_is_no_obstacle():
    """Hinweis aus dem Test (1.11.): Wo Kontakt Teil der Aufgabe ist (Ball schießen, Annähern), weicht sie dem Ziel nicht aus."""
    aw = Ausweicher()
    ball = [(0.25 + dx / 100, dy / 100, 0.05) for dx in range(-4, 5, 2) for dy in range(-4, 5, 2)]
    st = _state(punkte=ball)
    aw.merken(st, 0.05)
    assert aw.lenken(st, Twist(0.15, 0, 0)).seite != 0                  # ohne Ziel: ausweichen
    e = aw.lenken(st, Twist(0.15, 0, 0), ziel=(0.25, 0.0, 0.12))
    assert e.twist == Twist(0.15, 0, 0) and not e.note                  # mit Ziel: geradeaus hin
    tofd = _state(quelle="tofd", sektoren={"links": 0.9, "mitte": 0.2, "rechts": 0.9})
    assert aw.lenken(tofd, Twist(0.15, 0, 0), ziel=(0.25, 0.0, 0.12)).twist.vyaw == 0   # auch mit Sektoren
    wand = [(0.15, dy / 100, 0.1) for dy in range(-30, 31, 3)]
    st = _state(punkte=wand)
    aw.merken(st, 0.05)
    assert aw.lenken(st, Twist(0.15, 0, 0), ziel=(1.5, 0.0, 0.12)).twist.vx == 0.0   # andere Hindernisse bleiben


def test_kicking_the_ball_never_avoids_it():
    async def go():
        sim, eng = await make()
        ball = next(i for i in sim.world_model.items if i.kind == "ball")
        sim.x, sim.y, sim.yaw = ball.x - 0.6, ball.y, 0.0
        eng.ausweicher.vergessen()
        eng.run(B.KickBall("kick_left"))
        for _ in range(500):
            await _lauf(sim, eng, 0.05)
            if any(e["type"] in ("kick", "kick_miss") for e in eng.events):
                break
        kinds = [e["type"] for e in eng.events]
        assert "kick" in kinds and "kick_miss" not in kinds, kinds
        assert not [e for e in eng.events if e["type"] == "reflex"], "dem Ball ausgewichen"
    asyncio.run(go())
