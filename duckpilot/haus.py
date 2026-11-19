"""Haushalt und Smart Home (seit 0.45): Licht, Saugroboter, Szenen und Meldungen – lokal über Home Assistant oder
direkt über die Hue Bridge.

Entscheidung des Maintainers (19.11.): „Home Assistant + Hue“ – beide Wege lokal im eigenen Netz, keine Herstellerwolke,
keine Marke fest eingebaut (bei Home Assistant nur die allgemeinen Gerätearten).

Leitplanken (nicht aufweichen):

- **Nur freigegebene Gerätearten**: Licht, Saugroboter, Szenen, Meldungen. **Nie** Schlösser, Alarmanlagen, Heizung,
  Garagentore, Rollläden oder Steckdosen – auch nicht, wenn ein Sprachmodell es vorschlägt. Die Freigabe steht nur hier
  (`ARTEN`, `DIENSTE`); was nicht drinsteht, wird weder angezeigt noch geschaltet. Eine Szene aus Home Assistant zählt
  nur, wenn sie ausschließlich Licht schaltet (ihre Liste `entity_id` wird geprüft) – sonst könnte eine Szene „Gute
  Nacht“ die Tür abschließen oder die Heizung drehen.
- **Lokal zuerst**: Adressen nur im eigenen Netz (private IP, `.local`, `.lan`, `.home.arpa`, Tailscale `.ts.net`,
  Rechnername ohne Punkt). Eine Adresse im Internet wird abgelehnt.
- **Schlüssel nur im Tresor** (Home-Assistant-Token, Hue-Schlüssel); in `<daten>/haus.json` stehen nur Adressen.
- Einrichten nur am PC (`remote.PC_ONLY`); schalten darf auch das gekoppelte Handy.
- Nach dem Not-Aus startet in der Sperre kein Saugroboter (die Laufzeit prüft das, `sperre`).
- Meldungen sind nur Text (höchstens 200 Zeichen), nie Bilder.

Home Assistant über die REST-Schnittstelle (`/api/states`, `/api/services/<art>/<dienst>`, Räume über `/api/template`).
Hue über die lokale Schnittstelle der Bridge (v1, `http://<bridge>/api/<schlüssel>/…`); gekoppelt wird mit dem Knopf an
der Bridge, ohne Konto bei Philips.
"""

from __future__ import annotations

import ipaddress
import json
import re
import time
import urllib.parse
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable

TRESOR_HA = "home_assistant_token"
TRESOR_HUE = "hue_schluessel"
DATEI = "haus.json"
WARTEN_S = 5.0
GUELTIG_S = 10.0
MELDUNG_MAX = 200

# Freigegeben – und nur das. Home-Assistant-Art → eigene Art
ARTEN = {"light": "licht", "vacuum": "sauger", "scene": "szene"}
# Je Art die erlaubten Handlungen → Dienst in Home Assistant
DIENSTE: dict[str, dict[str, str]] = {
    "licht": {"an": "turn_on", "aus": "turn_off"},
    "sauger": {"start": "start", "pause": "pause", "stopp": "stop", "heim": "return_to_base"},
    "szene": {"an": "turn_on"},
}
# Ausdrücklich nie (zur Erklärung und für den Test – maßgeblich ist die Freigabe oben)
NIE = ("lock", "alarm_control_panel", "climate", "water_heater", "cover", "switch", "siren", "valve", "humidifier",
       "fan", "button", "script", "automation", "camera", "media_player", "input_boolean", "remote", "lawn_mower")
NIE_TEXT = "Schlösser, Alarm, Heizung, Rollläden, Garagentore und Steckdosen schalte ich nie – das bleibt bei dir."

LOKALE_ENDUNGEN = (".local", ".lan", ".home", ".home.arpa", ".internal", ".fritz.box", ".ts.net")


Anfrage = Callable[[str, str, Any, dict[str, str]], Any]


def lokale_adresse(adresse: str, standard_port: int | None = None, nur_http: bool = False) -> str:
    """Adresse prüfen und vereinheitlichen (`http://host:port`). Nur im eigenen Netz; sonst ValueError."""
    a = str(adresse or "").strip().rstrip("/")
    if not a:
        raise ValueError("Adresse fehlt")
    if "://" not in a:
        a = "http://" + a
    teile = urllib.parse.urlsplit(a)
    if teile.scheme not in (("http",) if nur_http else ("http", "https")):
        raise ValueError("Adresse: nur http://" + ("" if nur_http else " oder https://"))
    if teile.username or teile.password or teile.query or teile.fragment or teile.path not in ("", "/"):
        raise ValueError("Adresse: nur Rechner und Port, ohne Pfad und ohne Zugangsdaten")
    host = (teile.hostname or "").lower()
    if not host or len(a) > 200:
        raise ValueError("Adresse unvollständig")
    try:
        ip = ipaddress.ip_address(host)
        lokal = ip.is_private or ip.is_link_local or ip.is_loopback
        if isinstance(ip, ipaddress.IPv4Address) and ip in ipaddress.ip_network("100.64.0.0/10"):
            lokal = True                                  # Tailscale
    except ValueError:
        if not re.fullmatch(r"[a-z0-9]([a-z0-9-]{0,62})(\.[a-z0-9]([a-z0-9-]{0,62}))*", host):
            raise ValueError("Adresse: ungültiger Rechnername") from None
        lokal = "." not in host or host.endswith(LOKALE_ENDUNGEN)
    if not lokal:
        raise ValueError("Nur Adressen im eigenen Netz (z. B. 192.168.… oder homeassistant.local) – keine Cloud")
    port = teile.port or standard_port
    netloc = f"[{host}]" if ":" in host else host
    return f"{teile.scheme}://{netloc}" + (f":{port}" if port else "")


def _anfrage(methode: str, url: str, daten: Any = None, kopf: dict[str, str] | None = None) -> Any:
    import urllib.request

    body = None if daten is None else json.dumps(daten).encode("utf-8")
    req = urllib.request.Request(url, data=body, method=methode,
                                 headers={"Content-Type": "application/json", "User-Agent": "Knowlin (Haushalt)",
                                          **(kopf or {})})
    with urllib.request.urlopen(req, timeout=WARTEN_S) as res:   # noqa: S310 – nur geprüfte Adressen im eigenen Netz
        roh = res.read(2 * 1024 * 1024).decode("utf-8")
    try:
        return json.loads(roh) if roh.strip() else None
    except ValueError:
        return roh


@dataclass
class Geraet:
    id: str
    name: str
    art: str                    # licht | sauger | szene
    quelle: str                 # ha | hue
    raum: str = ""
    an: bool | None = None
    zustand: str = ""

    def handlungen(self) -> list[str]:
        return list(DIENSTE[self.art])


# ── Home Assistant ──────────────────────────────────────────────────────────
class HomeAssistant:
    def __init__(self, adresse: str, token: str, anfrage: Anfrage | None = None) -> None:
        self.adresse = lokale_adresse(adresse, 8123)
        self.token = token
        self.anfrage = anfrage or _anfrage

    def _kopf(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}

    def pruefen(self) -> str:
        r = self.anfrage("GET", f"{self.adresse}/api/", None, self._kopf())
        return str(r.get("message") if isinstance(r, dict) else r or "")

    def _raeume(self, ids: list[str]) -> dict[str, str]:
        if not ids:
            return {}
        vorlage = "{% for e in " + json.dumps(ids) + " %}{{ e }}|{{ area_name(e) or '' }}\n{% endfor %}"
        try:
            r = self.anfrage("POST", f"{self.adresse}/api/template", {"template": vorlage}, self._kopf())
            out: dict[str, str] = {}
            for zeile in str(r or "").splitlines():
                eid, _, raum = zeile.partition("|")
                if eid.strip():
                    out[eid.strip()] = raum.strip()
            return out
        except Exception:  # noqa: BLE001 – ohne Räume geht es auch
            return {}

    def geraete(self) -> list[Geraet]:
        zustaende = self.anfrage("GET", f"{self.adresse}/api/states", None, self._kopf())
        if not isinstance(zustaende, list):
            raise ValueError("Home Assistant hat keine Geräteliste geliefert")
        alle = {str(z.get("entity_id", "")): z for z in zustaende if isinstance(z, dict)}
        out: list[Geraet] = []
        for eid, z in alle.items():
            domain = eid.split(".", 1)[0]
            art = ARTEN.get(domain)
            if art is None:
                continue
            attr = z.get("attributes") or {}
            if art == "szene":
                drin = attr.get("entity_id")
                if not isinstance(drin, list) or not drin or any(str(x).split(".", 1)[0] != "light" for x in drin):
                    continue                              # Szene schaltet mehr als Licht (oder sagt nicht, was) → nie
            s = str(z.get("state", ""))
            out.append(Geraet(id=f"ha:{eid}", name=str(attr.get("friendly_name") or eid)[:60], art=art, quelle="ha",
                              an=(s == "on") if art == "licht" else None, zustand=s[:30]))
        raeume = self._raeume([g.id[3:] for g in out])
        for g in out:
            g.raum = raeume.get(g.id[3:], "")[:40]
        return out

    def schalten(self, eid: str, art: str, aktion: str) -> None:
        dienst = DIENSTE[art][aktion]
        domain = {v: k for k, v in ARTEN.items()}[art]
        if eid.split(".", 1)[0] != domain:
            raise ValueError("Gerät passt nicht zur Art")
        self.anfrage("POST", f"{self.adresse}/api/services/{domain}/{dienst}", {"entity_id": eid}, self._kopf())

    def melden(self, dienst: str, text: str) -> None:
        if not re.fullmatch(r"[a-z0-9_]{1,60}", dienst):
            raise ValueError("Meldedienst: z. B. mobile_app_mein_handy")
        self.anfrage("POST", f"{self.adresse}/api/services/notify/{dienst}",
                     {"title": "Knowlin", "message": text[:MELDUNG_MAX]}, self._kopf())


# ── Hue Bridge ──────────────────────────────────────────────────────────────
class HueBridge:
    def __init__(self, adresse: str, schluessel: str = "", anfrage: Anfrage | None = None) -> None:
        self.adresse = lokale_adresse(adresse, nur_http=True)
        self.schluessel = schluessel
        self.anfrage = anfrage or _anfrage

    def koppeln(self) -> str | None:
        """Schlüssel holen – klappt nur in den 30 s nach dem Druck auf den Knopf der Bridge. None = Knopf nicht gedrückt."""
        r = self.anfrage("POST", f"{self.adresse}/api", {"devicetype": "knowlin#pc"}, {})
        eintrag = r[0] if isinstance(r, list) and r else {}
        if "success" in eintrag:
            return str(eintrag["success"]["username"])
        fehler = eintrag.get("error") or {}
        if fehler.get("type") == 101:
            return None
        raise ValueError(f"Hue Bridge: {fehler.get('description') or 'unerwartete Antwort'}")

    def _basis(self) -> str:
        if not re.fullmatch(r"[\w\-]{10,80}", self.schluessel or ""):
            raise ValueError("Hue Bridge nicht gekoppelt")
        return f"{self.adresse}/api/{self.schluessel}"

    @staticmethod
    def _pruefen(r: Any) -> Any:
        if isinstance(r, list) and r and isinstance(r[0], dict) and "error" in r[0]:
            raise ValueError(f"Hue Bridge: {r[0]['error'].get('description', 'Fehler')}")
        return r

    def geraete(self) -> list[Geraet]:
        lichter = self._pruefen(self.anfrage("GET", f"{self._basis()}/lights", None, {})) or {}
        gruppen = self._pruefen(self.anfrage("GET", f"{self._basis()}/groups", None, {})) or {}
        szenen = self._pruefen(self.anfrage("GET", f"{self._basis()}/scenes", None, {})) or {}
        raum_von: dict[str, str] = {}
        raum_name: dict[str, str] = {}
        for gid, g in (gruppen.items() if isinstance(gruppen, dict) else []):
            if g.get("type") == "Room":
                raum_name[str(gid)] = str(g.get("name", ""))[:40]
                for lid in g.get("lights", []):
                    raum_von[str(lid)] = str(g.get("name", ""))[:40]
        out = [Geraet(id=f"hue:licht:{lid}", name=str(l.get("name", lid))[:60], art="licht", quelle="hue",
                      raum=raum_von.get(str(lid), ""), an=bool((l.get("state") or {}).get("on")),
                      zustand="an" if (l.get("state") or {}).get("on") else "aus")
               for lid, l in (lichter.items() if isinstance(lichter, dict) else [])]
        for sid, s in (szenen.items() if isinstance(szenen, dict) else []):
            gruppe = str(s.get("group") or "")
            if s.get("type") == "GroupScene" and gruppe in raum_name:
                out.append(Geraet(id=f"hue:szene:{gruppe}:{sid}", name=str(s.get("name", sid))[:60], art="szene",
                                  quelle="hue", raum=raum_name[gruppe]))
        return out

    def schalten(self, teil: str, art: str, aktion: str) -> None:
        if art == "licht":
            if not re.fullmatch(r"\d{1,4}", teil):
                raise ValueError("Unbekanntes Licht")
            self._pruefen(self.anfrage("PUT", f"{self._basis()}/lights/{teil}/state", {"on": aktion == "an"}, {}))
        elif art == "szene":
            m = re.fullmatch(r"(\d{1,4}):([\w\-]{1,40})", teil)
            if not m:
                raise ValueError("Unbekannte Szene")
            self._pruefen(self.anfrage("PUT", f"{self._basis()}/groups/{m.group(1)}/action", {"scene": m.group(2)}, {}))
        else:
            raise ValueError("Über die Hue Bridge gibt es nur Licht und Szenen")


# ── Alles zusammen ──────────────────────────────────────────────────────────
class Haus:
    """Einstellungen (Adressen), Tresor und beide Wege. `tresor_lesen`/`tresor_schreiben` sind austauschbar (Tests)."""

    def __init__(self, ordner: Path, tresor_lesen: Callable[[str], str | None],
                 tresor_schreiben: Callable[[str, str | None], None], anfrage: Anfrage | None = None) -> None:
        self.ordner = ordner
        self.lesen, self.schreiben = tresor_lesen, tresor_schreiben
        self.anfrage = anfrage or _anfrage
        self._cache: tuple[float, list[Geraet], list[str]] | None = None

    # Einstellungen ------------------------------------------------------
    def einstellungen(self) -> dict[str, Any]:
        try:
            d = json.loads((self.ordner / DATEI).read_text(encoding="utf-8"))
            return d if isinstance(d, dict) else {}
        except (OSError, ValueError):
            return {}

    def _speichern(self, **neu: Any) -> None:
        d = {**self.einstellungen(), **neu}
        d = {k: v for k, v in d.items() if v not in (None, "")}
        self.ordner.mkdir(parents=True, exist_ok=True)
        (self.ordner / DATEI).write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
        self._cache = None

    def ha(self) -> HomeAssistant | None:
        a, t = self.einstellungen().get("ha_adresse"), self.lesen(TRESOR_HA)
        return HomeAssistant(a, t, self.anfrage) if a and t else None

    def hue(self) -> HueBridge | None:
        a, k = self.einstellungen().get("hue_adresse"), self.lesen(TRESOR_HUE)
        return HueBridge(a, k, self.anfrage) if a and k else None

    def ha_verbinden(self, adresse: str, token: str, melden: str = "") -> str:
        token = str(token or "").strip()
        if not re.fullmatch(r"[\w\-.]{20,600}", token):
            raise ValueError("Langlebiges Zugriffstoken aus Home Assistant (Profil → Sicherheit) einfügen")
        if melden and not re.fullmatch(r"[a-z0-9_]{1,60}", melden):
            raise ValueError("Meldedienst: z. B. mobile_app_mein_handy (ohne „notify.“)")
        ha = HomeAssistant(adresse, token, self.anfrage)
        antwort = ha.pruefen()                         # Fehler (falsches Token, nicht erreichbar) gehen nach oben
        self.schreiben(TRESOR_HA, token)
        self._speichern(ha_adresse=ha.adresse, ha_melden=melden)
        return antwort

    def hue_koppeln(self, adresse: str) -> bool:
        bridge = HueBridge(adresse, "", self.anfrage)
        schluessel = bridge.koppeln()
        if schluessel is None:
            self._speichern(hue_adresse=bridge.adresse)   # Adresse merken, Kopplung noch offen
            return False
        self.schreiben(TRESOR_HUE, schluessel)
        self._speichern(hue_adresse=bridge.adresse)
        return True

    def trennen(self, weg: str) -> None:
        if weg == "ha":
            self.schreiben(TRESOR_HA, None)
            d = self.einstellungen()
            d.pop("ha_adresse", None)
            d.pop("ha_melden", None)
        else:
            self.schreiben(TRESOR_HUE, None)
            d = self.einstellungen()
            d.pop("hue_adresse", None)
        self.ordner.mkdir(parents=True, exist_ok=True)
        (self.ordner / DATEI).write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        self._cache = None

    def stand(self) -> dict[str, Any]:
        e = self.einstellungen()
        return {"ha": {"adresse": e.get("ha_adresse", ""), "verbunden": self.ha() is not None,
                       "melden": e.get("ha_melden", "")},
                "hue": {"adresse": e.get("hue_adresse", ""), "verbunden": self.hue() is not None},
                "nie": NIE_TEXT}

    # Geräte --------------------------------------------------------------
    def geraete(self, neu: bool = False) -> tuple[list[Geraet], list[str]]:
        """Alle freigegebenen Geräte beider Wege und Fehler je Weg (ehrlich, statt still leer)."""
        if not neu and self._cache and time.monotonic() - self._cache[0] < GUELTIG_S:
            return self._cache[1], self._cache[2]
        out: list[Geraet] = []
        fehler: list[str] = []
        for name, weg in (("Home Assistant", self.ha()), ("Hue Bridge", self.hue())):
            if weg is None:
                continue
            try:
                out += weg.geraete()
            except Exception as exc:  # noqa: BLE001 – ein Weg fällt aus, der andere bleibt
                fehler.append(f"{name} nicht erreichbar: {str(exc)[:120]}")
        out.sort(key=lambda g: (g.art != "licht", g.raum or "~", g.name.lower()))
        self._cache = (time.monotonic(), out, fehler)
        return out, fehler

    def geraet(self, gid: str) -> Geraet | None:
        return next((g for g in self.geraete()[0] if g.id == gid), None) or \
            next((g for g in self.geraete(neu=True)[0] if g.id == gid), None)

    def schalten(self, gid: str, aktion: str) -> Geraet:
        """Nur ein Gerät aus der freigegebenen Liste und nur eine erlaubte Handlung – sonst ValueError."""
        g = self.geraet(str(gid))
        if g is None:
            raise ValueError("Dieses Gerät kenne ich nicht – oder es gehört nicht zu dem, was ich schalten darf. "
                             + NIE_TEXT)
        if aktion not in DIENSTE[g.art]:
            raise ValueError(f"{g.name}: erlaubt ist {', '.join(DIENSTE[g.art])}")
        if g.quelle == "ha":
            weg = self.ha()
            if weg is None:
                raise ValueError("Home Assistant ist nicht verbunden")
            weg.schalten(g.id[3:], g.art, aktion)
        else:
            weg2 = self.hue()
            if weg2 is None:
                raise ValueError("Hue Bridge ist nicht gekoppelt")
            weg2.schalten(g.id.split(":", 2)[2], g.art, aktion)
        self._cache = None
        if g.art == "licht":
            g.an = aktion == "an"
        return g

    def finden(self, text: str, art: str | None = None) -> list[Geraet]:
        """Geräte zu einem Satz: Raum- oder Gerätename kommt darin vor („Licht im Wohnzimmer“). Ohne Treffer: alle der Art."""
        t = text.lower()
        kandidaten = [g for g in self.geraete()[0] if art is None or g.art == art]
        treffer = [g for g in kandidaten if g.name.lower() in t or (g.raum and g.raum.lower() in t)]
        if treffer:
            namen = [g for g in treffer if g.name.lower() in t]
            return namen or treffer
        return kandidaten

    def melden(self, text: str) -> bool:
        """Meldung über Home Assistant aufs Handy – nur wenn ein Meldedienst eingetragen ist. Nur Text."""
        dienst = self.einstellungen().get("ha_melden")
        weg = self.ha()
        if not dienst or weg is None:
            return False
        weg.melden(str(dienst), " ".join(str(text).split()))
        return True


def als_dict(g: Geraet) -> dict[str, Any]:
    return {**asdict(g), "handlungen": g.handlungen()}


# ── Ohne Sprachmodell: „Licht im Wohnzimmer an“, „Starte den Sauger“ ───────
LICHT = re.compile(r"\b(licht|lampe\w*|beleuchtung|light|lights|lamp)\b")
SAUGER = re.compile(r"\b(saug\w*|staubsaug\w*|vacuum|robot vacuum|dreame|roborock)\b")
SZENE = re.compile(r"\b(szene|scene)\b")
AN = re.compile(r"\b(an|ein|anmachen|einschalten|anschalten|on|turn on|switch on)\b")
AUS = re.compile(r"\b(aus|ausmachen|ausschalten|off|turn off|switch off)\b")
START = re.compile(r"\b(start\w*|los|saug\w* los|anwerfen|begin|go)\b")
HEIM = re.compile(r"\b(zur (ladestation|station|basis)|nach hause|heim|zurück zur station|back to (base|the dock)|dock)\b")
STOPP = re.compile(r"\b(stopp?\w*|anhalten|halt|pause|pausier\w*)\b")
VERBOTEN = re.compile(r"\b(\w*tür(e|en)?|\w*schloss|\w*schlösser|abschließ\w*|aufschließ\w*|\w*alarm\w*|\w*heizung\w*|"
                      r"\w*thermostat\w*|rollladen|rollläden|rollos?|\w*garag\w*|\w*steckdose\w*|lock|unlock|doors?|"
                      r"heating|garage|blinds|shutters?|outlets?|plugs?)\b")


def befehl(text: str) -> dict[str, Any] | None:
    """Ein Haushaltsbefehl ohne Sprachmodell → {"art", "aktion", "text"} oder {"nie": True}; None = kein Befehl."""
    t = " " + text.lower().strip(" ?!.") + " "
    if VERBOTEN.search(t) and (AN.search(t) or AUS.search(t) or re.search(r"\b(öffne|schließ|abschließ|aufschließ|"
                                                                          r"entsperr|sperr|mach|stell|dreh|open|close|"
                                                                          r"set|turn|lock|unlock|arm|disarm)\w*", t)):
        return {"nie": True}
    if SAUGER.search(t):
        aktion = "heim" if HEIM.search(t) else "stopp" if STOPP.search(t) else "start" if (START.search(t) or AN.search(t)) else None
        return {"art": "sauger", "aktion": aktion, "text": text} if aktion else None
    if LICHT.search(t):
        aktion = "aus" if AUS.search(t) else "an" if AN.search(t) else None
        return {"art": "licht", "aktion": aktion, "text": text} if aktion else None
    if SZENE.search(t) and (AN.search(t) or re.search(r"\b(aktivier\w*|starte?|activate)\b", t)):
        return {"art": "szene", "aktion": "an", "text": text}
    return None


# ── Tresor ──────────────────────────────────────────────────────────────────
def tresor_lesen(wer: str) -> str | None:
    from . import settings as S

    kr = S._keyring()
    if kr is None:
        return None
    try:
        return kr.get_password(S.KEYRING_SERVICE, wer) or None
    except Exception:  # noqa: BLE001 – nicht lesbar = nicht verbunden
        return None


def tresor_schreiben(wer: str, wert: str | None) -> None:
    """Schlüssel ablegen (oder mit None löschen). Ohne Tresor gibt es keine Verbindung – nie in eine Datei."""
    from . import settings as S

    kr = S._keyring()
    if kr is None:
        if wert is None:
            return
        raise RuntimeError(f"Kein {S.vault_name()} verfügbar – ohne ihn speichere ich keinen Schlüssel.")
    if wert is None:
        try:
            kr.delete_password(S.KEYRING_SERVICE, wer)
        except Exception:  # noqa: BLE001 – war schon weg
            pass
        return
    kr.set_password(S.KEYRING_SERVICE, wer, wert)
