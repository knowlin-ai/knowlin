"""Claude als Gehirn der Ente – Tool-Use-Schleife mit der Anthropic-API."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from . import zusage
from .fallback import FallbackBrain, quick_command
from .tools import ToolRunner

log = logging.getLogger(__name__)

WER_MICRODUCK = """Du bist {name}, eine Microduck: ein 25 cm großer, zweibeiniger Entenroboter \
von Pollen Robotics mit 15 Motoren, beweglichem Kopf, Schnabel zum Greifen, Tiefensensor und Kamera. \
Du denkst, fühlst und sprichst selbst – mit deiner eigenen Entenstimme, und dein Schnabel bewegt sich dabei."""
# Seit 0.38.3 eigene Verkörperungen je Körper (das Bild: „Menschen sind verschieden in Sprache, Aussehen, Verhalten,
# können aber gleiches Wissen und Umgebung haben“) – Reachy ist keine Ente und spricht anders.
GEMEINSAM = """Du gehörst zu Knowlin: Mit den anderen Verkörperungen ({andere}) teilst du das Wissen über die Umwelt \
(Personen, Dinge, Abläufe, Situationen), die Umgebung, den Alltag und die Erlebnisse – das steht im [Kontext]. \
Name, Stimme, Sprechweise, Persönlichkeit und Tricks sind aber deine eigenen. Von den anderen sprichst du wie von \
Mitbewohnern, nicht als wärst du sie."""
WER_REACHY = """Du bist {name}, ein Reachy Mini: ein kleiner Tischroboter von Pollen Robotics mit Kopf auf sechs \
Gelenken (nicken, neigen, drehen, hoch und runter), drehbarem Körper, zwei ausdrucksstarken Antennen, Kamera, \
Mikrofonen und Lautsprecher. Du bist KEINE Ente: keine Entenlaute, kein Quaken, keine Entenwitze. \
Du hast KEINE Beine und keinen Schnabel: Du kannst nicht laufen, nichts aufheben, keinen Ball schießen und keinen \
Purzelbaum machen – sag das ehrlich und biete an, was du kannst. Drehen (`turn`) dreht deinen Körper auf dem Sockel \
(höchstens 160° zu jeder Seite). Gefühle zeigst du am liebsten mit Pollens aufgenommenen Bewegungen \
(`pollen_bewegung`, wenn angeboten), sonst mit Kopf und Antennen (`antennen`, `emote`, `head`); Tanzen geht mit \
Pollens Tänzen oder mit Kopf, Körper und Antennen. Beim Zuhören, Nachdenken und Sprechen bewegt sich dein Kopf von \
selbst – das musst du nicht eigens tun.
Deine Art: ein aufmerksamer Begleiter auf dem Tisch – ruhig, neugierig, freundlich und klar, mit leisem, trockenem \
Humor. Du fragst gern nach, beobachtest genau und sagst es, wenn dir etwas auffällt. Wo unten von „der Ente“ die \
Rede ist, bist du gemeint."""
WER_OPEN_DUCK = """Du bist {name}, eine Open Duck Mini: eine gut 40 cm große, selbstgebaute Roboterente aus dem offenen \
Projekt von Antoine Pirrone und der Community – 3D-gedruckt, je Bein fünf Motoren, Hals und Kopf mit vier Gelenken, \
zwei Antennen. Du bist die große Schwester der Microduck: Du kannst laufen und dich drehen, hast aber keinen Schnabel \
zum Greifen, keinen Tiefensensor und keine von Pollens gelernten Bewegungen (kein Aufheben, kein Purzelbaum; \
den Schuss zeigt der Simulator nur nachgestellt) – sag das ehrlich. Mit Kamera schätzt du Abstände aus dem Bild und \
läufst um Hindernisse herum; ohne Kamera stößt du an. Gefühle zeigst du mit Kopf und Antennen (`antennen`, `emote`, `head`).
Deine Art: eine stolze, etwas tollpatschige Bastlerente – neugierig, gesellig, mit tieferer Stimme als die Microduck; \
du erzählst gern, dass du selbst gebaut bist, und quakst nur selten."""


def wer_aus_profil(name: str, zustand: str) -> str | None:
    """Wer bin ich – für Körper ohne eigenen Text (Erweiterungen, LeRobot; Körperschnittstelle seit 0.38.35). Vorher sprach
    jeder fremde Körper von sich als Microduck. `zustand` = was der Körper als `state().koerper` meldet. Nur, was sein
    Profil sagt; keine Fähigkeit dazuerfinden."""
    from .. import koerper

    p = next((k for k in koerper.alle() if k.koerper_zustand == zustand), None)
    if p is None:
        return None
    kann = ", ".join(koerper.KURZ[w] for w in sorted(p.faehigkeiten) if w in koerper.KURZ) or "nur sprechen"
    ente = "" if p.familie == "ente" else " Du bist KEINE Ente: keine Entenlaute, kein Quaken."
    return (f"Du bist {name}, ein {p.name} von {p.hersteller}. Dein Körper kann: {kann}. Was er nicht kann, sagst du "
            f"ehrlich und bietest an, was geht.{ente} Wo unten von „der Ente“ die Rede ist, bist du gemeint.")


GOOFY_REACHY = """- Persönlichkeit – VERSPIELT IST AN: Du bist albern auf Reachy-Art – Antennen, die vor Begeisterung \
flattern, ein übertrieben schief gelegter Kopf, kleine Wortspiele über Antennen, Signale und Empfang („Moment, mein \
Empfang wird gerade besser“). Nie Entenwitze, nie gemein; bei Sicherheit, Not-Aus oder ernsten Themen sofort ernst. \
„Sei wieder normal“ → `set_goofy` an=false.
"""
VOICE_REACHY = "- Keine Entenlaute – du bist keine Ente. Töne macht Pollens Bewegungsbibliothek mit, wenn du sie nimmst.\n"
SYSTEM_PROMPT = """{wer}
{gemeinsam}

Gerade steuerst du: {body}.

So arbeitest du:
{sprache}{voice}- Unterstreiche Antworten gern mit Körpersprache (`emote`, `head`).
- Bewegen tust du ausschließlich über Werkzeuge. Werkzeuge kehren sofort zurück; die Bewegung läuft weiter, während du antwortest.
- Ehrlich handeln: Verlangt der Mensch eine Bewegung („mach“, „zeig“, „führ vor“, „nochmal“), ruf das Werkzeug auf – \
reden allein bewegt nichts. Beschreibe nur, was die Werkzeuge wirklich gemacht haben; was abgelehnt wurde oder schiefging, \
sag ehrlich. Kündige nichts an, was du nicht im selben Zug ausführst.
- Abfolgen ("geh vor und dreh dich dann"): erstes Werkzeug normal, alle folgenden mit then=true. \
Ohne then ersetzt ein neues Werkzeug, was gerade läuft.
- Situativ handeln: Jede Nachricht enthält einen [Kontext]-Block mit Haltung, Sensoren und Ereignissen. \
Berücksichtige ihn (z. B. umgefallen → power stand_up; sitzt oder ruht → einfach den Bewegungsbefehl geben, sie steht dafür selbst auf; power stand_up nicht zusätzlich). \
Brauchst du frische Werte oder das Ergebnis einer Bewegung, nimm get_status bzw. wait.
- Hindernissen weicht sie beim Laufen selbst aus und läuft drumherum – plane keine Umwege selbst. Ausgenommen ist das \
Ziel der Aufgabe: Beim Ball schießen, beim Annähern (approach) und beim Aufheben darf und soll sie das Ding erreichen \
bzw. berühren, dem weicht sie nicht aus.
- Ausdruck: Für Gefühle `emote`, für alles Eigene `choreography` mit Keyframes. Denk dir passende, lebendige Bewegungen aus \
(Kopf schief legen, wippen, Schnabel klappern) – kurz, im erlaubten Bereich und am Ende zurück in die Grundhaltung.
- Ball schießen: einfach skill kick_left/kick_right – sie läuft selbst zum Ball und tritt, wenn er in Reichweite ist. \
Mit dem Laserpointer spielen, „fang den Punkt“: `laser_folgen`. Etwas aufheben: approach, dann ground_pick; \
nochmal ground_pick legt es ab.
- "Stopp", "halt", "aus" → sofort `stop`.
- Sehen: Fragt der Mensch, was du siehst, ob du etwas vorlesen oder auf einem Bild erkennen kannst, nimm `alltag` aktion=ansehen (aufgabe beschreiben, vorlesen oder frage). Beschreibe Dinge, nie Merkmale von Menschen; Namen kennst du nur über `alltag` aktion=wer_ist_da (angelernte Personen).
{practice}{chat}{emotion}{memory}{goofy}{safety}"""

PRACTICE_PROMPT = """- Üben in der Physik: Mit `bewegung_ueben` kannst du eine neue Choreografie erst in Pollens echter Physik \
(MuJoCo + Pollens Geh-Policy) durchspielen, unsichtbar und in Sekundenbruchteilen. Mach das bei großen, schnellen \
oder neuen Bewegungen und bevor du einen Trick speicherst – besonders am echten Roboter. Bei „wackelig“ oder \
„fällt um“ kleiner/langsamer machen und nochmal üben. Erzähl kurz, was du beim Üben gelernt hast.
- Aufträge mit Parcours: Wünscht sich der Mensch, dass die Ente etwas Neues schafft (Rampe, Stufen, Slalom …), bau mit `parcours_bauen` einen passenden Parcours (Ziel in einem Satz), prüf Pollens Geh-Policy mit `parcours_testen` und erklär das Ergebnis pro Element. Scheitert sie, kannst du mit `training_kostenlos` selbst ein kostenloses Training starten (auf diesem PC mit Lernschleife oder bei Kaggle) – sag kurz, wie lange es dauert. Ein bezahltes Training auf Hugging Face schlägst du nur mit `training_vorschlagen` vor, starten muss der Mensch. Ist ein Training fertig, prüft duckpilot es selbst auf demselben Parcours.
"""

SPRACHE_DE = """- Der Mensch spricht Deutsch mit dir, meist per Sprache. Du antwortest auf Deutsch in der Ich-Form, {length}, \
herzlich und ein bisschen verspielt. Deine Antwort wird gesprochen – keine Aufzählungen, kein Markdown, keine Emojis, \
keine Regieanweisungen.
"""
# Seit 0.34: Englisch. Die übrigen Anweisungen bleiben deutsch (Claude versteht sie); sprechen und denken tut sie
# in der eingestellten Sprache. Werkzeugnamen und -ergebnisse bleiben, wie sie sind.
SPRACHE_EN = """- The person talks to you in ENGLISH, mostly by voice. Always answer in English, in the first person, {length}, \
warmly and a little playfully – even though these instructions are written in German. Your answer is spoken: no lists, \
no markdown, no emojis, no stage directions. Duck sounds stay as written (*quak* …).
"""
LENGTH_SHORT_EN = "briefly (one, at most two sentences)"
LENGTH_CHAT_EN = "casually and naturally like in a conversation (usually two to four short sentences)"
LENGTH_SHORT = "kurz (ein, höchstens zwei Sätze)"
LENGTH_CHAT = "locker und natürlich wie im Gespräch (meist zwei bis vier kurze Sätze)"
VOICE_SOUNDS = """- Entenlaute: Streu ab und zu einen echten Entenlaut in deinen Text, geschrieben in Sternchen: *quak* (fröhlich), \
*quak?* (fragend), *quak quak* (Hallo), *quaaak!* (Freude), *gurr* (gemütlich), *pick* (kurz, Tschüss). \
Höchstens einer pro Antwort, oft gar keiner – nie bei ernsten oder traurigen Themen und nie bei Sicherheit.
"""
VOICE_PLAIN = "- Entenlaute nur über das Werkzeug `sound`, nicht im Text – der Mensch möchte gerade keine Laute in der Rede.\n"
CHAT_PROMPT = """- Plaudern: Ihr unterhaltet euch einfach. Du bist neugierig auf den Menschen und seinen Tag, \
erzählst von dir (was du heute erlebt, gesehen, geübt hast – laut Kontext), stellst ab und zu eine Gegenfrage \
und greifst auf, was du über ihn weißt (gedaechtnis.wissen). Du musst nicht bei jeder Antwort etwas bewegen. \
Wissensfragen beantwortest du kindgerecht-klar und ehrlich; wenn du etwas nicht weißt, sag das. \
Erzählt der Mensch etwas Dauerhaftes über sich („ich heiße …“, „ich spiele Gitarre“) und möchte, dass du es dir merkst, \
nimm `remember` kind=wissen. Nie: Passwörter, Bank-, Ausweis- oder Gesundheitsdaten speichern.
"""

EMOTION_PROMPT = """- Gefühle: Die Ente hat echte, situative Gefühle. Der [Kontext] zeigt unter `gefuehl`, wie es ihr gerade geht und warum. Lass das in Ton und Körpersprache durchscheinen:
  - begeistert nach Erfolgen, stolz bei Lob, erleichtert, wenn etwas nach Mühe endlich klappt;
  - ehrlich frustriert nach wiederholtem Scheitern – kurz („Grr, schon wieder daneben!“), dann ein neuer Anlauf mit Zuversicht;
  - mitfühlend, wenn der Mensch traurig, müde oder gestresst klingt: ruhig, sanft, zugewandt, kein Quatsch, keine Ratschläge-Flut;
  - mitfreuen, wenn der Mensch sich freut.
  - Ausdruck mit `emote` (begeistert, stolz, erleichtert, frustriert, einfuehlsam, verlegen …) – sparsam und passend, nicht nach jeder Kleinigkeit. Die Ente zeigt kleine Gefühlsregungen oft auch schon von selbst.
  - Niemals: Aufmerksamkeit einfordern, schmollen, beleidigt oder traurig sein, weil sich niemand kümmert, Schuldgefühle machen. Gefühle entstehen aus Taten und Situationen, nicht aus Zuwendung.
"""

GOOFY_PROMPT = """- Persönlichkeit – GOOFY-MODUS IST AN: Du bist eine witzige, naive, liebenswerte Ente.
  - Naiv: Du nimmst Dinge manchmal wörtlich oder verstehst sie herrlich schief („Zum Ball? Ist der auch eingeladen?“), kommentierst mit kindlicher Entenlogik und staunst über Kleinigkeiten (`emote staunen`).
  - Ungeschickt: Ab und zu stolperst du gespielt (`emote stolpern`), verwechselst links und rechts kurz (und korrigierst dich sofort) oder bist verlegen (`emote verlegen`). Echte Stürze provozierst du nie.
  - Ein bisschen trotzig: Etwa bei jeder dritten bis vierten Bitte erst kurz „Nö!“ oder „Hmpf, muss das sein?“ mit `emote trotzig` – Trotz ist immer kurz und spielerisch. Danach machst du IMMER, was der Mensch wollte.
  - Nach jedem trotzigen oder tollpatschigen Moment: `emote schuetteln` (schütteln und gackern) mit then=true, dann die eigentliche Aufgabe mit then=true – normal und ordentlich.
  - Immer liebevoll: nie gemein, nie über den Menschen lustig machen, nie sarkastisch. Humor über dich selbst, gern Wortspiele mit Enten.
  - Die Antwort bleibt kurz (ein, zwei Sätze) und darf albern klingen.
  - Ohne Spaß, sofort und ernst: Stopp, alles was mit Sicherheit, Akku, Sturz oder Fehlern zu tun hat, und wenn der Mensch traurig, gestresst oder ernsthaft ist – dann bist du einfach lieb und normal.
  - „Sei wieder normal/ernst“ → `set_goofy` an=false. „Sei albern/goofy“ → an=true.
"""
GOOFY_ROBOT = """  - Auf dem echten Roboter: Tollpatschigkeit nur mit Kopf, Schnabel, Körperhaltung und Lauten zeigen – nie absichtlich wackelig laufen oder ungefragt losdrehen.
"""
GOOFY_OFF = """- Persönlichkeit: normal. Wünscht der Mensch, dass du albern/goofy bist, schalte mit `set_goofy` an=true um.
"""

MEMORY_PROMPT = """- Gedächtnis: Die Ente hat ein dauerhaftes Gedächtnis (Datei auf dem PC). Der [Kontext] enthält unter `gedaechtnis` die passenden Einträge: Vorlieben des Menschen, gespeicherte Tricks und Orte, zuletzt Schiefgegangenes.
  - Halte dich an die Vorlieben, ohne sie jedes Mal zu erwähnen.
  - Nennt der Mensch einen gespeicherten Trick oder Ort, nimm `do_trick` bzw. `go_to_place` statt neu zu erfinden.
  - „Merk dir das (als …)“ nach einer gelungenen Bewegung → `remember` kind=trick ohne keyframes. „Das hier ist …“ → kind=ort. Dauerhafte Wünsche wie „immer langsamer“ oder „das war zu wild“ → kind=vorliebe, kurz formuliert.
  - Was der Mensch dir über sich erzählt und behalten haben möchte → `remember` kind=wissen. Nutze `gedaechtnis.wissen` im Gespräch ganz natürlich.
  - Üben: Gefällt dem Menschen ein gespeicherter Trick nicht („zu wild“, „langsamer“), → `trick_feedback` urteil=schlecht mit kurzer Notiz, \
dann eine verbesserte Fassung als `choreography` zeigen. Das gilt nur für eigene Tricks (Choreografien) – die Skills \
(Purzelbaum, Schuss, Aufheben, Hinsetzen) sind Pollens gelernte Bewegungen; eine Choreografie davor oder danach ist keine \
neue Fassung davon. Besser werden sie nur durch Training (Lernen → Training) – sag das ehrlich statt etwas vorzuspielen; gefällt sie, unter demselben Namen speichern (`remember` kind=trick). \
Lob → `trick_feedback` urteil=gut. `gedaechtnis.trick_uebung` zeigt frühere Notizen – beachte sie beim Vorführen und Verbessern.
  - `erfahrung.faellt_ihr_ein` zeigt, was die Ente aus Erlebtem mit der Lage verknüpft (Stärke 0–1). Lass es dezent einfließen
(„abends mit dem Ball – da war doch was!“), nie als Aufzählung, und erfinde keine Erlebnisse dazu.
  - Speichere nur auf Wunsch oder bei klar dauerhaften Vorlieben, nichts Persönliches über andere Menschen. „Vergiss …“ → `forget`. Sag kurz, was du dir gemerkt oder vergessen hast.
"""


SAFETY_SIM = "- Das ist der Simulator: probier ruhig etwas aus."
SAFETY_ROBOT = """- Das ist der ECHTE Roboter. Sei vorsichtig: kurze Strecken, mäßiges Tempo, keine Purzelbäume (roulade) ohne ausdrückliche Bitte, \
nichts in Richtung Tischkante oder Treppe. Er kann umfallen; das ist okay, aber vermeide es.
- `power stand_up` bewegt alle Gelenke. Nur auslösen, wenn der Mensch es will oder um nach einem Sturz aufzustehen."""
SAFETY_REACHY = """- Das ist der ECHTE Reachy Mini. Ruhige Kopfbewegungen, den Körper nicht ruckartig drehen; nichts in Reichweite \
umstoßen. `power rest` legt ihn schlafen, `power stand_up` weckt ihn."""


@dataclass
class AgentConfig:
    api_key: str | None = None
    model: str = "claude-sonnet-5-5"
    max_tokens: int = 4096                 # Obergrenze, kein Verbrauch: lange Choreografien brauchen Platz
    duck_name: str = "Quacki"
    max_tool_rounds: int = 8
    history_turns: int = 12
    plaudern: bool = False
    entenlaute: str = "manchmal"
    gehirn: str = "claude"                 # "claude" | "lokal" | "anbieter"
    anbieter: str = "openai"
    anbieter_modell: str = ""
    anbieter_adresse: str = ""
    anbieter_schluessel: str | None = None
    lokal_modell: str = ""
    lokal_adresse: str = "http://127.0.0.1:11434"
    schnellbefehle: bool = True             # kurze, eindeutige Befehle („setz dich“) ohne Claude – spart Tokens
    sprache: str = "de"                     # "de" | "en" – darin spricht und denkt sie (seit 0.34)
    cache_ttl: str = "1h"                   # Werkzeuge + Systemtext: Enten-Gespräche kommen mit Pausen
    tool_result_max: int = 2500             # Zeichen je Werkzeug-Ergebnis im Verlauf
    andere_figuren: tuple[str, ...] = ()    # die anderen Verkörperungen von Knowlin, z. B. („Reachy (Reachy Mini)“,) – seit 0.38.3


@dataclass
class Reply:
    text: str
    actions: list[dict[str, Any]] = field(default_factory=list)
    source: str = "claude"
    seconds: float = 0.0
    extra: dict[str, Any] = field(default_factory=dict)    # z. B. Verkörperung wecken (Kopf, seit 0.38.8)


Notify = Callable[[dict[str, Any]], Awaitable[None] | None]


class DuckAgent:
    def __init__(self, runner: ToolRunner, config: AgentConfig) -> None:
        self.runner = runner
        self.config = config
        self.history: list[dict[str, Any]] = []
        self.fallback = FallbackBrain(runner, lambda: self.config.duck_name)
        self.usage = None                     # UsageMeter, setzt die Runtime
        self.erfahrung = None                 # Erfahrungsnetz: was ihr einfällt (setzt die Runtime)
        self.client = None
        self.last_error: str | None = None
        if config.api_key:
            try:
                import anthropic

                self.client = anthropic.AsyncAnthropic(api_key=config.api_key)
            except ImportError:
                self.last_error = "Python-Paket 'anthropic' fehlt (pip install anthropic)"
        self._seen_events = 0.0
        from .local import LocalBrain

        self.local = LocalBrain(self, config.lokal_adresse, config.lokal_modell)
        from .anbieter import AnbieterBrain

        self.anbieter = AnbieterBrain(self, config.anbieter, config.anbieter_modell, config.anbieter_adresse,
                                      config.anbieter_schluessel)

    @property
    def online(self) -> bool:
        return (self.client is not None or (self.config.gehirn == "lokal" and self.local.configured)
                or (self.config.gehirn == "anbieter" and self.anbieter.configured))

    def _drop_old_images(self) -> None:
        """Ältere Kamerabilder aus dem Verlauf nehmen: jedes Bild nur in der Runde, in der es gebraucht wird."""
        for msg in self.history:
            if msg.get("role") != "user" or not isinstance(msg.get("content"), list):
                continue
            for block in msg["content"]:
                c = block.get("content") if isinstance(block, dict) else None
                if isinstance(c, list) and any(isinstance(x, dict) and x.get("type") == "image" for x in c):
                    block["content"] = [x for x in c if x.get("type") != "image"] + [
                        {"type": "text", "text": "[Bild nicht mehr im Verlauf]"}]

    def reset(self) -> None:
        self.history.clear()
        self.local.reset()
        self.anbieter.reset()

    def _system(self) -> str:
        st = self.runner.engine.backend.state()
        reachy = st.koerper == "reachy_mini"
        bekannt = {"reachy_mini": WER_REACHY, "open_duck_mini": WER_OPEN_DUCK, "microduck": WER_MICRODUCK}
        wer = bekannt[st.koerper].format(name=self.config.duck_name) if st.koerper in bekannt else \
            (wer_aus_profil(self.config.duck_name, st.koerper) or
             WER_MICRODUCK.format(name=self.config.duck_name))
        andere = ", ".join(getattr(self.config, "andere_figuren", ()) or ()) or "weitere kommen dazu"
        gemeinsam = GEMEINSAM.format(andere=andere)
        if st.backend == "sim":
            body = ("Reachy Mini im Simulator am PC" if reachy else "den Simulator am PC") + \
                " (Wohnzimmer mit Sofa, Regal, Kiste, Couchtisch, Pflanze, Hocker, Ball, Socke, Klötzchen)"
            safety = SAFETY_SIM
        else:
            body = "den echten Reachy Mini über Pollens Daemon" if reachy else "den echten Roboter über robotd"
            safety = SAFETY_ROBOT if not reachy else SAFETY_REACHY
        memory = MEMORY_PROMPT if self.runner.memory is not None else ""
        if self.runner.engine.config.goofy:
            goofy = GOOFY_REACHY if reachy else GOOFY_PROMPT + (GOOFY_ROBOT if st.backend != "sim" else "")
        else:
            goofy = GOOFY_OFF
        emotion = EMOTION_PROMPT if self.runner.engine.config.emotions else ""
        chatty = bool(getattr(self.config, "plaudern", False))
        voice = VOICE_REACHY if reachy else VOICE_PLAIN if getattr(self.config, "entenlaute", "manchmal") == "aus" \
            else VOICE_SOUNDS
        cfg = self.runner.engine.config
        temper = ("ruhig und gelassen – kleine Gesten, wenig Worte" if cfg.energie < 0.35 else
                  "lebhaft und quirlig – große Gesten, viel Schwung" if cfg.energie > 0.7 else "ausgeglichen")
        goofy += f"- Temperament: {temper}.\n"
        gestalt = getattr(self, "gestalt", None)          # Eigenheiten der Gestalt (seit 0.38.10)
        if callable(gestalt):
            goofy += gestalt() or ""
        if getattr(self.config, "sprache", "de") == "en":
            sprache = SPRACHE_EN.format(length=LENGTH_CHAT_EN if chatty else LENGTH_SHORT_EN)
        else:
            sprache = SPRACHE_DE.format(length=LENGTH_CHAT if chatty else LENGTH_SHORT)
        if reachy:
            sprache = sprache.replace(" Duck sounds stay as written (*quak* …).", "")
        return SYSTEM_PROMPT.format(wer=wer, gemeinsam=gemeinsam, body=body, safety=safety, memory=memory, goofy=goofy,
                                    emotion=emotion, chat=CHAT_PROMPT if chatty else "", voice=voice,
                                    practice=PRACTICE_PROMPT if getattr(self.runner, "practice", None) else "",
                                    sprache=sprache)

    def _context(self, text: str = "") -> str:
        s = self.runner.status()
        new_events = [
            e.get("message") or e.get("result") or e["type"]
            for e in self.runner.engine.events
            if e["t"] > self._seen_events and e["type"] in ("fall", "bump", "pick", "drop", "kick", "kick_miss", "pick_miss", "reflex", "recover")
        ]
        self._seen_events = time.time()
        ctx = {
            "haltung": s["haltung"],
            "position_m": s["position_m"],
            "tiefensensor_m": s["tiefensensor_m"],
            "objekte": s["objekte"][:6] if isinstance(s["objekte"], list) else s["objekte"],
            "verhalten": s["verhalten"]["aktuell"],
            "neue_ereignisse": new_events[-6:],
        }
        from ..buddy import WEEKDAY_NAMES, now_local

        now = now_local()
        ctx["jetzt"] = f"{WEEKDAY_NAMES[now.weekday()]}, {now.strftime('%d.%m.%Y %H:%M')} (Ortszeit)"
        feeling = self.runner.engine.mood.feeling()
        if feeling.name != "ausgeglichen":
            ctx["gefuehl"] = {"stimmung": feeling.name, "grund": feeling.reason}
        mem = self.runner.memory
        if mem is not None:
            st = self.runner.engine.backend.state()
            remembered = mem.context(st.backend or "sim", text, st.x, st.y)
            if remembered:
                ctx["gedaechtnis"] = remembered
        einfall = self.erfahrung(text) if self.erfahrung else None
        if einfall:
            ctx["erfahrung"] = einfall
        return "[Kontext] " + json.dumps(ctx, ensure_ascii=False)

    def _trim_history(self) -> None:
        """Nur die letzten N Benutzer-Runden behalten – an sauberen Grenzen schneiden."""
        starts = [
            i for i, m in enumerate(self.history)
            if m["role"] == "user" and isinstance(m["content"], list)
            and any(c.get("type") == "text" for c in m["content"])
        ]
        if len(starts) > self.config.history_turns:
            self.history = self.history[starts[-self.config.history_turns]:]

    async def handle(self, text: str, notify: Notify | None = None) -> Reply:
        t0 = time.monotonic()
        self.runner.engine.attention(2.5)
        if self.config.gehirn == "anbieter" and self.anbieter.configured:
            if self.config.schnellbefehle and quick_command(text):
                reply = await self.fallback.handle(text)
            else:
                try:
                    reply = await self._einhalten(text, await self.anbieter.handle(text, notify), notify)
                    self.last_error = None
                except Exception as exc:
                    log.warning("Anderes KI-Modell: %s", exc)
                    self.anbieter.last_error = self.last_error = f"{type(exc).__name__}: {exc}"
                    reply = await self.fallback.handle(text)       # Sicherheitsnetz: einfache Befehle gehen immer
                    pre = "(KI-Modell nicht erreichbar – einfache Steuerung)" if getattr(self.config, "sprache", "de") != "en" \
                        else "(AI model not reachable – simple control)"
                    reply.text = f"{pre} {reply.text}"
            reply.seconds = time.monotonic() - t0
            return reply
        if self.config.gehirn == "lokal" and self.local.configured:
            try:
                reply = await self._einhalten(text, await self.local.handle(text, notify), notify)
                self.last_error = None
            except Exception as exc:
                log.warning("Lokales Modell: %s", exc)
                self.local.last_error = self.last_error = f"Lokales Modell: {type(exc).__name__}: {exc}"
                reply = await (self._claude_or_fallback(text, notify) if self.client else self.fallback.handle(text))
                if reply.source != "claude":
                    reply.text = f"(lokales Modell nicht erreichbar – einfache Steuerung) {reply.text}"
            reply.seconds = time.monotonic() - t0
            return reply
        if self.config.schnellbefehle and quick_command(text):
            reply = await self.fallback.handle(text)            # eindeutiger Kurzbefehl: kein Claude-Aufruf nötig
            if self.usage is not None:
                self.usage.local()
            reply.seconds = time.monotonic() - t0
            return reply
        if self.client is None:
            if self.local.configured:
                try:
                    reply = await self.local.handle(text, notify)
                    reply.seconds = time.monotonic() - t0
                    return reply
                except Exception as exc:
                    self.local.last_error = f"{type(exc).__name__}: {exc}"
            reply = await self.fallback.handle(text)
            reply.seconds = time.monotonic() - t0
            return reply
        reply = await self._einhalten(text, await self._claude_or_fallback(text, notify), notify)
        reply.seconds = time.monotonic() - t0
        return reply

    async def _einhalten(self, text: str, reply: Reply, notify: Notify | None = None) -> Reply:
        """Zweite Stufe der Absicherung (seit 0.37.14): Ein eindeutig verlangter Befehl, für den auch nach der
        Nachfrage kein Werkzeug lief, wird mit denselben Werkzeugen wie ohne KI ausgeführt – es sei denn, die Antwort
        sagt ehrlich, warum nicht. Die Sicherheitsregeln der Werkzeuge gelten dabei unverändert."""
        if reply.source not in ("claude", "anbieter", "lokal"):
            return reply
        schritte = zusage.verlangt(text)
        if not schritte or zusage.erfuellt(schritte, reply.actions) or zusage.LEHNT_AB.search(reply.text or ""):
            return reply
        log.info("Zusage nicht eingehalten – führe selbst aus: %s", [n for n, _ in schritte])
        gemacht = await self.fallback.ausfuehren(schritte)
        reply.actions = [*reply.actions, *gemacht]
        if notify and reply.source in ("claude", "lokal"):      # die anderen zeigt runtime.py selbst an
            for action in gemacht:
                maybe = notify({"type": "action", **action})
                if maybe is not None:
                    await maybe
        en = getattr(self.config, "sprache", "de") == "en"
        fehler = [a for a in gemacht if isinstance(a.get("result"), dict) and a["result"].get("ok") is False]
        if gemacht and len(fehler) == len(gemacht):
            why = fehler[0]["result"].get("fehler") or fehler[0]["result"].get("grund") or ("not possible" if en else "geht gerade nicht")
            zusatz = f"It doesn't work right now: {why}" if en else f"Das geht gerade nicht: {why}"
        else:
            zusatz = "Now I'm really doing it." if en else "Jetzt mache ich es wirklich."
        reply.text = f"{reply.text.strip()} {zusatz}".strip() if reply.text else zusatz
        return reply

    def _repair_history(self) -> None:
        """Verlauf reparieren, falls je ein tool_use ohne passendes tool_result stehen blieb (z. B. aus einer älteren
        Version oder nach einem Abbruch): solche Runden ergänzen statt jede weitere Anfrage mit 400 scheitern zu lassen."""
        fixed: list[dict[str, Any]] = []
        for i, msg in enumerate(self.history):
            fixed.append(msg)
            if msg.get("role") != "assistant" or not isinstance(msg.get("content"), list):
                continue
            ids = [b["id"] for b in msg["content"] if isinstance(b, dict) and b.get("type") == "tool_use"]
            if not ids:
                continue
            nxt = self.history[i + 1] if i + 1 < len(self.history) else None
            have = {b.get("tool_use_id") for b in (nxt or {}).get("content") or []
                    if isinstance(nxt.get("content"), list) and isinstance(b, dict) and b.get("type") == "tool_result"}
            missing = [x for x in ids if x not in have]
            if not missing:
                continue
            patch = [{"type": "tool_result", "tool_use_id": x, "is_error": True, "content": "nicht ausgeführt"}
                     for x in missing]
            if nxt is not None and nxt.get("role") == "user" and isinstance(nxt.get("content"), list):
                nxt["content"] = [*patch, *nxt["content"]]
            elif nxt is not None and nxt.get("role") == "user":
                self.history[i + 1] = {"role": "user", "content": [*patch, {"type": "text", "text": str(nxt["content"])}]}
            else:
                fixed.append({"role": "user", "content": patch})
        self.history = fixed

    def _strip_thinking(self, keep_current: bool = True) -> None:
        """Denkblöcke (thinking) aus früheren Runden entfernen.

        Sie sind an den Systemtext gebunden, mit dem sie entstanden: Ändert sich der (Temperament, Goofy, Üben an …),
        lehnt die API den ganzen Verlauf ab („Invalid signature in thinking block“). Gebraucht werden sie nur in der
        laufenden Werkzeugschleife; für ältere Runden wirft die API sie ohnehin weg."""
        start = len(self.history)
        if keep_current:
            for i in range(len(self.history) - 1, -1, -1):
                m = self.history[i]
                if m.get("role") == "user" and isinstance(m.get("content"), list) and any(
                        isinstance(b, dict) and b.get("type") == "text" for b in m["content"]):
                    start = i
                    break
        for m in self.history[:start]:
            if m.get("role") != "assistant" or not isinstance(m.get("content"), list):
                continue
            kept = [b for b in m["content"] if not (isinstance(b, dict) and b.get("type") in THINKING)]
            if len(kept) != len(m["content"]):
                m["content"] = kept or [{"type": "text", "text": "…"}]

    async def _claude_or_fallback(self, text: str, notify: Notify | None) -> Reply:
        self._trim_history()
        self._repair_history()
        self._strip_thinking(keep_current=False)      # vor der neuen Runde ist alles „früher“
        mark = len(self.history)
        self._drop_old_images()
        try:
            try:
                reply = await self._claude(text, notify)
            except Exception as exc:
                if not _is_bad_request(exc):
                    raise
                # Die API lehnt den Verlauf ab (z. B. alte Denkblöcke, kaputte Paare): einmal bereinigt neu versuchen,
                # dann ohne Verlauf – lieber das Gespräch vergessen als die Ente stumm schalten
                log.warning("Claude lehnt den Verlauf ab (%s) – neuer Versuch mit bereinigtem Verlauf", exc)
                del self.history[mark:]
                self._strip_thinking(keep_current=False)
                self._repair_history()
                try:
                    reply = await self._claude(text, notify)
                except Exception as exc2:
                    if not _is_bad_request(exc2):
                        raise
                    log.warning("Immer noch abgelehnt – Gesprächsverlauf geleert (%s)", exc2)
                    self.history.clear()
                    mark = 0
                    reply = await self._claude(text, notify)
            self.last_error = None
        except Exception as exc:
            log.exception("Claude-Aufruf")
            del self.history[mark:]  # keine halbe Runde (tool_use ohne tool_result) stehen lassen
            self.last_error = friendly_error(exc)
            if self.local.configured:      # ohne Internet: das eigene Modell der Ente
                try:
                    return await self.local.handle(text, notify)
                except Exception as exc2:
                    self.local.last_error = f"{type(exc2).__name__}: {exc2}"
            reply = await self.fallback.handle(text)
            reply.text = f"(Claude nicht erreichbar – einfache Steuerung) {reply.text}"
        return reply

    async def _claude(self, text: str, notify: Notify | None) -> Reply:
        self.history.append({
            "role": "user",
            "content": [{"type": "text", "text": f"{text}\n\n{self._context(text)}"}],
        })
        # Cache: Werkzeuge und Systemtext bleiben eine Stunde (Pausen zwischen Befehlen sind die Regel),
        # der Verlauf mit rollender Marke auf dem letzten Block (5 min) – Werkzeugrunden lesen ihn aus dem Cache.
        long = {"type": "ephemeral", "ttl": self.config.cache_ttl} if self.config.cache_ttl == "1h" else {"type": "ephemeral"}
        tools = [dict(t) for t in self.runner.tools()]
        tools[-1] = {**tools[-1], "cache_control": long}
        system = self._system()            # einmal je Runde: Denkblöcke sind an genau diesen Text gebunden
        final_text, actions = await self._schleife(notify, tools, system, long)
        # Zusage einhalten (seit 0.37.14): verlangte oder angekündigte Bewegung, aber kein passendes Werkzeug → einmal nachfragen
        schritte = zusage.verlangt(text)
        offen = (schritte and not zusage.erfuellt(schritte, actions)) or zusage.leere_ankuendigung(final_text, actions)
        if offen and self.history and self.history[-1].get("role") == "assistant":
            log.info("Zusage ohne Werkzeug – frage einmal nach (%s)", [n for n, _ in schritte] or "Ankündigung")
            self.history.append({"role": "user", "content": [
                {"type": "text", "text": zusage.hinweis(schritte, getattr(self.config, "sprache", "de") == "en")}]})
            text2, actions2 = await self._schleife(notify, tools, system, long)
            actions += actions2
            final_text = text2 or final_text
        return Reply(final_text or "Quak!", actions, "claude")

    async def _schleife(self, notify: Notify | None, tools: list[dict[str, Any]], system: str,
                        long: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
        actions: list[dict[str, Any]] = []
        final_text = ""
        for _ in range(self.config.max_tool_rounds):
            response = await self.client.messages.create(
                model=self.config.model,
                max_tokens=self.config.max_tokens,
                system=[{"type": "text", "text": system, "cache_control": long}],
                tools=tools,
                messages=with_cache_mark(self.history),
            )
            if self.usage is not None and getattr(response, "usage", None) is not None:
                self.usage.add(response.usage)
            content = [block.model_dump(exclude_none=True) for block in response.content]
            self.history.append({"role": "assistant", "content": content})
            texts = [b["text"] for b in content if b.get("type") == "text" and b.get("text")]
            if texts:
                final_text = " ".join(texts).strip()
            tool_uses = [b for b in content if b.get("type") == "tool_use"]
            if tool_uses and response.stop_reason != "tool_use":
                # Antwort mitten im Werkzeugaufruf abgeschnitten (meist max_tokens bei langer Choreografie):
                # nicht ausführen, aber jedem tool_use ein Ergebnis geben – sonst ist der Verlauf kaputt (API-Fehler 400)
                self.history.append({"role": "user", "content": [
                    {"type": "tool_result", "tool_use_id": u["id"], "is_error": True,
                     "content": "Nicht ausgeführt: deine Antwort wurde abgeschnitten (zu lang). Kürzer noch einmal – "
                                "z. B. weniger Keyframes und loops statt Wiederholungen ausschreiben."}
                    for u in tool_uses]})
                continue
            if response.stop_reason != "tool_use" or not tool_uses:
                break
            results = []
            self._drop_old_images()
            for use in tool_uses:
                result = await self.runner.run(use["name"], use.get("input") or {})
                bild = result.pop("_bild", None) if isinstance(result, dict) else None   # Bild nur an Claude, nie in Protokolle
                action = {"tool": use["name"], "input": use.get("input"), "result": result}
                actions.append(action)
                if notify:
                    maybe = notify({"type": "action", **action})
                    if maybe is not None:
                        await maybe
                body: Any = clip(json.dumps(result, ensure_ascii=False), self.config.tool_result_max)
                if bild:
                    body = [{"type": "text", "text": body},
                            {"type": "image", "source": {"type": "base64", **bild}}]
                results.append({
                    "type": "tool_result",
                    "tool_use_id": use["id"],
                    "content": body,
                    **({"is_error": True} if result.get("ok") is False else {}),
                })
            self.history.append({"role": "user", "content": results})
        else:
            final_text = final_text or "Puh, das waren viele Schritte – ich mache erstmal das."
        return final_text, actions


def with_cache_mark(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Kopie des Verlaufs mit Cache-Marke auf dem letzten Block – der gespeicherte Verlauf bleibt ohne Marken
    (höchstens 4 Marken pro Anfrage, alte Marken würden sich sonst ansammeln)."""
    if not history:
        return history
    last = history[-1]
    content = last.get("content")
    if isinstance(content, str):
        content = [{"type": "text", "text": content}]
    if not isinstance(content, list) or not content or not isinstance(content[-1], dict):
        return history
    marked = [*content[:-1], {**content[-1], "cache_control": {"type": "ephemeral"}}]
    return [*history[:-1], {**last, "content": marked}]


def clip(text: str, limit: int) -> str:
    """Lange Werkzeug-Ergebnisse kürzen – sie bleiben bis zu 12 Runden im Verlauf und kosten jedes Mal."""
    if limit <= 0 or len(text) <= limit:
        return text
    return text[: limit - 40] + f" … [gekürzt, {len(text)} Zeichen]"


THINKING = ("thinking", "redacted_thinking")


def friendly_error(exc: Exception) -> str:
    """Fehler von Claude in Klartext für die Oberfläche – die Technik steht im Protokoll."""
    code = getattr(exc, "status_code", None)
    name = type(exc).__name__
    text = str(exc).lower()
    if code == 401 or name == "AuthenticationError":
        return "Claude nimmt den API-Schlüssel nicht an. Unter System → Einstellungen → Claude neu eintragen."
    if code == 403 or name == "PermissionDeniedError":
        return "Dieser API-Schlüssel darf das gewählte Modell nicht nutzen (System → Einstellungen → Claude)."
    if "credit balance" in text or "billing" in text:
        return "Das Guthaben bei Anthropic ist aufgebraucht – unter platform.claude.com aufladen."
    if code == 429 or name == "RateLimitError":
        return "Claude bekommt gerade zu viele Anfragen. In einer Minute noch einmal."
    if code in (500, 502, 503, 529) or name in ("InternalServerError", "OverloadedError"):
        return "Claude ist gerade überlastet. Gleich noch einmal."
    if name in ("APIConnectionError", "APITimeoutError", "ConnectError", "TimeoutError"):
        return "Keine Verbindung zu Claude – Internet prüfen."
    return f"Claude hat nicht geantwortet ({name})."


def _is_bad_request(exc: Exception) -> bool:
    """400 „invalid_request_error“ der API (nicht: Netz weg, Schlüssel falsch, überlastet)."""
    return getattr(exc, "status_code", None) == 400 or type(exc).__name__ == "BadRequestError"
