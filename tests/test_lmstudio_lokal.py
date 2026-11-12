"""LM Studio unter „Lokales Modell“ (seit 0.38.41, Alex: „macht keinen Sinn, dass LM Studio bei andere Modelle steht“)."""

from types import SimpleNamespace

from duckpilot import settings as S
from duckpilot.server.runtime import gehirn_fuer_agent


def test_altes_lmstudio_zieht_unter_lokal_um():
    alt = {"gehirn": "anbieter", "anbieter": "lmstudio", "anbieter_modell": "qwen3-8b",
           "anbieter_adresse": "http://127.0.0.1:1234/v1"}
    neu = S.lmstudio_umziehen(alt)
    assert neu["gehirn"] == "lokal" and neu["lokal_programm"] == "lmstudio"
    assert neu["lmstudio_modell"] == "qwen3-8b" and neu["lmstudio_adresse"] == "http://127.0.0.1:1234/v1"
    assert neu["anbieter"] == "openai" and neu["anbieter_modell"] == ""
    cloud = {"gehirn": "anbieter", "anbieter": "mistral", "anbieter_modell": "mistral-small"}
    assert S.lmstudio_umziehen(cloud) == cloud


def test_agent_bekommt_lmstudio_als_anbieter_ohne_schluessel():
    cfg = SimpleNamespace(gehirn="lokal", lokal_programm="lmstudio", lmstudio_modell="gemma-3", lmstudio_adresse="",
                          anbieter="openai", anbieter_modell="gpt-x", anbieter_adresse="")
    g = gehirn_fuer_agent(cfg)
    assert g == {"gehirn": "anbieter", "anbieter": "lmstudio", "anbieter_modell": "gemma-3", "anbieter_adresse": "",
                 "anbieter_schluessel": None}
    cfg.lokal_programm = "ollama"
    assert gehirn_fuer_agent(cfg)["gehirn"] == "lokal"


def test_neue_felder_sind_einstellbar():
    assert S.validate({"lokal_programm": "lmstudio", "lmstudio_modell": "qwen3-8b",
                       "lmstudio_adresse": "http://127.0.0.1:1234/v1"})["lokal_programm"] == "lmstudio"
