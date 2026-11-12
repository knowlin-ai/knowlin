"""Konfiguration aus duckpilot.toml (optional) und Umgebungsvariablen."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PROJECT_DIR = Path(__file__).resolve().parents[1]


@dataclass
class Config:
    # [backend]
    backend: str = "sim"                       # "sim" | "robotd" (bei Reachy Mini: echtes Gerät über Pollens Daemon)
    modul: str = "duckpilot"                   # welcher Körper: id eines Profils aus duckpilot.koerper (seit 0.38.35)
    # Angaben, die ein Körper zum Verbinden braucht (seit 0.38.35, Körperschnittstelle) – z. B. LeRobot:
    # {"typ": "so101_follower", "port": "COM5", "id": "mein_arm"}. Nie Geheimnisse.
    koerper_optionen: dict[str, str] = field(default_factory=dict)
    reachy_adresse: str = "http://localhost:8000"   # Pollens Reachy-Mini-Daemon (Lite: localhost, Wireless: reachy-mini.local)
    robot: str = "tcp:127.0.0.1:7900"          # robotd-Adresse: tcp:host:port oder unix:/pfad
    tof: str | None = None                     # tofd-Socket für den Tiefensensor (optional)
    updater: str | None = None                 # updaterd-Socket für Tricks vom Hub (optional)
    media: str | None = None                   # mediad-Socket für die Kamera (optional, sonst robotd-Port + 3)
    configd: str | None = None                 # configd-Socket für WLAN, System, Protokolle (sonst robotd-Port + 4)
    tricks: list[str] = field(default_factory=list)   # vorgemerkte Hub-Repos (org/name)
    # aktive Skill-Pakete (duckpilot/skills). Seit 0.38.34 auch Pollens App-Bewegungen und Community-Tricks mit
    # Vorschauvideos – auf einem neuen PC war die Tricks-Seite sonst leer („fehlt hier nicht noch was?“)
    pakete: list[str] = field(default_factory=lambda: ["alltag", "app_moves", "community"])
    sim_physik: bool = False                   # Simulator mit echter Physik (MuJoCo + Pollens Policies)
    model_style: str = "original"              # 3D: "original" (Pollens CAD) oder "einfach"
    farbe: str = "cream"                       # Farbe der Microduck wie bei Pollen: cream, graphite, lavender, sky (0.38.19)
    head_signs: list[float] = field(default_factory=lambda: [1.0, 1.0, 1.0, 1.0])  # Kalibrierung echter Kopf
    # [claude]
    api_key: str | None = None
    model: str = "claude-sonnet-5-5"
    duck_name: str = "Quacki"
    kopf_name: str = "Knowlin"                 # Name des Kopfes (Startseite, seit 0.38.9) – im Gespräch oder hier vergeben
    nutzer_name: str = ""                      # wie dich der Kopf anspricht; leer = „Mensch“ (bleibt auf dem PC)
    kopf_stimme_motor: str = "piper"           # Knowlins eigene Stimme (seit 0.38.10): "browser" | "piper" | "qwen"
    kopf_stimme_piper: str = "thorsten"        # Piper-Stimme des Kopfes (fehlt sie: Browser-Stimme, normal)
    kopf_stimme_qwen: str = ""                 # entworfene Stimme des Kopfes
    # [voice]
    stt: str = "browser"                       # "browser" | "whisper" | "aus"
    whisper_model: str = "small"
    whisper_device: str = "auto"
    wake_word: str = "ente"
    tts: bool = True
    # [stimme] – die Stimme der Ente (duckpilot/voice/tts.py)
    stimme_motor: str = "browser"              # "browser" | "piper" | "qwen"
    stimme_piper: str = "thorsten_emotional"
    stimme_qwen: str = ""                      # entworfene Entenstimme (Kennung)
    qwen_qualitaet: str = "schnell"            # "schnell" (0,6 Mrd.) | "hoch" (1,7 Mrd.)
    # Seit 0.38.40 („Oder es wird trotzdem nutzbar und darf halt langsamer sein“): immer mit der entworfenen
    # Stimme sprechen, auch wenn sie langsamer rechnet als sie spricht – der Text steht sofort da, der Ton folgt
    qwen_geduldig: bool = False
    entenhaft: float = 0.45                    # 0 = Menschenstimme … 1 = ganz Ente
    weitere_enten: int = 0                     # weitere Enten im einfachen Simulator (seit 0.36.3)
    klang_hoehe: float = 0.0                   # Klangsignatur (seit 0.36.1): Laute in Halbtönen höher/tiefer
    klang_farbe: float = 0.0                   # Klangsignatur: −1 dunkler … +1 heller
    entenlaute: str = "manchmal"               # "aus" | "selten" | "manchmal" | "oft"
    plaudern: bool = False                     # Gesprächsmodus: länger reden, Mikro bleibt kurz offen
    schnellbefehle: bool = True                # kurze eindeutige Befehle ohne Claude (spart Tokens)
    mcp: bool = False                          # andere Programme dürfen die Ente über MCP steuern (nur am PC)
    sprache: str = "de"                        # Oberfläche, Sprechen und Denken der Ente: "de" | "en" (seit 0.34)
    # [gehirn]
    gehirn: str = "claude"                     # "claude" | "lokal" (Ollama) | "anbieter" (anderes KI-Modell, seit 0.35)
    lokal_modell: str = ""
    lokal_adresse: str = "http://127.0.0.1:11434"
    anbieter: str = "openai"                    # anderes KI-Modell (seit 0.35): openai | gemini | mistral | openrouter | lmstudio | eigen
    anbieter_modell: str = ""
    anbieter_adresse: str = ""                  # nur für „eigen“ (LM Studio seit 0.38.41 unter „Lokales Modell“)
    # Lokales Modell (seit 0.38.41, Alex: „macht keinen Sinn, dass LM Studio bei andere Modelle steht“): Ollama oder
    # LM Studio – beides läuft auf diesem PC; LM Studio spricht dieselbe Schnittstelle wie die anderen Anbieter
    lokal_programm: str = "ollama"              # "ollama" | "lmstudio"
    lmstudio_modell: str = ""
    lmstudio_adresse: str = ""
    # [engine]
    idle_life: bool = True
    obstacle_guard: bool = True
    ausweichen: bool = True                    # Hindernissen ausweichen und sie umlaufen (aus = nur bremsen)
    auto_recover: bool = True                  # nach einem Sturz selbst aufstehen (nach dem Stopp-Fenster)
    stopp_fenster_s: float = 3.0               # so lange hört sie nach einem Sturz zu („Stopp“ hält sie liegen), 2–10 s
    notaus_sperre_s: float = 120.0             # nach dem Not-Aus nichts von selbst – Standard 120 s, wählbar 15 s … 10 min
    notaus_danach: str = "weiter"              # danach: „weiter“ wie vorher oder „still“, bis du sie ansprichst
    kollision_protest: bool = True             # Kollisionsmodus: beschwert sich ab und zu (Quak, Geste, Satz)
    reachy_begruessung: bool = True            # Reachy Mini grüßt beim Aufwecken (Geste und kurzer Satz, seit 0.38.13)
    eigenstaendig: str = "ab_und_zu"           # ohne Befehle selbst etwas tun, passend zum Charakter: aus | ab_und_zu | oft
    radio_adressen: list[str] = field(default_factory=list)   # zuletzt genutzte Webradios (Mitwippen), höchstens 5
    updates_suchen: bool = True                # seit 0.38.32: einmal am Tag bei GitHub nach einer neuen Version sehen
    kopf_stabil: bool = False                  # Kopf-Stabilisator: Kopf bleibt beim Laufen ruhig wie beim Huhn
    # [personality] – Punkt im X/Y-Regler
    energie: float = 0.55                      # X: ruhig 0 … 1 lebhaft
    humor: float = 0.25                        # Y: ernst 0 … 1 albern (ab 0,5 Goofy-Modus)
    emotions: bool = True                      # Gefühle zeigen (seit 0.38.10 Teil des Grundcharakters, gilt für alle)
    grund_energie: float = 0.35                # Grundcharakter bei Knowlin (seit 0.38.10): anfangs ruhig …
    grund_humor: float = 0.1                   # … und seriös; gilt nur für Knowlin – Verkörperungen haben ihren eigenen
    eigenschaften: list[str] | None = None     # Eigenschaften der Gestalt (None = Vorgabe der Gestalt)

    @property
    def goofy(self) -> bool:
        return self.humor >= 0.5
    # [memory]
    memory: bool = True
    memory_path: str | None = None            # leer = lokaler App-Datenordner (nicht OneDrive)
    # [server]
    host: str = "127.0.0.1"
    port: int = 8765
    open_browser: bool = True
    app_mode: bool = False                     # eigenes Programmfenster
    hintergrund: bool = False                  # mit Windows gestartet, ohne Fenster (Handy-Fernbedienung)
    key_source: str | None = None              # tresor | umgebung | datei | toml

    def public(self) -> dict[str, Any]:
        """Was der Browser wissen darf – ohne Schlüssel."""
        return {
            "backend": self.backend,
            "modul": self.modul,
            "koerper_optionen": dict(self.koerper_optionen),
            "reachy_adresse": self.reachy_adresse,
            "model": self.model,
            "duck_name": self.duck_name,
            "kopf_name": self.kopf_name,
            "nutzer_name": self.nutzer_name,
            "kopf_stimme_motor": self.kopf_stimme_motor,
            "kopf_stimme_piper": self.kopf_stimme_piper,
            "kopf_stimme_qwen": self.kopf_stimme_qwen,
            "stt": self.stt,
            "wake_word": self.wake_word,
            "tts": self.tts,
            "stimme_motor": self.stimme_motor,
            "entenhaft": self.entenhaft,
            "entenlaute": self.entenlaute,
            "klang_hoehe": self.klang_hoehe,
            "weitere_enten": self.weitere_enten,
            "klang_farbe": self.klang_farbe,
            "plaudern": self.plaudern,
            "qwen_geduldig": self.qwen_geduldig,
            "schnellbefehle": self.schnellbefehle,
            "gehirn": self.gehirn,
            "lokal_modell": self.lokal_modell,
            "anbieter": self.anbieter,
            "anbieter_modell": self.anbieter_modell,
            "lokal_programm": self.lokal_programm,
            "lmstudio_modell": self.lmstudio_modell,
            "lmstudio_adresse": self.lmstudio_adresse,
            "sprache": self.sprache,
            "goofy": self.goofy,
            "humor": self.humor,
            "energie": self.energie,
            "emotions": self.emotions,
            "grund_energie": self.grund_energie,
            "grund_humor": self.grund_humor,      # die Gestalt-Eigenschaften gehen als „gestalt“ mit (Init-Nachricht)
            "model_style": self.model_style,
            "farbe": self.farbe,
            "sim_physik": self.sim_physik,
            "pakete": list(self.pakete),
            "auto_recover": self.auto_recover,
            "stopp_fenster_s": self.stopp_fenster_s,
            "notaus_sperre_s": self.notaus_sperre_s,
            "notaus_danach": self.notaus_danach,
            "kollision_protest": self.kollision_protest,
            "reachy_begruessung": self.reachy_begruessung,
            "eigenstaendig": self.eigenstaendig,
            "radio_adressen": list(self.radio_adressen),
            "updates_suchen": self.updates_suchen,
        }


def _read_dotenv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def load(path: str | os.PathLike | None = None, use_user_settings: bool = True, **overrides: Any) -> Config:
    cfg = Config()
    toml_path = Path(path) if path else PROJECT_DIR / "duckpilot.toml"
    if toml_path.exists():
        data = tomllib.loads(toml_path.read_text(encoding="utf-8"))
        flat: dict[str, Any] = {}
        for section in ("backend", "claude", "voice", "stimme", "gehirn", "engine", "personality", "server"):
            flat.update(data.get(section, {}))
        mem = data.get("memory", {})
        if "enabled" in mem:
            flat["memory"] = bool(mem["enabled"])
        if mem.get("path"):
            flat["memory_path"] = str(mem["path"])
        if "type" in flat:  # [backend] type = "sim"
            flat["backend"] = flat.pop("type")
        for key, value in flat.items():
            if hasattr(cfg, key):
                setattr(cfg, key, value)
    if os.environ.get("DUCKPILOT_MODEL"):
        cfg.model = os.environ["DUCKPILOT_MODEL"]
    if use_user_settings:
        from .settings import load_user_settings

        for key, value in load_user_settings().items():
            setattr(cfg, key, value)
    dotenv = _read_dotenv(PROJECT_DIR / ".env")
    vault = None
    if use_user_settings:
        from .settings import get_vault_key

        vault = get_vault_key()
    if cfg.api_key:
        cfg.key_source = "toml"
    elif vault:
        cfg.api_key, cfg.key_source = vault, "tresor"
    elif os.environ.get("ANTHROPIC_API_KEY"):
        cfg.api_key, cfg.key_source = os.environ["ANTHROPIC_API_KEY"], "umgebung"
    elif dotenv.get("ANTHROPIC_API_KEY"):
        cfg.api_key, cfg.key_source = dotenv["ANTHROPIC_API_KEY"], "datei"
    for key, value in overrides.items():
        if value is not None and hasattr(cfg, key):
            setattr(cfg, key, value)
    return cfg
