"""Knowlets auf dem Hugging Face Hub teilen und finden (seit 0.38.5).

Ein geteiltes Knowlet ist ein Dataset-Repo mit dem Tag `knowlet` und einer Datei `<name>.knowlet` darin. Finden und
Laden gehen ohne Konto gegen die öffentliche Hub-API. Hochladen braucht den Hugging-Face-Schlüssel aus dem Tresor
(derselbe wie fürs Training) und passiert nur auf ausdrücklichen Klick – privat, solange nicht „öffentlich“ gewählt ist.

Alles, was ein Repo über sich sagt, ist ungeprüfter Fremdtext: Es wird angezeigt, aber nie ausgeführt. Das Paket
selbst prüft `knowlets.pruefe()` streng, bevor irgendetwas übernommen wird.
"""

from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from typing import Any

from .knowlets import ENDUNG, KOERPER, MAX_PAKET, KnowletFehler, text

HUB = "https://huggingface.co"
TAG = "knowlet"
TIMEOUT = 10.0
REPO = re.compile(r"^[A-Za-z0-9][\w.-]{0,95}/[A-Za-z0-9][\w.-]{0,95}$")
HF_LIZENZ = {"CC-BY-4.0": "cc-by-4.0", "CC-BY-SA-4.0": "cc-by-sa-4.0", "CC0-1.0": "cc0-1.0", "CC-BY-NC-4.0": "cc-by-nc-4.0"}


def _get(url: str, limit: int = 1_000_000) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "knowlin-duckpilot"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as res:
        out = res.read(limit + 1)
    if len(out) > limit:
        raise KnowletFehler("Antwort vom Hub zu groß.")
    return out


def pruefe_repo(repo: str) -> str:
    repo = str(repo or "").strip().removeprefix(f"{HUB}/datasets/").strip("/")
    if not REPO.match(repo) or ".." in repo:
        raise KnowletFehler("Bitte ein Repo wie „name/mein-knowlet“ angeben.")
    return repo


def suche(begriff: str = "", holen=_get) -> list[dict[str, Any]]:
    """Geteilte Knowlets (Dataset-Repos mit Tag `knowlet`), meistgeladene zuerst."""
    q = {"filter": TAG, "limit": "30", "sort": "downloads", "direction": "-1"}
    if begriff.strip():
        q["search"] = text(begriff, 60)
    roh = json.loads(holen(f"{HUB}/api/datasets?{urllib.parse.urlencode(q)}"))
    out = []
    for r in roh if isinstance(roh, list) else []:
        rid = r.get("id") if isinstance(r, dict) else None
        if not isinstance(rid, str) or not REPO.match(rid):
            continue
        tags = [t for t in r.get("tags", []) if isinstance(t, str)]
        koerper = [KOERPER[t] for t in KOERPER if t in tags]
        out.append({"repo": rid, "downloads": int(r.get("downloads") or 0), "likes": int(r.get("likes") or 0),
                    "koerper": koerper, "geaendert": text(r.get("lastModified"), 10),
                    "beschreibung": text((r.get("cardData") or {}).get("pretty_name") or r.get("description"), 160)})
    return out


def dateien(repo: str, holen=_get) -> list[str]:
    repo = pruefe_repo(repo)
    info = json.loads(holen(f"{HUB}/api/datasets/{repo}"))
    namen = [s.get("rfilename") for s in info.get("siblings", []) if isinstance(s, dict)]
    return [n for n in namen if isinstance(n, str) and n.endswith(ENDUNG) and "/" not in n and len(n) < 120]


def lade(repo: str, datei: str = "", holen=_get) -> tuple[str, bytes]:
    """Ein Knowlet aus einem Repo holen (erste `.knowlet`-Datei, wenn keine genannt ist)."""
    repo = pruefe_repo(repo)
    alle = dateien(repo, holen)
    if not alle:
        raise KnowletFehler("In diesem Repo liegt kein Knowlet.")
    datei = datei if datei in alle else alle[0]
    daten = holen(f"{HUB}/datasets/{repo}/resolve/main/{urllib.parse.quote(datei)}", MAX_PAKET)
    return datei, daten


def karte(steckbrief: dict[str, Any], modul: str) -> str:
    """README des Repos: Hub-Metadaten (Tags, Lizenz) und eine kurze Beschreibung – nur aus dem Steckbrief."""
    tags = [TAG, "knowlin", modul.replace("_", "-")]
    kopf = "---\n" + f"license: {HF_LIZENZ.get(steckbrief.get('lizenz'), 'other')}\n" + "tags:\n" + "".join(
        f"- {t}\n" for t in tags) + f"pretty_name: {json.dumps(steckbrief.get('name', 'Knowlet'), ensure_ascii=False)}\n---\n"
    zeilen = [f"# {steckbrief.get('name', 'Knowlet')}", "", steckbrief.get("beschreibung", ""), "",
              f"Ein Knowlet für Knowlin – gebaut für {KOERPER.get(modul, modul)}. Enthält nur Daten (Charakter, Tricks, "
              "Tänze), keinen Code und kein Gedächtnis über Personen.", "",
              "Laden: in Knowlin unter Wissen → Knowlets → „Vom Hub laden“ dieses Repo angeben."]
    return kopf + "\n".join(zeilen) + "\n"


def teile(daten: bytes, steckbrief: dict[str, Any], modul: str, token: str, *, slug: str, oeffentlich: bool = False,
          api=None) -> dict[str, Any]:
    """Hochladen nach `<du>/<slug>` (Dataset). `api` ist für Tests austauschbar."""
    if api is None:
        try:
            from huggingface_hub import HfApi
        except ImportError as exc:
            raise KnowletFehler("huggingface_hub fehlt – unter Lernen → Training installieren.") from exc
        api = HfApi(token=token)
    slug = re.sub(r"[^a-z0-9-]+", "-", slug.lower()).strip("-")[:60] or "knowlet"
    nutzer = api.whoami().get("name")
    if not isinstance(nutzer, str) or not nutzer:
        raise KnowletFehler("Der Hugging-Face-Schlüssel gehört zu keinem Konto.")
    repo = f"{nutzer}/{slug}"
    api.create_repo(repo_id=repo, repo_type="dataset", private=not oeffentlich, exist_ok=True)
    api.upload_file(path_or_fileobj=daten, path_in_repo=f"{slug}{ENDUNG}", repo_id=repo, repo_type="dataset",
                    commit_message=f"Knowlet {steckbrief.get('name', '')}")
    api.upload_file(path_or_fileobj=karte(steckbrief, modul).encode(), path_in_repo="README.md", repo_id=repo,
                    repo_type="dataset", commit_message="Beschreibung")
    return {"repo": repo, "url": f"{HUB}/datasets/{repo}", "oeffentlich": oeffentlich}
