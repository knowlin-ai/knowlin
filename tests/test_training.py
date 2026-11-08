"""Reinforcement Learning 0.16: Kosten, Start von Pollens Stand oder eigenem Lauf, Lernkurven, Stillstand,
Export des Zwischenstands, Varianten."""
from __future__ import annotations

import asyncio
import io
import tarfile

import pytest

from duckpilot import training as T

TOKEN = "hf_" + "x" * 30


def _log(start: int, end: int, total: int, reward, s_it: float = 2.0) -> list[str]:
    """Ein Protokoll im Format von rsl_rl 5 (ein Block pro Iteration, mit ANSI-Farben wie im Job)."""
    out = []
    for it in range(start, end):
        out.append("#" * 80 + "\n" + f"\x1b[1m Learning iteration {it}/{total} \x1b[0m".center(80))
        out += ["          Mean action std: 0.80", f"              Mean reward: {reward(it):.4f}",
                f"      Mean episode length: {100 + it * 0.1:.2f}",
                f"Episode_Reward/upright: {0.1 + it * 0.0001:.4f}", f"Episode_Reward/torques: {-0.05:.4f}",
                f"Episode_Termination/fell: {max(0.0, 0.5 - it * 0.0005):.4f}",
                f"           Iteration time: {s_it:.2f}s", "             Time elapsed: 00:10:00",
                f"                      ETA: 00:{min(59, (total - it) // 60):02d}:00"]
    return out


def test_parse_log_and_summary():
    lines = _log(0, 50, 1000, lambda i: i * 0.1)
    pts = T.parse_log(["vorher Rauschen"] + lines)
    assert len(pts) == 50 and pts[10]["it"] == 10 and pts[10]["von"] == 1000
    assert pts[10]["belohnung"] == pytest.approx(1.0) and pts[10]["s_it"] == 2.0
    assert pts[10]["terme"]["upright"] == pytest.approx(0.101) and "fell" in pts[10]["abbruch"]
    s = T.summarize(pts)
    assert s["iteration"] == 49 and 0 < s["fortschritt"] < 0.1 and s["trend"] > 0.1 and not s["stillstand"]
    assert s["s_it"] == 2.0 and s["rest_min"] is not None
    assert {t["term"] for t in s["terme"]} == {"upright", "torques"}
    # Mehrere Zeilen in einem Eintrag (so liefert der Hub die Logs teils) werden genauso gelesen
    assert len(T.parse_log(["\n".join(lines)])) == 50
    # flache Kurve ab einem Drittel und genug Iterationen → Stillstand
    flat = T.parse_log(_log(0, 600, 1000, lambda i: min(i, 50) * 0.1))
    assert T.summarize(flat)["stillstand"] is True
    assert T.summarize([]) == {"punkte": 0}
    assert "faehigkeit" not in s                       # ohne time_out im Protokoll keine Fähigkeit


def test_skill_from_time_out_share():
    lines = []
    for it in range(0, 100):
        lines += [f" Learning iteration {it}/100 ", f"Mean reward: {it * 0.1:.3f}",
                  f"Episode_Termination/time_out: {it / 100:.3f}", f"Episode_Termination/fell_over: {1 - it / 100:.3f}"]
    s = T.summarize(T.parse_log(lines))
    assert s["faehigkeit_start"] == 0.0 and 0.9 <= s["faehigkeit"] <= 1.0 and s["faehigkeit_max"] == pytest.approx(0.99)
    assert T.skill_of({"abbruch": {"time_out": 0.0, "fell": 0.0}}) is None


def test_plan_start_cost_and_limits():
    p = T.check_plan("Mjlab-Roulade-Flat-MicroDuck", 1000, None, "l4x1", "pollen")
    assert p["start_von"] == "pollen" and p["bei_stillstand"] == "weiter" and 1 <= p["max_stunden"] <= 12
    e = T.estimate(p)
    assert e["usd_h"] == T.GPUS["l4x1"]["usd_h"] and e["usd"] > 0 and e["usd_max"] >= e["usd"] and not e["gemessen"]
    e2 = T.estimate(p, {"l4x1": 0.5})
    assert e2["gemessen"] and e2["usd"] < e["usd"]
    assert T.check_plan("Mjlab-Spin-Flat-MicroDuck", 500, None, "l4x1", None, 3)["max_stunden"] == 3
    with pytest.raises(ValueError):                 # Pirouette hat keinen Stand von Pollen
        T.check_plan("Mjlab-Spin-Flat-MicroDuck", 500, None, "l4x1", "pollen")
    for bad in (dict(start_von="lauf:../x"), dict(max_stunden=13), dict(max_stunden="viel"), dict(bei_stillstand="egal")):
        with pytest.raises(ValueError):
            T.check_plan("Mjlab-Roulade-Flat-MicroDuck", 500, **bad)
    for key in ("agent.load_checkpoint", "agent.max_iterations", "agent.logger"):
        with pytest.raises(ValueError):
            T.check_overrides({key: 1})
    # Familien und Pollens Stände: gleiche Aufgabe = weitertrainieren, verwandte = Warmstart
    assert T.family("Mjlab-Velocity-Rough-Backlash-MicroDuck") == T.family("Mjlab-Velocity-Flat-MicroDuck")
    assert T.pollen_start("Mjlab-Roulade-Flat-MicroDuck") == ("microduck_roulade/blrqbcit_750", False)
    assert T.pollen_start("Mjlab-StandUp-Rough-MicroDuck")[1] is True
    assert T.pollen_start("Mjlab-Spin-Flat-MicroDuck") is None
    assert T.latest_checkpoint(["a/b/model_50.pt", "a/b/model_1000.pt", "a/b/model_999.pt", "x.onnx"]) == "a/b/model_1000.pt"
    assert T.latest_checkpoint(["../../model_5.pt", "README.md"]) is None
    args = T.train_args(p, False, "hf://pollen-robotics/microduck-training/bundles/x")
    assert args[-2:] == ["--init-checkpoint", "hf://pollen-robotics/microduck-training/bundles/x"]


def _tarball() -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        info = tarfile.TarInfo("microduck_rl-main/pyproject.toml")
        info.size = 9
        tar.addfile(info, io.BytesIO(b"[project]"))
    return buf.getvalue()


class FakeHub:
    def __init__(self):
        self.jobs: list[dict] = []
        self.cancelled: list[str] = []
        self.stage: dict[str, str] = {}
        self.files: dict[str, list[str]] = {}
        self.logs: list[str] = []

    def whoami(self):
        return {"name": "alex", "orgs": []}

    def create_repo(self, *a, **k):
        pass

    def upload_file(self, **k):
        pass

    def run_job(self, **k):
        jid = f"job{len(self.jobs) + 1}"
        self.jobs.append({"id": jid, **k})
        self.stage[jid] = "RUNNING"
        return type("Job", (), {"id": jid, "url": None})()

    def inspect_job(self, job_id, namespace):
        return type("J", (), {"status": type("S", (), {"stage": self.stage[job_id], "message": None})()})()

    def list_repo_files(self, repo, repo_type):
        return self.files.get(repo, [])

    def fetch_job_logs(self, job_id, namespace, follow, tail):
        return iter(self.logs[-tail:])

    def cancel_job(self, job_id, namespace):
        self.cancelled.append(job_id)
        self.stage[job_id] = "CANCELED"


def test_submit_from_pollen_and_own_run_then_stall_and_export(tmp_path, monkeypatch):
    import sys
    import types

    monkeypatch.setitem(sys.modules, "huggingface_hub", types.ModuleType("huggingface_hub"))   # ohne Volume
    hub = FakeHub()
    tr = T.Trainer(tmp_path, api_factory=lambda token: hub, fetch=lambda url: _tarball())

    # 1) Auf Pollens Stand: --init-checkpoint auf das Bündel, keine Warmstart-Variable, Zeitlimit aus dem Plan
    plan = T.check_plan("Mjlab-Roulade-Flat-MicroDuck", 1000, {"env.rewards.upright.weight": 2}, "l4x1", "pollen",
                        2, "abbrechen")
    run = tr.submit(plan, TOKEN)
    job = hub.jobs[-1]
    assert job["timeout"] == "2h" and "MICRODUCK_WARM_START" not in job["env"]
    assert "--init-checkpoint hf://pollen-robotics/microduck-training/bundles/microduck_roulade/blrqbcit_750" in job["env"]["TRAIN_ARGS"]
    assert run["start_von"].startswith("Pollens Stand") and run["schaetzung"]["usd"] > 0

    # 2) Lernkurve steht → bei „abbrechen“ wird der Job beendet und der letzte Zwischenstand exportiert
    hub.logs = _log(0, 600, 1000, lambda i: min(i, 40) * 0.1)
    hub.files[run["ckpt_repo"]] = ["logs/x/model_500.pt", "logs/x/model_550.pt"]
    runs = tr.refresh(TOKEN)
    r = next(x for x in runs if x["id"] == run["id"])
    assert hub.cancelled == [run["job"]] and r["status"] == "exportiert" and r["export_von"] == "logs/x/model_550.pt"
    exp = hub.jobs[-1]
    assert exp["flavor"] == T.EXPORT_FLAVOR and exp["env"]["CKPT_PATH"] == "logs/x/model_550.pt"
    assert exp["command"][-1] == T.BOOTSTRAP_EXPORT and exp["env"]["SRC_TARBALL"] == run["src_tarball"]
    assert r["kurve"]["stillstand"] and tr.measured() == {"l4x1": 2.0}
    curve = tr.curve(TOKEN, run["id"])
    assert len(curve["punkte"]) > 100 and curve["zusammenfassung"]["iteration"] == 599
    assert tr.refresh(TOKEN) and len(hub.cancelled) == 1 and len(hub.jobs) == 2   # kein zweiter Abbruch/Export
    hub.stage[r["export_job"]] = "COMPLETED"
    hub.files[run["ckpt_repo"]].append("exported/policy.onnx")
    assert next(x for x in tr.refresh(TOKEN) if x["id"] == run["id"])["status"] == "fertig"

    # 3) Eigenen Lauf auf uneben weiter: gleiche Familie → Warmstart vom neuesten Zwischenstand
    plan2 = T.check_plan("Mjlab-Roulade-Flat-MicroDuck", 800, None, "l4x1", f"lauf:{run['id']}")
    run2 = tr.submit(plan2, TOKEN)
    assert f"--init-checkpoint hf://{run['ckpt_repo']}/logs/x/model_550.pt" in hub.jobs[-1]["env"]["TRAIN_ARGS"]
    assert run2["id"] != run["id"] and "MICRODUCK_WARM_START" not in hub.jobs[-1]["env"]
    with pytest.raises(T.TrainingError):          # andere Familie geht nicht
        tr.submit(T.check_plan("Mjlab-Spin-Flat-MicroDuck", 500, None, "l4x1", f"lauf:{run['id']}"), TOKEN)

    # 4) Manuell abgebrochener Lauf: Zwischenstand exportieren
    hub.stage[run2["job"]] = "CANCELED"
    hub.files[run2["ckpt_repo"]] = ["logs/y/model_100.pt"]
    tr.refresh(TOKEN, curves=False)
    r2 = tr.export(TOKEN, run2["id"])
    assert r2["status"] == "exportiert" and hub.jobs[-1]["env"]["CKPT_PATH"] == "logs/y/model_100.pt"
    with pytest.raises(T.TrainingError):          # fertige Läufe haben ihr Ergebnis schon
        tr.export(TOKEN, run["id"])
    with pytest.raises(T.TrainingError):          # läuft schon
        tr.export(TOKEN, run2["id"])
    assert tr.cancel(TOKEN, run2["id"])["status"] == "abgebrochen" and hub.cancelled[-1] == r2["export_job"]

    # 5) Training lief durch, aber ohne exportierte Policy → fehlgeschlagen, Export möglich
    run3 = tr.submit(T.check_plan("Mjlab-Spin-Flat-MicroDuck", 500), TOKEN)
    hub.stage[run3["job"]] = "COMPLETED"
    r3 = next(x for x in tr.refresh(TOKEN, curves=False) if x["id"] == run3["id"])
    assert r3["status"] == "fehlgeschlagen" and "Zwischenstand exportieren" in r3["fehler"]

    # 6) Obergrenze kürzer als die Schätzung → abgelehnt; mehr als 12 h geschätzt → abgelehnt
    with pytest.raises(ValueError, match="Obergrenze"):
        T.check_plan("Mjlab-Velocity-Flat-MicroDuck", 4000, None, "l4x1", None, 1)
    with pytest.raises(ValueError, match="12 h"):
        T.check_plan("Mjlab-Velocity-Rough-MicroDuck", 20000)
    assert T.check_plan("Mjlab-Velocity-Rough-MicroDuck", 20000, measured={"l4x1": 1.0})["max_stunden"] <= 12


def test_variants_estimate_endpoint_and_review_tool(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from duckpilot import settings as S
    from duckpilot.config import load
    from duckpilot.server.app import Runtime, _plans_from, create_app

    plans = _plans_from({"aufgabe": "Mjlab-Spin-Flat-MicroDuck", "iterationen": 500,
                         "anpassungen": {"env.rewards.upright.weight": 1},
                         "varianten": [{"env.rewards.upright.weight": 2}, {"env.rewards.upright.weight": 3}]}, T.check_plan)
    assert [p["anpassungen"]["env.rewards.upright.weight"] for p in plans] == ["1", "2", "3"]
    with pytest.raises(ValueError):
        _plans_from({"aufgabe": "Mjlab-Spin-Flat-MicroDuck", "varianten": [{}, {}, {}]}, T.check_plan)
    with pytest.raises(ValueError):
        _plans_from({"aufgabe": "Mjlab-Spin-Flat-MicroDuck", "varianten": ["x"]}, T.check_plan)

    monkeypatch.setenv("DUCKPILOT_SETTINGS", str(tmp_path / "settings.json"))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(S, "_keyring", lambda: None)
    rt = Runtime(load(memory_path=str(tmp_path / "mem.json")))
    with TestClient(create_app(rt), base_url="http://127.0.0.1:8765") as c:
        st = c.get("/api/training").json()
        assert st["pollen"]["Mjlab-Roulade-Flat-MicroDuck"]["buendel"].startswith("microduck_roulade")
        assert st["preise"]["l4x1"] == 0.8 and st["familien"]["Mjlab-StandUp-Rough-MicroDuck"] == "Mjlab-StandUp-MicroDuck"
        one = c.post("/api/training/schaetzen", json={"aufgabe": "Mjlab-Spin-Flat-MicroDuck", "iterationen": 1000}).json()
        two = c.post("/api/training/schaetzen", json={"aufgabe": "Mjlab-Spin-Flat-MicroDuck", "iterationen": 1000,
                                                      "varianten": [{"env.rewards.upright.weight": 2}]}).json()
        assert one["ok"] and two["laeufe"] == 2 and two["usd"] == pytest.approx(one["usd"] * 2, abs=0.02)
        bad = c.post("/api/training/schaetzen", json={"aufgabe": "Mjlab-Spin-Flat-MicroDuck", "max_stunden": 99})
        assert bad.status_code == 400
        assert c.get("/api/training/unbekannt/kurve").status_code == 404
        assert c.post("/api/training/x/exportieren").status_code == 400          # ohne Token

        # Claude schlägt Varianten vor und liest Lernkurven – starten kann es nicht
        names = {t["name"] for t in rt.runner.tools()}
        assert {"training_vorschlagen", "training_auswerten"} <= names and not any("start" in n for n in names if "training" in n)

        async def propose():
            return await rt.runner.run("training_vorschlagen", {
                "aufgabe": "Mjlab-Roulade-Flat-MicroDuck", "begruendung": "sauberer abrollen", "start_von": "pollen",
                "anpassungen": {"env.rewards.upright.weight": 1.5}, "varianten": [{"env.rewards.upright.weight": 3}],
                "bei_stillstand": "abbrechen"})
        out = asyncio.run(propose())
        v = c.get("/api/training").json()["vorschlag"]
        assert out["ok"] and v["start_von"] == "pollen" and len(v["varianten"]) == 1 and v["bei_stillstand"] == "abbrechen"

        async def review():
            return await rt.runner.run("training_auswerten", {})
        res = asyncio.run(review())
        assert isinstance(res, dict)


def test_parallel_refresh_does_not_lose_a_started_run(tmp_path):
    import threading
    import time as _t

    hub = FakeHub()
    slow = hub.inspect_job

    def inspect(job_id, namespace):      # langsamer Hub: die Aktualisierung hält ihren Stand lange fest
        _t.sleep(0.05)
        return slow(job_id, namespace)

    hub.inspect_job = inspect
    tr = T.Trainer(tmp_path, api_factory=lambda token: hub, fetch=lambda url: _tarball())
    first = tr.submit(T.check_plan("Mjlab-Spin-Flat-MicroDuck", 500), TOKEN)
    stop = threading.Event()

    def refresher():
        while not stop.is_set():
            tr.refresh(TOKEN, curves=False)

    th = threading.Thread(target=refresher)
    th.start()
    started = [tr.submit(T.check_plan("Mjlab-Spin-Flat-MicroDuck", 500), TOKEN) for _ in range(5)]
    stop.set()
    th.join()
    runs = {r["id"]: r for r in tr.runs()}
    assert all(runs[s["id"]]["job"] == s["job"] for s in [first, *started])
