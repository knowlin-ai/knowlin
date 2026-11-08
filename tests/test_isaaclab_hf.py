"""Policies direkt von Hugging Face laden (0.38.30, Frage „kann ich die Policies nicht OTA laden?“)."""

import shutil
from types import SimpleNamespace

import pytest

pytest.importorskip("mujoco")
pytest.importorskip("onnxruntime")
pytest.importorskip("onnx")

from fastapi.testclient import TestClient  # noqa: E402
from onnx_fixtures import linear_policy  # noqa: E402

from duckpilot.physics import isaaclab as IL  # noqa: E402
from duckpilot.physics import isaaclab_hf as HF  # noqa: E402


@pytest.mark.parametrize("text, erwartet", [
    ("RemiFabre/microduck-rough-walk-g", ("RemiFabre/microduck-rough-walk-g", None, None)),
    ("besitzer/repo/exported/policy.onnx", ("besitzer/repo", "exported/policy.onnx", None)),
    ("https://huggingface.co/besitzer/repo", ("besitzer/repo", None, None)),
    ("https://huggingface.co/besitzer/repo/blob/main/walk.onnx", ("besitzer/repo", "walk.onnx", "main")),
    ("https://huggingface.co/besitzer/repo/resolve/abc123/a/b.onnx?download=true", ("besitzer/repo", "a/b.onnx", "abc123")),
])
def test_adressen_werden_verstanden(text, erwartet):
    assert HF.adresse_lesen(text) == erwartet


@pytest.mark.parametrize("text", ["https://example.com/besitzer/repo", "http://huggingface.co/a/b", "besitzer",
                                  "besitzer/repo/../geheim.onnx", "besitzer/repo/datei.exe", "",
                                  "https://huggingface.co.evil.de/a/b"])
def test_fremde_und_kaputte_adressen_werden_abgelehnt(text):
    with pytest.raises(IL.ImportFehler):
        HF.adresse_lesen(text)


def _api(dateien, lizenz="apache-2.0"):
    sib = [SimpleNamespace(rfilename=p, size=int(mb * 1048576)) for p, mb in dateien]
    info = SimpleNamespace(siblings=sib, sha="f" * 40, card_data={"license": lizenz} if lizenz else None, tags=[])
    aufrufe = []

    class Api:
        def model_info(self, repo, **kw):
            aufrufe.append((repo, kw))
            return info

    return Api(), aufrufe


def _laden(quelle):
    geladen = []

    def herunterladen(repo, pfad, **kw):
        geladen.append((repo, pfad, kw))
        ziel = quelle.parent / "cache" / pfad
        ziel.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(quelle, ziel)
        return str(ziel)

    return herunterladen, geladen


def test_laedt_exportierte_policy_und_merkt_die_herkunft(tmp_path, monkeypatch):
    monkeypatch.delenv("DUCKPILOT_OFFLINE", raising=False)
    api, _ = _api([("README.md", 0), ("exported/policy.onnx", 0.1), ("exported/policy_alt.onnx", 0.1)])
    herunter, geladen = _laden(linear_policy(tmp_path / "q.onnx"))
    e = HF.laden(tmp_path / "root", "jemand/microduck-rough", "", api=api, herunterladen=herunter, mit_pruefstand=False)
    assert geladen[0][:2] == ("jemand/microduck-rough", "exported/policy.onnx")
    assert geladen[0][2]["revision"] == "f" * 40                       # genau der angesehene Stand
    assert e["name"] == "isaac_microduck_rough"
    assert e["download"] == {"repo": "jemand/microduck-rough", "pfad": "exported/policy.onnx", "stand": "f" * 40,
                             "lizenz": "apache-2.0", "url": "https://huggingface.co/jemand/microduck-rough"}
    assert IL.liste(tmp_path / "root")[0]["download"]["repo"] == "jemand/microduck-rough"


def test_mehrere_policies_ergeben_eine_auswahl_statt_zu_raten(tmp_path, monkeypatch):
    monkeypatch.delenv("DUCKPILOT_OFFLINE", raising=False)
    api, _ = _api([("walk.onnx", 0.1), ("run.onnx", 0.2)])
    herunter, geladen = _laden(linear_policy(tmp_path / "q.onnx"))
    with pytest.raises(HF.Auswahl) as fehler:
        HF.laden(tmp_path, "a/b", api=api, herunterladen=herunter, mit_pruefstand=False)
    assert [d["pfad"] for d in fehler.value.dateien] == ["walk.onnx", "run.onnx"] and not geladen
    e = HF.laden(tmp_path, "a/b", datei="run.onnx", api=api, herunterladen=herunter, mit_pruefstand=False)
    assert geladen[0][1] == "run.onnx" and e["name"] == "isaac_run"


def test_zu_gross_offline_und_ohne_onnx(tmp_path, monkeypatch):
    herunter, geladen = _laden(linear_policy(tmp_path / "q.onnx"))
    monkeypatch.delenv("DUCKPILOT_OFFLINE", raising=False)
    api, _ = _api([("policy.onnx", 80)])
    with pytest.raises(IL.ImportFehler, match="60 MB"):
        HF.laden(tmp_path, "a/b", api=api, herunterladen=herunter)
    api, _ = _api([("README.md", 0)])
    with pytest.raises(IL.ImportFehler, match="keine ONNX"):
        HF.laden(tmp_path, "a/b", api=api, herunterladen=herunter)
    with pytest.raises(IL.ImportFehler, match="nicht in diesem Repo"):
        HF.laden(tmp_path, "a/b/fehlt.onnx", api=_api([("policy.onnx", 1)])[0], herunterladen=herunter)
    monkeypatch.setenv("DUCKPILOT_OFFLINE", "1")
    with pytest.raises(IL.ImportFehler, match="offline"):
        HF.laden(tmp_path, "a/b", api=api, herunterladen=herunter)
    assert not geladen


def test_route_nur_am_pc_und_mit_auswahl(tmp_path, monkeypatch):
    from duckpilot import settings as S
    from duckpilot.config import load
    from duckpilot.remote import pc_only
    from duckpilot.server.app import Runtime, create_app

    assert pc_only("POST", "/api/isaaclab/hf")
    monkeypatch.setenv("DUCKPILOT_SETTINGS", str(tmp_path / "settings.json"))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("DUCKPILOT_OFFLINE", raising=False)
    monkeypatch.setattr(S, "_keyring", lambda: None)
    monkeypatch.setattr(IL, "pruefstand", lambda *a, **k: {"bestanden": True, "roboter_frei": True, "pruefungen": {}})
    api, _ = _api([("walk.onnx", 0.1), ("run.onnx", 0.1)], lizenz=None)
    herunter, _ = _laden(linear_policy(tmp_path / "q.onnx"))
    echt = HF.laden
    monkeypatch.setattr(HF, "laden", lambda *a, **k: echt(*a, api=api, herunterladen=herunter, **k))
    rt = Runtime(load(memory_path=str(tmp_path / "mem.json")))
    with TestClient(create_app(rt), base_url="http://127.0.0.1:8765") as c:
        h = {"origin": "http://127.0.0.1:8765"}
        r = c.post("/api/isaaclab/hf", json={"adresse": "https://example.com/x/y"}, headers=h)
        assert r.status_code == 400 and "huggingface.co" in r.json()["fehler"]
        r = c.post("/api/isaaclab/hf", json={"adresse": "a/b"}, headers=h)
        assert r.status_code == 409 and len(r.json()["auswahl"]) == 2
        r = c.post("/api/isaaclab/hf", json={"adresse": "a/b", "datei": "walk.onnx", "name": "lauf"}, headers=h)
        assert r.status_code == 200 and r.json()["neu"]["roboter_frei"] and r.json()["neu"]["download"]["lizenz"] is None


def test_vorschlaege_nur_repos_mit_onnx_meistgeladene_zuerst(monkeypatch):
    monkeypatch.delenv("DUCKPILOT_OFFLINE", raising=False)
    HF._cache.update(zeit=0.0, liste=None)

    def modell(repo, dateien, downloads, lizenz=None):
        return SimpleNamespace(id=repo, siblings=[SimpleNamespace(rfilename=d) for d in dateien], downloads=downloads,
                               likes=0, card_data={"license": lizenz} if lizenz else None, tags=[], last_modified=None)

    aufrufe = []

    class Api:
        def list_models(self, search, **kw):
            aufrufe.append((search, kw["expand"]))
            if search != "microduck":
                return [modell("a/doppelt", ["policy.onnx"], 5)]
            return [modell("a/doppelt", ["policy.onnx"], 5), modell("b/ohne-onnx", ["README.md"], 900),
                    modell("c/viele", ["x.onnx", "exported/policy.onnx"], 50, "apache-2.0")]

    liste = HF.suchen(api=Api())
    assert [e["repo"] for e in liste] == ["c/viele", "a/doppelt"]
    assert liste[0]["dateien"][0] == "exported/policy.onnx" and liste[0]["lizenz"] == "apache-2.0"
    assert "siblings" in aufrufe[0][1]
    n = len(aufrufe)
    assert HF.suchen(api=Api()) == liste and len(aufrufe) == n          # 10 min zwischengespeichert
    monkeypatch.setenv("DUCKPILOT_OFFLINE", "1")
    with pytest.raises(IL.ImportFehler, match="offline"):
        HF.suchen(api=Api(), neu=True)


def test_ohne_huggingface_hub_direkt_ueber_huggingface_co(tmp_path, monkeypatch):
    """Gemeldet nach 0.38.32 (Installer): „Hugging Face war nicht erreichbar“ – dort fehlt das Paket huggingface_hub."""
    import builtins
    import json as _json

    monkeypatch.delenv("DUCKPILOT_OFFLINE", raising=False)
    echt_import = builtins.__import__

    def ohne_hub(name, *a, **k):
        if name.startswith("huggingface_hub"):
            raise ImportError("kein huggingface_hub")
        return echt_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", ohne_hub)
    policy = linear_policy(tmp_path / "q.onnx").read_bytes()
    aufrufe = []

    def holen(url, token=None, limit=0):
        aufrufe.append((url, token))
        if url.startswith(f"{HF.HF}/api/models?"):
            return _json.dumps([{"id": "a/microduck-walk", "downloads": 7, "likes": 1,
                                 "siblings": [{"rfilename": "exported/policy.onnx"}], "cardData": {"license": "mit"}}]).encode()
        if url.startswith(f"{HF.HF}/api/models/a/microduck-walk"):
            return _json.dumps({"id": "a/microduck-walk", "sha": "e" * 40,
                                "siblings": [{"rfilename": "exported/policy.onnx", "size": len(policy)}]}).encode()
        if url == f"{HF.HF}/a/microduck-walk/resolve/{'e' * 40}/exported/policy.onnx":
            return policy
        raise HF.RepoNotFound(url)

    monkeypatch.setattr(HF, "_holen", holen)
    HF._cache.update(zeit=0.0, liste=None)
    assert isinstance(HF._hub()[0], HF.EigeneApi)
    liste = HF.suchen(neu=True)
    assert liste[0]["repo"] == "a/microduck-walk" and liste[0]["lizenz"] == "mit"
    assert all(u.startswith("https://huggingface.co/") for u, _ in aufrufe)
    e = HF.laden(tmp_path / "root", "a/microduck-walk", token="hf_geheim", mit_pruefstand=False)
    assert e["download"]["stand"] == "e" * 40 and e["download"]["lizenz"] is None
    assert ("hf_geheim" in {t for _, t in aufrufe})
    with pytest.raises(IL.ImportFehler, match="gibt es nicht"):
        HF.laden(tmp_path / "root", "a/gibts-nicht", mit_pruefstand=False)
