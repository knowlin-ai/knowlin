"""Training: Hugging Face Jobs (bezahlt, zwei Klicks), dieser PC und Kaggle (kostenlos)."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ...aio import spawn
from ..plans import _plans_from
from ..runtime import (
    Runtime,
    _json_default,
)
from ..security import _json_body

log = logging.getLogger(__name__)


def register(app: FastAPI, runtime: Runtime) -> None:
    # ── Training ─────────────────────────────────────────────────────────
    @app.get("/api/training")
    async def training_status() -> JSONResponse:
        return JSONResponse(json.loads(json.dumps(runtime.training_message(), default=_json_default)))

    @app.post("/api/training/token")
    async def training_token(request: Request) -> JSONResponse:
        from ...training import set_token, token_hint

        body = await request.json()
        try:
            set_token(str(body.get("token", "")))
        except (ValueError, RuntimeError) as exc:
            return JSONResponse({"ok": False, "fehler": str(exc)}, status_code=400)
        from ...training import get_token

        try:
            who = await asyncio.to_thread(runtime.trainer.account, get_token())
        except Exception as exc:
            who = {"fehler": str(exc)[:200]}
        return JSONResponse({"ok": True, "token": token_hint(get_token()), "konto": who})

    @app.delete("/api/training/token")
    async def training_token_delete() -> JSONResponse:
        from ...training import delete_token

        delete_token()
        return JSONResponse({"ok": True})

    @app.post("/api/training/start")
    async def training_start(request: Request) -> JSONResponse:
        from ...training import check_plan, get_token

        body = await request.json()
        if not isinstance(body, dict):
            return JSONResponse({"ok": False, "fehler": "Erwartet ein Objekt"}, status_code=400)
        try:
            plans = _plans_from(body, check_plan, runtime.trainer.measured())
        except ValueError as exc:
            return JSONResponse({"ok": False, "fehler": str(exc)}, status_code=400)
        if not get_token():
            return JSONResponse({"ok": False, "fehler": "Erst den Hugging-Face-Token hinterlegen."}, status_code=400)
        if runtime.training_job.get("laeuft"):
            return JSONResponse({"ok": False, "fehler": "Ein Start läuft schon."}, status_code=409)
        ns = body.get("namensraum") or None
        if ns is not None and not re.fullmatch(r"[A-Za-z0-9][\w.-]{0,95}", str(ns)):
            return JSONResponse({"ok": False, "fehler": "ungültiger Namensraum"}, status_code=400)
        runtime.training_job = {"laeuft": True, "text": "startet …", "fehler": None}   # sofort: kein Doppelstart
        spawn(runtime.start_training(plans, ns))
        return JSONResponse({"ok": True, "laeufe": len(plans)})

    @app.post("/api/training/schaetzen")
    async def training_estimate(request: Request) -> JSONResponse:
        from ...training import check_plan, estimate

        body = await request.json()
        if not isinstance(body, dict):
            return JSONResponse({"ok": False, "fehler": "Erwartet ein Objekt"}, status_code=400)
        try:
            plans = _plans_from(body, check_plan, runtime.trainer.measured())
        except ValueError as exc:
            return JSONResponse({"ok": False, "fehler": str(exc)}, status_code=400)
        measured = runtime.trainer.measured()
        each = [estimate(p, measured) for p in plans]
        return JSONResponse({"ok": True, "laeufe": len(plans), "max_stunden": plans[0]["max_stunden"],
                             "stunden": each[0]["stunden"], "s_it": each[0]["s_it"], "gemessen": each[0]["gemessen"],
                             "usd": round(sum(e["usd"] for e in each), 2), "usd_max": round(sum(e["usd_max"] for e in each), 2)})

    @app.get("/api/training/{rid}/kurve")
    async def training_curve(rid: str) -> JSONResponse:
        from ...training import get_token

        try:
            data = await asyncio.to_thread(runtime.trainer.curve, get_token(), rid)
        except KeyError:
            return JSONResponse({"ok": False, "fehler": "unbekannter Lauf"}, status_code=404)
        return JSONResponse({"ok": True, **data})

    @app.post("/api/training/{rid}/exportieren")
    async def training_export(rid: str) -> JSONResponse:
        from ...training import TrainingError, get_token

        token = get_token()
        if not token:
            return JSONResponse({"ok": False, "fehler": "Erst den Hugging-Face-Token hinterlegen."}, status_code=400)
        try:
            await asyncio.to_thread(runtime.trainer.export, token, rid)
        except KeyError:
            return JSONResponse({"ok": False, "fehler": "unbekannter Lauf"}, status_code=404)
        except (TrainingError, ValueError) as exc:
            return JSONResponse({"ok": False, "fehler": str(exc)[:300]}, status_code=400)
        except Exception as exc:
            return JSONResponse({"ok": False, "fehler": str(exc)[:300]}, status_code=502)
        await runtime.broadcast(runtime.training_message())
        return JSONResponse({"ok": True})

    @app.post("/api/training/aktualisieren")
    async def training_refresh() -> JSONResponse:
        from ...training import get_token

        token = get_token()
        if token:
            try:
                await asyncio.to_thread(runtime.trainer.refresh, token)
            except Exception as exc:
                return JSONResponse({"ok": False, "fehler": str(exc)[:300]}, status_code=502)
            spawn(runtime.after_training_refresh())
        return JSONResponse(json.loads(json.dumps(runtime.training_message(), default=_json_default)))

    @app.get("/api/training/{rid}/protokoll")
    async def training_logs(rid: str) -> JSONResponse:
        from ...training import get_token

        try:
            lines = await asyncio.to_thread(runtime.trainer.logs, get_token(), rid)
        except KeyError:
            return JSONResponse({"ok": False, "fehler": "unbekannter Lauf"}, status_code=404)
        except Exception as exc:
            return JSONResponse({"ok": False, "fehler": str(exc)[:300]}, status_code=502)
        return JSONResponse({"ok": True, "zeilen": lines})

    @app.post("/api/training/{rid}/abbrechen")
    async def training_cancel(rid: str) -> JSONResponse:
        from ...training import get_token

        try:
            await asyncio.to_thread(runtime.trainer.cancel, get_token(), rid)
        except KeyError:
            return JSONResponse({"ok": False, "fehler": "unbekannter Lauf"}, status_code=404)
        except Exception as exc:
            return JSONResponse({"ok": False, "fehler": str(exc)[:300]}, status_code=502)
        return JSONResponse({"ok": True})

    @app.post("/api/training/{rid}/ausprobieren")
    async def training_try(rid: str) -> JSONResponse:
        from ...training import TASKS, get_token

        add = getattr(runtime.backend, "add_local_policy", None)
        if add is None:
            return JSONResponse({"ok": False, "fehler": "Ausprobieren geht im Physik-Simulator (Einstellungen → Körper)."},
                                status_code=400)
        try:
            path = await asyncio.to_thread(runtime.trainer.result, get_token(), rid)
        except KeyError:
            return JSONResponse({"ok": False, "fehler": "unbekannter Lauf"}, status_code=404)
        except Exception as exc:
            return JSONResponse({"ok": False, "fehler": f"Ergebnis nicht ladbar: {exc}"[:300]}, status_code=502)
        run = next(r for r in runtime.trainer.runs() if r["id"] == rid)
        task = run["plan"]["aufgabe"]
        name = "eigen_" + re.sub(r"[^a-z0-9]+", "_", TASKS[task]["name"].lower()).strip("_")[:24]
        try:
            msg = await asyncio.to_thread(add, str(path), name, TASKS[task]["art"])
        except Exception as exc:
            return JSONResponse({"ok": False, "fehler": f"Policy passt nicht: {exc}"[:300]}, status_code=400)
        store = getattr(runtime.backend, "store", None)
        if store is not None and hasattr(store, "merke_eigen"):       # bleibt nach dem Neustart (seit 0.37.14)
            try:
                store.merke_eigen(str(path), name, TASKS[task]["art"], task)
                getattr(runtime.backend, "eigene", {})[name] = task
            except Exception:
                log.warning("Eigene Policy merken", exc_info=True)
        await runtime.broadcast(runtime.init_message())
        return JSONResponse({"ok": True, "meldung": msg, "name": name})

    # ── Kostenlos trainieren: dieser PC ──────────────────────────────────
    def _lernen_json(full: bool = False) -> JSONResponse:
        return JSONResponse(json.loads(json.dumps(runtime.lernen_message(full), default=_json_default)))

    @app.get("/api/lernen")
    async def lernen_status(voll: int = 0) -> JSONResponse:
        if runtime._gpus is None:
            await asyncio.to_thread(runtime.gpus)
        return _lernen_json(bool(voll))

    @app.post("/api/lernen/start")
    async def lernen_start(request: Request) -> JSONResponse:
        body = await _json_body(request)
        body["von"] = "mensch"
        res = await runtime.start_local(body)
        if not res.get("ok"):
            return JSONResponse(res, status_code=400)
        return JSONResponse({**res, **json.loads(json.dumps(runtime.lernen_message(), default=_json_default))})

    @app.post("/api/lernen/stopp")
    async def lernen_stop() -> JSONResponse:
        await runtime.lernen.stop()
        return _lernen_json()

    @app.get("/api/lernen/lauf/{jid}")
    async def lernen_run(jid: str) -> JSONResponse:
        j = runtime.local.laden(jid)
        if j is None:
            return JSONResponse({"ok": False, "fehler": "unbekannter Lauf"}, status_code=404)
        return JSONResponse(json.loads(json.dumps({"ok": True, **j}, default=_json_default)))

    @app.post("/api/lernen/lauf/{jid}/retten")
    async def lernen_rescue(jid: str) -> JSONResponse:
        from ...physics.lernen import LernFehler

        try:
            j = await asyncio.to_thread(runtime.local.exportieren, jid)
        except LernFehler as exc:
            return JSONResponse({"ok": False, "fehler": str(exc)}, status_code=400)
        runtime._lab_changed()
        return JSONResponse(json.loads(json.dumps({"ok": True, "ergebnis": j.get("ergebnis")}, default=_json_default)))

    @app.post("/api/lernen/ausprobieren")
    async def lernen_try(request: Request) -> JSONResponse:
        from ...physics import lernen as L

        body = await _json_body(request)
        quelle = str(body.get("quelle") or "")
        add = getattr(runtime.backend, "add_local_policy", None)
        if add is None:
            return JSONResponse({"ok": False, "fehler": "Ausprobieren geht im Physik-Simulator (System → Einstellungen → Körper)."},
                                status_code=400)
        if not quelle.startswith("lokal:"):
            return JSONResponse({"ok": False, "fehler": "Nur am PC gelernte Policies („lokal:…“)."}, status_code=400)
        try:
            path, _scale, _label = L.aufloesen(runtime.local.root, quelle)
            name = "pc_" + re.sub(r"[^a-z0-9]+", "_", quelle[6:].lower()).strip("_")[-24:]
            msg = await asyncio.to_thread(add, str(path), name, "gangart")
        except Exception as exc:
            return JSONResponse({"ok": False, "fehler": f"{exc}"[:300]}, status_code=400)
        await runtime.broadcast(runtime.init_message())
        return JSONResponse({"ok": True, "meldung": msg, "name": name})

    # ── Policies aus Isaac Lab übernehmen (seit 0.38.27) ──────────────────
    def _isaac_root():
        from ... import settings as S

        return S.settings_path().parent

    def _isaac_message() -> dict[str, Any]:
        from ...physics import isaaclab as IL

        gait = getattr(runtime.backend, "gait_policy", None)
        return {"ok": True, "liste": IL.liste(_isaac_root()), "aufgaben": IL.AUFGABEN, "standard": IL.STANDARD_AUFGABE,
                "physik": hasattr(runtime.backend, "add_local_policy"), "aktiv": getattr(gait, "name", None),
                "quelle": IL.QUELLE}

    @app.get("/api/isaaclab")
    async def isaaclab_liste() -> JSONResponse:
        return JSONResponse(json.loads(json.dumps(_isaac_message(), default=_json_default)))

    @app.post("/api/isaaclab")
    async def isaaclab_uebernehmen(request: Request) -> JSONResponse:
        """Rohdaten der ONNX-Datei im Körper, Name und Aufgabe als Parameter – prüfen, ablegen, Prüfstand rechnen."""
        from ...physics import isaaclab as IL

        daten = await request.body()
        if not daten or len(daten) > IL.MAX_BYTES:
            return JSONResponse({"ok": False, "fehler": "Keine oder eine zu große Datei."}, status_code=400)
        root = _isaac_root()
        eingang = root / "policies" / "import" / "_eingang.onnx"
        eingang.parent.mkdir(parents=True, exist_ok=True)
        eingang.write_bytes(daten)
        q = request.query_params
        try:
            e = await asyncio.to_thread(IL.importieren, root, eingang, str(q.get("name") or ""),
                                        str(q.get("aufgabe") or IL.STANDARD_AUFGABE))
        except IL.ImportFehler as exc:
            return JSONResponse({"ok": False, "fehler": str(exc)}, status_code=400)
        except Exception as exc:                     # Physik fehlt, Modell nicht geladen …
            log.warning("Isaac-Lab-Import: %s", exc)
            return JSONResponse({"ok": False, "fehler": f"Prüfstand ging nicht: {str(exc)[:200]}"}, status_code=400)
        finally:
            eingang.unlink(missing_ok=True)
        return JSONResponse(json.loads(json.dumps({**_isaac_message(), "neu": e}, default=_json_default)))

    @app.get("/api/isaaclab/hf/suche")
    async def isaaclab_hf_suche(neu: bool = False) -> JSONResponse:
        """Seit 0.38.31: Microduck-Repos mit ONNX-Dateien auf Hugging Face vorschlagen (nur lesen, nichts laden)."""
        from ...physics import isaaclab as IL
        from ...physics import isaaclab_hf as HF
        from ...training import get_token

        try:
            liste = await asyncio.to_thread(HF.suchen, None, get_token(), neu)
        except IL.ImportFehler as exc:
            return JSONResponse({"ok": False, "fehler": str(exc)}, status_code=503)
        return JSONResponse({"ok": True, "liste": liste})

    @app.post("/api/isaaclab/hf")
    async def isaaclab_von_hf(request: Request) -> JSONResponse:
        """Seit 0.38.30: Policy direkt von Hugging Face laden (nur huggingface.co, nur .onnx bis 60 MB) und prüfen."""
        from ...physics import isaaclab as IL
        from ...physics import isaaclab_hf as HF
        from ...training import get_token

        body = await _json_body(request)
        try:
            e = await asyncio.to_thread(HF.laden, _isaac_root(), str(body.get("adresse") or ""),
                                        str(body.get("name") or ""), str(body.get("aufgabe") or IL.STANDARD_AUFGABE),
                                        get_token(), str(body.get("datei") or ""))
        except HF.Auswahl as exc:
            return JSONResponse({"ok": False, "fehler": str(exc), "auswahl": exc.dateien}, status_code=409)
        except IL.ImportFehler as exc:
            return JSONResponse({"ok": False, "fehler": str(exc)}, status_code=400)
        except Exception as exc:
            log.warning("Hugging-Face-Import: %s", exc)
            return JSONResponse({"ok": False, "fehler": f"Laden oder Prüfstand ging nicht: {str(exc)[:200]}"},
                                status_code=400)
        return JSONResponse(json.loads(json.dumps({**_isaac_message(), "neu": e}, default=_json_default)))

    @app.post("/api/isaaclab/{name}/nutzen")
    async def isaaclab_nutzen(name: str) -> JSONResponse:
        from ...physics import isaaclab as IL

        add = getattr(runtime.backend, "add_local_policy", None)
        if add is None:
            return JSONResponse({"ok": False, "fehler": "Einsetzen geht im Physik-Simulator (System → Einstellungen → Körper)."},
                                status_code=400)
        pfad = _isaac_root() / "policies" / "import" / name / "policy.onnx"
        if not IL.NAME.fullmatch(name) or not pfad.exists():
            return JSONResponse({"ok": False, "fehler": "Diese Policy kenne ich nicht."}, status_code=404)
        try:
            msg = await asyncio.to_thread(add, str(pfad), name, "gangart")
        except Exception as exc:
            return JSONResponse({"ok": False, "fehler": str(exc)[:300]}, status_code=400)
        await runtime.broadcast(runtime.init_message())
        return JSONResponse({**_isaac_message(), "meldung": msg})

    @app.post("/api/isaaclab/standard")
    async def isaaclab_standard() -> JSONResponse:
        if not hasattr(runtime.backend, "add_local_policy"):
            return JSONResponse({"ok": False, "fehler": "Nur im Physik-Simulator."}, status_code=400)
        res = await runtime.backend.reset_gait("walk")
        await runtime.broadcast(runtime.init_message())
        return JSONResponse({**_isaac_message(), "meldung": res.reason or "Wieder Pollens Gangart"})

    # ── Kostenlos trainieren: Kaggle ─────────────────────────────────────
    def _kaggle_message() -> dict[str, Any]:
        from ... import kaggle_training as K

        return {"type": "kaggle", "zugang": K.credentials_hint(K.get_credentials()), "laeufe": runtime.kaggle.runs()[::-1][:20],
                "job": runtime.kaggle_job, "obergrenze_h": runtime.kaggle.hard_cap_stunden,
                "konto": runtime.__dict__.get("kaggle_konto")}

    @app.get("/api/kaggle")
    async def kaggle_status() -> JSONResponse:
        return JSONResponse(json.loads(json.dumps(_kaggle_message(), default=_json_default)))

    @app.post("/api/kaggle/zugang")
    async def kaggle_login(request: Request) -> JSONResponse:
        from ... import kaggle_training as K

        body = await _json_body(request)
        try:
            if body.get("json"):
                user, key = K.parse_kaggle_json(str(body["json"]))
            else:
                user, key = str(body.get("name") or "").strip(), str(body.get("schluessel") or "").strip()
            K.set_credentials(user, key)
            runtime.kaggle_konto = await asyncio.to_thread(runtime.kaggle.account)
        except (ValueError, RuntimeError) as exc:
            return JSONResponse({"ok": False, "fehler": str(exc)[:300], **_kaggle_message()}, status_code=400)
        return JSONResponse({"ok": True, **json.loads(json.dumps(_kaggle_message(), default=_json_default))})

    @app.delete("/api/kaggle/zugang")
    async def kaggle_logout() -> JSONResponse:
        from ... import kaggle_training as K

        K.delete_credentials()
        runtime.kaggle_konto = None
        return JSONResponse({"ok": True, **_kaggle_message()})

    @app.post("/api/kaggle/schaetzen")
    async def kaggle_estimate(request: Request) -> JSONResponse:
        from ... import kaggle_training as K

        b = await _json_body(request)
        try:
            plan = K.check_plan(str(b.get("aufgabe") or ""), b.get("iterationen"), b.get("anpassungen") or {},
                                b.get("start_von") or None, b.get("max_stunden"), str(b.get("bei_stillstand") or "weiter"),
                                runtime.kaggle.measured())
        except ValueError as exc:
            return JSONResponse({"ok": False, "fehler": str(exc)}, status_code=400)
        est = K.estimate(plan, runtime.kaggle.measured())
        return JSONResponse({"ok": True, **est, "max_stunden": plan["max_stunden"], "hinweis": plan.get("hinweis")})

    @app.post("/api/kaggle/start")
    async def kaggle_start(request: Request) -> JSONResponse:
        body = await _json_body(request)
        try:
            res = await runtime.start_kaggle(body)
        except (ValueError, RuntimeError) as exc:
            return JSONResponse({"ok": False, "fehler": str(exc)[:300]}, status_code=400)
        return JSONResponse({"ok": True, **res})

    @app.post("/api/kaggle/aktualisieren")
    async def kaggle_refresh() -> JSONResponse:
        try:
            await asyncio.to_thread(runtime.kaggle.refresh)
        except Exception as exc:
            return JSONResponse({"ok": False, "fehler": str(exc)[:300], **_kaggle_message()}, status_code=502)
        await runtime.after_training_refresh()
        return JSONResponse({"ok": True, **json.loads(json.dumps(_kaggle_message(), default=_json_default))})

    @app.get("/api/kaggle/{rid}/kurve")
    async def kaggle_curve(rid: str) -> JSONResponse:
        try:
            data = await asyncio.to_thread(runtime.kaggle.curve, rid)
        except KeyError:
            return JSONResponse({"ok": False, "fehler": "unbekannter Lauf"}, status_code=404)
        except Exception as exc:
            return JSONResponse({"ok": False, "fehler": str(exc)[:300]}, status_code=502)
        return JSONResponse(json.loads(json.dumps({"ok": True, **data}, default=_json_default)))

    @app.post("/api/kaggle/{rid}/abbrechen")
    async def kaggle_cancel(rid: str) -> JSONResponse:
        try:
            res = await asyncio.to_thread(runtime.kaggle.cancel, rid)
        except Exception as exc:
            return JSONResponse({"ok": False, "fehler": str(exc)[:400]}, status_code=400)
        return JSONResponse({"ok": True, **res})

    @app.post("/api/kaggle/{rid}/ausprobieren")
    async def kaggle_try(rid: str) -> JSONResponse:
        from ...training import TASKS

        add = getattr(runtime.backend, "add_local_policy", None)
        if add is None:
            return JSONResponse({"ok": False, "fehler": "Ausprobieren geht im Physik-Simulator (System → Einstellungen → Körper)."},
                                status_code=400)
        try:
            path = await asyncio.to_thread(runtime.kaggle.result, rid)
            run = next(r for r in runtime.kaggle.runs() if r["id"] == rid)
            task = run["plan"]["aufgabe"]
            name = "kaggle_" + re.sub(r"[^a-z0-9]+", "_", TASKS[task]["name"].lower()).strip("_")[:22]
            msg = await asyncio.to_thread(add, str(path), name, TASKS[task]["art"])
        except Exception as exc:
            return JSONResponse({"ok": False, "fehler": f"{exc}"[:300]}, status_code=400)
        await runtime.broadcast(runtime.init_message())
        return JSONResponse({"ok": True, "meldung": msg, "name": name})
