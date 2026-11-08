"""Hinweise 7.11. abends: „Der erkundete Bereich lässt sich auf dem Boden nicht mehr gut erkennen“ und „die
gelaufene Spur sieht auch nicht so gut aus, passt nicht so zum Rest“ – seit den Dielen (0.38.18) lagen ein blasses Blau
in Kacheln und eine dünne Linie aus Dunkelgrau ins Blau auf dem Holz."""

from test_gui import tmp_settings, vault  # noqa: F401 – Fixtures

from duckpilot.server.app import STATIC

JS = (STATIC / "duck3d.js").read_text(encoding="utf-8")


def test_erkundeter_bereich_als_helle_kaestchen():
    karte = JS[JS.index("  setKarte(k) {"):JS.index("  // Gemerkte Orte:")]
    assert "InstancedMesh" in karte and "toneMapped: false" in karte                # Kästchen, hell und kräftig genug
    assert "0.006);" in karte and "polygonOffset: true" in karte                       # über dem Teppich, ohne Flimmern
    assert "karteFrei: 0xcfe2ff" in JS                                                 # heller, kühler Schleier auf Holz


def test_spur_als_helles_band():
    spur = JS[JS.index("  _buildTrail() {"):JS.index("  _buildTarget() {")]
    assert "THREE.Line(" not in spur and "new THREE.Mesh(geo" in spur and "setXYZW(" in spur   # Band mit Ausblenden
    assert "trail: 0xfff6e8" in JS and "C.bg" not in spur                             # kein Dunkelgrau mehr
    assert "this._spurGlatt" in spur and "* 0.18" in spur                              # geglättet, ohne Schrittzittern


def test_spielen_knopf_auch_ohne_physik(tmp_settings, vault, tmp_path, monkeypatch):  # noqa: F811
    """Frage 7.11.: „Wo finde ich den Modus, Objekte zu platzieren?“ – ohne echte Physik fehlte der Knopf ganz."""
    import json

    from duckpilot.config import load
    from duckpilot.kollision_service import KollisionService
    from duckpilot.server.app import Runtime

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    tmp_settings.write_text(json.dumps({"backend": "sim", "sim_physik": False}))
    rt = Runtime(load(memory_path=str(tmp_path / "mem.json")))
    st = KollisionService(rt).status()
    assert not st["verfuegbar"] and st["braucht_physik"]
    js = (STATIC / "kollision.js").read_text(encoding="utf-8")
    assert "btn.hidden = !ok && !vorbereiten;" in js and "{ sim_physik: true }" in js
