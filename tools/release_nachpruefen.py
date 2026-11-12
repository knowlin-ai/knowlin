"""Nach einem Release alles in einem Durchgang nachprüfen (seit 0.38.41, statt vieler Einzelschritte).

    python tools/release_nachpruefen.py 0.38.41 [--repo knowlin-ai/knowlin]

Prüft mit der GitHub-CLI (`gh`): Ist der Installer angehängt, und stimmt seine sha256 nach dem Herunterladen mit der
Angabe bei GitHub überein? Steht die Version auf PyPI? Was meldet die Update-Probe des Installer-Laufs zum Release
(Zeilen „B: …“)? Am Ende eine Zeile für Releaseplan und ZWEIG, z. B.
„✅ Release, Installer sha256 e1604d01…, PyPI 0.38.40, Update 0.38.39 → 0.38.40 bestanden, Start nach dem Installer 5 s“.
Rückgabewert 0 nur, wenn alles stimmt.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import urllib.error
import urllib.request


def gh(*args: str) -> str:
    return subprocess.run(["gh", *args], capture_output=True, text=True, check=True).stdout


def sha256_url(url: str) -> str:
    h = hashlib.sha256()
    with urllib.request.urlopen(url, timeout=600) as r:  # noqa: S310 – feste https-Adresse von GitHub
        for block in iter(lambda: r.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def pypi_da(version: str) -> bool:
    try:
        with urllib.request.urlopen(f"https://pypi.org/pypi/knowlin/{version}/json", timeout=30) as r:  # noqa: S310
            return r.status == 200
    except urllib.error.URLError:
        return False


def probe(repo: str, version: str) -> list[str]:
    """Zeilen „B: …“ aus dem Installer-Lauf zum Release-Ereignis."""
    laeufe = json.loads(gh("api", f"repos/{repo}/actions/workflows/installer.yml/runs?event=release&per_page=5"))
    for lauf in laeufe.get("workflow_runs", []):
        if lauf.get("display_title", "").endswith(version) or version in (lauf.get("head_branch") or ""):
            break
    else:
        lauf = (laeufe.get("workflow_runs") or [None])[0]
    if not lauf:
        return []
    jobs = json.loads(gh("api", f"repos/{repo}/actions/runs/{lauf['id']}/jobs"))["jobs"]
    job = next((j for j in jobs if j["name"] == "bauen"), None)
    if not job:
        return []
    log = gh("api", f"repos/{repo}/actions/jobs/{job['id']}/logs")
    return [m.group(1) for m in re.finditer(r"^\S+ (B: (?:installiert|Start|Update).*)$", log, re.M)]


def zusammenfassen(sha: str, pypi: bool, zeilen: list[str], version: str) -> tuple[bool, str]:
    alt = next((re.search(r"installiert (\S+)", z).group(1) for z in zeilen if "installiert" in z), "?")
    start = next((re.search(r"(\d+) s", z).group(1) for z in zeilen if "Start nach dem Installer" in z), None)
    durch = any("durchgelaufen" in z for z in zeilen)
    teile = ["✅ Release" if (pypi and durch) else "❌ Release", f"Installer sha256 {sha[:8]}…",
             f"PyPI {version}" if pypi else "PyPI fehlt",
             f"Update {alt} → {version} {'bestanden' if durch else 'NICHT bestanden'}"]
    if start:
        teile.append(f"Start nach dem Installer {start} s")
    return pypi and durch, ", ".join(teile)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("version")
    ap.add_argument("--repo", default="knowlin-ai/knowlin")
    a = ap.parse_args(argv)
    rel = json.loads(gh("api", f"repos/{a.repo}/releases/tags/v{a.version}"))
    setup = next((x for x in rel.get("assets", []) if x["name"] == f"Knowlin-Setup-{a.version}.exe"), None)
    if not setup:
        print("❌ Installer noch nicht angehängt")
        return 1
    soll = (setup.get("digest") or "").removeprefix("sha256:")
    ist = sha256_url(setup["browser_download_url"])
    print(f"sha256 GitHub {soll[:16]}…, heruntergeladen {ist[:16]}… – {'gleich' if soll == ist else 'ANDERS'}")
    zeilen = probe(a.repo, a.version)
    print("\n".join(zeilen) or "keine Zeilen der Update-Probe gefunden")
    ok, zeile = zusammenfassen(ist, pypi_da(a.version), zeilen, a.version)
    print(zeile)
    return 0 if ok and soll == ist else 1


if __name__ == "__main__":
    raise SystemExit(main())
