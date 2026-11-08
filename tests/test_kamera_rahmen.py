"""Hinweise 7.11. spätabends zur Kameraführung (0.38.25):
„wenn quasi hinter der Kamera zu nah ein Objekt ist, zoomt er viel zu nah ran“ und „Odi ist ja etwas größer und der Kopf
ist schon Oberkante vom Kameraausschnitt“."""

from duckpilot.server.app import STATIC

JS = (STATIC / "duck3d.js").read_text(encoding="utf-8")


def _block(name: str) -> str:
    start = JS.index(f"  {name}(")
    return JS[start:JS.index("\n  }\n", start)]


def test_moebel_nah_an_der_kamera_wird_durchsichtig_statt_heranzuzoomen():
    b = _block("_kameraAusweichen")
    assert "this._wunsch * 0.5" in b and "_durchsichtig(" in b         # nah an der Kamera → durchsichtig
    assert "_figurHoehe() * 2" in b                                     # nie näher als der Mindestrahmen
    d = _block("_durchsichtig")
    assert "opacity = 0.28" in d and "echtStoff" in d                   # eigener Stoff, danach wiederhergestellt


def test_startperspektive_und_blickpunkt_richten_sich_nach_der_groesse():
    h = _block("_figurHoehe")
    assert "open_duck_mini: 0.42" in h and "reachy_mini: 0.3" in h      # Richtwerte je Körper
    assert "this.controls.target.set(p.x, p.y + this._figurHoehe() * 0.42, p.z)" in JS
    assert "p.y + this._figurHoehe() * 0.36" in JS                      # Folgen: Blick auf die Mitte, nicht die Füße
    assert "0.92 * s" in JS and "_rahmenMass()" in JS
