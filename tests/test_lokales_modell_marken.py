"""Lokale Modelle schreiben Werkzeuge manchmal als Text (gemeldet 11.11. mit qwen3.5:9b):
„Blau ist toll! [emote: begeistert] [head: yaw deg=10, pitch deg=-5, seconds=2]“ – ausführen, nie zeigen."""

from duckpilot.brain.local import text_werkzeuge
from duckpilot.brain.tools import TOOLS

SCHEMAS = {t["name"]: t["input_schema"] for t in TOOLS}


def test_marken_werden_werkzeuge_und_verschwinden_aus_dem_text():
    text, aufrufe = text_werkzeuge("Quak! Ich mag Blau – wie mein Federkleid! [emote: begeistert] "
                                   "[head: yaw deg=10, pitch deg=-5, seconds=2]", SCHEMAS)
    assert text == "Quak! Ich mag Blau – wie mein Federkleid!"
    assert aufrufe == [("emote", {"emotion": "begeistert"}),
                       ("head", {"yaw_deg": 10.0, "pitch_deg": -5.0, "seconds": 2.0})]


def test_unbekannte_marken_weg_normale_klammern_bleiben():
    text, aufrufe = text_werkzeuge("Ein Satz (mit Klammer) [zaubern: alles] und [emote] fertig.", SCHEMAS)
    assert text == "Ein Satz (mit Klammer) und [emote] fertig." and aufrufe == []


def test_pflichtangabe_fehlt_kein_aufruf():
    text, aufrufe = text_werkzeuge("Hm. [skill: x=1]", SCHEMAS)
    assert text == "Hm." and aufrufe == []


def test_lm_studio_400_mit_grund():
    from duckpilot.brain.anbieter import grund_400

    zu_klein = grund_400("lmstudio", '{"error": {"message": "The number of tokens to keep from the initial prompt '
                                     'is greater than the context length"}}')
    assert "Kontextlänge" in zu_klein and "16 384" in zu_klein
    assert "abgelehnt" in grund_400("openai", '{"error": "bad tool schema"}')
