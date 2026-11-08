"""Policies direkt von Hugging Face übernehmen (seit 0.38.30, Frage „kann ich die Policies nicht OTA laden?“).

Statt die Datei erst herunterzuladen und dann in Knowlin zu wählen, gibt man die Hugging-Face-Adresse ein – etwa
`RemiFabre/microduck-rough-walk-g` oder einen Link auf die Datei. Knowlin lädt nur ONNX-Dateien bis 60 MB von
huggingface.co, nichts anderes, und schickt sie danach durch dieselbe Prüfung und denselben Prüfstand wie eine Datei vom
PC (`isaaclab.importieren`). Liegen im Repo mehrere Policies, kommt eine Auswahl zurück statt einer geratenen Datei.

Woher die Datei kam (Repo, Pfad, Stand, Lizenz laut Modellkarte), steht danach im Manifest.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from . import isaaclab as IL

REPO = r"[A-Za-z0-9][A-Za-z0-9_.-]{0,95}/[A-Za-z0-9][A-Za-z0-9_.-]{0,95}"
PFAD = r"[A-Za-z0-9_.\-/]{1,300}\.onnx"
_KURZ = re.compile(rf"(?P<repo>{REPO})(?:/(?P<pfad>{PFAD}))?")
_LINK = re.compile(rf"https://huggingface\.co/(?P<repo>{REPO})(?:/(?:blob|resolve|tree)/(?P<rev>[A-Za-z0-9_.\-]{{1,64}})"
                   rf"(?:/(?P<pfad>{PFAD}))?)?/?(?:\?.*)?")
BEVORZUGT = ("exported/policy.onnx", "policy.onnx")


class Auswahl(IL.ImportFehler):
    """Im Repo liegen mehrere Policies – die Oberfläche zeigt sie zur Wahl."""

    def __init__(self, dateien: list[dict[str, Any]]):
        super().__init__(f"In diesem Repo liegen {len(dateien)} Policies – bitte eine wählen.")
        self.dateien = dateien


def offline() -> bool:
    return os.environ.get("DUCKPILOT_OFFLINE", "") not in ("", "0")


def adresse_lesen(text: str) -> tuple[str, str | None, str | None]:
    """„owner/repo“, „owner/repo/pfad.onnx“ oder ein huggingface.co-Link → (repo, pfad, stand)."""
    t = (text or "").strip()
    m = _LINK.fullmatch(t)
    if m:
        pfad = m.group("pfad")
        if pfad and ".." in pfad.split("/"):
            raise IL.ImportFehler("Diese Adresse verstehe ich nicht.")
        return m.group("repo"), pfad, m.group("rev")
    if "://" in t or t.startswith("www."):
        raise IL.ImportFehler("Nur Adressen von huggingface.co – etwa „besitzer/repo“ oder ein Link auf die Datei.")
    m = _KURZ.fullmatch(t)
    if not m or ".." in t.split("/"):
        raise IL.ImportFehler("Diese Adresse verstehe ich nicht – etwa „besitzer/repo“ oder „besitzer/repo/policy.onnx“.")
    return m.group("repo"), m.group("pfad"), None


def _lizenz(info: Any) -> str | None:
    karte = getattr(info, "card_data", None) or getattr(info, "cardData", None)
    lic = karte.get("license") if hasattr(karte, "get") else None
    if not lic:
        lic = next((t.split(":", 1)[1] for t in (getattr(info, "tags", None) or []) if t.startswith("license:")), None)
    return str(lic)[:60] if lic else None


def waehle(dateien: list[dict[str, Any]], pfad: str | None) -> dict[str, Any]:
    """Die passende ONNX-Datei aus der Repo-Liste – oder Auswahl, wenn es mehrere gibt."""
    if pfad:
        d = next((x for x in dateien if x["pfad"] == pfad), None)
        if not d:
            raise IL.ImportFehler(f"„{pfad}“ liegt nicht in diesem Repo.")
        return d
    if not dateien:
        raise IL.ImportFehler("In diesem Repo liegt keine ONNX-Datei.")
    for p in BEVORZUGT:
        d = next((x for x in dateien if x["pfad"] == p), None)
        if d:
            return d
    if len(dateien) == 1:
        return dateien[0]
    raise Auswahl(dateien[:40])


# ── Ohne huggingface_hub (seit 0.38.33) ───────────────────────────────────────────────────────────────────────────
# Im Windows-Installer fehlt das Paket (es kommt erst mit Training oder Qwen3-TTS) – Vorschläge und Laden meldeten dann
# „Hugging Face war nicht erreichbar“. Dieselben zwei Abfragen und der Download gehen auch direkt über die öffentliche
# Schnittstelle von huggingface.co; nur dorthin, der Schlüssel nie an eine Weiterleitung.
HF = "https://huggingface.co"


class RepoNotFound(Exception):
    pass


def _ns(d: dict[str, Any]) -> SimpleNamespace:
    sib = [SimpleNamespace(rfilename=str(x.get("rfilename", "")), size=x.get("size"))
           for x in d.get("siblings") or [] if isinstance(x, dict)]
    return SimpleNamespace(id=d.get("id") or d.get("modelId") or "", sha=d.get("sha"), siblings=sib,
                           downloads=d.get("downloads", 0), likes=d.get("likes", 0), card_data=d.get("cardData"),
                           tags=d.get("tags") or [], last_modified=d.get("lastModified"))


def _holen(url: str, token: str | None = None, limit: int = 8_000_000) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Knowlin"})
    if token:
        req.add_unredirected_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:          # noqa: S310 – nur huggingface.co
            return r.read(limit + 1)
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403, 404):
            raise RepoNotFound(str(exc)) from exc
        raise


class EigeneApi:
    """Das Nötigste aus huggingface_hub.HfApi – list_models und model_info."""

    def list_models(self, search: str, sort: str = "downloads", limit: int = 60, token: str | None = None,
                    expand: list[str] | None = None) -> list[SimpleNamespace]:
        q = [("search", search), ("sort", sort), ("direction", "-1"), ("limit", str(limit))]
        q += [("expand[]", e) for e in expand or []]
        daten = json.loads(_holen(f"{HF}/api/models?{urllib.parse.urlencode(q)}", token))
        return [_ns(d) for d in daten if isinstance(d, dict)]

    def model_info(self, repo: str, revision: str | None = None, files_metadata: bool = True,
                   token: str | None = None) -> SimpleNamespace:
        url = f"{HF}/api/models/{repo}" + (f"/revision/{urllib.parse.quote(revision, safe='')}" if revision else "")
        return _ns(json.loads(_holen(url + ("?blobs=true" if files_metadata else ""), token)))


def eigener_download(repo: str, pfad: str, revision: str | None = None, token: str | None = None,
                     cache_dir: str = ".") -> str:
    stand = revision or "main"
    url = f"{HF}/{repo}/resolve/{urllib.parse.quote(stand, safe='')}/{urllib.parse.quote(pfad)}"
    roh = _holen(url, token, IL.MAX_BYTES)
    if len(roh) > IL.MAX_BYTES:
        raise IL.ImportFehler("Die Datei ist größer als 60 MB.")
    ziel = Path(cache_dir) / repo.replace("/", "--") / stand[:40] / pfad
    ziel.parent.mkdir(parents=True, exist_ok=True)
    ziel.write_bytes(roh)
    return str(ziel)


def _hub() -> tuple[Any, Any]:
    try:
        from huggingface_hub import HfApi, hf_hub_download
        return HfApi(), hf_hub_download
    except ImportError:
        return EigeneApi(), eigener_download


def laden(root: Path, adresse: str, name: str = "", aufgabe: str = IL.STANDARD_AUFGABE, token: str | None = None,
          datei: str = "", api: Any = None, herunterladen: Any = None, **kw: Any) -> dict[str, Any]:
    """Adresse lesen → Repo ansehen → Datei laden → wie eine Datei vom PC übernehmen (Prüfung + Prüfstand).

    `datei` ist die Wahl aus der Auswahl-Liste (Pfad im Repo) und gilt vor einem Pfad in der Adresse."""
    repo, pfad, stand = adresse_lesen(adresse)
    if offline():
        raise IL.ImportFehler("Knowlin ist offline gestellt – Laden von Hugging Face geht gerade nicht.")
    if datei:
        if not re.fullmatch(PFAD, datei) or ".." in datei.split("/"):
            raise IL.ImportFehler("Diese Datei verstehe ich nicht.")
        pfad = datei
    if api is None or herunterladen is None:
        hub_api, hub_laden = _hub()
        api = api or hub_api
        herunterladen = herunterladen or hub_laden
    try:
        info = api.model_info(repo, revision=stand, files_metadata=True, token=token or None)
    except Exception as exc:
        name_fehler = type(exc).__name__
        if "NotFound" in name_fehler or "Authorization" in name_fehler or "Gated" in name_fehler:
            raise IL.ImportFehler(f"„{repo}“ gibt es nicht oder es ist privat (dann den Hugging-Face-Schlüssel unter "
                                  "Training hinterlegen).") from exc
        raise IL.ImportFehler(f"Hugging Face antwortet nicht: {str(exc)[:160]}") from exc
    dateien = [{"pfad": s.rfilename, "mb": round((getattr(s, "size", None) or 0) / 1048576, 1)}
               for s in (getattr(info, "siblings", None) or []) if s.rfilename.lower().endswith(".onnx")]
    d = waehle(dateien, pfad)
    if d["mb"] * 1048576 > IL.MAX_BYTES:
        raise IL.ImportFehler(f"„{d['pfad']}“ ist {d['mb']:.0f} MB groß – mehr als 60 MB übernimmt Knowlin nicht.")
    lokal = herunterladen(repo, d["pfad"], revision=getattr(info, "sha", None) or stand, token=token or None,
                          cache_dir=str(Path(root) / "policies" / "hf-cache"))
    if Path(lokal).stat().st_size > IL.MAX_BYTES:
        raise IL.ImportFehler("Die Datei ist größer als 60 MB.")
    vorschlag = name or (repo.split("/")[1] if d["pfad"] in BEVORZUGT else Path(d["pfad"]).stem)
    herkunft = {"repo": repo, "pfad": d["pfad"], "stand": (getattr(info, "sha", None) or stand or "")[:40],
                "lizenz": _lizenz(info), "url": f"https://huggingface.co/{repo}"}
    return IL.importieren(root, lokal, vorschlag, aufgabe, herkunft=herkunft, **kw)


# ── Vorschläge (seit 0.38.31, „kann das nicht schon automatisch aufgelistet werden?“) ─────────────────────
SUCHWORTE = ("microduck", "micro-duck", "micro_duck")
_cache: dict[str, Any] = {"zeit": 0.0, "liste": None}
CACHE_S = 600


def _eintrag(m: Any) -> dict[str, Any] | None:
    onnx = [s.rfilename for s in (getattr(m, "siblings", None) or []) if s.rfilename.lower().endswith(".onnx")]
    if not onnx or not re.fullmatch(REPO, getattr(m, "id", "") or ""):
        return None
    geaendert = getattr(m, "last_modified", None) or getattr(m, "lastModified", None)
    return {"repo": m.id, "dateien": sorted(onnx, key=lambda p: (p not in BEVORZUGT, p))[:40],
            "downloads": int(getattr(m, "downloads", 0) or 0), "likes": int(getattr(m, "likes", 0) or 0),
            "lizenz": _lizenz(m), "geaendert": str(geaendert)[:10] if geaendert else None,
            "url": f"https://huggingface.co/{m.id}"}


def suchen(api: Any = None, token: str | None = None, neu: bool = False) -> list[dict[str, Any]]:
    """Öffentliche Microduck-Repos mit ONNX-Dateien auf Hugging Face – meistgeladene zuerst, 10 min zwischengespeichert.

    Nur eine Liste zum Auswählen: geladen wird erst beim Übernehmen, und jede Datei muss den Prüfstand bestehen."""
    import time

    if offline():
        raise IL.ImportFehler("Knowlin ist offline gestellt – die Suche auf Hugging Face geht gerade nicht.")
    if not neu and _cache["liste"] is not None and time.time() - _cache["zeit"] < CACHE_S:
        return _cache["liste"]
    if api is None:
        api = _hub()[0]
    gesehen: dict[str, dict[str, Any]] = {}
    for wort in SUCHWORTE:
        try:
            modelle = api.list_models(search=wort, sort="downloads", limit=60, token=token or None,
                                      expand=["siblings", "downloads", "likes", "lastModified", "cardData"])
            for m in modelle:
                e = _eintrag(m)
                if e and e["repo"] not in gesehen:
                    gesehen[e["repo"]] = e
        except Exception as exc:
            if not gesehen:
                raise IL.ImportFehler(f"Hugging Face antwortet nicht: {str(exc)[:160]}") from exc
    liste = sorted(gesehen.values(), key=lambda e: (-e["downloads"], -e["likes"], e["repo"].lower()))[:30]
    _cache.update(zeit=time.time(), liste=liste)
    return liste
