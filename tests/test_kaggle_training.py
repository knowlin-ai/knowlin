"""Kostenlos trainieren auf Kaggle: Zugangsdaten im Tresor, erzeugtes Skript, Kernel starten, Status,
Lernkurve, Ergebnis laden, Fehlermeldungen – alles ohne Netz (gefälschte Kaggle-API)."""
from __future__ import annotations

import base64
import json
import sys
import textwrap
import types

import pytest

from duckpilot import kaggle_training as K
from duckpilot import settings as S
from duckpilot import training as T

USER = "alex"
KEY = "0123456789abcdef0123456789abcdef"
ONNX = b"\x08\x07\x12\x07pytorch" + b"\x00" * 200


@pytest.fixture()
def vault(monkeypatch):
    store = {}

    class FakeKeyring:
        def get_password(self, s, u): return store.get((s, u))
        def set_password(self, s, u, p): store[(s, u)] = p
        def delete_password(self, s, u): store.pop((s, u), None)

    monkeypatch.setattr(S, "_keyring", lambda: FakeKeyring())
    return store


def _block(it: int, total: int, reward: float) -> list[str]:
    return ["#" * 80, f"\x1b[1m Learning iteration {it}/{total} \x1b[0m".center(80),
            f"              Mean reward: {reward:.4f}", f"      Mean episode length: {100 + it:.2f}",
            "Episode_Reward/upright: 0.1000", f"Episode_Termination/time_out: {min(1.0, it / 100):.3f}",
            f"Episode_Termination/fell: {max(0.0, 1 - it / 100):.3f}", "           Iteration time: 6.50s",
            "             Time elapsed: 00:10:00", "                      ETA: 01:00:00",
            "         Computation: 12345 steps/s (collection: 1.2s, learning 0.3s)"]


class FakeKaggle:
    """Kaggles öffentliche API im Speicher – mit den Pfaden und JSON-Feldern der echten (kagglesdk)."""

    def __init__(self):
        self.calls: list[dict] = []
        self.status: dict[str, dict] = {}
        self.logs: dict[str, list[str]] = {}
        self.outputs: dict[str, dict[str, bytes]] = {}
        self.final_log: dict[str, list[str]] = {}
        self.quota = {"quotaRefreshTime": "2026-11-01T00:00:00Z",
                      "gpuQuota": {"timeUsed": "18000s", "totalTimeAllowed": "108000s", "timeReserved": "0s"}}
        self.save_error = ""
        self.http_status: dict[str, int] = {}

    def __call__(self, method, url, headers=None, data=None, timeout=60, max_seconds=None, max_bytes=None):
        headers = headers or {}
        payload = json.loads(data) if data else None
        self.calls.append({"method": method, "url": url, "headers": headers, "payload": payload})
        if url.startswith("https://storage.example/"):
            assert "Authorization" not in headers            # signierte Adresse: keine Zugangsdaten mitschicken
            slug, name = url.removeprefix("https://storage.example/").rsplit("/", 1)
            return K.Antwort(200, self.outputs[slug][name], "application/octet-stream")
        auth = headers.get("Authorization", "")
        if auth != "Basic " + base64.b64encode(f"{USER}:{KEY}".encode()).decode():
            return K.Antwort(401, b'{"code": 401, "message": "Unauthenticated"}', "application/json")
        if url.startswith(f"{K.API}/kernels/logs/stream/"):
            slug = url.rsplit("/", 1)[1]
            body = "".join(f"data: {json.dumps({'stream_name': 'stdout', 'time': 1.0, 'data': ln + chr(10)})}\n\n"
                           for ln in self.logs.get(slug, []))
            return K.Antwort(200, body.encode(), "text/event-stream")
        method_name = url.rsplit("/", 1)[1]
        assert url == f"{K.API}/{K.SERVICE}/{method_name}" and method == "POST"
        if method_name in self.http_status:
            return K.Antwort(self.http_status[method_name], b'{"message": "nope"}', "application/json")
        if method_name == "GetAcceleratorQuotaStatistics":
            return self._json(self.quota)
        if method_name == "SaveKernel":
            if self.save_error:
                return self._json({"error": self.save_error})
            slug = payload["slug"].split("/", 1)[1]
            self.status[slug] = {"status": "QUEUED"}
            return self._json({"ref": f"/code/{payload['slug']}", "url": f"https://www.kaggle.com/code/{payload['slug']}",
                               "versionNumber": 1, "kernelId": 4711})
        slug = payload.get("kernelSlug")
        if method_name == "GetKernelSessionStatus":
            return self._json(self.status[slug])
        if method_name == "ListKernelSessionOutput":
            files = [{"fileName": n, "url": f"https://storage.example/{slug}/{n}"} for n in self.outputs.get(slug, {})]
            log = json.dumps([{"stream_name": "stdout", "time": 1.0, "data": ln + "\n"}
                              for ln in self.final_log.get(slug, [])])
            return self._json({"files": files, "log": log})
        raise AssertionError(url)

    @staticmethod
    def _json(obj) -> K.Antwort:
        return K.Antwort(200, json.dumps(obj).encode(), "application/json")

    def saves(self) -> list[dict]:
        return [c["payload"] for c in self.calls if c["url"].endswith("/SaveKernel")]


def _trainer(tmp_path, fake):
    return K.KaggleTrainer(tmp_path, http=fake, credentials=lambda: (USER, KEY))


# ── Zugangsdaten ────────────────────────────────────────────────────────────
def test_credentials_only_in_vault(vault, tmp_path):
    assert K.get_credentials() is None
    for user, key in (("ma rten", KEY), (USER, "zu-kurz"), ("", KEY)):
        with pytest.raises(ValueError):
            K.set_credentials(user, key)
    K.set_credentials(f" {USER} ", f"{KEY}\n")
    assert K.get_credentials() == (USER, KEY)
    assert K.credentials_hint(K.get_credentials()) == f"{USER} · …cdef" and KEY not in K.credentials_hint((USER, KEY))
    assert {u for (_, u) in vault} == {K.KEYRING_USER_NAME, K.KEYRING_USER_KEY}
    assert K.parse_kaggle_json(json.dumps({"username": USER, "key": KEY})) == (USER, KEY)
    with pytest.raises(ValueError):
        K.parse_kaggle_json("kein json")
    K.set_credentials(USER, "KGAT_" + "a" * 32)                 # neue API-Tokens gehen auch (als Bearer)
    assert K.KaggleApi(USER, "KGAT_" + "a" * 32)._auth().startswith("Bearer ")
    K.delete_credentials()
    assert K.get_credentials() is None and K.credentials_hint(None) is None
    monkey = K.KaggleTrainer(tmp_path, http=FakeKaggle())          # ohne Zugangsdaten → deutsche Meldung
    with pytest.raises(K.KaggleError, match="Zugangsdaten"):
        monkey.account()
    assert not list(tmp_path.rglob("*"))                            # nichts auf die Platte geschrieben


def test_account_quota_and_bad_key(tmp_path):
    fake = FakeKaggle()
    acc = _trainer(tmp_path, fake).account()
    assert acc["name"] == USER and acc["kontingent"] == {"gpu_h_gesamt": 30.0, "gpu_h_genutzt": 5.0,
                                                         "gpu_h_frei": 25.0, "erneuert": "2026-11-01T00:00:00Z"}
    bad = K.KaggleTrainer(tmp_path, http=fake, credentials=lambda: (USER, "f" * 32))
    with pytest.raises(K.KaggleError, match="lehnt die Zugangsdaten ab") as exc:
        bad.account()
    assert exc.value.status == 401
    fake.http_status["GetAcceleratorQuotaStatistics"] = 404           # ohne Kontingent-Abfrage: anders prüfen

    def with_list(method, url, **kw):
        if url.endswith("/ListKernels"):
            assert json.loads(kw["data"])["user"] == USER
            return FakeKaggle._json({"kernels": []})
        return fake(method, url, **kw)

    assert K.KaggleTrainer(tmp_path, http=with_list, credentials=lambda: (USER, KEY)).account()["kontingent"] is None


# ── Plan und Skript ─────────────────────────────────────────────────────────
def test_plan_hard_cap_and_estimate():
    p = K.check_plan("Mjlab-Roulade-Flat-MicroDuck", 1000, None, "pollen")
    assert p["grafikkarte"] == "kaggle-t4" and 1 <= p["max_stunden"] <= K.HARD_CAP_STUNDEN
    assert K.estimate(p)["usd"] == 0 and K.estimate(p)["usd_max"] == 0
    for bad in (dict(max_stunden=12), dict(max_stunden=0), dict(max_stunden="viel"), dict(start_von="lauf:../x"),
                dict(bei_stillstand="egal"), dict(overrides={"agent.max_iterations": 5})):
        with pytest.raises(ValueError):
            K.check_plan("Mjlab-Roulade-Flat-MicroDuck", 500, **bad)
    with pytest.raises(ValueError):
        K.check_plan("Mjlab-Spin-Flat-MicroDuck", 500, None, "pollen")
    long = K.check_plan("Mjlab-Velocity-Rough-MicroDuck", 20000)       # zu lang: erlaubt, hält rechtzeitig an
    assert long["max_stunden"] == K.HARD_CAP_STUNDEN and "hält das Skript an" in long["hinweis"]
    assert K.HARD_CAP_STUNDEN * 3600 + K.SESSION_MARGIN_S < K.KAGGLE_SESSION_H * 3600


def test_script_commands_time_cap_and_helpers(tmp_path):
    p = K.check_plan("Mjlab-Roulade-Flat-MicroDuck", 1200, {"env.rewards.upright.weight": 2}, "pollen", 4, "abbrechen")
    init = f"hf://{T.POLLEN_TRAINING}/bundles/{T.POLLEN_BUNDLES['Mjlab-Roulade-Flat-MicroDuck']}"
    script = K.build_script(p, init, False)
    compile(script, "duckpilot_kaggle.py", "exec")
    for needle in (T.RL_TARBALL, '"sync", "--no-progress"', '"run", "train"', "scripts/export.py", "--checkpoint-file",
                   "/kaggle/working", "policy.onnx", "metrics.json", "nvidia-smi", "os.killpg", "def parse_log",
                   "def summarize"):
        assert needle in script, needle
    ns = {"__name__": "kaggle_test"}
    exec(script, ns)                                                   # main() läuft nicht
    cfg = ns["CFG"]
    assert cfg["budget_s"] == 4 * 3600 and cfg["export_reserve_s"] == K.EXPORT_RESERVE_MIN * 60
    assert cfg["init"] == init and cfg["warm"] is False and cfg["bei_stillstand"] == "abbrechen"
    assert cfg["args"][0] == "Mjlab-Roulade-Flat-MicroDuck"
    joined = " ".join(cfg["args"])
    assert "--agent.max_iterations 1200" in joined and "--env.rewards.upright.weight 2" in joined
    assert "--agent.logger tensorboard" in joined and "--agent.save_interval 100" in joined
    assert ns["latest_checkpoint"](["a/model_50.pt", "a/model_1000.pt", "a/model_999.pt", "x.onnx"]) == "a/model_1000.pt"
    # Die Auswertung im Kernel ist dieselbe wie in duckpilot
    lines = [ln for it in range(30) for ln in _block(it, 100, it * 0.1)]
    assert ns["parse_log"](lines) == T.parse_log(lines)


def test_script_reader_thins_log_and_stops_before_time_cap(tmp_path, monkeypatch, capsys):
    """Der Kernel-Teil, der `uv run train` überwacht: knappes Protokoll für parse_log, Anhalten an der Wanduhr."""
    p = K.check_plan("Mjlab-Spin-Flat-MicroDuck", 300, None, None, 2)
    ns = {"__name__": "kaggle_test"}
    exec(K.build_script(p, None, False), ns)
    fake_train = tmp_path / "fake_train.py"
    blocks = [ln for it in range(40) for ln in _block(it, 300, it * 0.1)]
    fake_train.write_text(textwrap.dedent(f"""
        import sys, time
        for ln in {blocks!r}:
            print(ln, flush=True)
        print("Traceback (most recent call last): nur ein Test", flush=True)
        try:
            time.sleep(60)
        except KeyboardInterrupt:
            sys.exit(130)
    """))
    clock = {"t": 0.0}
    ns["elapsed"] = lambda: clock["t"]
    real_sleep = __import__("time").sleep

    def sleep(_s):
        real_sleep(0.3)
        if len(ns["POINTS"]) >= 39:                                  # der 40. Block endet erst mit der Ausgabe
            clock["t"] = ns["CFG"]["budget_s"]                          # Wanduhr springt ans Budgetende

    ns["time"] = types.SimpleNamespace(sleep=sleep, monotonic=__import__("time").monotonic)
    ns["WORK"] = str(tmp_path)
    ns["CFG"]["every"] = 10
    rc, grund = ns["train"]([sys.executable, str(fake_train), "--"], None)
    out = capsys.readouterr().out
    assert grund == "zeit" and rc != 0 and len(ns["POINTS"]) == 40
    assert '"phase": "angehalten"' in out and "Traceback" in out and "Computation" not in out
    shown = T.parse_log(out.splitlines())
    assert [x["it"] for x in shown] == [0, 10, 20, 30] and shown[1]["belohnung"] == pytest.approx(1.0)
    # Stillstand: bei „abbrechen“ hält der Kernel selbst an
    ns["POINTS"].clear()
    ns["POINTS"].extend(T.parse_log([ln for it in range(0, 600) for ln in _block(it, 1000, 4.0)]))
    assert ns["summarize"](list(ns["POINTS"]))["stillstand"]


# ── Starten, Status, Kurve, Ergebnis ────────────────────────────────────────
def test_submit_status_curve_and_result(tmp_path):
    fake = FakeKaggle()
    tr = _trainer(tmp_path, fake)
    assert tr.is_free is True and K.KaggleTrainer.hard_cap_stunden == K.HARD_CAP_STUNDEN
    plan = K.check_plan("Mjlab-Roulade-Flat-MicroDuck", 1000, None, "pollen", 3, "abbrechen")
    run = tr.submit(plan, gruppe="g1", variante="A")
    save = fake.saves()[-1]
    assert save["slug"] == f"{USER}/{run['job'].split('/', 1)[1]}" and save["newTitle"].startswith("duckpilot ")
    assert K._slugify(save["newTitle"]) == save["slug"].split("/", 1)[1] and len(save["newTitle"]) <= 50
    assert save["kernelType"] == "script" and save["language"] == "python" and save["isPrivate"] is True
    assert save["enableGpu"] is True and save["enableInternet"] is True and save["enableTpu"] is False
    assert save["machineShape"] == "NvidiaTeslaT4" and save["kernelDataSources"] == []
    assert save["sessionTimeoutSeconds"] == 3 * 3600 + K.SESSION_MARGIN_S < 12 * 3600
    assert "hf://pollen-robotics/microduck-training/bundles/microduck_roulade" in save["text"]
    assert run["anbieter"] == "kaggle" and run["kosten"] == 0 and run["status"] == "gestartet"
    assert run["url"].startswith("https://www.kaggle.com/code/") and run["variante"] == "A"
    assert run["start_von"].startswith("Pollens Stand") and run["schaetzung"]["usd"] == 0
    assert (tmp_path / "kaggle_runs.json").exists() and KEY not in (tmp_path / "kaggle_runs.json").read_text()
    slug = run["job"].split("/", 1)[1]

    # wartet → trainiert (mit Lernkurve aus dem Live-Protokoll) → fertig
    assert tr.refresh()[0]["status"] == "wartet auf eine GPU"
    fake.status[slug] = {"status": "RUNNING"}
    fake.logs[slug] = ['[duckpilot] {"phase": "installiert", "t": 900}'] + \
        [ln for it in range(0, 50, 5) for ln in _block(it, 1000, it * 0.1)]
    r = tr.refresh()[0]
    assert r["status"] == "trainiert" and r["phase"] == K.PHASEN["installiert"]
    assert r["kurve"]["iteration"] == 45 and r["kurve"]["s_it"] == 6.5 and tr.measured() == 6.5
    c = tr.curve(run["id"])
    assert c["anbieter"] == "kaggle" and len(c["punkte"]) == 10 and c["punkte"][-1]["faehigkeit"] is not None

    pts = T.parse_log([ln for it in range(0, 1000, 10) for ln in _block(it, 1000, min(it, 300) * 0.01)])
    metrics = {"grund": "zeit", "checkpoint": "model_900.pt", "punkte": pts, "zusammenfassung": T.summarize(pts)}
    fake.status[slug] = {"status": "KERNEL_WORKER_STATUS_COMPLETE"}
    fake.outputs[slug] = {"policy.onnx": ONNX, "metrics.json": json.dumps(metrics).encode(),
                          "checkpoint/model_900.pt": b"pt"}
    r = tr.refresh()[0]
    assert r["status"] == "fertig" and r["checkpoint"] == "model_900.pt" and "Höchstdauer" in r["hinweis"]
    assert r["kurve"]["iteration"] == 990 and "policy.onnx" in r["ausgaben"]
    calls = len(fake.calls)
    assert tr.refresh() and len(fake.calls) == calls                   # fertige Läufe werden nicht mehr gefragt

    path = tr.result(run["id"])
    assert path == tmp_path / "policies" / "kaggle" / run["id"] / "policy.onnx" and path.read_bytes() == ONNX
    assert (path.parent / "metrics.json").exists() and tr.runs()[0]["onnx"] == str(path)
    assert tr.result(run["id"]) == path                                 # schon da: kein neuer Download

    # Weitertrainieren vom eigenen Kaggle-Lauf: dessen Ausgaben als Datenquelle, Warmstart bei anderer Variante
    run2 = tr.submit(K.check_plan("Mjlab-Roulade-Flat-MicroDuck", 500, None, f"lauf:{run['id']}", 2))
    save2 = fake.saves()[-1]
    assert save2["kernelDataSources"] == [run["job"]] and '"init": "kaggle-input"' in save2["text"]
    assert run2["id"] != run["id"] and run2["warmstart"] is False
    with pytest.raises(K.KaggleError, match="derselben Aufgabe"):
        tr.submit(K.check_plan("Mjlab-Spin-Flat-MicroDuck", 500, None, f"lauf:{run['id']}"))
    with pytest.raises(K.KaggleError, match="schon 2"):                  # höchstens MAX_AKTIV gleichzeitig
        tr.submit(K.check_plan("Mjlab-Spin-Flat-MicroDuck", 500))
        tr.submit(K.check_plan("Mjlab-Spin-Flat-MicroDuck", 500))
    # Abbrechen geht über Kaggles öffentliche API nicht – erklärt mit Link
    with pytest.raises(K.KaggleError, match="Cancel run"):
        tr.cancel(run2["id"])


def test_errors_are_german(tmp_path):
    fake = FakeKaggle()
    tr = _trainer(tmp_path, fake)
    plan = K.check_plan("Mjlab-Spin-Flat-MicroDuck", 500, None, None, 2)

    # Telefonbestätigung fehlt (Kaggle lehnt GPU/Internet beim Speichern ab)
    fake.save_error = "Phone verification is required to enable GPU and internet"
    with pytest.raises(K.KaggleError, match="Telefon"):
        tr.submit(plan)
    assert tr.runs()[-1]["status"] == "fehlgeschlagen" and "Telefon" in tr.runs()[-1]["fehler"]
    fake.save_error = ""

    # Kontingent aufgebraucht bzw. zu knapp
    fake.quota["gpuQuota"]["timeUsed"] = "107000s"
    with pytest.raises(K.KaggleError, match="aufgebraucht"):
        tr.submit(plan)
    fake.quota["gpuQuota"]["timeUsed"] = "102000s"
    with pytest.raises(K.KaggleError, match="höchstens 1 h"):
        tr.submit(plan)
    fake.quota["gpuQuota"]["timeUsed"] = "0s"

    # Kernel scheitert: keine GPU zugeteilt (Meldung des Skripts) → deutscher Text mit letzten Zeilen
    run = tr.submit(plan)
    slug = run["job"].split("/", 1)[1]
    fake.status[slug] = {"status": "ERROR", "failureMessage": "Process exited with code 1"}
    fake.final_log[slug] = ['[duckpilot] {"phase": "start", "t": 0}',
                            '[duckpilot] {"phase": "fehler", "code": "keine_gpu", "text": "nvidia-smi findet keine GPU"}']
    r = next(x for x in tr.refresh() if x["id"] == run["id"])
    assert r["status"] == "fehlgeschlagen" and "keine GPU" in r["fehler"] and "nvidia-smi" in r["fehler"]
    with pytest.raises(K.KaggleError, match="nicht fertig"):
        tr.result(run["id"])

    # Kernel lief durch, aber ohne policy.onnx → fehlgeschlagen mit den letzten Protokollzeilen
    run = tr.submit(plan)
    slug = run["job"].split("/", 1)[1]
    fake.status[slug] = {"status": "COMPLETE"}
    fake.final_log[slug] = ["irgendwas", "RuntimeError: CUDA error: no kernel image is available"]
    r = next(x for x in tr.refresh() if x["id"] == run["id"])
    assert r["status"] == "fehlgeschlagen" and "no kernel image" in r["fehler"]

    # Fehler des Skripts nur in metrics.json (Protokoll leer)
    run = tr.submit(plan)
    slug = run["job"].split("/", 1)[1]
    fake.status[slug] = {"status": "ERROR"}
    fake.outputs[slug] = {"metrics.json": json.dumps({"fehler": {"code": "gpu_zu_alt", "text": "Tesla P100"}}).encode()}
    r = next(x for x in tr.refresh() if x["id"] == run["id"])
    assert "zu alte GPU" in r["fehler"] and "P100" in r["fehler"]

    # HTTP-Fehler
    assert "bremst" in K.erklaere("", 429) and "nicht richtig" in K.erklaere("", 503)
    assert "Kontingent" in K.erklaere("You have exceeded your weekly GPU quota")
    assert K.log_events('[{"stream_name": "stdout", "time": 1, "data": "a\\n"}]') == ["a\n"]
    assert K.log_events("data: {\"data\": \"x\"}\n\ndata: END_OF_LOG\n\ndata: {\"data\": \"y\"}", "") == ["x"]
