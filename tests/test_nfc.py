"""NFC-Tags: Tag → Satz, Berührung führt den Satz wie einen Befehl aus."""

import time

import pytest
from fastapi.testclient import TestClient

from duckpilot import settings as S
from duckpilot.config import load
from duckpilot.nfc import TagStore, normalize_uid
from duckpilot.server.app import Runtime, create_app

H = {"Origin": "http://127.0.0.1:8765"}


def test_uid_is_normalized_and_validated():
    assert normalize_uid("04:a2:3b:1c") == "04A23B1C"
    assert normalize_uid("TEST-ABC123") == "TEST-ABC123"
    assert normalize_uid("") is None and normalize_uid("x") is None and normalize_uid("../etc") is None


def test_store_learns_unknown_tags_and_keeps_assignments(tmp_path):
    st = TagStore(tmp_path / "t.json")
    r = st.touched("04:A2:3B:1C")
    assert r["ok"] and r["neu"] and r["satz"] == "" and r["tag"]["name"]
    st.put("04A23B1C", "Ladeplatz", "setz dich")
    again = TagStore(tmp_path / "t.json").touched("04a23b1c")
    assert not again["neu"] and again["satz"] == "setz dich" and again["tag"]["name"] == "Ladeplatz"
    probe = st.put("neu", "Probe", "tanz")
    assert probe["tag"]["uid"].startswith("TEST-")
    assert st.remove("04A23B1C") and not st.remove("04A23B1C")


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DUCKPILOT_SETTINGS", str(tmp_path / "s.json"))
    monkeypatch.setattr(S, "_keyring", lambda: None)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    rt = Runtime(load(memory_path=str(tmp_path / "m.json")))
    with TestClient(create_app(rt), base_url="http://127.0.0.1:8765") as c:
        c.runtime = rt
        yield c


def test_touching_a_tag_runs_its_sentence(client, monkeypatch):
    said = []

    async def chat(text, via="text"):
        said.append((text, via))
    monkeypatch.setattr(client.runtime, "chat", chat)
    r = client.post("/api/nfc/tag", json={"uid": "04A23B1C", "name": "Ladeplatz", "satz": "setz dich"}, headers=H).json()
    assert r["ok"]
    assert client.get("/api/nfc").json()["tags"][0]["satz"] == "setz dich"
    r = client.post("/api/nfc/beruehrt", json={"uid": "04:A2:3B:1C"}, headers=H).json()
    assert r["ok"] and not r["neu"]
    for _ in range(40):                       # läuft im Hintergrund wie ein getippter Befehl
        if said:
            break
        time.sleep(0.05)
    assert said == [("setz dich", "nfc")]


def test_unknown_tag_is_remembered_without_doing_anything(client):
    r = client.post("/api/nfc/beruehrt", json={"uid": "AABBCCDD"}, headers=H).json()
    assert r["ok"] and r["neu"] and r["satz"] == ""
    assert client.post("/api/nfc/beruehrt", json={"uid": "<script>"}, headers=H).status_code == 400
    assert client.delete("/api/nfc/tag/AABBCCDD", headers=H).json()["ok"]
