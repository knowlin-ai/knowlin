"""Hinweise 8.11.: „Die Socke sieht fehlerhaft aus“, „nicht mal wie eine Socke“, „es soll nach Socke aussehen“."""

from duckpilot.server.app import STATIC

DINGE = (STATIC / "dinge3d.js").read_text(encoding="utf-8")
DUCK = (STATIC / "duck3d.js").read_text(encoding="utf-8")


def test_socke_hat_den_typischen_umriss():
    assert "THREE.Shape()" in DINGE and "ExtrudeGeometry" in DINGE                 # flacher Stoff, kein Rohr, kein Ring
    for teil in ("// Ferse", "// Spitze", "// Spann", "zwei Ringel"):
        assert teil in DINGE
    assert "TorusGeometry" not in DINGE and "TubeGeometry" not in DINGE


def test_im_schnabel_haengt_sie_am_buendchen_und_liegt_danach_wieder_flach():
    assert "sockeHaengen(mesh)" in DUCK and "sockeLegen(mesh, it)" in DUCK
    assert "imSchnabel(mesh, it, p," in DUCK                                        # ausgerichtet mit der Ente
