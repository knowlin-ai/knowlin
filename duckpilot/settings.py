"""Einstellungen aus der Oberfläche – und der API-Schlüssel im Tresor des Betriebssystems.

* Einstellungen landen als `settings.json` im lokalen App-Datenordner
  (Windows: %LOCALAPPDATA%\\duckpilot), nicht im Projektordner – also nicht in OneDrive.
* Der Anthropic-Schlüssel landet über `keyring` in der Windows-Anmeldeinformations-
  verwaltung (macOS: Schlüsselbund). Er wird nie an den Browser geschickt.

Wer gewinnt: Standardwerte < duckpilot.toml < Einstellungen aus der App < Befehlszeile.
Beim Schlüssel gilt, was du in der App einträgst: Tresor > Umgebungsvariable > .env.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

KEYRING_SERVICE = "duckpilot"
KEYRING_USER = "anthropic_api_key"

MODELS = {
    "claude-sonnet-5-5": "Sonnet 5.5 – ausgewogen (Standard)",
    "claude-haiku-5-5": "Haiku 5.5 – schnell und günstig",
    "claude-opus-5-5": "Opus 5.5 – am gründlichsten, langsamer",
}
WHISPER_MODELS = ("tiny", "base", "small", "medium")

# Was die Oberfläche ändern darf – mit Prüfung. Alles andere wird ignoriert.
EDITABLE: dict[str, Any] = {
    "backend": ("sim", "robotd"),
    "modul": ("duckpilot", "reachy_mini", "open_duck_mini"),     # Körper der Suite (seit 0.38.1, Open Duck seit 0.38.4)
    "reachy_adresse": "http_url",
    "robot": str,
    "tof": str,
    "updater": str,
    "media": str,
    "configd": str,
    "tricks": "repos",
    "pakete": "packs",
    "model_style": ("original", "einfach"),
    "farbe": ("cream", "graphite", "lavender", "sky"),   # Microduck-Farben wie bei Pollen (seit 0.38.19)
    "sim_physik": bool,
    "head_signs": "signs",
    "model": tuple(MODELS),
    "duck_name": str,
    "kopf_name": str,                          # seit 0.38.9: Name des Kopfes (leer = Knowlin)
    "nutzer_name": str,                        # seit 0.38.9: wie der Kopf dich anspricht (leer = Mensch)
    "kopf_stimme_motor": ("browser", "piper", "qwen"),   # seit 0.38.10: Knowlins eigene Stimme
    "kopf_stimme_piper": "piper_voice",
    "kopf_stimme_qwen": "voice_id",
    "stt": ("browser", "whisper", "aus"),
    "whisper_model": WHISPER_MODELS,
    "wake_word": str,
    "tts": bool,
    "stimme_motor": ("browser", "piper", "qwen"),
    "stimme_piper": "piper_voice",
    "stimme_qwen": "voice_id",
    "qwen_qualitaet": ("schnell", "hoch"),
    "entenhaft": "unit",
    "weitere_enten": "enten",                  # weitere Enten im einfachen Simulator (seit 0.36.3), 0 … 8 (seit 0.38.24, vorher 4)
    "klang_hoehe": "halbtoene",                # Klangsignatur (seit 0.36.1): Laute höher/tiefer, −5 … +5
    "klang_farbe": "plusminus",                # Klangsignatur: dunkler −1 … heller +1
    "entenlaute": ("aus", "selten", "manchmal", "oft"),
    "plaudern": bool,
    "schnellbefehle": bool,
    "mcp": bool,
    "gehirn": ("claude", "lokal", "anbieter"),
    "anbieter": ("openai", "gemini", "mistral", "openrouter", "lmstudio", "eigen"),
    "anbieter_modell": "ollama_model",
    "anbieter_adresse": "anbieter_url",
    "sprache": ("de", "en"),
    "lokal_modell": "ollama_model",
    "lokal_adresse": "local_url",
    "idle_life": bool,
    "obstacle_guard": bool,
    "ausweichen": bool,
    "auto_recover": bool,
    "stopp_fenster_s": "stopp_fenster",
    "notaus_sperre_s": (120, 300, 600),        # seit 0.38.13: nur länger als die Sicherheitsregel, nie kürzer
    "notaus_danach": ("weiter", "still"),
    "kollision_protest": bool,
    "reachy_begruessung": bool,                # seit 0.38.13: Reachy grüßt beim Aufwecken
    "eigenstaendig": ("aus", "ab_und_zu", "oft"),   # ohne Befehle selbst etwas tun (Wunsch des Maintainers 5.11.)
    "radio_adressen": "radio_urls",            # seit 0.38.13: zuletzt genutzte Webradios (Mitwippen), höchstens 5
    "kopf_stabil": bool,
    "memory": bool,
    "humor": "unit",
    "energie": "unit",
    "grund_energie": "unit",                   # seit 0.38.10: Grundcharakter bei Knowlin
    "grund_humor": "unit",
    "eigenschaften": "eigenschaften",          # Eigenschaften der Gestalt (Kennungen aus figuren.GESTALT)
    "emotions": bool,
}
# Ältere Schalter, die auf den Humor-Regler abgebildet werden
GOOFY_HUMOR = {"sanft": 0.6, "mittel": 0.75, "wild": 0.95}


def data_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / "duckpilot"


def settings_path() -> Path:
    override = os.environ.get("DUCKPILOT_SETTINGS")
    return Path(override) if override else data_dir() / "settings.json"


def load_user_settings() -> dict[str, Any]:
    path = settings_path()
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return {k: v for k, v in raw.items() if k in EDITABLE}
    except Exception as exc:
        log.error("Einstellungen nicht lesbar (%s) – nutze Standardwerte", exc)
        return {}


def validate(patch: dict[str, Any]) -> dict[str, Any]:
    """Nur bekannte Schlüssel mit gültigen Werten durchlassen; sonst ValueError."""
    clean: dict[str, Any] = {}
    patch = dict(patch)
    if "goofy" in patch or "goofy_level" in patch:  # Abkürzung: Goofy an/aus = Humor-Regler oben/unten
        on = patch.pop("goofy", True)
        level = patch.pop("goofy_level", None)
        if not isinstance(on, bool):
            raise ValueError("goofy: an oder aus erwartet")
        if on:
            current = load_user_settings().get("humor", 0.25)
            patch.setdefault("humor", GOOFY_HUMOR.get(level, max(float(current), 0.75)))
        else:
            patch.setdefault("humor", min(float(load_user_settings().get("humor", 0.25)), 0.25))
    for key, value in patch.items():
        rule = EDITABLE.get(key)
        if rule is None:
            raise ValueError(f"Unbekannte Einstellung '{key}'")
        if rule is bool:
            if not isinstance(value, bool):
                raise ValueError(f"{key}: an oder aus erwartet")
        elif rule is str:
            value = str(value or "").strip()
            limit = 24 if key in ("duck_name", "wake_word", "kopf_name") else 40 if key == "nutzer_name" else 200
            if len(value) > limit:
                raise ValueError(f"{key}: höchstens {limit} Zeichen")
            if key in ("duck_name", "wake_word") and not value:
                raise ValueError(f"{key}: darf nicht leer sein")
            if key == "kopf_name" and not value:
                value = "Knowlin"
            if key in ("tof", "updater", "media", "configd") and not value:
                value = None
        elif rule == "stopp_fenster":
            # WCAG 2.2.1: die Zeit zum „Stopp“-Rufen nach einem Sturz ist einstellbar
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not 2 <= value <= 10:
                raise ValueError(f"{key}: 2 bis 10 Sekunden")
            value = round(float(value), 1)
        elif rule == "enten":
            if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 8:
                raise ValueError(f"{key}: 0 bis 8 weitere Enten")
        elif rule == "halbtoene":
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not -5 <= value <= 5:
                raise ValueError(f"{key}: −5 bis +5 Halbtöne")
            value = round(float(value), 1)
        elif rule == "plusminus":
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not -1 <= value <= 1:
                raise ValueError(f"{key}: Zahl zwischen −1 und 1 erwartet")
            value = round(float(value), 2)
        elif rule == "unit":
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1:
                raise ValueError(f"{key}: Zahl zwischen 0 und 1 erwartet")
            value = round(float(value), 3)
        elif rule == "radio_urls":
            # Webradio-Adressen (Mitwippen): nur http(s), ohne Zugangsdaten in der Adresse, höchstens 5, neueste zuerst
            if not isinstance(value, list) or len(value) > 20:
                raise ValueError(f"{key}: Liste von Adressen erwartet")
            urls: list[str] = []
            for u in value:
                u = str(u or "").strip()
                if not re.fullmatch(r"https?://[^\s/@:]+(:\d{1,5})?(/[^\s]*)?", u) or len(u) > 300:
                    raise ValueError(f"{key}: '{u[:60]}' ist keine Adresse eines Streams (http:// oder https://)")
                if u not in urls:
                    urls.append(u)
            value = urls[:5]
        elif rule == "repos":
            if not isinstance(value, list) or len(value) > 40:
                raise ValueError("tricks: Liste mit höchstens 40 Repos")
            repos = []
            for r in value:
                r = str(r).strip()
                if not re.fullmatch(r"[A-Za-z0-9][\w.-]{0,95}/[\w.-]{1,96}", r):
                    raise ValueError(f"tricks: '{r[:40]}' ist kein Hub-Repo (org/name)")
                if r not in repos:
                    repos.append(r)
            value = repos
        elif rule == "eigenschaften":
            from .figuren import GESTALT

            erlaubt = {e["id"] for liste in GESTALT.values() for e in liste}
            if value is not None and (not isinstance(value, list) or len(value) > 12
                                      or any(str(v) not in erlaubt for v in value)):
                raise ValueError("eigenschaften: Liste bekannter Eigenschaften erwartet")
            value = None if value is None else list(dict.fromkeys(str(v) for v in value))
        elif rule == "packs":
            from .skills import PACKS, activatable

            if not isinstance(value, list) or len(value) > 20:
                raise ValueError("pakete: Liste mit Paket-Kennungen erwartet")
            ok = activatable()
            packs = []
            for v in value:
                v = str(v)
                if v not in PACKS:
                    raise ValueError(f"pakete: '{v[:40]}' gibt es nicht")
                if v not in ok:
                    raise ValueError(f"pakete: '{v}' lässt sich noch nicht aktivieren")
                if v not in packs:
                    packs.append(v)
            value = packs
        elif rule == "piper_voice":
            from .voice.tts import PIPER_VOICES

            if value not in PIPER_VOICES:
                raise ValueError(f"stimme_piper: erlaubt sind {', '.join(PIPER_VOICES)}")
        elif rule == "voice_id":
            value = str(value or "")
            if not re.fullmatch(r"[a-z0-9-]{0,40}", value):
                raise ValueError("stimme_qwen: ungültige Kennung")
        elif rule == "ollama_model":
            value = str(value or "").strip()
            if not re.fullmatch(r"[\w.:/-]{0,80}", value):
                raise ValueError("lokal_modell: ungültiger Modellname")
        elif rule == "local_url":
            value = str(value or "").strip().rstrip("/") or "http://127.0.0.1:11434"
            m = re.fullmatch(r"https?://([^/:]+|\[[0-9a-fA-F:]+\])(:\d{1,5})?", value)
            if not m:
                raise ValueError("lokal_adresse: z. B. http://127.0.0.1:11434")
            host = m.group(1).strip("[]")
            if host != "localhost":
                import ipaddress

                try:
                    ip = ipaddress.ip_address(host)
                except ValueError:
                    raise ValueError("lokal_adresse: nur dieser PC oder eine IP im Heimnetz") from None
                if not (ip.is_loopback or ip.is_private):
                    raise ValueError("lokal_adresse: nur dieser PC oder eine IP im Heimnetz")
        elif rule == "http_url":
            # Reachy-Mini-Daemon (seit 0.38.1): dieser PC, ein Name im Heimnetz (*.local) oder eine private IP
            value = str(value or "").strip().rstrip("/") or "http://localhost:8000"
            m = re.fullmatch(r"http://([A-Za-z0-9.-]+|\[[0-9a-fA-F:]+\])(:\d{1,5})?", value)
            if not m:
                raise ValueError("reachy_adresse: z. B. http://localhost:8000 oder http://reachy-mini.local:8000")
            host = m.group(1).strip("[]")
            if host != "localhost" and not host.endswith(".local"):
                import ipaddress

                try:
                    ip = ipaddress.ip_address(host)
                except ValueError:
                    raise ValueError("reachy_adresse: nur dieser PC, ein Name auf .local oder eine IP im Heimnetz") from None
                if not (ip.is_loopback or ip.is_private):
                    raise ValueError("reachy_adresse: nur dieser PC, ein Name auf .local oder eine IP im Heimnetz")
        elif rule == "anbieter_url":
            # Eigene Adresse eines OpenAI-kompatiblen Dienstes: https überall, http nur auf diesem PC oder im Heimnetz
            # (der Schlüssel geht dorthin – nie unverschlüsselt ins Internet)
            value = str(value or "").strip().rstrip("/")
            if value:
                m = re.fullmatch(r"(https?)://([^/:]+|\[[0-9a-fA-F:]+\])(:\d{1,5})?(/[\w./-]*)?", value)
                if not m:
                    raise ValueError("anbieter_adresse: z. B. https://…/v1 oder http://127.0.0.1:1234/v1")
                if m.group(1) == "http":
                    host = m.group(2).strip("[]")
                    import ipaddress

                    try:
                        ok = host == "localhost" or ipaddress.ip_address(host).is_loopback or ipaddress.ip_address(host).is_private
                    except ValueError:
                        ok = False
                    if not ok:
                        raise ValueError("anbieter_adresse: http nur auf diesem PC oder im Heimnetz, sonst https")
        elif rule == "signs":
            if not (isinstance(value, list) and len(value) == 4 and all(v in (1, -1, 1.0, -1.0) for v in value)):
                raise ValueError("head_signs: vier Werte, jeweils 1 oder -1")
            value = [float(v) for v in value]
        elif isinstance(rule, tuple):
            if value not in rule:
                raise ValueError(f"{key}: erlaubt sind {', '.join(map(str, rule))}")
        clean[key] = value
    if clean.get("backend") == "robotd" or "robot" in clean:
        robot = clean.get("robot")
        if robot is not None:
            from .backends.robotd import parse_address

            parse_address(robot)  # wirft ValueError bei Unsinn
    return clean


def save_user_settings(patch: dict[str, Any]) -> dict[str, Any]:
    clean = validate(patch)
    current = load_user_settings()
    current.update(clean)
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)
    return clean


# ── Schlüssel im Tresor ─────────────────────────────────────────────────────
def _keyring():
    try:
        import keyring
        from keyring.backends import fail

        kr = keyring.get_keyring()
        if isinstance(kr, fail.Keyring):
            return None
        return keyring
    except Exception:
        return None


def vault_available() -> bool:
    return _keyring() is not None


def vault_name() -> str:
    if sys.platform == "win32":
        return "Windows-Anmeldeinformationsverwaltung"
    if sys.platform == "darwin":
        return "macOS-Schlüsselbund"
    return "Schlüsselbund des Systems"


def get_vault_key() -> str | None:
    kr = _keyring()
    if kr is None:
        return None
    try:
        return kr.get_password(KEYRING_SERVICE, KEYRING_USER) or None
    except Exception as exc:
        log.warning("Tresor nicht lesbar: %s", exc)
        return None


def set_vault_key(key: str) -> None:
    kr = _keyring()
    if kr is None:
        raise RuntimeError(f"Kein {vault_name()} verfügbar – Schlüssel bitte als Umgebungsvariable setzen")
    kr.set_password(KEYRING_SERVICE, KEYRING_USER, key)


def delete_vault_key() -> None:
    kr = _keyring()
    if kr is None:
        return
    try:
        kr.delete_password(KEYRING_SERVICE, KEYRING_USER)
    except Exception:
        pass


def get_anbieter_key(anbieter: str) -> str | None:
    """Schlüssel eines anderen KI-Anbieters (seit 0.35) – je Anbieter ein Eintrag im Tresor."""
    kr = _keyring()
    if kr is None or not re.fullmatch(r"[a-z]{2,20}", anbieter or ""):
        return None
    try:
        return kr.get_password(KEYRING_SERVICE, f"anbieter_key_{anbieter}") or None
    except Exception as exc:
        log.warning("Tresor nicht lesbar: %s", exc)
        return None


def set_anbieter_key(anbieter: str, key: str) -> None:
    kr = _keyring()
    if kr is None:
        raise RuntimeError(f"Kein {vault_name()} verfügbar")
    key = (key or "").strip()
    if not re.fullmatch(r"[a-z]{2,20}", anbieter or "") or len(key) < 8 or len(key) > 400 or any(c.isspace() for c in key):
        raise ValueError("Das sieht nicht nach einem Schlüssel aus.")
    kr.set_password(KEYRING_SERVICE, f"anbieter_key_{anbieter}", key)


def delete_anbieter_key(anbieter: str) -> None:
    kr = _keyring()
    if kr is None or not re.fullmatch(r"[a-z]{2,20}", anbieter or ""):
        return
    try:
        kr.delete_password(KEYRING_SERVICE, f"anbieter_key_{anbieter}")
    except Exception:
        pass


def check_key_format(key: str) -> str:
    key = (key or "").strip()
    if not key.startswith("sk-ant-") or len(key) < 30 or any(c.isspace() for c in key):
        raise ValueError("Das sieht nicht nach einem Anthropic-Schlüssel aus (beginnt mit sk-ant-).")
    return key


def key_hint(key: str | None) -> str | None:
    return f"sk-ant-…{key[-4:]}" if key else None
