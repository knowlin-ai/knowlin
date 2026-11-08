"""Stimmbeschreibung auf Deutsch → Englisch für Qwen3-TTS (VoiceDesign).

Qwens Beispiele für Stimmbeschreibungen sind Chinesisch oder Englisch; Deutsch geht, Feinheiten
(„ein bisschen rau“, „ein Lachen in der Stimme“) kommen auf Englisch meist genauer an. Deshalb
beschreibt man in duckpilot auf Deutsch, und vor dem Entwerfen wird übersetzt:

1. Eine der Vorlagen → deren geprüfte englische Fassung (ohne Netz).
2. Schon englisch → bleibt, wie es ist.
3. Sonst übersetzt Claude, ohne Schlüssel das lokale Sprachmodell (Ollama).
4. Geht beides nicht, wird der deutsche Text genommen – mit Hinweis.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from .tts import DESIGN_PRESETS, DESIGN_PRESETS_MODUL

log = logging.getLogger(__name__)

# Vorlagen, wie man sie sieht (Deutsch), mit der englischen Fassung, die ans Modell geht
PRESETS_DE: dict[str, str] = {
    "Quirlige Ente": "Eine kleine, quirlige Comic-Ente: hohe, helle, leicht näselnde Stimme mit einem verspielten, "
                     "quakigen Unterton, flottes fröhliches Tempo, warm und liebevoll, jung und neugierig.",
    "Gemütliche Ente": "Eine gemütliche, freundliche Ente: weiche, warme, leicht näselnde, mittelhohe Stimme, "
                       "ruhiges entspanntes Tempo, lächelt beim Sprechen, sanft und lieb.",
    "Freche Ente": "Eine freche junge Ente: hohe, lebhafte Stimme mit etwas Rauheit und einem Lachen darin, "
                   "hüpfender Rhythmus, schelmisch, aber liebenswert, leicht näselnd.",
}
assert PRESETS_DE.keys() == DESIGN_PRESETS.keys()

# Je Körper (Hinweis aus dem Test 5.11.): Reachy freundlich-neugierig, leicht technisch, nie quakig; Open Duck größer, tiefer,
# mit Bastler-Charme; „kopf“ = Knowlin ohne Körper. Die englischen Fassungen stehen in `tts.DESIGN_PRESETS_MODUL`.
PRESETS_DE_MODUL: dict[str, dict[str, str]] = {
    "duckpilot": PRESETS_DE,
    "open_duck_mini": {
        "Bastler-Ente": "Eine selbstgebaute Roboter-Ente: etwas tiefere, warme, leicht näselnde Stimme, gemütliches Tempo, "
                        "stolz und ein bisschen tollpatschig, mit Bastler-Charme und einem Lächeln in der Stimme.",
        "Große Ente": "Eine größere, gutmütige Ente: tiefe, runde, sonore Stimme mit leicht quakigem Unterton, langsames, "
                      "freundliches Tempo, brummig-herzlich.",
        "Tollpatschige Ente": "Eine tollpatschige junge Ente: mittlere bis tiefere Stimme, etwas holprig und lebhaft, lacht "
                              "gern über sich selbst, leicht näselnd, herzlich und verspielt.",
    },
    "reachy_mini": {
        "Freundlicher Tischroboter": "Ein freundlicher, neugieriger kleiner Tischroboter: warme, klare, mittlere Stimme mit "
                                     "einem leicht technischen, sanft synthetischen Schimmer, ruhiges, aufmerksames Tempo, "
                                     "freundlich und hilfsbereit, nicht quäkig.",
        "Neugieriger Beobachter": "Ein aufmerksamer, neugieriger Roboter: ruhige, weiche Stimme mittlerer Höhe, staunt gern, "
                                  "spricht bedächtig und deutlich, mit leisem trockenem Humor und einem Hauch Elektronik im "
                                  "Klang.",
        "Fröhlicher Helfer": "Ein fröhlicher kleiner Helfer-Roboter: helle, warme Stimme, etwas schneller und lebhaft, "
                             "freundlich und zugewandt, leicht metallischer Unterton, aber natürlich und gut verständlich.",
    },
    "kopf": {
        "Ruhig und tief": "Eine ruhige, tiefe, warme Stimme eines erwachsenen Wesens – seriös, klar und ein wenig "
                          "geheimnisvoll, langsames Tempo, deutliche Aussprache.",
        "Freundlich und klar": "Eine freundliche, klare, mittlere Stimme – ruhig und zugewandt, gelassenes Tempo, warm, mit "
                               "leisem Lächeln.",
    },
}
assert all(PRESETS_DE_MODUL[m].keys() == DESIGN_PRESETS_MODUL[m].keys() for m in PRESETS_DE_MODUL)
# Beschreibungs-Entwurf mit dem Namen der Verkörperung (änderbar) – die Microduck beginnt wie bisher mit leerem Feld
ENTWURF: dict[str, str] = {
    "open_duck_mini": "{name}, eine selbstgebaute Ente: etwas größer und tiefer als eine kleine Ente, warm und leicht "
                      "näselnd, gemütliches Tempo, mit Bastler-Charme.",
    "reachy_mini": "{name}, ein freundlicher, neugieriger Tischroboter: warme, klare, mittlere Stimme mit leicht technischem "
                   "Schimmer, ruhiges Tempo, aufmerksam und hilfsbereit – nicht quäkig.",
}


def vorlagen(art: str) -> dict[str, str]:
    """Vorlagen zum Entwerfen für einen Körper (`config.modul`) oder „kopf“ – unbekannt: die der Microduck."""
    return dict(PRESETS_DE_MODUL.get(art, PRESETS_DE))


def entwurf(art: str, name: str | None) -> str:
    """Vorschlag fürs Beschreibungsfeld mit dem Namen der Verkörperung – leer, wo es keinen gibt."""
    vorlage = ENTWURF.get(art, "")
    if not vorlage:
        return ""
    return vorlage.format(name=(name or "").strip() or {"reachy_mini": "Reachy", "open_duck_mini": "Odi"}[art])

SYSTEM = ("Du übersetzt die Beschreibung einer Stimme vom Deutschen ins Englische, für ein Text-to-Speech-Modell, "
          "das Stimmen nach Beschreibung erfindet. Übersetze sinngemäß und bildhaft, behalte jede Klangeigenschaft "
          "(Höhe, Tempo, Klangfarbe, Charakter) bei und füge nichts hinzu. Antworte nur mit der Übersetzung, "
          "ohne Anführungszeichen und ohne Erklärung.")

_DE = {"und", "eine", "ein", "mit", "die", "der", "das", "stimme", "leicht", "etwas", "nicht", "sehr", "aber",
       "hohe", "tiefe", "klingt", "spricht", "ist", "wie", "ente", "fröhlich", "lustig", "ruhig", "frech"}
_EN = {"a", "an", "the", "with", "and", "voice", "slightly", "but", "high", "low", "tone", "speaks", "is", "like",
       "duck", "cheerful", "warm", "soft", "bright"}


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def preset_english(text: str) -> str | None:
    t = _norm(text)
    for art, presets in PRESETS_DE_MODUL.items():
        for key, de in presets.items():
            en = DESIGN_PRESETS_MODUL[art][key]
            if t == _norm(de) or t == _norm(en):
                return en
    return None


def looks_english(text: str) -> bool:
    if re.search(r"[äöüßÄÖÜ]", text):
        return False
    words = re.findall(r"[a-zA-Z]+", text.lower())
    en = sum(w in _EN for w in words)
    de = sum(w in _DE for w in words)
    return en > de


def _clean(out: str, original: str) -> str:
    out = _norm(out).strip("\"'„“”«»")
    out = re.sub(r"^(translation|übersetzung)\s*:\s*", "", out, flags=re.I)
    if not 5 <= len(out) <= 3 * len(original) + 80:
        raise ValueError("Übersetzung unbrauchbar")
    return out[:500]


async def to_english(text: str, agent: Any = None) -> tuple[str, str]:
    """→ (Beschreibung fürs Modell, Weg: vorlage | englisch | claude | lokal | deutsch)."""
    text = _norm(text)[:500]
    hit = preset_english(text)
    if hit:
        return hit, "vorlage"
    if looks_english(text):
        return text, "englisch"
    if agent is not None and getattr(agent, "client", None) is not None:
        try:
            resp = await agent.client.messages.create(
                model=agent.config.model, max_tokens=400, system=SYSTEM,
                messages=[{"role": "user", "content": text}])
            out = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
            return _clean(out, text), "claude"
        except Exception as exc:
            log.warning("Stimmbeschreibung übersetzen (Claude): %s", exc)
    local = getattr(agent, "local", None) if agent is not None else None
    if local is not None and getattr(local, "configured", False):
        try:
            data = await local._post("/api/chat", {
                "model": local.model, "stream": False, "think": False,
                "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": text}],
                "options": {"temperature": 0.2}}, timeout=90.0)
            return _clean((data.get("message") or {}).get("content", ""), text), "lokal"
        except Exception as exc:
            log.warning("Stimmbeschreibung übersetzen (lokal): %s", exc)
    return text, "deutsch"
