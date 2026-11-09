"""Tests für Einstellungen, Schlüssel, Herkunftsschutz und die Server-Schnittstellen der GUI."""

import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from duckpilot import settings as S
from duckpilot.config import load
from duckpilot.server.app import Runtime, create_app, origin_allowed
from duckpilot.server.oberflaeche import seite, stil, stil_dateien

ORIGIN = {"Origin": "http://testserver"}


@pytest.fixture()
def tmp_settings(tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    monkeypatch.setenv("DUCKPILOT_SETTINGS", str(path))
    return path


@pytest.fixture()
def vault(monkeypatch):
    """Ein Tresor im Speicher statt der Windows-Anmeldeinformationsverwaltung."""
    store = {}

    class FakeKeyring:
        def get_password(self, s, u): return store.get((s, u))
        def set_password(self, s, u, p): store[(s, u)] = p
        def delete_password(self, s, u): store.pop((s, u), None)

    monkeypatch.setattr(S, "_keyring", lambda: FakeKeyring())
    return store


def test_validate_rejects_unknown_and_bad_values(tmp_settings):
    with pytest.raises(ValueError):
        S.validate({"api_key": "x"})
    with pytest.raises(ValueError):
        S.validate({"model": "gpt-4"})
    with pytest.raises(ValueError):
        S.validate({"head_signs": [1, 1, 1]})
    with pytest.raises(ValueError):
        S.validate({"robot": "irgendwas ohne port"})
    assert S.validate({"head_signs": [1, -1, 1, 1], "tts": False}) == {"head_signs": [1.0, -1.0, 1.0, 1.0], "tts": False}


def test_saved_settings_override_toml(tmp_settings):
    S.save_user_settings({"duck_name": "Quackline", "model": "claude-haiku-5-5"})
    cfg = load()
    assert cfg.duck_name == "Quackline" and cfg.model == "claude-haiku-5-5"
    assert json.loads(tmp_settings.read_text(encoding="utf-8"))["duck_name"] == "Quackline"


def test_vault_key_wins_over_environment(tmp_settings, vault, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-aus-der-umgebung-0000000000000")
    assert load().key_source == "umgebung"
    S.set_vault_key("sk-ant-aus-dem-tresor-11111111111111111")
    cfg = load()
    assert cfg.key_source == "tresor" and cfg.api_key.endswith("1111")


def test_origin_rules():
    assert origin_allowed(None, "127.0.0.1:8765")
    assert origin_allowed("http://127.0.0.1:8765", "127.0.0.1:8765")
    assert origin_allowed("http://localhost:8765", "localhost:8765")
    assert not origin_allowed("https://evil.example", "127.0.0.1:8765")
    assert not origin_allowed("http://evil.example:8765", "evil.example:8765")  # DNS-Rebinding
    assert origin_allowed("http://192.168.1.20:8765", "192.168.1.20:8765")


@pytest.fixture()
def client(tmp_settings, tmp_path, vault, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    cfg = load(memory_path=str(tmp_path / "mem.json"))
    runtime = Runtime(cfg)
    with TestClient(create_app(runtime), base_url="http://127.0.0.1:8765") as c:
        c.runtime = runtime
        yield c


def test_settings_roundtrip_and_live_apply(client):
    r = client.get("/api/settings").json()
    assert r["werte"]["backend"] == "sim" and r["schluessel"]["gesetzt"] is False
    r = client.post("/api/settings", json={"idle_life": False, "duck_name": "Erna"},
                    headers={"Origin": "http://127.0.0.1:8765"}).json()
    assert r["ok"] and set(r["geaendert"]) == {"idle_life", "duck_name"}
    assert client.runtime.engine.config.idle_life is False
    assert client.runtime.agent.config.duck_name == "Erna"


def test_foreign_origin_is_refused(client):
    r = client.post("/api/settings", json={"tts": False}, headers={"Origin": "https://evil.example"})
    assert r.status_code == 403
    assert client.runtime.config.tts is True
    with pytest.raises(Exception):
        with client.websocket_connect("/ws", headers={"Origin": "https://evil.example", "Host": "127.0.0.1:8765"}) as ws:
            ws.receive_text()


def test_key_flow(client):
    h = {"Origin": "http://127.0.0.1:8765"}
    bad = client.post("/api/key", json={"key": "hallo"}, headers=h)
    assert bad.status_code == 400
    ok = client.post("/api/key", json={"key": "sk-ant-api03-" + "x" * 40}, headers=h).json()
    assert ok["ok"] and ok["schluessel"]["quelle"] == "tresor" and ok["schluessel"]["hinweis"].endswith("xxxx")
    assert client.runtime.agent.online
    settings = client.get("/api/settings").text
    assert "x" * 40 not in settings  # der Schlüssel selbst verlässt den Server nie
    gone = client.delete("/api/key", headers=h).json()
    assert gone["schluessel"]["gesetzt"] is False and not client.runtime.agent.online


def test_swap_body_to_robot_and_back(client):
    h = {"Origin": "http://127.0.0.1:8765"}
    r = client.post("/api/settings", json={"backend": "robotd", "robot": "tcp:127.0.0.1:7998"}, headers=h).json()
    assert r["ok"]
    assert client.runtime.backend.name == "robotd"
    r = client.post("/api/settings", json={"backend": "sim"}, headers=h).json()
    assert client.runtime.backend.name == "sim"


def test_websocket_sends_init_and_memory(client):
    with client.websocket_connect("/ws", headers={"Origin": "http://127.0.0.1:8765", "Host": "127.0.0.1:8765"}) as ws:
        first = json.loads(ws.receive_text())
        second = json.loads(ws.receive_text())
    assert first["type"] == "init" and first["config"]["version"]
    assert second["type"] == "memory" and second["enabled"] is True


def test_static_assets_exist():
    from duckpilot.server.app import STATIC

    for name in ("index.html", "app.js", "dashboard.js", "duck3d.js", "voice.js", "style.css",
                 "icon-192.png", "icon-512.png", "manifest.webmanifest",
                 "vendor/three.module.min.js", "vendor/OrbitControls.js", "vendor/plex/IBMPlexSans-Regular.woff2", "pointcloud.js", "stimme.js", "parcours.js", "training.js"):
        assert (STATIC / name).exists(), name
    assert os.path.exists(STATIC.parents[2] / "duckpilot.ico")


def test_app_is_named_after_the_duck(client):
    h = {"Origin": "http://127.0.0.1:8765"}
    assert client.get("/manifest.webmanifest").json()["name"] == "Quacki"
    client.post("/api/settings", json={"duck_name": "Erna"}, headers=h)
    m = client.get("/manifest.webmanifest")
    assert m.json()["name"] == m.json()["short_name"] == "Erna"
    assert m.headers["content-type"].startswith("application/manifest+json")
    html = client.get("/").text
    assert 'href="/manifest.webmanifest?v=' in html


def test_emotion_catalog_knows_who_does_what(client):
    cat = {e["name"]: e for e in client.get("/api/emotions").json()}
    assert cat["lachen"]["art"] == "pollen" and cat["freude"]["art"] == "eigen"
    assert cat["gaehnen"]["art"] == "charakter" and "Gemütlich" in cat["gaehnen"]["bei"]
    assert cat["gaehnen"]["text"]


def test_background_tasks_list_running_jobs(tmp_path, monkeypatch):
    from duckpilot import settings as S
    from duckpilot.config import load
    from duckpilot.server.app import Runtime

    monkeypatch.setenv("DUCKPILOT_SETTINGS", str(tmp_path / "settings.json"))
    monkeypatch.setattr(S, "_keyring", lambda: None)
    rt = Runtime(load(memory_path=str(tmp_path / "mem.json")))
    assert rt.tasks_message() == {"type": "aufgaben", "liste": []}
    rt.installer.jobs["qwen"] = {"laeuft": True, "schritt": 2, "schritte": 4}
    rt.speaker.jobs["entwurf"] = {"laeuft": True, "text": "entwirft …"}
    rt.pulls["qwen3.5:9b"] = {"laeuft": True, "status": "lädt", "anteil": 0.4}
    rt.lab.job = {"laeuft": True, "text": "2 von 3 Versuchen"}
    rt.installer.jobs["piper"] = {"laeuft": False, "fehler": "kaputt"}
    items = {t["id"]: t for t in rt.tasks_message()["liste"]}
    assert set(items) == {"install:qwen", "stimme:entwurf", "ollama:qwen3.5:9b", "parcours"}
    assert items["install:qwen"]["ziel"] == {"view": "stimme", "part": "stimme"}
    assert items["ollama:qwen3.5:9b"]["ziel"]["part"] == "gespraech" and items["ollama:qwen3.5:9b"]["anteil"] == 0.4
    assert items["parcours"]["ziel"]["view"] == "parcours"


def test_training_is_three_clear_steps():
    """Erst was, dann wo und wie, dann ein deutlicher Start-Knopf (Wunsch des Maintainers: der Lernen-Knopf war zu übersehen)."""
    import re


    html = seite()
    flow = html[html.index('class="tr-flow"'):html.index('id="tr-local-progress"')]
    what, how, go = (flow.index(f'id="tr-step-{s}"') for s in ("what", "how", "go"))
    assert what < how < go
    assert flow.index('name="tr-goal"') < how < flow.index('name="tr-prov"')
    start = flow[go:]
    # Beide Start-Knöpfe stehen im dritten Schritt und gehören über form= zu ihrem Formular
    assert re.search(r'type="submit" form="lr-form" id="lr-go"', start)
    assert re.search(r'type="submit" form="tr-form" id="tr-start"', start)
    assert "Zwei Klicks" in start                      # bezahltes Training bleibt beim Zwei-Klick-Start


def test_pages_share_one_grid():
    """Ein Raster für alle Seiten (Carbon 2x Grid): Seitenraster tragen `.grid`, legen keine eigenen Spalten fest
    und brechen nur an den zwei Container-Breiten um (Hinweis aus dem Test: Kachelbreiten sprangen zwischen den Seiten)."""
    import re

    from duckpilot.server.app import STATIC

    css = stil()
    html = seite()
    js = (STATIC / "skills.js").read_text("utf-8")
    pages = ["dash", "emo-grid", "hub-grid", "pack-grid", "mem-grid", "settings-grid", "settings-layout", "talk-grid",
             "al-hero", "al-grid", "engines", "ak-layout", "pc-grid"]
    for name in pages:
        tags = [t for t in re.findall(r'class="([^"]*)"', html) if name in t.split()]
        assert tags and all("grid" in t.split() for t in tags), name
        # keine eigenen Spalten: weder auto-fill noch feste Brüche
        assert not re.search(rf"\.{name}(?![\w-])[^{{}}]*\{{[^}}]*grid-template-columns", css), name
    for name in ("move-grid", "talent-grid"):
        assert re.search(rf"'{name} grid grid--tiles", js), name
    assert "@container" not in css           # Carbon: Umbruchpunkte nach Fensterbreite
    assert ".page-inner { max-width: var(--grid-max); margin-inline: auto; }" in css
    # Spalten-Spans passen ins 16er-Raster; der alte 12er-Rest ist weg
    assert all(int(n) <= 16 for n in re.findall(r"grid-column: span (\d+)", css))
    assert "repeat(12" not in css                      # der alte 12er-Rest ist weg


def test_css_uses_only_carbon_values():
    """Carbon konsequent (Wunsch des Maintainers): Abstände nur aus der Spacing-Skala, Schriftgrade und Farben nur als Token,
    Schnitte 300/400/600, Umbruchpunkte nur sm/md/lg/max, Dauern nur als Token. Ausnahmen stehen in ds/tokens.css."""
    import re

    from duckpilot.server.app import STATIC

    tokens = (STATIC / "ds" / "tokens.css").read_text("utf-8")
    on_scale = {int(v) for v in re.findall(r"--spacing-\d\d: (\d+)px", tokens)}
    assert on_scale == {2, 4, 8, 12, 16, 24, 32, 40, 48, 64, 80, 96, 160}
    for name in (*stil_dateien(), "ds/components.css"):
        css = re.sub(r"/\*.*?\*/", "", (STATIC / name).read_text("utf-8"), flags=re.S)
        assert not re.search(r"var\(--s-\d|var\(--dur-\d", css), name
        assert not re.search(r"var\(--p-", css), f"{name}: Grundwerte (--p-*) nur in ds/tokens.css"
        for prop, val in re.findall(r"(?<=[;{\s])((?:margin|padding|gap|row-gap|column-gap)(?:-[a-z]+)?)\s*:\s*([^;}]*)", css):
            for n in re.findall(r"(?<![\w.(-])(\d+)px", val):
                assert int(n) in (0, 1) or "calc(" in val, f"{name}: {prop}: {val} – Abstand als Token"
        for val in re.findall(r"font-size:\s*([^;}]*)", css):
            assert val.startswith("var(--t-") or val.endswith("em") or val in ("inherit", "100%") or "clamp" in val, val
        assert not re.findall(r"font-weight:\s*(?!300|400|600|inherit)\S+", css), name
        for prop, val in re.findall(r"(?<=[;{\s])(--?[a-z_][\w-]*|[a-z-]+)\s*:\s*([^;{}]*)", css):
            assert not re.search(r"#[0-9a-fA-F]{3,8}\b|rgba?\(", val), f"{name}: {prop}: {val} – Farbe als Token"
        for val in re.findall(r"(?:transition|animation):\s*([^;}]*)", css):
            assert not re.search(r"(?<![\w.-])(?!0s\b)\d*\.?\d+m?s\b", val), f"{name}: {val} – Dauer als Token"
        widths = set(re.findall(r"@media[^{]*?(?:max|min)-width:\s*([\d.]+)px", css))
        assert widths <= {"671.98", "672", "1055.98", "1056", "1311.98", "1312", "1583.98", "1584"}, (name, widths)


def test_collision_mode_and_stop_window_are_wired():
    """Kollisionsmodus (nur Simulator) und Stopp-Fenster nach einem Sturz: Oberfläche hängt an den Nachrichten und hat
    für alles eine Taste (WCAG 2.1.1); die Wartezeit ist einstellbar (WCAG 2.2.1)."""
    from duckpilot.server.app import STATIC

    html = seite()
    app = (STATIC / "app.js").read_text("utf-8")
    kol = (STATIC / "kollision.js").read_text("utf-8")
    for needle in ('id="kol-btn"', 'id="kol-panel"', 'data-seite="links"', 'data-ding="wurf"', 'id="stopp-fenster"',
                   'data-set="auto_recover"', 'data-set="stopp_fenster_s" data-num', 'id="sf-stop"'):
        assert needle in html, needle
    for needle in ("case 'kollision':", "case 'kollision_objekte':", "kollision?.onEvent(msg.event)", "initKollision("):
        assert needle in app, needle
    assert "'stopp_fenster'" in kol and "openWindow(dauer)" in kol and "estop()" in kol
    for path in ("/stoss", "/wurf", "/rollen", "/objekt"):
        assert f"'{path}'" in kol, path
    # Bedienung wie in CAD/Robotik-Simulatoren: Zeigen bewegt nichts (nur Hervorheben), die Ente wird am Anfasspunkt
    # per Feder gezogen (Ebene quer zur Kamera), Dinge gleiten in ihrer Höhe über den Boden, senkrecht nur mit
    # Umschalttaste oder am blauen Pfeil; Wurf = Schwung über den Boden + Wurfwinkel aus dem Regler.
    for needle in ("type: 'kollision_zug_start'", "type: 'kollision_zug'", "type: 'kollision_zug_ende'",
                   "type: 'kollision_greifen'", "type: 'kollision_loslassen', v:", "function pick()",
                   "function setHover(", "drag.senkrecht", "e.key === 'Shift'", "function throwV()", "bogenZeigen(",
                   "wurfWinkel"):
        assert needle in kol, needle
    move = kol[kol.index("  function move(e) {"):kol.index("  function down(e) {")]
    assert "send(" not in move and "sendThrottled(" not in move, "Zeigen allein darf nichts an die Physik schicken"
    assert "planeAt(handHeight)" not in kol and 'id="kol-hoehe"' not in html and 'id="kol-tiefe"' not in html
    assert 'id="kol-winkel"' in html and "kol-winkel-tipp" in html
    # Zielwurf (Schleuder): Zuglänge → Tempo, Bogen prüft Treffer an der Ente, Esc bricht ab
    assert 'name="kol-wurfart" value="ziel"' in html
    for needle in ("function schleuderV()", "function bogenMitTreffer(", "drag.art === 'schleuder'", "e.key === 'Escape'"):
        assert needle in kol, needle
    # In der Luft abstellen (Schalter) und Landepunkt auf Boden oder Möbel senkrecht darunter
    assert 'id="kol-fest"' in html and "type: 'kollision_loslassen', fest: true" in kol and "function landeHoehe(" in kol
    # Wegräumen wie in CAD: gewähltes Ding mit Entf oder sichtbarem Knopf
    assert 'id="kol-weg"' in html and "e.key !== 'Delete'" in kol and "aktion: 'parken', name: id" in kol
    # Regression: ein frisch hingelegtes, ruhendes Ding kam nie im Strom an und war nicht zu sehen/anzufassen
    assert "applyObjekte(msg.objekte);" in kol and "refresh(true)" in kol
    css = stil()
    assert ".stage--greifbar canvas { cursor: grab; }" in css and ".stage--ziehen canvas { cursor: grabbing; }" in css


def test_push_series_card_is_wired():
    """Lernen → Training → „Robustheit gegen Stöße“: ein Klick startet, Fortschritt über den WebSocket, Ergebnis als
    Tabelle mit Wort + Zeichen je Zelle (Farbe nie allein, WCAG 1.4.1), Vergleich mit einem älteren Profil; nur am PC.
    Erreichbar als #training/stossreihe (z. B. aus dem Kollisionsmodus)."""
    from duckpilot.server.app import STATIC

    html = seite()
    app = (STATIC / "app.js").read_text("utf-8")
    js = (STATIC / "stossreihe.js").read_text("utf-8")
    view = html[html.index('id="view-training"'):html.index('<!-- Alltag -->')]
    card = view[view.index('id="stossreihe"') - 80:view.index('id="stossreihe"') + 6000]
    assert 'class="card sr-card pc-only" id="stossreihe"' in view and 'id="kol-panel"' not in view
    for needle in ('id="sr-go">Stoßreihe starten</button>', 'id="sr-policy"', 'id="sr-stop"', '<progress',
                   'aria-live="polite"', 'id="sr-vergleich"', 'id="sr-profil"', '<caption', 'id="sr-tfoot"'):
        assert needle in card, needle
    assert "import { initStossreihe } from './stossreihe.js';" in app and "case 'stossreihe': return stossreihe.update(msg);" in app
    assert "stossreihe.load()" in app and "wantedPart === 'stossreihe'" in app
    for needle in ("'/api/kollision/reihe'", "'/api/kollision/reihe/stopp'", "/api/kollision/reihe/profile",
                   "scope = 'col'", "scope = 'row'", "zeichen: '✓', wort: 'steht'", "zeichen: '≈', wort: 'wackelt'",
                   "zeichen: '✕', wort: 'fällt'", "'sr-delta is-up'", "'sr-delta is-down'"):
        assert needle in js, needle
    assert "innerHTML" not in js                             # Namen nur über textContent
    css = stil()
    for tone in ("good", "warning", "critical"):
        assert f"var(--{tone}-tint)" in css[css.index(".sr-card"):]


def test_phone_controller_is_wired_and_safe():
    """Controller fürs Handy: Live-Bild (Entenblick / Kamerabild), Fahr-Stick, Tasten, Not-Aus, Umschauen wie Street View,
    Bewegungssensor nur mit https und Kippen nur mit Totmann, Vibrieren bei Stößen (Handy und Gamepad)."""
    from duckpilot.server.app import STATIC

    html = seite()
    app = (STATIC / "app.js").read_text("utf-8")
    ctl = (STATIC / "controller.js").read_text("utf-8")
    for needle in ('id="ctl-btn"', 'id="ctl"', 'role="dialog"', 'id="ctl-stop"', 'id="ctl-stick"', 'id="ctl-look"', 'id="ctl-cam"',
                   'name="ctl-gyro" value="kopf"', 'name="ctl-gyro" value="fahren"', 'id="ctl-vib"', 'data-taste="3"', 'id="ctl-talk"'):
        assert needle in html, needle
    assert "initController(" in app and "ctl?.onEvent(msg.event)" in app
    for needle in ("h.estop()", "/api/kamera/bild?breite=", "setStageMode('entenblick')", "window.isSecureContext",
                   "DeviceOrientationEvent.requestPermission", "navigator.vibrate", "playEffect('dual-rumble'",
                   "st.ruck", "type: 'blick'", "visibilitychange"):
        assert needle in ctl, needle
    # Kippen fährt nur mit Daumen auf dem Stick (Totmann); loslassen stoppt
    loop = ctl[ctl.index("  setInterval(() => {\n    if (!offen) return;"):ctl.index("// ── Umschauen")]
    assert "gyroArt === 'fahren' && totmann" in loop
    assert "if (!an) fahrt = { vx: 0, vyaw: 0 };" in ctl
    # Tasten dürfen nur Bewegung, Ausdruck und Laute auslösen
    import re

    namen = set(re.findall(r"name: '([a-z_]+)', args", ctl))
    assert namen <= {"sound", "skill", "emote", "dance", "look_around"}, namen


def test_phone_orientation_math():
    """Lage des Handys → Blick (Kopf) und Kippen (Fahren), in Hoch- und Querformat."""
    import json
    import shutil
    import subprocess

    from duckpilot.server.app import STATIC

    node = shutil.which("node")
    if not node:
        pytest.skip("node fehlt")
    code = ("import { handyLage } from '" + (STATIC / "controller.js").as_uri() + "';"
            "const d = (a,b,g,w) => Object.values(handyLage(a,b,g,w)).map(v => Math.round(v*180/Math.PI));"
            "console.log(JSON.stringify([d(0,90,0,0), d(30,90,0,0), d(0,110,0,0), d(0,0,-90,90), d(0,0,-70,90), d(0,-20,-90,90)]));")
    out = json.loads(subprocess.run([node, "--input-type=module", "-e", code], capture_output=True, text=True, check=True).stdout)
    hoch, links, hoch_auf, quer, quer_ab, quer_lenk = out     # je [gier, nick, lenk]
    assert links[0] - hoch[0] == 30 and hoch[1] == 0                  # nach links gedreht: Gier +30°
    assert hoch_auf[1] == 20                                           # nach oben geneigt: Nick +20°
    assert quer[1] == 0 and quer_ab[1] == -20                          # quer: Oberkante weg = schaut runter = vor
    assert quer[2] == 0 and quer_lenk[2] == 20 and quer_lenk[1] == 0   # Lenken ändert den Blick nicht


def test_weckwort_als_ganzes_wort_am_satzanfang():
    """0.37.5 (Hinweis aus dem Test „Weckwort reagiert nicht richtig“): ganzes Wort am Satzanfang, häufige Verhörer, nicht in
    „Rente“/„Enten“; nur das Weckwort → '' (dann gilt der nächste Satz als Befehl)."""
    import json
    import shutil
    import subprocess

    from duckpilot.server.app import STATIC

    node = shutil.which("node")
    if not node:
        pytest.skip("node fehlt")
    faelle = [["Ente lauf vor", "ente"], ["Ente", "ente"], ["Ende, tanz mal", "ente"], ["hey Ente, dreh dich", "ente"],
              ["alle Enten tanzen", "ente"], ["meine Rente ist sicher", "ente"], ["das ist das Ende vom Lied", "ente"],
              ["Duck, walk forward", "duck"], ["hey Quacki komm her", "quacki"]]
    code = ("globalThis.window = {}; globalThis.document = { documentElement: { lang: 'de' } };"
            "const { findeWeckwort } = await import('" + (STATIC / "voice.js").as_uri() + "');"
            "console.log(JSON.stringify(" + json.dumps(faelle) + ".map(([t, w]) => findeWeckwort(t, w))));")
    out = json.loads(subprocess.run([node, "--input-type=module", "-e", code], capture_output=True, text=True,
                                    check=True).stdout)
    assert out == ["lauf vor", "", "tanz mal", "dreh dich", None, None, None, "walk forward", "komm her"]
    voice = (STATIC / "voice.js").read_text("utf-8")
    assert "if (this.rec !== rec) return;" in voice and "this._wachBis = performance.now() + 6000" in voice


def test_own_voice_never_blocks_the_conversation():
    """Regression 0.37.6 (Anna: „das Programm hängt nach dem Aktivieren der Stimme“): Kommt ein Satz vom PC nicht
    rechtzeitig, spricht die Browser-Stimme; das Gespräch endet immer (Mikrofon wieder an), auch nach einem Stopp."""
    import shutil
    import subprocess

    from duckpilot.server.app import STATIC

    node = shutil.which("node")
    if not node:
        pytest.skip("node fehlt")
    code = ("globalThis.window = {}; globalThis.document = { documentElement: { lang: 'de' } };"
            "globalThis.fetch = () => new Promise(() => {});"          # der PC rechnet und rechnet …
            "const gesagt = []; globalThis.SpeechSynthesisUtterance = function (t) { this.text = t; };"
            "window.speechSynthesis = globalThis.speechSynthesis = { cancel() {}, getVoices: () => [], addEventListener() {},"
            "  speak(u) { gesagt.push(u.text); setTimeout(() => u.onend && u.onend(), 5); } };"
            "const v = await import('" + (STATIC / "voice.js").as_uri() + "');"
            "v.STIMME.clipWartenMs = 40;"
            "const log = [];"
            "const hooks = { onStart: () => log.push('start'), onEnd: () => log.push('ende'), onError: (w) => log.push(w) };"
            "await v.playPlan({ motor: 'qwen', teile: [{ art: 'text', text: 'Hallo Anna.', id: 'a1' }] }, hooks);"
            "const log2 = []; const p2 = v.playPlan({ motor: 'qwen', teile: [{ art: 'text', text: 'Zweiter.', id: 'b2' },"
            "  { art: 'text', text: 'Dritter.', id: 'c3' }] }, { onStart: () => log2.push('start'), onEnd: () => log2.push('ende') });"
            "await new Promise((r) => setTimeout(r, 60)); v.stopSpeaking(); await p2;"
            "console.log(JSON.stringify({ log, gesagt, log2 }));")
    out = json.loads(subprocess.run([node, "--input-type=module", "-e", code], capture_output=True, text=True,
                                    check=True).stdout)
    assert out["log"] == ["start", "zu langsam", "ende"] and out["gesagt"][0] == "Hallo Anna."
    assert out["log2"] == ["start", "ende"]                          # Stopp: Gespräch beendet, Mikrofon wieder an


def test_furniture_is_recognizable_but_light():
    """0.37.6 (Anna: „die 3D-Objekte sind sehr abstrakt – schöner, wenn man erkennt, dass es ein Couchtisch ist; soll
    flüssig laufen“): jedes Möbel aus wenigen einfachen Teilen, zu je Material einem Körper verschmolzen."""
    import shutil
    import subprocess

    from duckpilot.backends.world import World
    from duckpilot.server.app import STATIC

    node = shutil.which("node")
    if not node:
        pytest.skip("node fehlt")
    w = World.living_room()
    moebel = [{"name": b.name, "x": b.x, "y": b.y, "sx": b.sx, "sy": b.sy, "h": b.h, "color": b.color} for b in w.boxes]
    moebel += [{"name": c.name, "x": c.x, "y": c.y, "r": c.r, "h": c.h, "color": c.color} for c in w.cylinders]
    moebel.append({"name": "Waschmaschine", "x": 0, "y": 0, "sx": 0.5, "sy": 0.5, "h": 0.8, "color": "#ffffff"})
    code = ("const THREE = await import('" + (STATIC / "vendor" / "three.module.min.js").as_uri() + "');"
            "const { baueMoebel } = await import('" + (STATIC / "moebel3d.js").as_uri() + "');"
            "const tone = (h) => new THREE.Color(h);"
            "const out = {};"
            "for (const b of " + json.dumps(moebel) + ") { const g = baueMoebel(b, tone);"
            "  if (!g) { out[b.name] = null; continue; }"
            "  let n = 0, tri = 0; g.traverse((o) => { if (o.isMesh) { n++; const geo = o.geometry;"
            "    tri += (geo.index ? geo.index.count : geo.attributes.position.count) / 3; } });"
            "  const box = new THREE.Box3().setFromObject(g);"
            "  out[b.name] = { n, tri, x: g.position.x, z: g.position.z, hoch: box.max.y, breit: box.max.x - box.min.x }; }"
            "console.log(JSON.stringify(out));")
    out = json.loads(subprocess.run([node, "--input-type=module", "-e", code], capture_output=True, text=True,
                                    check=True).stdout)
    assert out["Waschmaschine"] is None                              # Unbekanntes bleibt ein einfacher Kasten
    for b in moebel[:-1]:
        m = out[b["name"]]
        # echte Dreiecke; seit 0.38.18 mit gebrochenen Kanten (je Kasten ~100 statt 12) – ein Möbel bleibt unter 3000,
        # der ganze Raum bei wenigen Zehntausend (und in der App je Möbel zu wenigen Meshes verschmolzen)
        assert m and 1 <= m["n"] <= 8 and m["tri"] < 3000, (b["name"], m)
        assert abs(m["x"] - b["x"]) < 1e-6 and abs(m["z"] + b["y"]) < 1e-6
        assert m["hoch"] <= b["h"] + 0.06                            # passt zur Kollision (Tasse darf herausschauen)
        breite = b.get("sx", 2 * b.get("r", 0)) if b["name"] != "Regal" else b["sy"]
        assert m["breit"] <= max(b.get("sx", 0), b.get("sy", 0), 2 * b.get("r", 0)) + 0.03, (b["name"], m, breite)
    duck3d = (STATIC / "duck3d.js").read_text("utf-8")
    assert "import { baueMoebel } from './moebel3d.js';" in duck3d and "o.userData.moebel = info" in duck3d


def test_mapping_switches_to_cockpit_and_music_button():
    """0.37.10 (Anna: „Kartieren macht im Simulator scheinbar nichts“ – auf „Tricks“ ist die 3D-Ansicht pausiert und
    unsichtbar; „Musikstück laden geht nicht mehr“ – dasselbe Stück zweimal gewählt löste kein „change“ aus)."""
    from duckpilot.server.app import STATIC

    raum = (STATIC / "raum.js").read_text("utf-8")
    app = (STATIC / "app.js").read_text("utf-8")
    tanz = (STATIC / "tanz.js").read_text("utf-8")
    html = seite()
    assert "if (zumCockpit) zumCockpit();" in raum and "zumCockpit: () => showView('cockpit')" in app
    assert "function plan(d)" in raum and "piktogramm(s)" in raum and 'id="raum-plan"' in html
    assert 'id="tanz-waehlen"' in html and 'label class="btn btn--primary" for="tanz-datei"' not in html
    assert "inp.value = '';" in tanz and "addEventListener('drop'" in tanz and "EncodingError" in tanz


def test_brain_rotates_and_zooms_and_map_feeds_the_lagebild():
    """0.37.12 (Anna): Hirnaktivität drehen und zoomen wie 3D, nach ein paar Sekunden zurück; die gelernte Karte auch
    im Lagebild."""
    from duckpilot.server.app import STATIC

    hirn = (STATIC / "hirn.js").read_text("utf-8")
    dash = (STATIC / "dashboard.js").read_text("utf-8")
    app = (STATIC / "app.js").read_text("utf-8")
    assert "function projizieren(p, w, hgt)" in hirn and "RUECKKEHR_MS" in hirn and "addEventListener('wheel'" in hirn
    assert "pa.vz" in hirn and "unterdruecken" in hirn                       # Tiefe; Drehen öffnet keinen Knoten
    assert "setKarte(k)" in dash and "this.karte.belegt" in dash
    assert "lagebild: (k) => map.setKarte(k)" in app and "raum?.laden()" in app


def test_farbe_der_microduck_einstellbar(client):
    """Seit 0.38.19: Cream, Graphite, Lavender, Sky wie bei Pollen; andere Werte lehnt die Prüfung ab."""
    assert client.get("/api/settings").json()["werte"]["farbe"] == "cream"
    r = client.post("/api/settings", json={"farbe": "lavender"}, headers={"Origin": "http://127.0.0.1:8765"})
    assert r.status_code == 200
    assert client.runtime.config.farbe == "lavender"
    assert client.post("/api/settings", json={"farbe": "pink"}, headers={"Origin": "http://127.0.0.1:8765"}).status_code >= 400
    html = seite()
    for f in ("cream", "graphite", "lavender", "sky"):
        assert f'value="{f}" data-set="farbe"' in html
    js = (Path(__file__).parent.parent / "duckpilot/server/static/duckmodel.js").read_text(encoding="utf-8")
    assert "setFarbe" in js and "Math.min(...rgb) > 0.7" in js     # nur helle Schalen, Orange bleibt
