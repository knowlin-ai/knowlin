# Knowlin / duckpilot – Handbuch

Alles im Detail: Bereiche, Körper, Funktionen, Technik. Installation und Überblick stehen in der
[README](../README.md), die Architektur für Mitwirkende in [ARCHITECTURE.md](../ARCHITECTURE.md), was sich je Version
geändert hat im [CHANGELOG](../CHANGELOG.md).

## Knowlin: Startseite und Module (seit 0.38)

Die Module der Suite **Knowlin** – „ein Kopf, viele Körper“ – tragen Codenamen nach ihrer Bauart: **duckpilot** für
die laufenden Enten (Microduck, Open Duck Mini), **deskpilot** für stationäre Roboter auf dem Tisch (Reachy Mini; seit
0.38.10 so genannt). Beim Start erscheint die
Startseite: eine Kachel je Modul (Microduck, seit 0.38.1 Reachy Mini, seit 0.38.4 Open Duck Mini; Knowlin Lab und
„Ohne Körper“ sind schon als „geplant“ zu sehen) und darunter, was für jeden Körper gilt – Charakter, Gedächtnis, Umgebung, Alltag,
Einstellungen. Das Knowlin-Zeichen oben links führt jederzeit zurück.

- **Verknüpfungen:** „Knowlin“ (mit dem Knowlin-Zeichen) öffnet die Startseite, „Knowlin - Microduck“ (mit der Ente)
  startet direkt bei der Microduck. Weitere legt die Kachel mit „Verknüpfung“ an („Knowlin - Reachy Mini“ …). Seit
  0.38.27 heißt überall Knowlin, was du siehst: Alte Verknüpfungen („duckpilot“, „Reachy Mini“) benennt Knowlin beim
  Start einmal um und zieht Symbol, Ziel und Arbeitsordner auf den aktuellen Stand nach – nur die eigenen, und nicht aus
  einem Stand unter „Zweige“ (sonst zeigten sie nach dem Aufräumen ins Leere). Als Web-App (im Browser „Installieren“
  bzw. „Zum Startbildschirm“) heißt sie ebenfalls Knowlin. Das Python-Paket heißt weiter `duckpilot`.
- **Gliederung:** Steuern (Cockpit, Tricks, Tanzen, Team, Vom Hub) · Alltag · **Umgebung** · Charakter (Persönlichkeit,
  Stimme, Gespräch, Gedächtnis mit Innenleben) · Lernen · System (Körper, Einstellungen mit KI-Modell, Erweiterungen).

### Verkörperungen (seit 0.38.3)

Knowlin ist die übergeordnete Anwendung. Jeder Körper hat seine eigene **Verkörperung** – Quacki die Microduck, Reachy den
Reachy Mini, Odi die Open Duck Mini – mit eigenem Namen, Aussehen, eigener Stimme, Sprechweise, Verhalten und eigenen
Tricks. Den **Charakter** wählst du seit 0.38.10 übergeordnet bei Knowlin (Einstellungen → Knowlin: seit 0.38.11 ein
Feld mit Quadranten ruhig–lebhaft und seriös–verspielt, die Verkörperungen als Punkte darum herum; dazu Gefühle zeigen); jede Verkörperung ist eine leichte Ausprägung darum herum und hat dazu die
**Eigenschaften ihrer Gestalt** (Charakter → Persönlichkeit), z. B. Schnabelklappern bei der Microduck oder
Antennenspiel bei Reachy.
**Gemeinsam** haben sie das Wissen über die Umwelt (Personen, Dinge, Abläufe, Situationen), die Umgebung, den Alltag
und die Erlebnisse. Die Startseite zeigt oben das Gemeinsame und darunter die Verkörperungen; die Kacheln heißen wie die
Roboter-Modelle, der Spitzname darunter ist der Name der Verkörperung. „Reachy wecken“ weckt ihn in seinem Körper. Oben im
Körper steht „Knowlin › Reachy · Reachy Mini“; ein Klick auf „Knowlin“ führt zurück.

- **Kopf zuerst (seit 0.38.4):** Nach dem Start ist Knowlin nur im Kopf – die Leiste zeigt Knowlin, Alltag,
  Umgebung, Wissen und Einstellungen; niemand steht auf, spricht oder läuft im Zimmer herum. Erst wer eine Verkörperung weckt
  (Kachel, Verknüpfung, Lesezeichen oder Handy-Controller), betritt den Körper; dann kommen Steuern, Charakter und
  System dazu, die Verkörperung steht auf und grüßt in ihrer Art.
- **Startseite als Schnelleinstieg (seit 0.38.8):** Oben grüßt Knowlin selbst („Hallo Mensch“, mit deinem Namen,
  sobald du ihn sagst oder einstellst), darunter das Dialogfeld, links der Kopf als wabernde Form (ruht, hört zu,
  denkt nach, spricht). Knowlin ist eine intelligente, selbstlernende Lebensform, anfangs seriös, mit eigener Stimme
  (Einstellungen → Knowlins Stimme: wählen, entwerfen, probehören). Wünschst du dir etwas Körperliches, nennt er die
  Verkörperung, die es kann, und fragt, ob er sie nutzen soll; auf „ja“ geht er hinein und gibt ihr den Wunsch weiter.
  „Stopp“ wirkt immer auf jeden Körper.
- **Übergänge:** „Mind to Body“ beim Wecken, seit 0.38.10 auch kurz zurück („Body to Mind“). Im Körper trägt jede
  Antwort den Namen der Verkörperung; beim Wechsel trennt eine Zeile den Verlauf.
- **Raumklang:** Laute anderer Roboter im Simulator klingen von dort, wo sie stehen – links, rechts, nah oder weit
  (nur zu hören, nicht extra angezeigt).

### Open Duck Mini (seit 0.38.4)

Der offene Selbstbau-Vorgänger der Microduck (Antoine Pirrone und Community, Apache-2.0) als dritter Körper: gut
40 cm groß, Beine mit je fünf Motoren, Kopf mit vier Gelenken und zwei Antennen, kein Schnabel und kein Tiefensensor.
Die Verkörperung heißt **Odi** – eine Ente, aber größer und tiefer als Quacki.

- **Im Simulator** mit dem offenen 3D-Modell (wird mitgeliefert, Hinweis in `static/model/LIZENZ-open-duck-mini.md`):
  laufen, drehen, sitzen, Kopf bewegen, Antennen zeigen Gefühle und wackeln beim Sprechen.
- **Was fehlt, ist nicht da:** Pollens gelernte Bewegungen (Aufheben, Purzelbaum), Apportieren, Ausweichen und
  Erkunden (kein Tiefensensor) verschwinden aus der Oberfläche, auch aus dem Menü am angeklickten Ding (seit 0.38.25);
  das Gehirn weiß es. Schießen zeigt der Simulator nachgestellt.
- **Ausweichen mit der Kamera (seit 0.38.25):** Ist eine Kamera verbaut, schätzt Odi die Abstände aus dem Kamerabild
  (bis etwa 1,5 m, mit ein paar Prozent Schätzfehler) und läuft wie die Microduck um Hindernisse herum. Ohne Kamera stößt
  sie an. Am echten Roboter übernimmt das später ein kleines Tiefenmodell am PC (geplant); Erkunden und den erkundeten
  Bereich gibt es weiter nur mit Tiefensensor.
- **Wählbar** auch unter Einstellungen → Körper (seit 0.38.13); im Tanz schlagen ihre Antennen im Takt mit. Bewegungen,
  die sie nicht hat, lehnt sie ehrlich ab, statt zuzusagen.
- **Echte Open Duck: geplant.** Die Open-Duck-Runtime hat noch keine Schnittstelle nach außen und ihr Repo keine
  Lizenzdatei – duckpilot übernimmt daraus keinen Code.

### Knowlets (seit 0.38.5)

Charakter, Tricks und Tänze einer Verkörperung als Paket teilen: Wissen → Knowlets (oder die Kachel „Knowlets“).

- **Packen:** Verkörperung wählen, ankreuzen, was mit soll, „Als Datei speichern“ – oder „Auf Hugging Face teilen …“ (braucht
  den Hugging-Face-Schlüssel aus Lernen → Training; privat, solange du nicht „öffentlich“ wählst).
- **Laden:** Datei öffnen, ein Repo angeben oder geteilte Knowlets suchen. Erst kommt die Vorschau, übernommen wird nur,
  was du auswählst. Ersetzt ein Knowlet den Charakter einer Verkörperung, sichert Knowlin vorher die bisherige.
- **Nur Daten:** nie Code, nie Wissen über Personen, Orte oder deine Wohnung, keine Musikstücke. Tricks aus Knowlets
  laufen am echten Roboter erst nach einer Probe im Simulator.

### Reachy Mini (seit 0.38.1)

Pollens Desktop-Roboter als zweiter Körper für denselben Kopf: gleiches Wissen, aber eine eigene Verkörperung (seit 0.38.3)
mit eigener Stimme und eigenem Charakter. Öffnen über die Kachel auf der Startseite oder oben im Körper-Menü („Reachy Mini im Simulator“).

- **Im Simulator:** Reachy Mini steht im selben Wohnzimmer, dreht den Körper (bis ±160°), bewegt den Kopf (nicken,
  neigen, drehen, hoch und runter) und die beiden Antennen; beim Sprechen wackeln sie mit. „Schlafen“ klappt die
  Antennen ein und senkt den Kopf, „Aufwachen“ richtet ihn wieder auf.
- **Ohne Beine:** Laufen, Tricks vom Hub, Apportieren, Schuss, Erkunden, Folg mir, Laser, Team und Lernen gibt es hier
  nicht – die Knöpfe verschwinden, und das Gehirn weiß es („ich habe keine Beine, aber ich kann mich umdrehen“).
- **Pollens Originalmodell und Bewegungen (seit 0.38.2):** Das 3D-Modell und Pollens Emotionen und Tänze lädt
  duckpilot auf deinem PC nach (Pollens Hardware-Dateien stehen unter CC BY-NC-SA und werden nicht mitgeliefert). Die
  Bewegungen stehen unter Steuern → Tricks; das Gehirn spielt sie auch selbst ab. Beim Zuhören neigt Reachy den Kopf,
  beim Nachdenken spielen die Antennen, beim Sprechen wippt der Kopf mit.
- **Echter Reachy Mini (ungetestet):** Einstellungen → Körper → Welcher Roboter: Reachy Mini, Echter Roboter, Adresse
  von Pollens Daemon (z. B. `http://reachy-mini.local:8000`, nur im eigenen Netz). duckpilot spricht Pollens REST
  (`/api/state/full`, `/api/move/set_target`, `wake_up`, `goto_sleep`); der Not-Aus hält die Drehung sofort an. Geprüft
  gegen Pollens `reachy-mini-daemon --mockup-sim`, nicht an Hardware.
- **Tanzen, Mitwippen, Begrüßung (seit 0.38.13):** Im Tanzmodus tanzt Reachy eigen – Kopf, Antennen und Drehung im
  Takt, ohne Posen und Entenlaute. „Mitwippen“ spielt ein Stück vom PC oder ein Webradio im Browser, Reachy wippt im
  Takt mit (lässt ein Sender das Mitlesen nicht zu: ruhiger Grundtakt). Beim Aufwecken grüßt er mit Tageszeit und
  deinem Namen (abschaltbar unter Persönlichkeit → Verhalten).
- **Kamera-Spiele (seit 0.38.13):** Steuern → Spiele: „Rotes Licht, grünes Licht“ und „Hand folgen“. Die Webcam läuft
  nur während eines Spiels, ausgewertet wird nur im Browser (64 × 48 graue Punkte – wie viel und wo sich etwas bewegt);
  kein Bild verlässt den PC, keine Gesichts- oder Personenerkennung. Not-Aus beendet Spiel und Webcam sofort.

### Weitere Körper: LeRobot und dein eigener Roboter (seit 0.38.35)

Jeder Körper beschreibt sich mit einem **Profil** – was er kann, aus einem festen Wortschatz – und muss die
**Sicherheitspflichten** bestehen (Not-Aus macht stromlos, ohne Strom bewegt sich nichts, Stopp hält an, Grenzen).
Prüfen: `python -m duckpilot.koerper_pruefung [id]`. Spezifikation: [Körperschnittstelle](koerper-schnittstelle.md).

- **LeRobot-Roboter** (SO-101, LeKiwi, Koch …): eingebaut als Körper `lerobot`. Was er kann (Arm, Greifer, Räder,
  Kamera), liest Knowlin aus dem Roboter selbst; der Not-Aus schaltet das Drehmoment ab. Einrichten vorerst in der
  Einstellungsdatei: `modul = "lerobot"`, `backend = "robotd"`, `koerper_optionen = {typ = "so101_follower",
  port = "COM5"}`; das Paket `lerobot` installierst du selbst. An echter Hardware noch ungeprüft.
- **Dein eigener Roboter:** als eigenes Python-Paket mit dem Entry Point `knowlin.koerper` – Vorlage
  `examples/knowlin-koerper-vorlage`. Er erscheint dann als Modul auf der Startseite, mit eigenem Namen und Weckwort
  aus seinem Profil (seit 0.38.36). Knowlin installiert solche Pakete nie selbst.

## Bedienung

Beim Start lädt Knowlins Bewusstsein (seit 0.38.24): Funken laufen ins Knowlin-Zeichen, bis die Ente verbunden ist,
dann leuchtet es auf – „Knowlin ist wach“. Einmal je Sitzung, Klick oder Taste überspringt es.

Links (auf dem Handy unten) sind fünf Bereiche, gebündelt nach dem, was du gerade willst: **mit der Ente
etwas tun**, **mit ihr den Tag organisieren**, **sie formen**, **ihr etwas beibringen** – und alles
Technische unter **System**. Wo ein Bereich mehrere Seiten hat, stehen sie oben als Reiter; duckpilot
merkt sich je Bereich den zuletzt offenen Reiter. Ausgeschaltete Funktionen (z. B. Gedächtnis aus)
verschwinden aus den Reitern statt leere Seiten zu zeigen.

| Bereich | Reiter | Was dort ist |
|---|---|---|
| **Steuern** | Cockpit · Tricks · Tanzen · Team · Vom Hub | 3D-Ansicht mit Telemetrie, Spur, Zielmarke, Orten und auf Wunsch der Punktwolke; oben rechts **Beobachten / Entenblick**, **Kopf ruhig** und das Menü **Ansicht**, rechts Gespräch, Schnellbefehle und Sprechknopf. Dazu Pollens 14 Emotionen und eigene Gesten zum Antippen und Bewegungen anderer vom Hugging Face Hub. |
| **Alltag** | – | Alltagsbuddy: große Uhr, Ruhe/Aktiv, Timer, Erinnerungen, Termine (auch als .ics-Datei), To-dos und unten **„Was der Buddy darf“** (Sehen, Personen erkennen und begrüßen). Erscheint, solange die Erweiterung „Alltagsbuddy“ an ist (Standard) – ein- und ausschalten unter System → Erweiterungen. |
| **Umgebung** | – | erkundeter Bereich mit Ansicht von oben, Bring mir, Wo zuletzt gesehen (seit 0.38 eigener Bereich) |
| **Charakter** | Persönlichkeit · Stimme · Gespräch · Gedächtnis | Charakter und Verhalten; Stimme und Entenlaute; Zuhören und Antworten; was sie sich gemerkt hat, dazu Stimmung und Hirnaktivität (Innenleben) |
| **Lernen** | Akrobatik · Parcours · Training | die Ente als Gliederpuppe mit Drehringen, Gleichgewichts-Ampel und Übungen; Aufträge mit Hindernisparcours in der Physik; Reinforcement Learning **kostenlos am PC** (mit Lernschleife) oder **auf Kaggle**, bezahlt auf Hugging Face Jobs. Ein Punkt am Symbol zeigt, dass gerade etwas läuft. |
| **System** | Körper · Einstellungen · Erweiterungen | Lagebild, Akku, Live-Diagramme, Tiefensensor, **Gelenk-Check** (alle 15 Gelenke mit Sollwert, Nachlauf, Last und Ampel), Ereignisse und Roboter-Pflege; Einstellungen (Claude, **KI-Modell**, Körper, 3D-Darstellung, **Handy-Fernbedienung**, Über); Skill-Pakete zum Ein- und Ausschalten |

Oben rechts zeigt **„N Aufgaben laufen“** alles, was im Hintergrund arbeitet – Installationen,
Modell-Downloads, Stimmentwürfe, Trainingsläufe, Parcours-Versuche – mit Fortschritt; ein Klick
springt zur passenden Seite. Direkt verlinkbar sind Seiten als `#seite/reiter`, z. B. `#tricks/hub`.

**Die Anzeige links unten im Cockpit** (das „?“ daneben erklärt sie auch): **Vorwärts** und **Drehung**
zeigen, wie schnell sie gerade läuft und sich dreht (Strich in der Mitte = steht); die Werte haben feste
Breite, damit nichts springt. Die **Kachel** zeigt den Tiefensensor vorne (8 × 8 Punkte, je heller, desto
näher) – **antippen** wechselt zum Kamerabild (im Simulator ihre Kopfkamera, am Roboter die echte).
**links / Mitte / rechts** ist der Abstand zum nächsten Hindernis im jeweiligen Drittel, „frei“ heißt
nichts bis etwa 2 m. Darüber stehen Stimmung und was sie gerade tut.

| | |
|---|---|
| **Sprechen** | Orangen Knopf halten oder **Leertaste** halten, sprechen, loslassen |
| **Weckwort** | Haken bei „Weckwort ente“ – dann hört das Fenster dauernd zu und reagiert auf „Ente, …“ |
| **Schreiben** | Textfeld unten rechts |
| **Hinschauen** | In der 3D-Ansicht auf den Boden oder ein Ding **klicken** – die Ente schaut hin; liegt es außer Reichweite des Kopfs, dreht sie sich mit |
| **Hinlaufen** | **Doppelklick** auf den Boden (oder auf Ball und Socke) – sie läuft hin und behält das Ziel im Blick |
| **Umschauen** | Oben rechts **Entenblick** wählen: die ganze Bühne zeigt, was ihre Kopfkamera sieht. **Ziehen** dreht den Kopf wie in Street View, am Anschlag dreht sich der Körper mit |
| **Kopf ruhig** | Knopf oben rechts (oder „Kopf-Stabilisator an“): Der Kopf gleicht Wackeln und Drehen des Körpers aus wie bei Huhn und Taube – beim Drehen hält der Blick, dann ein kurzer Ruck nach vorn. In echter Physik und am Roboter stellt duckpilot Kopf und Hals dafür direkt und gleicht Gieren und Rollen aus (Nicken nicht – das Servo kommt beim schnellen Schritt-Nicken nicht mit); gemessen in MuJoCo: Gieren −54 %, Rollen −13 %. Seit 0.18 mit Vorhalt gegen den Verzug der Gelenke und Ausgleich des Vor und Zurück pro Schritt (Hals und Kopf nicken gemeinsam): Drehzittern der Kopfkamera −60 %, Vor/Zurück −35 %. Seit 0.33 auch im Menü des Handy-Controllers |
| **Ruhe / Aktiv** | Schalter oben rechts (Sonne/Mond), oder „Ruhemodus“ / „Wach auf“. In Ruhe sitzt sie mit abgeschalteten Motoren; Ansprechen, Steuern oder ein fälliger Termin weckt sie |
| **Fahren von Hand** | `W` `S` vor/zurück, `A` `D` drehen, `Q` `E` seitwärts, oder ein Gamepad (linker Stick fahren, rechter Stick Kopf) |
| **Stopp** | `Esc`, Not-Aus-Taster unten in der Leiste (immer sichtbar) oder „Stopp“ sagen – wirkt sofort, ohne auf Claude zu warten, und schaltet die Motoren aus (seit 0.38.24): die Ente sackt zusammen, Reachys Kopf sinkt ab, weitere Enten im Zimmer ebenso. Danach steht oder setzt sich mindestens 2 Minuten nichts von selbst; unter Einstellungen → Not-Aus länger (5 oder 10 min) und wahlweise „still, bis ich sie anspreche“ |

Beispiele, die Claude versteht:

- „Lauf zum Ball und schieß ihn mit rechts.“
- „Heb die Socke auf, bring sie zum Sofa und leg sie dort ab.“
- „Zeig mir, wie du dich freust.“ – „Du bist müde.“ – „Schüttel den Kopf.“
- „Erkunde das Zimmer eine Minute lang.“
- „Tanz zu 120 bpm, erst wackeln, dann drehen.“
- „Mach eine Verbeugung.“ (dafür gibt es kein fertiges Werkzeug – Claude komponiert sie)
- „Was siehst du gerade?“
- „Gut so, merk dir das als Verbeugung.“ – „Das hier ist die Küche.“
- „Sei mal albern.“ – „Super gemacht!“ – „Ich bin heute ziemlich müde.“
- „Wie spät ist es?“ – „Stell einen Nudel-Timer auf 9 Minuten.“ – „Erinnere mich morgen um 9 an den Arzt.“
- „Trag Freitag 14:30 Zahnarzt ein.“ – „Setz Milch auf die Liste.“ – „Was steht heute an?“ – „Ruhemodus.“

## Wie es funktioniert

```
 Browser (127.0.0.1)                         Python (duckpilot)
┌──────────────────────┐   WebSocket   ┌─────────────────────────────────────────────┐
│ 3D-Ente (three.js)   │◀── Zustand ───│  Claude-Agent  ── Werkzeuge (walk, emote,    │
│ Chat, Push-to-Talk   │─── Text ─────▶│   (Tool-Use)       choreography, wait …)    │
│ Vorlesen, Quaklaute  │               │        │                                    │
└──────────────────────┘               │        ▼                                    │
                                       │  MotionEngine, 20 Hz (Befehle)              │
                                       │   1 Reflexe   Sturz, hochgehoben, Hindernis │
                                       │   2 Hand      Tastatur / Gamepad            │
                                       │   3 Verhalten Warteschlange von Claude      │
                                       │   4 Leerlauf  umschauen, atmen, Neugier     │
                                       │        │  robot.move / head / mouth / pose  │
                                       │        ▼                                    │
                                       │  Backend:  sim (Lite-Simulator, 50 Hz)      │
                                       │        oder robotd (echter Roboter/duck-sim)│
                                       └─────────────────────────────────────────────┘
```

**Zwei Takte, kein Widerspruch.** Die Microduck selbst regelt mit **50 Hz**: Ihre Policy rechnet 50-mal pro Sekunde
neue Gelenkziele, und daran hält sich auch der Simulator (Lite-Simulator 50 Hz, Physik 200 Hz mit Policy 50 Hz). Die
**MotionEngine** darüber entscheidet nur, *was* die Ente tun soll (laufen mit welcher Geschwindigkeit, Kopf wohin, Not-Aus)
– das geschieht 20-mal pro Sekunde. Der Daemon glättet diese Befehle in seinem eigenen 50-Hz-Takt, und der
500-ms-Totmann ist mit 20 Hz zehnfach abgedeckt.

**Ein Interface, zwei Körper.** `duckpilot/api.py` benutzt das Vokabular des echten Daemons
(`robot.move {vx, vy, vyaw}`, `robot.head`, `robot.mouth`, `robot.pose`, `robot.do {skill}`,
`robot.sound {tag}`, `robot.init`, `robot.enable`, `robot.rest`), dieselben Einheiten (m, s, rad),
denselben 500-ms-Totmann und dieselben Skill-Namen (`sit_toggle`, `ground_pick`, `kick_left`,
`kick_right`, `roulade`). Der Simulator verhält sich danach: Skills können abgelehnt werden
(„sitzt – erst aufstehen“), Anrempeln mit Tempo wirft die Ente um.

**Situativ statt starr.** Jede Nachricht an Claude trägt einen kurzen Lagebericht mit: Haltung,
Tiefensensor links/Mitte/rechts, gesehene Objekte, laufendes Verhalten, neue Ereignisse. Darunter
reagiert die Engine selbst, ohne auf Claude zu warten: bremst vor Hindernissen, stoppt alles bei einem
Sturz und steht nach dem Stopp-Fenster (Standard 3 s, „Stopp“ hält sie liegen) selbst wieder auf, schaut neugierig zu Dingen, die neu ins Blickfeld
kommen, und schaut hoch, wenn jemand mit ihr spricht. Verhalten, die Beine brauchen, warten, bis die
Ente steht.

**Dynamische Bewegungen.** Neben fertigen Verhalten (laufen, drehen, hingehen, annähern, erkunden,
umschauen, tanzen, neun Gefühle) hat Claude das Werkzeug `choreography`: Keyframes mit Kopf (Grad),
Schnabel, Körperhaltung, Fahrbefehlen, Lauten und Skills. Die Engine interpoliert weich und hält alles
in den Bereichen, auf die die echten Policies trainiert sind (z. B. Körperhöhe −25 bis +10 mm,
Rollen/Kippen ±15°).

## Aus Pollens Repositories

Seit 0.5 nutzt duckpilot direkt, was Pollen Robotics und die Community offen veröffentlicht haben.
Die Links stehen unter [Rechtliches und Quellen](../README.md#rechtliches-und-quellen).

| Was | Woher | Wie in duckpilot |
|---|---|---|
| **Originales 3D-Modell** | `microduck_rl`, MJCF und STL-Netze aus dem CAD | **Wird nicht mitgeliefert:** Beim ersten Start lädt duckpilot genau die 41 gebrauchten Dateien (≈ 22 MB, fester Stand, jede mit Prüfsumme) von GitHub in den Datenordner und baut daraus auf dem PC das Modell für die 3D-Ansicht und – mit MuJoCo – das für die Physik (`duckpilot/modell`; ohne Oberfläche: `python -m duckpilot.modell`). Bis dahin zeigt die 3D-Ansicht die einfache Ente. Der Bau übernimmt die Netze in voller Auflösung (rund 465 000 gezeichnete Dreiecke, 64 Teile, ≈ 4,4 MB; nur die vierzehn winzigen Kugellager werden vereinfacht), rechnet Normalen mit harten Kanten vor, merkt sich die Oberflächenart je Teil und schreibt `ansicht.dpm` (Format DPM2). Die 3D-Ansicht bewegt dieselben 15 Gelenke wie der echte Roboter; am Roboter zeigt sie die gemessenen Winkel. Unter System → Einstellungen → 3D-Darstellung (oder im Menü „Ansicht“ im Cockpit) lässt sich die einfache Ente zurückholen. |
| **14 Emotionen** | `microduck_emotions` | `tools/import_emotions.py` übernimmt die Keyframes (10 Hz, Hals, Kopf, Körper, Schnabel) samt Original-Tönen. Sie stehen unter Tricks, Claude kann sie aufrufen, und die Stimmung greift ab und zu darauf zurück (z. B. „aufgeregt“ statt der eigenen Freude). Hinsetzen wird zu leichtem Einsacken – die Ente setzt sich nie ungefragt. |
| **Entenstimme** | `quack.py` und `voices.rs` aus `microduck` | `tools/render_voice.py` erzeugt mit Pollens Stimm-Synthese 30 Laute (grüßen, fragen, zwitschern, gurren, juchzen, Alarm). Am Roboter spricht die Ente selbst. |
| **Laute der eigenen Gesten** | Pollens Sound-Design-Rezepte (Tag `workshop-2026-10-07` in `microduck_emotions`) | `tools/render_gestures.py` entwirft für jede eigene Geste Laute im selben Stil: dieselbe Stimme, je Gefühl Pollens Stimmfärbung (fröhlich, fragend, Coo, Ja, Nein, Lachen, Knurren, gedämpft), Gleittöne genau auf den Takten der Bewegung. Je Geste vier Varianten, der Schnabel öffnet mit dem Ton. |
| **Tricks vom Hub** | Hugging Face Hub, Repos mit `policy.onnx` und `manifest.json` | Suche wie `updaterd` auf dem Roboter. Am echten Roboter lädt `updaterd` die Policy (`policy.fetch`) und `robotd` macht daraus einen Skill (`robot.setSkill`); danach kennt Claude den Trick beim Namen. Im Simulator werden Tricks vorgemerkt. |

**Fremde Tricks sind ungeprüft.** Beschreibungen schreiben die Autoren selbst; duckpilot zeigt sie an,
führt aber nie etwas aus, was darin steht. Sicher machen einen Trick die Gelenkgrenzen, der
Sturzreflex und die Formprüfung auf dem Roboter. Das erste Mal am besten mit der Ente auf dem Ständer.
Policies für feste Plätze (Picken, Hinsetzen) lehnt duckpilot als Trick ab.

**Lizenzen:** Die 3D-Netze stehen unter CC BY-NC-SA 4.0, also auch das daraus gebaute Modell: nur
nicht-kommerziell, Namensnennung, Weitergabe unter gleichen Bedingungen. Deshalb verteilt duckpilot es
nicht, sondern baut es auf dem PC aus Pollens Originaldateien. Emotionen und Code von Pollen: Apache-2.0.

## Persönlichkeit und Gefühle

**Persönlichkeit als Regler.** Oben rechts (und unter Charakter → Persönlichkeit) liegt eine
Fläche mit einem Punkt, den du verschiebst:

- **waagerecht: ruhig ↔ lebhaft.** Bestimmt, wie aktiv sie im Leerlauf ist, wie groß ihre Gesten
  ausfallen, wie oft sie Gefühle zeigt und wie schnell sie spricht.
- **senkrecht: ernst ↔ albern.** Oberhalb der Mitte ist sie **goofy**: witzig, naiv, manchmal
  ungeschickt und kurz trotzig („Nö! … na gut“), aber immer liebevoll. Nach jedem Quatsch
  schüttelt sie sich gackernd und macht dann ordentlich weiter. Je weiter oben, desto häufiger
  stolpert sie gespielt, bockt kurz oder treibt im Leerlauf Unsinn (Schwanz jagen, Boden picken,
  Hintern wackeln).

Die Fläche hat zwölf Charaktere, von *Gelassen* (ruhig, ernst) über *Ausgeglichen* bis
*Chaos-Ente* (lebhaft, albern). Per Sprache geht es auch: „Sei mal albern“, „Sei wieder normal“.

**Charakter im Leerlauf.** Hat die Ente nichts zu tun, zeigt jeder Charakter außer *Ausgeglichen*,
wer er ist – mit eigener Mimik (Blickhöhe, Kopf schief, Haltung, Tempo des Umschauens, Schnabelzucken,
Wippen, Zappeln) und eigenen Gesten mit Lauten:

| Charakter | Im Leerlauf | etwa alle |
|---|---|---|
| Gelassen | seufzt, mustert das Zimmer, putzt sich, träumt, nickt | 16–30 s |
| Sachlich | mustert, richtet sich auf, nickt, horcht auf | 14–26 s |
| Eifrig | horcht auf, späht umher, mustert, nickt, hibbelt | 7–13 s |
| Gemütlich | gähnt, seufzt, putzt sich, döst ein und schreckt hoch | 11–20 s |
| Ausgeglichen | schaut sich nur ruhig um | – |
| Munter | wippt, trällert, horcht auf, späht umher, freut sich | 7–12 s |
| Verträumt | schaut in den Himmel, gähnt, döst, staunt, trällert | 9–16 s |
| Verschmitzt | Selbstgespräche, „Nänänä“, wackelt, ist kurz trotzig, erschrickt | 8–14 s |
| Quirlig | hibbelt, wippt, wackelt, hat Schluckauf, ist aufgeregt | 5–9 s |
| Tollpatschig | niest, döst, erschrickt, pickt am Boden, stolpert | 8–14 s |
| Goofy | niest, Schluckauf, Selbstgespräche, jagt den Schwanz, lacht | 6–11 s |
| Chaos-Ente | alles davon, ständig | 4–7 s |

Alle Gesten gibt es auch einzeln unter **Steuern → Tricks → Im Leerlauf**, und Claude kann sie aufrufen. Die
Fläche zeigt beim Verschieben, was der Charakter im Leerlauf tut. Auch hier gilt: nur Kopf, Schnabel
und Haltung. „Schwanz jagen“ dreht sich nur im Simulator; im Sitzen gibt es nur Kopfgesten; wer
gerade getröstet wird, bekommt keinen Quatsch.

**Gefühle aus der Situation.** Die Ente bewertet, was passiert, und zeigt es kurz mit Kopf,
Schnabel, Haltung und Lauten:

| Situation | Gefühl |
|---|---|
| Ball getroffen, Socke erwischt, Ziel erreicht | begeistert, stolz, fröhlich |
| mehrmals daneben, blockiert, nicht gefunden | ehrlich frustriert, mit jedem Fehlversuch etwas mehr |
| klappt nach Mühe doch noch | erleichtert |
| Sturz, Anstoßen | erschrocken |
| Lob („gut gemacht“) | stolz |
| du freust dich | freut sich mit |
| du bist traurig, müde oder gestresst | mitfühlend: ruhig, sanft, Kopf schief, kein Goofy-Quatsch |

Die Stimmung klingt von selbst wieder ab. Was es bewusst **nicht** gibt: traurig oder beleidigt
sein, weil sich niemand kümmert, Schmollen, um Aufmerksamkeit betteln. Ohne Ereignisse ist sie
einfach ausgeglichen.

Die aktuelle Stimmung steht mit Grund unter der Haltung im 3D-Bild, unter Charakter → Gedächtnis (Innenleben) gibt es einen
Verlauf der letzten zwei Minuten. Claude sieht Stimmung und Temperament im Lagebericht und
antwortet passend. Auch die Vorlesestimme ändert sich leicht: froh etwas heller, mitfühlend
langsamer. Gefühle lassen sich unter Charakter → Persönlichkeit ausschalten.

**Sicherheit geht immer vor:** Stopp wirkt sofort und ohne Trotz. Gefühle und Albernheiten bewegen
nur Kopf, Schnabel und Haltung, nie die Beine. Auf dem echten Roboter dreht sie sich nie ungefragt.

## Echte Physik am PC

System → Einstellungen → Körper → **Echte Physik**. Dann ist der Körper der Ente nicht mehr nachgebildet,
sondern berechnet – so, wie Pollen selbst Policies vor dem Aufspielen prüft
(`microduck_rl/scripts/infer_policy.py`):

- **MuJoCo** mit Pollens Robotermodell (dieselben Massen, Gelenke und Fußsohlen wie im Training),
  200 Hz Physik, 50 Hz Policy, dazu die Wohnung als feste Körper.
- **Pollens Policies** aus `pollen-robotics/microduck-policies`, einmal per Knopf geladen
  (wenige MB): VelStand fürs Gehen, Stehen, Kopf und Körperhaltung – und fürs Aufstehen nach einem
  Sturz –, dazu Hinsetzen, Aufheben, Schuss und Purzelbaum.
- Rempelt die Ente ein Möbel an, **fällt sie wirklich** und steht mit VelStand von selbst wieder
  auf. „Ente zurück auf die Füße“ setzt sie an den Start.
- **Tricks vom Hub, MicroDuck-App-Moves und Gangarten** laufen hier schon – gefahrlos ausprobieren,
  bevor die echte Ente da ist.
- Die 3D-Ansicht zeigt die berechneten Gelenkwinkel und die echte Lage des Rumpfs.
- **Entenblick** (Schalter über der 3D-Ansicht): was die Kamera im Kopf sieht, über die ganze Bühne. Die Kachel unten
  links zeigt das Kamerabild auch klein (antippen schaltet zwischen Tiefe und Kamera); das frühere kleine Bild in der
  Ecke gibt es seit 0.38.24 nicht mehr.

Installiert wird per Knopf: MuJoCo und ONNX Runtime (≈ 120 MB, läuft auf dem Prozessor). Optional
**Rhobans Motormodell BAM**, mit dem Pollen trainiert – ohne nimmt duckpilot MuJoCos
Positionsantriebe aus Pollens Modell (wie `infer_policy.py --no-bam`).

### Claude übt mit

Claude hat ein Werkzeug `bewegung_ueben`: Eine neu komponierte Bewegung läuft unsichtbar in einer
zweiten Physik-Welt, schneller als Echtzeit (ein paar Zehntelsekunden), und kommt mit Messwerten
zurück – Urteil *sicher*, *wackelig* oder *fällt um*, stärkste Neigung, Strecke, Drehung, wie gut
der Kopf folgt, dazu Hinweise. Claude verbessert die Bewegung und übt erneut, bevor die Ente sie
zeigt oder als Trick speichert. Das funktioniert auch, wenn der echte Roboter verbunden ist – erst
üben, dann vorführen. Und es braucht kein CUDA: der Weg, der auch mit einer AMD-Karte geht.

Für **neue Fähigkeiten** (eigene Policies trainieren) braucht Pollens Training MuJoCo Warp und damit
eine NVIDIA-Karte – siehe *Training*.

## Kollisionsmodus (Simulator)

Im Cockpit oben in den Werkzeugen über der Bühne: **Spielen** (Symbol Ball mit Schwunglinien). Er braucht den Simulator
mit echter Physik; ohne sie ist das Symbol blasser, und ein Klick schaltet die echte Physik ein (seit 0.38.25) – danach
öffnet ein zweiter Klick den Modus. Die Bedienung folgt CAD-Programmen und
Robotik-Simulatoren (Onshape, SketchUp, MuJoCo, Gazebo):

- **Zeigen bewegt nichts.** Was sich anfassen lässt, leuchtet auf, der Zeiger wird zur Hand, und ein Hinweis am
  Zeiger sagt, was Ziehen dort tut.
- **Ente ziehen:** Die Ente an einer Stelle anfassen (Kopf, Rumpf, Bein) und ziehen. Sie hängt dort an einer Feder
  zur Maus, die gestrichelte Linie zeigt die Feder, am Zeiger steht die Kraft. Kurz zupfen schubst sie, weit und
  lange ziehen wirft sie um. Gezogen wird auf einer Ebene quer zur Kamera durch den Anfasspunkt – für Ziehen nach
  vorn oder hinten die Kamera drehen.
- **Dinge hinlegen:** Im Bedienfeld ein Ding wählen und auf den Boden klicken. Es gibt **Ball, Würfel, Kegel,
  Wasserball, Kissen und Klotz** (leicht bis 0,6 kg, Wasserball und Kissen sind weich).
- **Dinge verschieben:** Anfassen und ziehen schiebt ein Ding in seiner Höhe über den Boden. Lot und Bodenring
  zeigen, wo es ist, am Zeiger stehen Höhe und Weg.
- **Dinge heben:** Mit gedrückter Umschalttaste oder am **blauen Pfeil** über dem Ding bewegt es sich nur senkrecht
  (blaue Achse, wie in CAD). Lot und Ring zeigen, wo es landen würde – auf dem Boden oder einem Möbel darunter.
- **Zielwurf (Schleuder):** Unter „Werfen“ auf „zielen“ stellen. Dann ein Ding anfassen und nach hinten ziehen wie
  bei einer Schleuder: Die Zuglänge gibt das Tempo (50 cm = 6 m/s), die Gegenrichtung die Richtung, der Regler
  „Wurfwinkel“ den Winkel. Der Bogen zeigt vorher, ob und wo er die Ente trifft – am Zeiger etwa „trifft Kopf mit
  2,9 m/s (0,17 N·s)“. Loslassen wirft, `Esc` bricht ab. Gedacht für gezielte, wiederholbare Stöße fürs Training.
- **In der Luft abstellen:** Mit dem Schalter „Dinge bleiben in der Luft, wo ich sie loslasse“ bleibt ein Ding ohne
  Schwung losgelassen stehen, wo es ist – etwa ein Ball auf Kopfhöhe, gegen den sie läuft. Wieder anfassen oder
  wegräumen löst es. **Fallen lassen:** Doppelklick auf ein schwebendes Ding, Taste `F` fürs gewählte, „Alle fallen
  lassen“ – oder den Schalter ausschalten, dann fällt alles.
- **Werfen:** Mit Schwung loslassen. Richtung und Tempo kommen aus der Mausbewegung über den Boden, der Winkel aus
  dem Regler **Wurfwinkel** (0–60°). Beim Schwingen zeigt ein gestrichelter Bogen, wo es landet, dazu Tempo,
  Winkel und Weite. Ohne Schwung loslassen legt es ab. Mit einem Ding gegen die Ente stoßen schubst sie.
- **Kamera:** Rechte Maustaste dreht, Mausrad zoomt. Am Touchscreen: ein Finger fasst an, zwei Finger drehen und
  zoomen.
- **Wegräumen:** Das zuletzt angefasste Ding ist gewählt (blauer Pfeil, Zeile im Bedienfeld). `Entf` oder
  „Wegräumen“ nimmt es weg. Woanders hinstellen: in der Leiste antippen und auf den Boden klicken.
- **Sie beschwert sich:** Ab und zu quakt sie, schüttelt grummelnd den Kopf oder sagt „Hey!“, „Na hör mal!“, nach
  einem Sturz „Puh. Quak!“ – passend zum Charakter, nie im Stopp-Fenster. Stimmung und Wesen ändert das nicht.
  Abschaltbar unter „Hilfe, ohne Maus, Aufstehen“.
- **Ohne Maus:** Unter „Hilfe, ohne Maus, Aufstehen“ im Bedienfeld: Stärke (leicht, mittel, kräftig), „Schubsen
  von“ vorn, hinten, links oder rechts, dazu „vor die Ente legen“, „auf sie werfen“, „zu ihr rollen“ und
  Wegräumen.
- **Sie hält selbst das Gleichgewicht:** Pollens Policies fangen Stöße ab. Fällt sie doch, beginnt das
  **Stopp-Fenster**: Oben erscheint „Gestürzt“ mit Countdown, und das Mikrofon ist kurz offen. „Stopp“ sagen oder
  „Liegen lassen“ drücken hält sie liegen (wie der Not-Aus). Sonst steht sie danach selbst auf, bis zu dreimal.
  Die Dauer ist einstellbar (2 bis 10 s, System → Einstellungen → Körper). Das gilt nach jedem Sturz, auch am
  echten Roboter.
- **Wie sie aufsteht** (wie Pollens `robotd`): Sie fällt mit schwachen Motoren (ein Viertel der Kraft), wartet,
  bis sie liegt, richtet sich in 0,6 s in die Grundstellung auf und übergibt dann an die Stand-Policy, die neu
  anfängt. Klappt das nach 6 s nicht, legt sie sich wieder hin und versucht es noch einmal.
- **Stoßreihe:** Unter Lernen → Training, Karte „Robustheit gegen Stöße“ (oder im Kollisionsmodus unter „Hilfe, ohne
  Maus, Aufstehen“). 48 Stöße aus 8 Richtungen, in 3 Stärken, an Rumpf und Kopf – unsichtbar in der Physik, in
  wenigen Sekunden. Die Tabelle zeigt, wo sie steht, wackelt oder fällt; ein älteres Profil lässt sich zum Vergleich
  danebenlegen, etwa vor und nach einem Training. Jeder Versuch wird auch eine Trainings-Episode. Seit 0.37 lässt sich
  jeder Stoß drei- oder fünfmal leicht gestreut wiederholen – dann zeigt die Tabelle Grenzfälle (mal stehen, mal
  fallen) und Ausfallschritte.
- **Trainingsdaten:** Jeder Stoß, Wurf und jede Berührung mit der Hand wird als Episode gespeichert (Reiz,
  Körperteil, Zustand vorher und nachher, Ausgang steht, wackelt, fällt oder steht wieder auf) in
  `kollision/episoden.jsonl` im Datenordner. Lernen → Training nutzt die gemessenen Stöße als Störungen beim Üben.
- **Kein Einfluss aufs Gemüt:** Spiel-Stöße ändern weder Stimmung noch Persönlichkeit, Gedächtnis oder
  Erfahrungsnetz. Höchstens ein kurzer Schreck, der nach wenigen Sekunden verfliegt.

## Akrobatik (Gliederpuppe)

**Lernen → Akrobatik**. Die Ente als Gliederpuppe in einer eigenen, unsichtbaren MuJoCo-Welt
(`physics/acrobatics.py`) – die Ente auf dem Bildschirm und der Roboter bewegen sich dabei nicht.

- **Biegen wie im CAD:** An jedem Gelenk sitzt ein Punkt (Hüfte, Knie, Fußgelenk, Hals, Kopf). Antippen
  wählt es, dann erscheinen **Drehringe** – nur für die Achsen, die der Motor dort wirklich hat
  (Hochachse blau, Kippen seitlich rot, Nicken grün). Am Ring ziehen dreht das Gelenk; daneben ziehen
  dreht die Kamera. Eine Karte daneben nennt das Gelenk, seine Grenzen und hat Regler je Achse; alle
  Regler gibt es aufklappbar unter „Alle Gelenke“.
- **Ampel:** Die Ente ruht flach auf dem unteren Fuß (ohne seitliches Fußgelenk neigt sich dafür der
  Rumpf). Alle Bodenpunkte spannen die **Stützfläche** auf, der **Schwerpunkt** hängt als Kugel mit
  Lot darüber. Grün = mindestens 4 mm innerhalb, gelb = knapp, rot = außerhalb (sie kippt) – immer
  mit Wort und Symbol, nicht nur Farbe.
- **Probe:** Die Motoren halten die Stellung wie eine gute Regelung (steif, aber mit der echten
  Kraftgrenze des XL330), MuJoCo rechnet zwei Sekunden und spielt sie ab.
- **Was beim Üben passiert** steht direkt daneben: was sie übt, was die Fähigkeit misst, was gespeichert
  wird – und dass das **kein Training des Laufprogramms** ist (das geht unter Lernen → Training).
- **Üben:** „Deine Haltung halten“, „Auf dem linken/rechten Bein“, „Tiefe Hocke“. Sie probiert viele
  leicht veränderte Haltungen (Kreuzentropie-Verfahren, Beine und Kopf – der Kopf ist ihr
  Balancier-Arm) und behält die besten. Die **Fähigkeit** (0–100 %) zählt, wie viele von fünf Stößen
  steigender Stärke sie übersteht und die Übung trotzdem schafft; der Strich zeigt den Stand vor dem
  ersten Üben. Beste Haltung und Verlauf landen in `akrobatik.json`. Beispiel aus dem Test: auf
  dem linken wie dem rechten Bein von 0 auf 50–75 % in rund zehn Sekunden. Für „Auf einem Bein“ probiert sie zuerst
  jede Art, das freie Bein zu heben, und nimmt die, auf der sie in der Probe am längsten steht (seit 0.38.37).
- **Ehrlich:** Am echten Microduck nimmt robotd für die Beine nur Policies an. Eine Beinhaltung wird
  dort erst durch Training möglich; Kopf und Hals gehen auch am Roboter direkt. Die Regler sind
  entsprechend markiert („nur Simulation“ / „auch am Roboter“).

## Mehrere Enten (Simulator)

Steuern → **Team** (bis 0.37 „Mehrere Enten“ unter Tricks): bis zu vier weitere Enten mit eigener Stimme, eigener Position und eigenem
Verhalten. Sie laufen frei herum und begrüßen sich, wenn sie sich treffen, folgen dir in Formation, setzen sich oder
tanzen – tanzt die Hauptente, tanzen alle im selben Takt mit, jede an ihrem Platz. Per Sprache: „alle tanzen“,
„alle mir nach“, „alle hinsetzen“, „alle frei“. Nur im einfachen Simulator. Standard sind keine weiteren Enten (seit
0.38.10); wer welche dazuholt, sieht sie im selben Modell wie die Hauptente. Seit 0.38.24 gelten weitere Enten bis zum
Beenden oder bis zum Wechsel in einen anderen Körper – jeder Start und jeder Wechsel beginnt wieder mit einer Ente. Weitere Enten tragen zufällig eine von Pollens vier Farben (erst
die, die im Zimmer noch fehlen); die Farbe deiner eigenen Ente wählst du unter Charakter → Persönlichkeit → Aussehen.

**Gezielt schießen** (seit 0.37.9): „Schieß den Ball zum Regal“, „schieß zu Kiki“, „schieß nach links“ – oder Ball
anklicken → „Schießen auf …“ → Ziel anklicken. Sie geht um Ball und andere Dinge herum zu einem Punkt hinter dem Ball,
kommt gerade und langsam heran, richtet sich genau aus, prüft, ob er ankam, und korrigiert einmal nach. Kommt er nicht
an (zu weit, etwas im Weg), sagt sie es.

**Purzelbaum** (seit 0.37.14 mit Platzprüfung): Vorn müssen etwa 50 cm frei sein, sonst dreht sie sich erst zur
freieren Seite oder sagt, dass der Platz fehlt. Landet sie verdreht, dreht sie sich in die alte Richtung zurück. Läuft
eine selbst trainierte Fassung, sagt sie das; ausprobierte eigene Policies bleiben nach dem Neustart erhalten.

**Teamarbeit** (seit 0.37.4): „Räumt alle Socken zum Sofa“ – jede Ente holt ein Ding, trägt es hin und meldet sich.
„Helft mir die Schachfigur suchen“ – jede sucht in ihrem Teil des Zimmers, wer sie zuerst sieht, ruft „Gefunden!“ und
bringt sie.

## Raum kennenlernen: Apportieren, Raum erkunden, Wo zuletzt gesehen (Simulator)

Bereich **Umgebung** (seit 0.38; vorher Steuern → Tricks → Raum kennenlernen):
- **Bring mir …** Socke, Klötzchen, Klemmbaustein oder Schachfigur: Sie holt das Ding, prüft, ob sie es wirklich im
  Schnabel hat (sonst Plan B: zurücktreten, neu ansetzen, bis zu drei Versuche) und bringt es zu dir – im Simulator zur
  Verkörperung, die die Maus führt – oder zurück zum Start. Per Sprache „Bring mir die Socke“.
- **Raum erkunden** (bis 0.37.12 „Kartieren“): Zwei Minuten lang geht sie gezielt an die noch unbekannten Ränder und
  sieht sich dort um; mit dem Tiefensensor hält sie fest, wo frei ist und wo etwas steht – der **erkundete Bereich**.
  Gemerkte Orte erreicht sie danach um Hindernisse herum. Der erkundete Bereich lässt sich auf dem Boden der 3D-Ansicht
  einblenden (Ansicht-Menü → „Erkundeter Bereich“) und erscheint im Lagebild. Per Sprache „Erkunde das Zimmer“.
- **Anwählen und Handeln** (seit 0.37.3): Klick auf ein Ding, ein Möbel oder eine andere Ente – ein Menü zeigt, was
  die Ente damit tun kann (aufheben, bringen, schießen, begrüßen, ärgern, hinterherlaufen …). Solange etwas angewählt
  ist, meint „das“ im Chat genau dieses Ding.
- **Zuletzt gesehen:** „Wo hast du die Socke zuletzt gesehen?“ – sie nennt Zeit und Stelle. Gemerkt werden nur Dinge und
  Möbel, nie Menschen. Erkundeter Bereich und Sichtungen bleiben auf dem PC.
- **Szene zurücksetzen** (seit 0.37.14): Liegt der Ball unerreichbar in einer Ecke, legt „Zurücklegen“ im Anwählen-Menü
  ihn an seinen Platz; „Szene zurücksetzen“ im Ansicht-Menü (oder per Sprache) räumt alle Dinge zurück und stellt die
  Ente wieder an den Start, sofern sie steht. Erkundeter Bereich und Gedächtnis bleiben. Nur im Simulator.

**Von oben** (seit 0.37.11): Beim Erkunden wächst neben den Knöpfen eine 2D-Ansicht mit freier Fläche,
Hindernissen, der Ente und allen gesehenen Dingen und Möbeln als Piktogramm. In 3D: „Im Cockpit in 3D ansehen“.

## Das lief schief – Fehler melden

System → Körper (oder Einstellungen → Über) → **Das lief schief**. duckpilot hält fest, was die Ente in den letzten
30 Sekunden getan hat (Haltung, Bewegung, Befehle, Stürze, Version, Einstellungen) und speichert es als Datei im
Datenordner. „Auf GitHub melden“ öffnet ein vorausgefülltes Issue, die Datei hängst du selbst an. **Nie dabei:**
Gespräche, Personen, Bilder, Schlüssel.

## Tanzen zu Musik (Choreomodus)

Steuern → **Tanzen**. Ein Musikstück wählen (mp3, m4a, ogg, wav, flac, bis 40 MB). Der Browser hört Tempo, die Eins
des Takts, Lautstärke und seit 0.38.23 ein **Klangbild je Takt** heraus (zwölf Tonklassen, sechs Frequenzbänder); die
Datei bleibt im Datenordner dieses PCs (`musik/`).

- **Zeitleiste** wie bei Roboter-Choreografie (Boston Dynamics Choreographer) und Licht-Sequenzern (xLights):
  Wellenform mit Taktraster, darunter die **Teile des Stücks** (Intro, Strophe, Refrain, Bridge, Drop, Breakdown,
  Outro – gleiche Teile durchgezählt, z. B. „Refrain 2“), eine Spur für Bewegungen und eine für Posen und Gesten.
- **Teile erkennen:** Grenzen liegen dort, wo sich das Klangbild deutlich ändert (bevorzugt alle vier Takte);
  Teile mit ähnlichem Klang gehören zusammen. Der wiederholte, laute Teil ist der Refrain – auch wenn er einmal
  leiser ist –, Wiederholungen vor dem ersten Refrain sind Strophen, ein einmaliger Teil mittendrin die Bridge.
- **Automatischer Tanz:** Jeder Teil hat sein Bewegungsmuster (ruhig nicken und wippen, laut wackeln und drehen),
  jeder Refrain wird gleich getanzt und beginnt mit einem Höhepunkt (Pose oder Geste), im letzten Takt die
  Schlusspose. Leise Phrasen in einem lauten Teil tanzt sie kleiner, Gesten folgen der Energie, langsame Stücke
  (unter 92 BPM) werden gewiegt. Alles sitzt auf Taktanfängen.
- **Mit KI choreografieren:** Das eingestellte Gehirn (Claude oder ein anderes Modell) bekommt die Teile des Stücks,
  die gespeicherten Posen und die Gesten aus Tricks und legt einen eigenen Tanz an – sichtbar im Gespräch.
- **Anpassen:** Die Liste ist nach Teilen gegliedert. Je Teil den Namen wählen – sein Tanz wird dann neu geplant, die
  anderen bleiben, wie du sie eingestellt hast; „Wie der erste tanzen“ übernimmt den Tanz des ersten gleichnamigen
  Teils. Je Schritt Bewegung, Länge in Takten und Pose/Geste. Klick in die Zeitleiste setzt die Startmarke,
  „Ab Marke proben“ spielt Musik und Tanz ab dort. Unter einem Namen speichern (`choreos.json`).
- **Posen** sind gespeicherte Haltungen aus Lernen → Akrobatik, z. B. auf einem Bein mit dem anderen nach hinten. Im
  Simulator mit echter Physik hält sie sie wirklich und kehrt danach in die Grundstellung zurück; im einfachen
  Simulator und am Roboter deutet sie sie mit Kopf und Haltung an. **Gesten** sind Pollens Emotionen und die eigenen
  Gesten aus Tricks.
- Per Sprache: „Tanz den Ententanz“. „Stopp“ beendet den Tanz sofort, die Musik hält mit an.
- **Bein zu Bein, Wiegen, Drehen** (seit 0.36.2): Seitschritte im Takt, Gewicht verlagern, ganze Drehungen – und sie
  bleibt dabei an ihrem Platz.
- **Tanzgesten** (seit 0.36.1): Gesten aus Tricks, im Takt gestreckt – der Planer wählt sie passend zum Teil des Stücks.
- **Nach Gehör** (seit 0.36.1): „Mithören und tanzen“ – sie hört übers Mikrofon Musik im Raum (Radio, Spotify,
  YouTube) und tanzt spontan. Das Audio bleibt im Browser, nur Tempo und Lautstärke gehen an duckpilot.
- **Weitere Enten** (seit 0.36.3): tanzen jede an ihrem Platz im selben Takt mit – siehe „Mehrere Enten“.
- **Klangsignatur** (seit 0.36.1): Charakter → Stimme → Klang – Tonhöhe und Klangfarbe ihrer Laute.

## Training

**Lernen → Training** führt in drei Schritten: **1. Was soll sie lernen?** – den Parcours schaffen oder eine
Grundfähigkeit (Gehen, Drehen, Aufstehen … aus Pollens Trainingsumgebungen). **2. Wo und wie?** – dieser PC,
Kaggle oder Hugging Face, mit den passenden Einstellungen. **3. Lernen starten** – ein Satz sagt, was gleich
passiert, darunter der große Start-Knopf. Den Parcours lernt sie nur am PC (Kaggle und Hugging Face sind dann
ausgegraut). Unter Lernen → Parcours wird „Lernen“ zum Hauptknopf, sobald ein Test zeigt, dass sie es noch nicht
schafft.

**Trainingsfeld** (oben auf der Seite, seit 0.38.19; seit 0.38.24 wie im Bild von NVIDIA zur Microduck): 144 Enten
(am Handy 40) üben gleichzeitig, jede auf ihrem eigenen Übungsfeld – Holzrampe, Stufen, Podest, Wellen oder flache
Matte, im klaren Raster in einer hellen Halle, Reihe für Reihe gegenläufig (seit 0.38.25) –, so wie das echte Training Tausende Physik-Welten rechnet.
**Hier lernt nichts**, es läuft keine Physik – das Schild am Feld sagt es: Ohne Lauf heißt es „Vorschau – hier lernt
nichts“ und zeigt eine Lernkurve im Zeitraffer; mit einem Lauf „Gemessene Quote, Bewegung nachgestellt“ – dann kommen
so viele Enten ohne Sturz ans Ende ihrer Kachel, wie der Lauf Durchgänge ohne Sturz geschafft hat. Gelernt wird nur in
einem Lauf, den du unten startest (am PC oder auf Kaggle). Seit 0.38.24 gehen die Enten mit den Gelenkwinkeln des
Simulators, jede auf ihrem Feld vom Start zum Ende (am Rand korrigiert sie, statt herunterzufallen; schwieriger Boden
lässt öfter stürzen), und schauen in Laufrichtung; zum Auftakt zieht die Kamera von einer Ente auf das ganze Feld auf; wer stürzt, kippt zur Seite, bleibt kurz liegen und wird wie eine Trainingswelt
an den Start zurückgesetzt. Die Figur (Original, wenn es in der 3D-Ansicht gewählt ist, sonst die einfache Ente) wird
einmal in acht Gangphasen und aus 16 Richtungen in voller Auflösung gezeichnet und bleibt im Browser gespeichert; bis
dahin stehen die einfachen Enten im Feld. Auf schwacher Grafik spart das Feld selbst (weniger Bildpunkte, weniger Enten).

| | Kosten | Was | Wer darf starten |
|---|---|---|---|
| **Dieser PC** | kostenlos (Strom) | duckpilots eigenes PPO-Nachtraining der Geh-Policy auf einem Parcours, Physik auf dem Prozessor, Netz auf der Radeon | du mit einem Klick, oder Claude |
| **Kaggle** | kostenlos, ≈ 30 GPU-Stunden pro Woche | Pollens Original-Training (`microduck_rl`) auf einer geschenkten NVIDIA-T4 | du mit einem Klick, oder Claude |
| **Hugging Face** | bezahlt, sekundengenau | Pollens Original-Training auf schnellen Mietkarten | nur du, mit zwei Klicks |

### Dieser PC: Lernschleife

Warum nicht einfach Pollens Training lokal? Es braucht MuJoCo Warp, und das läuft nur auf NVIDIA (unter
Windows gibt es für AMD weder Warp noch JAX/MJX). duckpilot rechnet deshalb anders: **mehrere
Rechenprozesse** (alle Kerne bis auf einen) fahren je acht Enten in eigenen MuJoCo-Welten – genau die Welt
des Parcours-Tests –, und das **Netz lernt auf der Grafikkarte** mit AMDs PyTorch für Windows (ROCm, die
RX 9070 XT meldet sich dort über `torch.cuda`); ohne passende Karte auf dem Prozessor.

- **Einrichten:** ein Klick installiert PyTorch für die erkannte Karte (Radeon: AMDs Paketquelle,
  ≈ 2,5 GB) und ONNX. Danach duckpilot neu starten.
- **Lernschleife:** eine Runde lernen (Standard ein Viertel des Budgets, 5–60 min), dann auf dem aktuellen
  Parcours **prüfen** (3 Durchgänge, wie „Testen“), dann vom **besten geprüften Stand** weiter – ein
  schlechterer Stand wird nie zur Grundlage. Schluss, wenn alle drei Durchgänge im Ziel sind oder das
  Zeitbudget (20 min bis 8 h) um ist. Kann die Start-Policy den Parcours schon, wird gar nicht gelernt.
- **Einmal am Stück:** ein Lauf mit dem ganzen Budget – auch ohne Parcours (3 m ebener Boden).
- **Sichtbar:** die Runden als Zeitleiste („Vorher 0 von 3 → Runde 1: 1 von 3 ▲ mehr im Ziel …“), dazu
  live die Kurven Fähigkeit (Anteil ohne Sturz), im Ziel und Belohnung, Schritte pro Sekunde und Zeit.
  Jeder Test landet auch unter Lernen → Parcours mit 3D-Wiederholung.
- **Ergebnis:** eine ONNX-Policy mit denselben Ein- und Ausgängen wie die Start-Policy
  (`policies\lokal\lokal-<name>-<datum>.onnx` im Datenordner). Sie steht im Parcours zur Auswahl und
  lässt sich im Physik-Simulator **ausprobieren**. Wird duckpilot mitten im Lauf beendet, speichert es den
  besten Stand; ein harter Abbruch lässt sich unter „Gespeicherte Ergebnisse“ nachträglich retten.
- **Ehrlich:** Das ist ein kleines Nachtraining (PPO wie rsl_rl, kleine Lernrate, Belohnung für
  Fortschritt, Ziel, ruhige Bewegungen, Strafe fürs Stürzen), kein Ersatz für Pollens großes Training.
  Für Schwellen und Rampen reicht es oft, für neue Kunststücke nimmst du Kaggle. Rechne mit einigen
  Tausend Schritten pro Sekunde – eine Nacht ist eine gute Größe. Speicher: ≈ 200 MB je Rechenprozess.
- Die Ente auf dem Bildschirm und der Roboter bewegen sich dabei nicht.

### Kaggle

Kaggle schenkt pro Woche rund 30 Stunden auf einer NVIDIA-T4. duckpilot schickt Pollens Training als
privates Notebook dorthin, holt Lernkurve und Ergebnis zurück und prüft es auf dem Parcours. Zugang: auf
kaggle.com anmelden (Telefon bestätigen, sonst gibt es keine GPU), unter Settings → API „Create New Token“,
die `kaggle.json` in duckpilot hineinziehen – der Schlüssel liegt nur im Windows-Tresor. Ein Lauf ist
höchstens 11 Stunden lang (Kaggles Grenze).

### Hugging Face Jobs

Pollens Reinforcement Learning (`microduck_rl`, mjlab) rechnet mit MuJoCo Warp,
das nur auf NVIDIA-Karten läuft. Pollen hat dafür selbst einen Weg eingebaut,
`uv run train <Aufgabe> --hf-jobs`: Der Lauf geht an **Hugging Face Jobs**, eine sekundengenau
gemietete GPU. duckpilot macht dasselbe ohne Kommandozeile – und möglichst günstig:

1. **Hugging-Face-Token** hinterlegen (fein eingestellt, mit Recht für *Jobs* und zum Anlegen eigener
   privater Repos). Er liegt im Windows-Tresor, nie in einer Datei; angezeigt wird nur `hf_…abcd`.
2. **Aufgabe** wählen – Gehen (eben, uneben, mit Getriebespiel), VelStand, Pirouette, Purzelbaum,
   Ball schießen, Aufstehen (eben/uneben), Hinsetzen, Aufheben.
3. **Start** wählen – das spart am meisten:
   - *Auf Pollens Stand*: setzt auf Pollens veröffentlichtem Trainingsstand auf
     (`pollen-robotics/microduck-training/bundles/…`, über Pollens `--init-checkpoint`). Gleiche
     Aufgabe = weitertrainieren, verwandte Aufgabe (z. B. Aufstehen uneben aus Aufstehen eben) =
     Warmstart. Meist reichen 500–1500 statt 3000–5000 Iterationen.
   - *Eigenen Lauf weiter*: nimmt den neuesten `model_*.pt` eines eigenen Laufs derselben Familie.
   - *Von vorn*: nur, wenn es nichts gibt.
4. **Kosten vorab**: Iterationen, Grafikkarte (mit Preis pro Stunde) und eine **Obergrenze in
   Stunden** – danach beendet Hugging Face den Job hart. duckpilot zeigt „≈ X $, höchstens Y $“ und
   rechnet nach den ersten Läufen mit **gemessenen** Sekunden pro Iteration statt mit Schätzwerten.
5. **Bei Stillstand abbrechen** (wahlweise): duckpilot liest die Lernkurve alle zehn Minuten. Steigt die
   Belohnung nach einem Drittel des Laufs kaum noch, bricht es ab und exportiert den letzten
   Zwischenstand auf einer kleinen Grafikkarte zur `policy.onnx` – statt Stunden für nichts zu zahlen.
6. **Varianten**: bis zu drei Läufe mit verschiedenen Belohnungsgewichten
   (`env.rewards.upright.weight = 3`; nur Zahlen und true/false) parallel. Ist ein Auftrag verknüpft,
   prüft duckpilot alle auf dem Parcours und nennt die beste.
7. **Zweimal klicken** zum Starten – der zweite Klick zeigt die Kosten noch einmal.

Jeder Lauf zeigt Fortschritt, Belohnung und Trend, auf Wunsch die **Lernkurve** (Belohnung und
Episodenlänge, Werte beim Überfahren), die einzelnen Belohnungsterme (Laufmitte gegen jetzt) und die
Abbruchgründe. Abgebrochene oder fehlgeschlagene Läufe lassen sich als **Zwischenstand exportieren**,
fertige **weitertrainieren**. **Im Physik-Simulator ausprobieren** lädt `exported/policy.onnx` und setzt
es als Gangart, Trick oder festen Platz ein.

Claude darf **kostenlose** Läufe selbst starten (`training_kostenlos`: dieser PC mit Lernschleife oder
Kaggle) und sagt dir dabei, was und wie lange. Bezahlte Läufe kann Claude nur **vorschlagen** (`training_vorschlagen`: Aufgabe, Start, Varianten, Obergrenze,
Stillstand-Regel, Begründung) und **auswerten** (`training_auswerten`: liest dieselbe Lernkurve und
schlägt gezielt Gewichte vor – „Wie läuft das Training?“). Starten, abbrechen und exportieren tust du.

### Policies aus Isaac Lab (seit 0.38.27)

NVIDIA trainiert die Microduck in **Isaac Lab** (Aufgaben `IsaacContrib-Velocity-Flat-MicroDuck` und
`…-Rough-MicroDuck`, mit NVIDIA-Grafikkarte; Anleitung im NVIDIA-Blog „Using AI agents to teach robots like Microduck to
walk in simulation“). Die dort exportierte Gang-Policy (`exported/policy.onnx`) übernimmst du unter **Lernen → Training →
Policies aus Isaac Lab übernehmen**:

1. Quelle wählen: **Von Hugging Face** (seit 0.38.30) – Adresse eingeben, etwa `besitzer/microduck-policy` oder einen
   Link auf die `.onnx`-Datei; Knowlin lädt nur von huggingface.co und nur Policy-Dateien bis 60 MB. Liegen im Repo
   mehrere, wählst du eine aus der Liste. Darunter schlägt Knowlin öffentliche Microduck-Policies von Hugging Face vor
   (meistgeladene zuerst) – „Auswählen“ trägt Adresse und Datei ein. Private Repos gehen mit dem Hugging-Face-Schlüssel aus dem Training. Oder
   **Datei von diesem PC**. Dann Namen geben und angeben, mit welcher Aufgabe sie trainiert wurde.
2. Knowlin prüft, ob sie zur Microduck passt: 61 Beobachtungswerte, 14 Gelenke in derselben Reihenfolge, dieselbe
   Grundstellung, 50 Hz. Passt sie nicht, sagt es warum und übernimmt nichts.
3. **Prüfstand** in der Physik (MuJoCo, mit BAM-Motormodell, wenn installiert): stehen, vorwärts 0,25 m/s, seitwärts
   0,15 m/s, drehen 0,8 rad/s und ein Schubs von der Seite – einmal **wie trainiert** (ohne Glättung) und einmal **wie am
   Roboter** (mit der Glättung von `robotd`). Ist Pollens Gangart geladen, läuft sie dieselben Prüfungen; eine Bewegung
   gilt dann auch als bestanden, wenn die neue Policy mindestens 80 % davon schafft.
4. Nur wer **besteht**, ist „für die echte Ente frei“. Ausprobieren im Physik-Simulator geht immer
   (**Im Physik-Simulator nutzen**, zurück mit **Zurück auf Pollens Standard**).

**Was gerade läuft (seit 0.38.35):** Oben auf der Karte steht, ob im Physik-Simulator Pollens Standard-Gangart
(`velstand.onnx` aus `pollen-robotics/microduck-policies`) oder eine übernommene Policy läuft; „Zurück auf Pollens
Standard“ steht direkt daneben. Übernehmen ändert nichts am Körper – erst „Im Physik-Simulator nutzen“ wechselt, und nach
jedem Neustart läuft wieder Pollens Standard. Pollens Paket ist in der Liste als „Standard · läuft schon in der Physik“
markiert; seine Dateien: `velstand` Gehen & Stehen (Standard), `alpha_walking`/`alpha_stand` ältere Fassungen,
`alpha_sitstand` Hinsetzen & Aufstehen, `alpha_ground_pick` Aufheben, `ball_kick_left/right` Schuss, `roulade`
Purzelbaum, `roller`/`roller_crouch` Fahren auf Rollen (Rollen noch nicht unterstützt). Die Rampen-Policy aus NVIDIAs
Vorführung gibt es nicht als Datei – veröffentlicht ist nur die Übungsumgebung in Isaac Lab (nur NVIDIA-Grafikkarten);
Ähnliches geht unter Lernen → Parcours mit einer Rampe und „Lernen, bis sie es kann“.

Befehle werden auf die im Training geübten Bereiche begrenzt (vorwärts ±0,4 m/s, seitwärts ±0,3 m/s, drehen ±1 rad/s) –
das steht in `manifest.json` neben der Policy unter `policies/import/<name>/`, bei Hugging Face auch Repo, Pfad,
Stand und Lizenz laut Modellkarte. Nur am PC.

## Parcours und Aufträge

**Lernen → Parcours** – der Ablauf aus NVIDIAs Microduck-Vorführung (GTC Berlin
2026: planen → Parcours bauen → trainieren → prüfen), nur ohne Isaac Sim und ohne NVIDIA-Karte:

| Schritt | Wer | Wie |
|---|---|---|
| Ziel | du | ein Satz: „Sie soll eine Rampe mit 8° hinauf und dann durch einen Slalom.“ |
| Parcours | Claude (oder das lokale Modell) | Werkzeug `parcours_bauen`; oder eine Vorlage |
| Basis-Test | duckpilot | Pollens Geh-Policy läuft mehrmals hindurch (`parcours_testen`) |
| Vorschlag | Claude | scheitert sie, schlägt Claude einen Trainingslauf vor (`training_vorschlagen`) |
| Training | du oder Claude | **„Lernen, bis sie es kann“** startet die Lernschleife am PC (kostenlos); oder Kaggle; bezahlt nur mit deinen zwei Klicks |
| Bewertung | duckpilot | ist der Lauf fertig, prüft duckpilot ihn selbst auf demselben Parcours |

**Elemente** (Bahn 50 cm breit, gerade, höchstens 8 Elemente und 8 m): Rampe (hinauf, oben eben,
hinunter), Stufen (1–4, bis 6 cm), Schwelle, unebener Boden aus flachen Platten, Slalom
(Stangen abwechselnd links und rechts umrunden) und Engstelle (zwei Wände). Werte über dem, was
Pollens Geh-Policy vermutlich kann (Rampe etwa 12°, Stufe 2,5 cm, Schwelle 2 cm), sind erlaubt und
werden markiert – genau das sind gute Ziele fürs Training.

**Testen ist kein Lernen.** Ein Test zeigt nur, ob sie es schon kann und wo es hakt (Seite oben erklärt
beides). Ein **Durchgang** ist ein Lauf vom Start bis Ziel, Sturz oder Zeitende; „2 von 3 Durchgängen im
Ziel“ steht bei jedem Test. Pollens Geh-Programm ist auf ebenem Boden trainiert – bleibt sie an einer
kleinen Schwelle hängen, hilft nur Training, am einfachsten mit **„Lernen, bis sie es kann“**.

**Test:** Ein einfacher Wegfolger gibt der Policy Gehbefehle von Marke zu Marke. Versuch 1 läuft
genau wie gebaut, weitere mit etwas anderer Bodenreibung (0,7–1,15) und Startlage – so zeigt sich,
ob es nur Glück war. Die Versuche rechnen nebeneinander auf dem Prozessor, schneller als Echtzeit.
Pro Element steht da: geschafft, gestürzt, steckt fest, Stange ausgelassen oder nicht erreicht.
Versuch 1 läuft als **3D-Wiederholung** mit Pollens Modell ab (abspielen, spulen, 1×/2×/4×).

**Was die Radeon RX 9070 XT dabei tut:** Claude oder das lokale Sprachmodell (Ollama auf der
Grafikkarte) plant und baut den Parcours, die Physik rechnet auf dem Prozessor, die Stimme
(Qwen3-TTS) auf der Grafikkarte – und beim Lernen am PC das neuronale Netz (PyTorch mit ROCm), während
die Physik auf dem Prozessor läuft. Pollens eigenes Training (mjlab mit MuJoCo Warp) braucht dagegen
NVIDIA – dafür Kaggle oder Hugging Face Jobs.

Der Auftrag liegt in `auftraege.json`, die Aufzeichnungen in `parcours\` im lokalen App-Datenordner.

### Fähigkeit und Abgleich Training ↔ Roboter

- Jeder Lauf zeigt eine **Fähigkeit**: den Anteil der Übungsdurchgänge, die bis zum Ende laufen
  (`Episode_Termination/time_out`) statt mit Sturz oder Abbruch zu enden – als Balken mit Startwert
  und als eigene Kurve unter „Lernkurve“.
- **Abgleich Training ↔ Roboter** (aufklappbar): was Pollens Training annimmt und was robotd am
  Roboter einstellt – Regler-Steifigkeit (beide 200), Aktionsskala (Training 1,0, Roboter 0,9),
  Glättung (Training ungefiltert, Roboter Tiefpass 0,5/0,7), Akkuspannung (abgedeckt), Gelenk-
  Nullpunkte (Pollen kalibriert nicht je Roboter, das Training streut ± 0,015 rad), Getriebespiel.
- Wer eine Gangart trainiert, bekommt den Hinweis auf die **Backlash-Variante** derselben Aufgabe –
  sie überträgt sich besser auf echte Servos.

## NFC-Tags als Auslöser

**Alltag → NFC-Tags.** Einem Tag wird ein Satz zugeordnet, so wie man ihn der Ente sagen würde – „setz dich“ für den
Ladeplatz, „tanz“ für die Party-Ecke. Berühren schickt genau diesen Satz durch dieselbe Verarbeitung wie ein
getippter Befehl, mit allen Sicherheitsregeln; kurze Befehle laufen ohne Claude.

- **Lesen am Handy:** Chrome unter Android kann NFC-Tags lesen (Web NFC) – nur über eine https-Adresse, also mit der
  Handy-Fernbedienung über Tailscale. Auf „Tags lesen“ tippen, Tag an die Rückseite halten. Ein unbekannter Tag
  wird gemerkt und fragt nach Name und Satz. Beschreiben muss man ihn nicht – erkannt wird er an seiner Seriennummer.
- **Ohne Lesegerät:** „Tag zum Ausprobieren anlegen“ und „Auslösen“ – zum Testen im Simulator.
- **Am Roboter:** Pollens `nfcd` liest Tags bisher nur zum Koppeln eines Gamepads und meldet sie nicht weiter.
  Sobald robotd Tag-Ereignisse anbietet, hängt duckpilot sie hier an.
- Die Zuordnungen liegen in `nfc_tags.json` im lokalen Datenordner.

## Folg mir

„Folg mir“, „komm mit“ oder der Knopf **Folg mir** in der 3D-Ansicht: Die Ente läuft hinter dem Menschen her und hält
etwa einen halben Meter Abstand. Bleibst du stehen, bleibt sie stehen; kommst du ihr zu nah, weicht sie einen kleinen
Schritt zurück und schaut zu dir hoch. Ist niemand mehr zu sehen, schaut sie sich um und hört nach 20 s auf.

- **Simulator und Physik:** Die Maus (oder der Finger) führt eine halb durchsichtige Verkörperung über den Boden.
- **Echter Roboter:** Das Verhalten folgt jedem Menschen, den die Wahrnehmung meldet (`art: person`). Die Erkennung
  aus dem Kamerabild – nur „ein Mensch“, ohne zu erkennen wer, ohne Bild zu speichern – kommt mit dem Roboter.
- Es gelten alle Sicherheitsregeln: Not-Aus, Hindernis-Reflex, höchstens 0,22 m/s. Laser und Folg mir schließen sich aus.
- Auch für Claude (`mir_folgen`) und über MCP.

## Laserpunkt folgen

Wie Pollens eigene Funktion: Die Ente läuft dem roten Punkt eines Laserpointers hinterher (der Pointer liegt dem
Zubehör-Pack bei).

- **Simulator und Physik:** Knopf **Laser** oben in der 3D-Ansicht. Dann ist die Maus (oder der Finger) der
  Pointer – der Punkt liegt, wo sie hinzeigt, auf Möbeln oben drauf. Maus aus dem Bild = Pointer aus.
- **Echter Roboter:** derselbe Knopf startet das Folgen; die Kopfkamera sucht den Punkt (klein, sehr hell, deutlich
  röter als die Umgebung, große rote Flächen wie der Ball zählen nicht) und rechnet ihn mit Kopfneigung und
  Kamerahöhe auf den Boden. Die Schwellen sind geschätzt und am echten Roboter nachzustellen.
- Sie bleibt knapp vor dem Punkt stehen und schaut ihn an, sucht ihn mit dem Kopf und dreht sich, wenn er weg ist,
  und hört nach 15 s ohne Punkt von selbst auf. Der Hindernis-Reflex bleibt an.
- Per Sprache: „folge dem Laser“, „fang den Punkt“ – Claude nutzt dafür das Werkzeug `laser_folgen`.

## Hindernissen ausweichen

Seit 0.33 bremst die Ente vor Hindernissen nicht nur, sie **weicht aus und läuft drumherum** – in allen Modi: Folg mir,
Laser, Hinlaufen, Erkunden, Annähern und beim Steuern von Hand.

- Sie merkt sich, was der Tiefensensor in den letzten Sekunden gesehen hat, damit sie ein Hindernis nicht vergisst,
  sobald es beim Drehen aus dem Blickfeld rutscht.
- Sie nimmt die nächstgelegene freie Richtung, bleibt bei der einmal gewählten Seite und geht am Hindernis entlang,
  bis der Weg zum Ziel frei ist. Dabei schaut sie in die Kurve; nah an Kanten geht sie langsamer.
- Sitzt sie fest (2,5 s gewollt und nicht weitergekommen), geht sie kurz zurück und dreht sich frei. Beim Steuern von
  Hand hilft sie nur beim Lenken und Bremsen – rückwärts fährt sie dort nie von selbst.
- **Echter Roboter:** vorerst nur mit den drei Sektoren des Tiefensensors; das Gedächtnis kommt dazu, sobald die
  Kopf-Kalibrierung geprüft ist.
- **Ganz ohne Tiefe** (Odi ohne Kamera, echte Open Duck, seit 0.38.27): Wo sie festsaß, anstieß, gegen etwas fiel oder
  einen Ruck von vorn bekam (nicht von deiner Hand), merkt sie sich die Stelle zwei Minuten lang als kurze Wand, setzt
  ein Stück weiter zurück und läuft beim nächsten Anlauf daran vorbei, statt wieder dagegen.
- Not-Aus und alle Sicherheitsregeln gelten unverändert; das Ausweichen macht sie nie schneller.
- Abschalten: Charakter → Persönlichkeit → Verhalten → „Hindernissen ausweichen“. Dann bremst sie nur, wie bis 0.32.

## Kamera und Enten-Erkenner (echter Roboter)

- **Entenblick** zeigt am echten Roboter das Bild der Kopfkamera: duckpilot holt über den Tunnel
  (`-L 7903:/run/mediad/media.sock`) ein paar Bilder pro Sekunde von `mediad` (`media.frame`, UYVY)
  und dreht sie aufrecht wie Pollens eigener Bildweg.
- **Enten-Erkenner** (Skill-Paket): Pollens YOLO-Modell `microduck-duck-detector` läuft auf dem PC,
  Rahmen erscheinen im Entenblick, und Claude bekommt das Werkzeug `andere_enten` (Richtung und
  ungefähre Nähe jeder erkannten Microduck).

## Roboter-Pflege (echter Roboter)

Unter System → Zustand, sobald der echte Roboter verbunden ist – über Pollens eigene Dienste statt über die
SSH-Konsole:

- **Zustand:** Name, Seriennummer, Laufzeit, WLAN (configd), Gesundheit, Akku, CPU- und
  Motortemperatur (robotd).
- **Updates:** nach einem neuen Stand suchen, **Probelauf** (lädt und prüft alles, tauscht nichts)
  und **einspielen** (zwei Klicks). Verlangt der Roboter dafür Root-Rechte, nennt duckpilot den
  Befehl für die Konsole.
- **Protokolle** von robotd, mediad, updaterd, configd, tofd, padd und btd.
- **Pflegeheft der Motoren** (`robot.vetbook`): je Gelenk Stunden unter Strom, Weg in Umdrehungen,
  heißeste Temperatur und ausgelöste Schutzschaltungen (Hitze, Geber, Stoß, Überlast), dazu die
  letzten Einträge. Motoren mit den meisten Auslösern stehen unter „Zuerst ansehen“.

**Gelenk-Check** (System → Zustand, in jedem Körper): je Gelenk Sollwert (Strich), Nachlauf (Soll − Ist) und
Last (am Roboter aus `currents_ma`, in der Physik aus dem Motormoment), mit Ampel gut / auffällig /
prüfen (Nachlauf ab 6° bzw. 14°, Last ab 70 % bzw. 90 %). Stromlos oder gestürzt wird nicht bewertet.
Die einfache Simulation hat keine Motoren und zeigt nur Winkel.

Tunnel für alles (leere Adressfelder folgen dieser Reihenfolge):
`ssh -N -L 7900:/run/robotd.sock -L 7901:/run/tofd/tof.sock -L 7902:/run/updaterd.sock -L 7903:/run/mediad/media.sock -L 7904:/run/configd.sock microduck@<IP>`

WLAN einrichten und den Roboter koppeln bleibt bei Pollens App (Bluetooth).

## Stimme und Gespräch

**Charakter → Stimme** (Gesprächsmodus und lokales Sprachmodell unter **System → Gehirn & Gespräch**). Alles läuft auf deinem PC; die Stimme kommt aus dem
PC-Lautsprecher, auch wenn der echte Roboter verbunden ist – sein Schnabel bewegt sich mit.

| Sprachmotor | Wie | Braucht |
|---|---|---|
| **Browser-Stimme** | Stimmen von Windows bzw. Edge | nichts |
| **Piper** | schnelle, natürliche Open-Source-Stimmen (Thorsten-Voice u. a.); „Thorsten, mit Gefühl“ klingt je nach Stimmung fröhlich, überrascht, flüsternd oder verschlafen | Prozessor genügt; ≈ 40 MB Programm + 60–110 MB je Stimme |
| **Qwen3-TTS** | am natürlichsten: Du **beschreibst die Entenstimme in Worten**, das Modell erfindet drei Fassungen, du übernimmst die schönste – danach klingt die Ente immer so | Grafikkarte empfohlen; ≈ 3,5 GB Pakete + 2,4 GB (schnell) bzw. 4,5 GB (hoch, Entwurf) Modelle |

Installieren geht in der Oberfläche mit einem Knopf (fest vorgegebene Pakete, das Protokoll ist
sichtbar). Für **AMD-Karten (Radeon RX 9000/7000)** installiert duckpilot PyTorch mit ROCm direkt
unter Windows aus AMDs Paketquelle; für NVIDIA PyTorch mit CUDA. Modelle und Stimmen liegen im
lokalen App-Datenordner (Windows `%LOCALAPPDATA%\duckpilot`, macOS `~/Library/Application Support/duckpilot`,
Linux `~/.local/share/duckpilot`), nicht in OneDrive.

**Entenstimme auf Deutsch beschreiben:** Die Vorlagen und dein eigener Text stehen auf Deutsch. Vor dem
Entwerfen übersetzt duckpilot die Beschreibung ins Englische, weil Qwen Stimmbeschreibungen so am
genauesten umsetzt – mit Claude, ohne Schlüssel mit dem lokalen Sprachmodell. Für die Vorlagen liegt
eine geprüfte englische Fassung bereit, dafür braucht es keine Übersetzung. Was ans Modell ging, steht
unter „An das Modell“. Geht beides nicht, wird der deutsche Text genommen; das klappt auch, nur
Feinheiten kommen ungenauer an. Die Ente spricht in jedem Fall Deutsch.

- **Wie sehr nach Ente:** höher und nasaler – für Thorsten & Co. etwa in der Mitte; bei entworfenen
  Qwen-Stimmen aus.
- **Entenlaute zwischendurch:** aus, selten, manchmal, oft. Claude schreibt Laute als `*quak*`,
  `*quak?*`, `*gurr*` in die Antwort; duckpilot spielt dafür echte Laute aus Pollens Stimmbank (am
  Roboter quakt er selbst) und streut je nach Einstellung selbst welche ein. Nie bei Stopp,
  Sicherheit oder ernsten Themen.
- **Schnabel:** Aus der Lautstärke jedes Satzes entsteht eine Schnabelspur – im Simulator und am
  echten Roboter.
- **Schnell trotz großer Modelle:** Jeder Satz wird einzeln erzeugt; der erste spielt schon, während
  die nächsten entstehen.
- **Zwei Qwen-Modelle:** Entworfen wird mit dem großen Entwurfsmodell, gesprochen mit dem kleineren
  Sprechmodell. Nach dem Übernehmen lädt duckpilot das Sprechmodell (beim ersten Mal ≈ 2,4 GB, Anzeige
  auf der Stimme-Seite); bis es da ist, spricht die Browser-Stimme. Braucht ein Satz länger als
  15 Sekunden, springt für ihn ebenfalls die Browser-Stimme ein – das Gespräch wartet nie.
- **Fortschritt und Fortsetzen:** Beim Herunterladen zeigt die Stimme-Seite, wie weit es ist. Bricht es
  ab, geht es beim nächsten Start an derselben Stelle weiter.
- **Eigener Prozess:** Qwen rechnet in einem eigenen Arbeitsprozess – die Oberfläche bleibt bedienbar, auch
  wenn das Modell lädt oder der Grafiktreiber hakt. Probleme stehen in `qwen-arbeiter.log` im App-Datenordner.
- **Tempo und Rückfall:** Die Stimme-Seite zeigt, wie viele Sekunden Qwen je Sekunde Sprache rechnet. Schafft
  es eine Antwort nicht flüssig, spricht die ganze Antwort Piper (falls geladen) bzw. die Browser-Stimme.
- **Kein Entenfilter:** Entworfene Stimmen klingen schon wie beschrieben; „Wie sehr nach Ente“ gilt nur für
  Piper und die Browser-Stimme.

**Plaudern** (Schalter unter der Sprechtaste oder auf der Seite Stimme): Die Ente redet
ausführlicher, fragt zurück, erzählt von ihrem Tag und hört nach jeder Antwort acht Sekunden lang zu,
ohne Weckwort (mit der Online-Spracherkennung). Erzählst du ihr etwas über dich und möchtest, dass
sie es behält, merkt sie es sich als **Wissen** – nie Passwörter, Bank-, Ausweis- oder
Gesundheitsdaten (das lehnt duckpilot auch selbst ab).

**Lokales Sprachmodell:** Unter *Einstellungen → KI-Modell → Lokales Modell* (bis 0.38.32 „Eigenes Modell“) läuft ein offenes Modell in
[Ollama](https://ollama.com) auf deiner Grafikkarte, z. B. Qwen 3.5 (9 Mrd.) oder Gemma 4 (12 Mrd.) –
laden per Knopf. Es bekommt dieselbe Persönlichkeit, denselben Lagebericht und **dasselbe
Gedächtnis**: Was die Ente mit Claude gelernt hat (Tricks, Wissen, Vorlieben), weiß sie auch hier.
Bewegen kann es sich mit einer Auswahl der Werkzeuge. Ist Claude nicht erreichbar, springt es
automatisch ein, danach die einfachen Befehle.

## Erfahrungsnetz und Hirnaktivität

Was die Ente zusammen erlebt, verknüpft sich – nach dem Prinzip „was zusammen feuert, verdrahtet sich“ (Hebb).

- **Knoten:** Personen (nur angelernte, mit Einverständnis), Orte, Dinge, Tageszeiten, Tätigkeiten, Gefühle,
  Sinneseindrücke (gestürzt, hochgehoben, Stimme gehört) und Rückmeldungen (Lob, Kritik).
- **Lernen:** Was gleichzeitig aktiv ist, wird stärker verbunden; starke Erlebnisse (Sturz, Lob) prägen tiefer.
  Tageszeit, Wochentag, der nächste gemerkte Ort und der Ruhemodus laufen leise als Rahmen mit.
- **Vergessen:** Ungenutztes verblasst (Halbwertszeit zwei Wochen); nach einer Stunde Ruhemodus wird gefestigt und aufgeräumt.
- **Erinnern:** Aus der Lage breitet sich Aktivierung aus; was mitschwingt, bekommt Claude als kleinen Ausschnitt
  („fällt ihr ein: Ball, Freude“) – nie Personen in einer Runde vom Handy.
- **Prägung:** Nach vielen Erlebnissen verschiebt sich ihr Temperament leicht (± 0,1): viel Spiel und Lob → etwas
  lebhafter, viele Schrecken → ruhiger. Die eingestellte Persönlichkeit bleibt der Anker.
- **Ansehen:** System → Zustand → **Hirnaktivität** zeigt das Netz live – aktive Knoten leuchten, frische
  Verknüpfungen blitzen auf; ein Klick zeigt, womit ein Knoten verknüpft ist und zuletzt warum, und lässt ihn vergessen.
  Unter Charakter → Gedächtnis: Überblick und „Netz zurücksetzen“ (zwei Klicks). „Alles vergessen“ leert auch das Netz.
- **Ehrlich:** ein lernendes Gewichtsnetz, kein Deep Learning und kein Bewusstsein; das Sprachmodell lernt nicht.
  Lernt nur bei eingeschaltetem Gedächtnis, liegt lokal in `erfahrung.json`.

**Was Knowlin über deine Welt weiß (seit 0.38.27):** Oben im Gedächtnis stehen Themenkarten – Menschen (nur am PC),
Orte, Dinge, Tätigkeiten, je die, über die Knowlin am meisten weiß. Zu jedem Thema: wie oft erlebt und wie viele
Verknüpfungen, der **Gefühlston** (aus den Verbindungen zu Freude und Lob bzw. Schreck, Sturz und Kritik – als Zeichen
und Wort: „+ eher schön“, „− eher heikel“, „± gemischt“), wann zuletzt erlebt, wie sicher („oft bestätigt“ …) und womit
es am stärksten verknüpft ist. Ein Klick auf ein Thema öffnet es im Netz. Unter dem Netz steht in Worten, was Punkte,
Linien und Leuchten bedeuten.

**Herkunft (seit 0.38.10):** Jeder Knoten und jede Verbindung zählt mit, wo sie gelernt wurden – Knowlin ohne Körper
oder welche Verkörperung, im Simulator oder echt. Über „Alle Herkünfte“ lässt sich filtern (der Rest wird blass), im
Knotendetail steht z. B. „Gelernt: 3× Quacki (Simulator), 1× Knowlin (ohne Körper)“. Im Gedächtnis steht bei Wissen
und Vorlieben „gemerkt von …“. Was vor 0.38.10 gelernt wurde, hat keine Herkunft.

**Bei Knowlin (seit 0.38.11):** Unter Wissen → Gedächtnis lebt das Netz – es dreht sich langsam von selbst, die Knoten
schweben, Impulse laufen die Verknüpfungen entlang, dahinter wabert eine weiche Hülle. In der Verkörperung bleibt die
Ansicht ruhig; mit „Bewegung reduzieren“ steht sie still.

## Gedächtnis

Claude selbst lernt nichts dazu. Die Ente merkt sich aber, was du ihr beibringst, in einer Datei auf
deinem PC. Bei jeder Nachricht bekommt Claude den passenden Ausschnitt mit, also deine Vorlieben, die
Namen der Tricks und die nächstgelegenen Orte, was sie über dich weiß und was du zu einem Trick
schon gesagt hast. Das funktioniert auch ohne Claude mit den einfachen Befehlen und mit dem eigenen
Sprachmodell.

| Du sagst | Die Ente merkt sich |
|---|---|
| „Merk dir das als Verbeugung“ (nach einer gelungenen Bewegung) | einen **Trick**. Danach reicht „Verbeug dich“. |
| „Das hier ist die Küche“ | einen **Ort**. Danach reicht „Geh in die Küche“. |
| „Merk dir: lauf lieber langsam“, oder zu Claude „Das war zu wild“ | eine **Vorliebe**, an die sich Claude hält |
| „Ich spiele Gitarre – merk dir das“ | **Wissen** über dich, auf das sie im Gespräch zurückkommt |
| „Die Verbeugung war zu wild“ | eine **Notiz am Trick**; sie zeigt eine ruhigere Fassung, und wenn sie dir gefällt, ersetzt die neue die alte (die alte bleibt als Version, „nimm die alte Verbeugung wieder“ holt sie zurück) |
| „Was hast du dir gemerkt?“ | zählt alles auf |
| „Vergiss die Küche“ | löscht den Eintrag |

Zusätzlich schreibt sie ein kurzes **Protokoll** dessen, was schiefging: Stürze, abgelehnte Befehle,
Kicks ins Leere. Claude sieht die letzten Einträge und kann darauf Rücksicht nehmen.

**Einsehen und löschen:** Oben rechts öffnet der Knopf „Gedächtnis“ eine Übersicht. Dort lassen sich
Tricks vorführen, Orte ansteuern und jeder Eintrag einzeln vergessen. „Alles vergessen“ löscht nach
einem zweiten Klick alles. Vorher legt Knowlin einen Sicherungspunkt an (seit 0.38.24).

**Sicherungspunkte, Zurücksetzen, Export** (seit 0.38.24, Einstellungen → Sicherungspunkte, nur am PC): Wie im Leben,
nur mit Rückweg. Knowlin legt jeden Tag beim Start einen Sicherungspunkt an (die letzten 14 bleiben) und vor jedem
Zurücksetzen, Wiederherstellen und „Alles vergessen“ noch einen (die letzten 10). Eigene Punkte mit Namen („Vor dem
Tanzabend“) bleiben, bis du sie löschst. Ein Punkt enthält sechs Bereiche:

| Bereich | Was darin steckt |
|---|---|
| Gedächtnis | Wissen, Vorlieben, Orte, Tricks und das Protokoll |
| Erfahrungsnetz | Knoten und Verbindungen der Hirnaktivität |
| Charakter | Energie, Humor, Eigenschaften und Eigenständigkeit jeder Verkörperung |
| Übungen | eingeübte Akrobatik und Posen |
| Tänze | eigene Choreografien (die Musikstücke bleiben, wo sie sind) |
| Raum | Karten und zuletzt gesehene Dinge je Körper |

**Zurücksetzen:** Bereiche ankreuzen, „Ausgewählte zurücksetzen“, zweiter Klick. **Wiederherstellen:** beim Punkt
„Wiederherstellen …“, Bereiche wählen, zweiter Klick – der jetzige Stand wird vorher gesichert, also lässt sich auch
das rückgängig machen. **Exportieren** lädt einen Punkt als ZIP herunter, **Sicherung importieren** nimmt so ein ZIP
wieder auf (streng geprüft: nur bekannte Dateien, gültiges JSON). Nie in einem Sicherungspunkt: Personen (Gesichter),
Schlüssel und Einstellungen. Die Punkte liegen im Datenordner unter `sicherungspunkte/`.

**Wo die Datei liegt:** standardmäßig *nicht* im Projektordner, sondern im lokalen App-Datenordner,
unter Windows `%LOCALAPPDATA%\duckpilot\memory.json`, unter macOS
`~/Library/Application Support/duckpilot/memory.json`, unter Linux `~/.local/share/duckpilot/memory.json`. So landet sie nicht ungefragt per OneDrive in der
Cloud. Der genaue Pfad steht beim Start im Fenster und unten in der Übersicht. Mit
`--memory <Datei>` oder `[memory] path` in `duckpilot.toml` lässt sich ein anderer Ort wählen,
mit `--no-memory` schaltest du das Gedächtnis aus. Die Datei ist lesbares JSON.

**Gut zu wissen**
- Orte gelten je Körper: Positionen aus dem Simulator werden auf dem echten Roboter nicht angeboten
  und umgekehrt. Auf dem Roboter beruhen sie auf der Odometrie. Sie verschieben sich mit der Zeit
  und stimmen nach einem Neustart der Ente nicht mehr.
- Grenzen: 50 Tricks (je 5 ältere Fassungen und 8 Notizen), 30 Orte, 40 Vorlieben, 60 Einträge
  Wissen, 200 Protokolleinträge. An Claude gehen höchstens 20
  Tricknamen, 10 Orte, 15 Vorlieben und die letzten 4 Pannen.
- Claude ist angewiesen, nur auf Wunsch oder bei klaren Vorlieben etwas zu speichern, und nichts
  Persönliches über andere Menschen.

## Claude

- Standardmodell Sonnet 5.5. Schneller und günstiger ist Haiku 5.5, gründlicher Opus 5.5. Umstellen
  unter System → Einstellungen → Claude.
- **Tokens sparen:** Werkzeuge und System-Prompt liegen eine Stunde im Prompt-Cache (Gespräche mit der Ente
  haben Pausen), der Verlauf mit rollender Cache-Marke – Werkzeugrunden lesen ihn für einen Bruchteil.
  Der Verlauf wird auf die letzten zwölf Runden gekürzt, lange Werkzeug-Ergebnisse auf 2 500 Zeichen.
- **Kurze Befehle ohne Claude** (an, abschaltbar): „setz dich“, „tanz“, „dreh dich“, „folge dem Laser“ erledigt
  duckpilot selbst – schneller und ohne Tokens. Fragen, Verneinungen, Bedingungen und alles Längere gehen an Claude.
- **Verbrauch** unter System → Einstellungen: Anfragen der letzten 7 Tage, Tokens je Anfrage, Anteil aus dem Cache
  und wie viele Befehle ohne Claude liefen (nur Zahlen, in `verbrauch.json` im lokalen Datenordner).
- Bricht Claudes Antwort mitten in einem langen Werkzeugaufruf ab (z. B. große Choreografie), wird nichts ausgeführt
  und Claude bekommt die Bitte, es kürzer zu machen – der Verlauf bleibt heil.
- Fällt die Verbindung aus, übernimmt die einfache Befehlserkennung, damit die Ente bedienbar bleibt.
- Der Schlüssel liegt in der Windows-Anmeldeinformationsverwaltung (macOS: Schlüsselbund). Er wird nie
  an die Oberfläche geschickt, dort steht nur `sk-ant-…` mit den letzten vier Zeichen. Ein Schlüssel
  aus der Umgebungsvariable `ANTHROPIC_API_KEY` oder einer `.env`-Datei funktioniert weiterhin. Der
  aus den Einstellungen hat Vorrang.

## Andere KI-Modelle statt Claude

Seit 0.35 kann ein anderes Modell denken: **Einstellungen → KI-Modell → „Anderes Modell“** (nur am PC; bis 0.37 unter Charakter → Gespräch).

- Anbieter: **OpenAI**, **Google Gemini**, **Mistral**, **OpenRouter** (viele Modelle über einen Schlüssel), **LM Studio**
  auf diesem PC oder eine **eigene Adresse** mit OpenAI-kompatibler Schnittstelle. Ollama bleibt „Lokales Modell“.
- Schlüssel des Anbieters eintragen (liegt nur im Tresor, je Anbieter ein Eintrag), **Modelle laden**, Modell wählen.
  **LM Studio:** dort ein Modell mit Werkzeug-Unterstützung laden (Hammer-Symbol), unter „Developer“ den lokalen
  Server starten (Port 1234); in Knowlin ist `http://127.0.0.1:1234/v1` vorbelegt, kein Schlüssel nötig.
  Eigene Adressen: https überall, http nur auf diesem PC oder im Heimnetz – der Schlüssel geht nie unverschlüsselt ins
  Internet.
- Gleiche Persönlichkeit, gleiches Gedächtnis, **dieselben Werkzeuge und Sicherheitsregeln** – die stecken in duckpilot,
  nicht im Modell. „Stopp“ und die Kurzbefehle laufen ohne Modell. Fällt der Anbieter aus, übernehmen die einfachen
  Befehle.
- Bilder („Was siehst du?“) kann vorerst nur Claude ansehen. Wie gut ein Modell Bewegungen plant, hängt am Modell;
  Claude ist dafür gemacht und bleibt Standard.

## Andere Programme steuern die Ente (MCP)

duckpilot ist auch ein **MCP-Server** (Model Context Protocol): Claude Desktop, Claude Code oder eigene Agenten können
die Ente über duckpilot bewegen – mit denselben Sicherheitsregeln wie überall (Not-Aus gewinnt, 2 Minuten Sperre,
Aufstehen nach einem Sturz erst nach dem Stopp-Fenster, hochgehoben nie).

- **Einschalten:** System → Einstellungen → Claude → „Andere Programme dürfen steuern (MCP)“, dann „Neuen Schlüssel
  erzeugen“. Der Schlüssel liegt im Tresor des Betriebssystems und steht nur direkt nach dem Erzeugen einmal im
  Befehl zum Kopieren.
- **Claude Code:** den angezeigten Befehl `claude mcp add --transport http duckpilot http://127.0.0.1:8765/mcp
  --header "Authorization: Bearer …"` ausführen.
- **Claude Desktop:** den angezeigten Block in `claude_desktop_config.json` übernehmen. Er startet die Brücke
  `python -m duckpilot.mcp_bridge`, die den Schlüssel selbst aus dem Tresor holt – in der Datei steht keiner.
- **Was geht:** 23 Werkzeuge zum Bewegen, Ausdrücken, für Tricks und den Zustand (gehen, drehen, hingehen, annähern,
  Kopf, Gefühle, Tanzen, Erkunden, Laser folgen, Choreografien, gespeicherte Tricks und Orte, Stopp …).
  **Was nicht geht:** Personen, Kamerabilder, Gedächtnis schreiben, Training, Alltag und Einstellungen.
- **Nur auf diesem PC:** nie vom Handy, nie über Tailscale oder einen Weiterleiter; fremde Webseiten werden
  abgewiesen. Jeder Aufruf erscheint in der Oberfläche als „Von außen (MCP): …“.

## Spracherkennung und Datenschutz

| System → Einstellungen → Spracherkennung | Was passiert mit dem Audio |
|---|---|
| **Online** (Standard) | Edge schickt die Aufnahme zur Erkennung an Microsoft, Chrome an Google. Bequem, aber das Audio verlässt den PC. |
| **Lokal** | Erkennung auf dem PC mit faster-whisper. Einmalig in der Eingabeaufforderung installieren: `"%LOCALAPPDATA%\duckpilot\venv\Scripts\python" -m pip install faster-whisper` (macOS/Linux im Knowlin-Ordner: `.venv/bin/pip install faster-whisper`). Das Modell („small“, ca. 460 MB) wird beim ersten Mal geladen, danach bleibt das Audio auf dem PC. |
| **Aus** | Nur Tippen und Knöpfe. |

An Claude geht in jedem Fall nur der erkannte Text plus der Lagebericht der Ente. Vorgelesen wird
lokal (Piper, Qwen3-TTS) oder mit den Stimmen des Betriebssystems – siehe *Stimme und Gespräch*. Mit
dem eigenen Sprachmodell bleibt auch der Text auf dem PC. Die Oberfläche
lauscht nur auf 127.0.0.1 und ist im Netzwerk nicht erreichbar – außer du schaltest die
Handy-Fernbedienung ein (siehe unten).

**Schutz vor fremden Webseiten:** Der duckpilot-Server nimmt Befehle nur aus seiner eigenen Oberfläche
an. Eine andere Webseite, die zufällig im Browser offen ist, kann die Ente nicht steuern und weder
Gedächtnis noch Einstellungen lesen oder ändern. Auch Umleitungen über fremde Domainnamen
(„DNS-Rebinding“) werden abgewiesen.

## Handy-Fernbedienung

duckpilot läuft auf dem PC – das Handy ist die Fernbedienung dafür.

**Am schnellsten (seit 0.38.28):** Auf der Startseite unter **Auf Handy oder Tablet** auf „Einschalten und Code
anzeigen“ klicken. Knowlin schaltet die Fernbedienung ein und zeigt einen QR-Code und einen kurzen Code (z. B.
`K7P-2QM`). Mit der Kamera scannen – oder ohne Kamera im Browser `knowlin.local:8766` öffnen und den kurzen Code
eintippen. Den Namen `knowlin.local` sagt Knowlin im Heimnetz an, solange die Fernbedienung an ist (mDNS/Bonjour);
iPhone, iPad, Mac und Windows finden ihn, manche Android-Geräte nicht – dort die angezeigte Zahlenadresse nehmen. Der
kurze Code gilt wie der QR-Code 5 Minuten, für ein Gerät, nach 5 Fehlversuchen ist er verbraucht.

Ausführlich unter **System → Einstellungen → Handy-Fernbedienung**:

1. **„Vom Handy aus bedienen“** einschalten. duckpilot öffnet dafür einen zweiten Zugang im Heimnetz
   (Standard-Port 8766). Windows fragt beim ersten Mal nach der Firewall: **„Private Netzwerke“ erlauben**,
   „Öffentliche“ nicht.
2. **„Handy koppeln“** zeigt einen QR-Code. Mit der Handykamera scannen, auf dem Handy „Koppeln“ tippen –
   fertig. Ohne Kamera geht auch die angezeigte Adresse im Handy-Browser.
3. Auf dem Handy erscheint dieselbe Oberfläche, angepasst an den kleinen Bildschirm, mit
   „verbunden · Handy“ oben. Tipp: im Browsermenü „Zum Startbildschirm hinzufügen“ – die App heißt dann „Knowlin“.

**Tablet (seit 0.38.27):** Genauso koppeln. Hochkant (z. B. 820 px breit) gibt es die Leiste unten wie am Handy, quer
(z. B. 1180 px) die Leiste links wie am PC. Mit dem Finger sind Knöpfe, Reiter, Auswahlfelder und Häkchen mindestens
44 px hoch; Tastatur-Hinweise („Leertaste halten“) fallen weg. Die Abnahme prüft beide Lagen.

Am Handy gibt es im Cockpit einen **Fahr-Joystick** (Daumen ziehen: vor, zurück, drehen) und unten eine
feste Eingabezeile.

**Controller** (Knopf „Controller“ oben in der 3D-Ansicht): Vollbild im Querformat, als Hintergrund das **Live-Bild der
Kopfkamera** (Simulator: Entenblick, Roboter: Kamerabild).

- **Links:** Fahr-Stick und „Sprechen“ (halten). **Rechts:** vier Tasten, im Menü frei belegbar (Quaken, Sitzen ↔
  Stehen, Kicken, Aufheben, Purzelbaum, Freuen, Nicken, Kopf schütteln, Tanzen, Umschauen). **Oben:** Not-Aus,
  Ton an diesem Gerät, Menü.
- **Umschauen wie in Street View:** das Bild ziehen dreht den Kopf; am Anschlag dreht sich der Körper mit.
- **Bewegungssensor** (Menü, braucht https, also Tailscale): „Handy = Kopf“ – wohin das Handy zeigt, schaut sie;
  „Kippen = laufen“ (sie läuft, lenkt und dreht sich; „fahren“ auf Rollen kommt mit dem Zubehör) – Daumen auf den Stick (Totmann), dann Oberkante weg = vor, wie ein Lenkrad drehen = lenken.
  Loslassen hält sie an. „Geradeaus neu ausrichten“ setzt den Nullpunkt.
- **Vibrieren** bei Stößen, Treffern, Anstoßen und Stürzen, stärker je fester (Android; am iPhone blitzt der Rand).
  Ein Gamepad am PC rüttelt dabei mit. Abschaltbar im Menü.
- Bricht die Verbindung ab oder wird der Bildschirm gesperrt, bleibt sie stehen (Fahrbefehle verfallen nach 0,35 s). **Sprechen** braucht im Handy-Browser https: im WLAN (http) tippst du oder nutzt das
Diktiermikrofon der Handy-Tastatur – mit **Tailscale** (unten) geht der Sprechknopf auch am Handy. Vorlesen ist am Handy zunächst aus, damit nicht PC und Handy
gleichzeitig sprechen; es lässt sich unter „Antworten vorlesen“ einschalten. **Nur am PC** bleiben:
API-Schlüssel und Hugging-Face-Zugang, bezahltes Training starten, Modelle exportieren, Installationen,
Modell-Downloads, Ordner öffnen, Roboter-Updates einspielen, die Fernbedienung selbst verwalten – und
Einstellungen, die bestimmen, wohin duckpilot sich verbindet oder was es kostet (Körper und
Roboter-Adressen, Claude-Modell, Gehirn und lokales Modell, Spracherkennung, Gedächtnis an/aus).
Stopp und Not-Aus funktionieren vom Handy genauso wie am PC.

**Schutz:**

- Standardmäßig **aus**. Ohne Einschalten ist duckpilot im Netz nicht erreichbar.
- Herein kommen nur **gekoppelte Geräte** aus dem **Heimnetz** (192.168.x.x, 10.x.x.x, 172.16–31.x.x,
  fe80::/fd00::). Alles andere wird abgewiesen – auch mit gültigem Gerät.
- Der QR-Code enthält einen **Einmal-Code**: 5 Minuten gültig, für genau ein Gerät, nach 5 Fehlversuchen
  verbraucht.
- Das Gerät bekommt ein zufälliges Gerätezeichen (Cookie, für Skripte unlesbar). duckpilot speichert
  davon nur eine Prüfsumme in `%LOCALAPPDATA%\duckpilot\fernzugang.json` – mit der Datei allein kann
  sich niemand anmelden. Höchstens 8 Geräte.
- **Abmelden** einzeln oder alle auf einmal (verlorenes Handy); die Verbindung wird sofort getrennt.
- Fremde Webseiten können weder koppeln noch steuern (gleiche Prüfung der Herkunft wie am PC); vom Handy
  zählen nur Anfragen aus der duckpilot-Seite selbst – nicht von anderen Diensten auf derselben PC-Adresse.
- Wer im WLAN fünfmal einen falschen Code schickt, macht den aktuellen QR-Code ungültig – dann einfach
  einen neuen anzeigen.
- **Nur am PC** sind außerdem: Sehen und Personen erkennen ein-/ausschalten, Personen anlernen und
  löschen, Kamerabilder an duckpilot schicken, der Kaggle-Zugang. Kostenloses Lernen (PC, Kaggle) darfst
  du vom Handy starten – es kostet nichts außer Strom bzw. Kaggle-Stunden.
- **Ehrlich:** Im WLAN läuft die Verbindung über **http, also unverschlüsselt** (über Tailscale verschlüsselt). Im eigenen, mit Passwort
  geschützten WLAN ist das üblich (wie bei vielen Heimgeräten), im Café-, Hotel- oder Firmen-WLAN
  solltest du die Fernbedienung nicht einschalten.

**Unterwegs und mit Sprache: Tailscale.** Tailscale ist ein kostenloses privates Netz für die eigenen
Geräte. Ist es auf PC und Handy installiert und mit demselben Konto angemeldet, schaltet „Auch unterwegs
und mit Sprache (Tailscale)“ eine **https-Adresse** `https://<pc-name>.<tailnet>.ts.net` ein
(`tailscale serve`, nur im eigenen Tailnet, nicht im offenen Internet). Damit geht das Mikrofon am Handy,
und die Ente ist auch außerhalb des WLANs erreichbar. Fragt Tailscale beim ersten Mal, ob HTTPS-Zertifikate
erlaubt werden, zeigt duckpilot den Link dafür. **Koppeln** musst du trotzdem: Anfragen über Tailscale
gelten nie als „der PC selbst“, auch wenn sie technisch von dort kommen; das Gerätezeichen ist dann nur
über https gültig. Dasselbe gilt für jeden anderen Weiterleiter auf dem PC (erkennbar an Kopfzeilen wie
`X-Forwarded-For`): solche Anfragen werden abgewiesen. Ausschalten beendet die Freigabe.

**Beenden:** Oben rechts **„Beenden“** öffnet wie bei Windows-Programmen die Wahl: **Im Hintergrund
weiterlaufen** (Fenster zu, die Ente ruht, Erinnerungen, Handy und Lernen über Nacht laufen weiter – wieder
öffnen mit der Desktop-Verknüpfung), **Beenden** (ganz schließen) und, wenn eine neue Version im Ordner liegt,
**Neu starten**. duckpilot merkt neue Dateien nach einem Update selbst und zeigt oben „liegt bereit – Jetzt neu
starten“. Der Knopf erscheint nur im Programmfenster am PC.

**Immer erreichbar:** Solange die Fernbedienung an ist, läuft duckpilot nach dem Schließen des Fensters im
Hintergrund weiter (Doppelklick auf die Verknüpfung öffnet es wieder; ganz beenden mit „duckpilot ganz
beenden“ auf derselben Karte). Mit **„Mit Windows starten“** legt duckpilot eine Verknüpfung in den
Autostart-Ordner: Nach dem Anmelden startet es ohne Fenster und schickt die Ente in den Ruhemodus – vom
Handy aus weckst du sie. Ausschalten (oder die Fernbedienung ausschalten) entfernt die Verknüpfung wieder (sie startet `pythonw -m duckpilot --app --hintergrund`).

## Installieren und Updates (seit 0.38.31)

- **Windows:** `Knowlin-Setup-….exe` aus dem neuesten Release (oder „Download“ auf knowlin.de). Installiert für den
  angemeldeten Benutzer unter `%LOCALAPPDATA%\Programs\Knowlin`, mit eigenem Python, ohne Administratorrechte.
  Gedächtnis, Einstellungen und Schlüssel liegen davon getrennt (`%LOCALAPPDATA%\duckpilot`, Tresor) und bleiben bei
  Updates und beim Deinstallieren erhalten.
- **pipx:** `pipx install knowlin`, dann `knowlin --app`; unter Windows legt `knowlin --verknuepfung` die Einträge im
  Startmenü und auf dem Desktop an.
- **Updates (seit 0.38.32):** Knowlin sieht höchstens einmal am Tag bei GitHub nach einer neuen Version. Gibt es eine,
  steht oben „Knowlin 0.38.xx ist da“ mit „Was ist neu“. **Jetzt aktualisieren** lädt beim Installer den neuen
  Installer aus dem Release, prüft die SHA-256-Prüfsumme gegen GitHub, beendet Knowlin, installiert still und startet
  neu; mit pipx aktualisiert es das Paket. Nie, während der echte Roboter verbunden ist, und nur am PC. Abschalten und
  von Hand suchen: Einstellungen → Über.
- **Was gerade passiert (seit 0.38.38):** Beim Herunterladen zeigt die Leiste oben einen Balken mit „… MB von … MB“.
  Danach führt eine Schrittliste durch das Update – Herunterladen, Prüfsumme prüfen, Installieren, Knowlin startet,
  Fertig – mit mitlaufender Zeit. Der neu startende Knowlin meldet sich sofort und sagt, wobei er ist („Körper, Stimme
  und Gedächtnis werden aufgebaut“); das Fenster lädt sich selbst neu, sobald alles bereit ist. Auch ein normaler Start
  öffnet das Fenster gleich mit „Knowlin startet …“. Der erste Start nach einem Update kann unter Windows ein, zwei
  Minuten dauern, weil Windows die neuen Dateien prüft. Wie lange jeder Schritt gedauert hat, steht im Protokoll
  `duckpilot.log` („Start nach … s“).
- **Nachinstallieren mit Fortschritt (seit 0.38.38):** Physik, Stimmen, Gesichter und PyTorch zeigen beim Herunterladen
  Datei, „… MB von … MB“ und einen Balken; danach „richtet die geladenen Pakete ein …“.

## Wenn der Roboter kommt

Pollen plant die ersten Auslieferungen vor Weihnachten 2026. Dann:

1. **Ente einrichten** wie in Pollens Anleitung (WLAN, Updates). Auf dem Roboter prüfen:
   `robotctl health`.
2. **Tunnel öffnen** (Windows-Terminal oder PowerShell; OpenSSH ist in Windows enthalten):
   ```
   ssh -N -L 7900:/run/robotd.sock -L 7901:/run/tofd/tof.sock -L 7902:/run/updaterd.sock microduck@<IP-der-Ente>
   ```
   Das leitet drei lokale Ports auf die Unix-Sockets des Roboters um – derselbe Weg, den Pollen für
   den Gamepad-Daemon vom Laptop aus beschreibt. 7902 (`updaterd`) braucht es nur für Tricks vom Hub.
3. **Umschalten:** System → Einstellungen → Körper → „Echter Roboter“. Die Adressen sind schon passend
   vorbelegt (`tcp:127.0.0.1:7900`, Tiefensensor `tcp:127.0.0.1:7901`, Updater `tcp:127.0.0.1:7902`). Oben steht dann
   „Echter Roboter“, und das Abzeichen zeigt, ob er erreichbar ist. Claude bekommt automatisch
   vorsichtigere Regeln.
4. **Erst auf dem Ständer testen.** „Aufstehen“ (`robot.init`) bewegt alle Gelenke. Dann
   „schau nach links“ sagen. Dreht der Kopf falsch herum, unter System → Einstellungen → Körper →
   Kopf-Kalibrierung „Drehen umkehren“ anhaken. Ebenso für Nicken.
5. **Gamepad nicht gleichzeitig benutzen** – Pad und duckpilot senden beide Fahrbefehle.
6. **Laute** kommen dann aus der Ente selbst (ihre eigene Stimmbank), nicht mehr aus dem PC.

Was sich gegenüber dem Simulator ändert: Objekte („Ball“, „Socke“) kennt duckpilot auf dem echten
Roboter noch nicht – die Kamera (`mediad`) ist nicht angebunden, also funktionieren `approach` und
„schieß den Ball“ erst mit Objekterkennung. Alles andere – Laufen, Drehen, Skills, Gefühle,
Choreografien, Erkunden mit dem Tiefensensor, Sturzreflex – läuft unverändert.

### Vorher schon gegen den Roboter-Pfad testen

```
python -m duckpilot --fake-robotd tcp:127.0.0.1:7900
python -m duckpilot --backend robotd --robot tcp:127.0.0.1:7900 --tof tcp:127.0.0.1:7900 --port 8766
```

Der erste Befehl bietet den Simulator als robotd-kompatiblen Server an; der zweite steuert ihn über
genau den Code, der später mit dem Roboter spricht.

Wer einen Linux-Rechner (oder WSL) hat, kann außerdem Pollens eigenen Simulator nehmen: echtes
`robotd` mit den echten Policies gegen einen MuJoCo-Körper (`scripts/duck-sim` im Repository
`pollen-robotics/microduck`, braucht zusätzlich `microduck_rl`). Dann:
`--backend robotd --robot unix:~/.cache/duck-sim/duck.sock`.

## 3D-Darstellung

Die 3D-Ansicht zeigt Pollens CAD-Modell so detailliert wie MuJoCo. Gerendert wird mit Umgebungslicht aus
einem Studio-Raum (Spiegelungen auf Lack, Metall und Glas), physikalischen Materialien je Teil (lackierte
Schalen, Servos, Gummisohlen, Kugellager, Kameralinse), Khronos-Neutral-Tonwerten (Pollens Farben bleiben
farbtreu), einem scharfen Schatten, dessen Ausschnitt mit der Ente wandert, und Umgebungsverdeckung (GTAO)
in Fugen und unter der Ente. System → Einstellungen → 3D-Darstellung: **Automatisch** (schaltet bei ruckelnder
Ansicht auf Schnell), **Hoch** oder **Schnell** (ohne Verdeckung, einfache Schatten, einfache Pixeldichte).

**Farbe der Microduck** (seit 0.38.19): Cream, Graphite, Lavender oder Sky wie bei Pollen – unter System →
Einstellungen → 3D-Darstellung und unter Charakter → Persönlichkeit → Aussehen. Gilt für das Original und die einfache
Gestalt, im Cockpit und im Trainingsfeld. **Startansicht** (seit 0.38.23): Die Kamera fliegt beim Aufwachen flach und
nah an die Figur heran, etwa in Augenhöhe am Boden.

## Skill-Pakete

Erweiterungen von Pollen und aus der Community, einzeln an- und abschaltbar unter **System → Erweiterungen**.
Ein aktives Paket bekommt auf der Tricks-Seite einen eigenen Abschnitt und – wenn es eins mitbringt – ein
Werkzeug für Claude. Die Wahl wird gespeichert (`pakete` in den Einstellungen). Kataloge kommen vom Hugging
Face Hub, werden sechs Stunden zwischengespeichert und bleiben ohne Internet mit dem letzten Stand nutzbar.

| Paket | Was | Simulator | Claude |
| --- | --- | --- | --- |
| **Bewegungen aus der MicroDuck-App** | rund 80 Ganzkörper-Moves vom Hub-Konto `microduckapp` (Tanz, Gehen, Albern, Missgeschicke, Alltag), mit Vorschauvideo. Laut Manifest Befehlsfolgen auf Pollens offiziellem Laufmodell. Wer hinter dem Konto steht, steht nicht dabei – daher „Community“. | Vorschauvideo, Vormerken | `app_bewegung` (nur Roboter, lädt beim ersten Mal) |
| **Got a Talent (Microduck Arena)** | 20-Sekunden-Vorführungen aus Pollens Arena: Zeitleiste aus Kopfbewegungen und Hinsetzen/Aufstehen (`timeline.json`, Regeln aus `microduck-challenges`). Mit Zeitleisten-Grafik. | spielt genauso wie am Roboter | `vorfuehrung` |
| **Community-Tricks (in der Physik geprüft)** | Salto, Flamingo, Moonwalk, Verbeugung … – einzelne Trick-Policies anderer Besitzer vom Hub (ohne Pollen- und App-Konto, ohne Gangarten). „Prüfen“ spielt einen Trick unsichtbar in Pollens MuJoCo-Modell durch: *sicher*, *akrobatisch* oder *bleibt liegen*. Am Roboter läuft nur Geprüftes, „bleibt liegen“ nur mit „Trotzdem zeigen“. | Prüfen und Ausprobieren mit echter Physik | `community_trick` |
| **Gangarten (Arena & Community)** | Laufmodelle mit Tag `microduck-slot:walk` – Pollens Arena-Referenzen und Community. Ersetzt das normale Gehen (`robot.loadPolicy` auf den Platz `walk`), „Standard wiederherstellen“ setzt zurück. Am Roboter erst nach zweitem Tippen („Wirklich laden?“, am besten auf dem Ständer); in der Physik ohne Rückfrage. | nur Stöbern | bewusst nicht |
| **Alltagsbuddy** (in duckpilot eingebaut, Standard an) | Uhrzeit, Timer, Erinnerungen, Termine (auch .ics-Import), To-dos, Ruhe/Aktiv – siehe „Alltagsbuddy“ | vollständig | `alltag` |
| Karte & Navigation (quack-nav) | Community-Projekt für Karte, Ortung, Wege und Treppenschutz auf der Ente | geplant, mit dem Roboter | – |
| Enten-Erkenner | Pollens YOLO-Modell findet andere Microducks im Kamerabild | geplant, mit der Kamera | – |

Darunter zeigen Kacheln unter **Geplant**, was als Nächstes kommt – mit der geplanten Version, nicht einschaltbar
(Liste in `duckpilot/geplant.py`).

Neue Pakete: Unterklasse von `Pack` in `duckpilot/skills/`, Eintrag in `PACKS`. Alles, was vom Hub kommt,
ist Fremdtext – es wird angezeigt, aber nie als Anweisung behandelt; Claude sieht nur bereinigte Kurznamen.

## Alltagsbuddy

Ein kleiner Assistent wie Jarvis, nur mit Federn – Bereich **Alltag**, per Sprache oder über Claude
(Werkzeug `alltag`). Die einfachen Sätze gehen auch ohne Claude.

- **Uhrzeit und Datum**, **Tagesüberblick** („Was steht heute an?“): Termine, Erinnerungen, offene
  To-dos, laufende Timer. Claude bekommt die Ortszeit bei jeder Nachricht mit.
- **Timer** mit Namen und Countdown, **Erinnerungen** (einmal, täglich, werktags, wöchentlich),
  **Termine** mit Ort und Vorwarnzeit, **To-dos** zum Abhaken.
- Zeiten auf Deutsch: „in 20 Minuten“, „um halb 9“, „morgen früh“, „Freitag um 14:30“, „am 3.11.
  um 9“, „heute Abend um 8“, „eine Viertelstunde“, „zweieinhalb Stunden“.
- **Kalender:** eine `.ics`-Datei (Export aus Outlook, Google oder Apple Kalender) übernehmen;
  erneuter Import aktualisiert statt zu verdoppeln. Serien (täglich, wöchentlich mit Wochentagen,
  monatlich, jährlich, mit Ende oder Anzahl) werden für die nächsten 120 Tage aufgelöst; nur sehr
  verschachtelte Regeln kommen mit dem ersten Termin. Zeitzonen und Sommer-/Winterzeit werden
  berücksichtigt. Eine Anmeldung
  bei einem Kalenderdienst gibt es bewusst nicht.
- **Wenn etwas fällig ist:** Band oben mit „Erledigt“ und „5 Minuten später“, die Ente quakt und
  macht eine Geste, auf Wunsch wird es vorgelesen. Unbestätigt meldet sie sich bis zu dreimal im
  Minutenabstand. Termine, die vorbei sind, während der PC aus war, wecken nicht nachträglich.
- **Ruhe und Aktiv:** In Ruhe sitzt sie mit abgeschalteten Motoren (`robot.rest`, spart am Roboter
  Akku) und bewegt sich nicht. Sie wacht auf, wenn du sie ansprichst oder steuerst, oder wenn etwas
  fällig ist – dann steht sie auf, meldet sich und schläft nach dem Bestätigen wieder ein. Wahlweise
  bleibt sie dabei sitzen („nur Ton und Durchsage“). „Von selbst ausruhen“ nach 10 min bis 2 h ohne
  Beschäftigung.
- **Sicherheit:** Nach einem Not-Aus (Knopf, Esc, „Stopp“ oder Claudes Stopp) bewegt sie sich zwei
  Minuten lang nicht von selbst – kein Aufstehen bei Alarmen, kein automatisches Hinsetzen. Ansprechen
  weckt sie dann nur auf, aufstehen tut sie erst auf „Steh auf“. Weckt sie ein Befehl wie „Schieß den Ball“, steht sie erst auf und führt ihn
  dann aus; kommt sie nicht am Ball an, lässt sie den Tritt aus. Im Simulator lädt der Akku in Ruhe nach. Hochgehoben steht sie
  nicht auf; nach einem Sturz erst nach dem Stopp-Fenster. Läuft gerade eine Bewegung, meldet sie sich ohne Geste, damit nichts abbricht.
- Alles liegt in `alltag.json` im Datenordner, nichts geht in die Cloud.

### Was der Buddy darf: sehen und Personen erkennen

Unten auf der Alltag-Seite, alles standardmäßig **aus**:

- **Sehen: vorlesen und beschreiben** – „Was siehst du?“, „Lies mir den Zettel vor“, „Ist das Fenster
  offen?“. Die Ente schaut hin (Werkzeug `alltag` → `ansehen`), **ein** Bild geht an Claude, Claude
  antwortet. Das Bild wird nicht gespeichert, nicht protokolliert und schon in der nächsten Runde nicht
  mehr mitgeschickt. Braucht den Claude-Schlüssel (das lokale Sprachmodell kann keine Bilder).
- **Augen im Simulator:** wahlweise die **Simulator-Ansicht** (ihre Kopfkamera in der 3D-Welt) oder die
  **PC-Webcam** – dann sieht sie dich und dein Zimmer. Die Webcam läuft nur, solange Sehen oder Personen
  an ist; oben steht dann „● Webcam“. Am echten Roboter sieht sie durch ihre Kopfkamera.
- **Personen erkennen und begrüßen** – nur Menschen, die du am PC **mit ihrem Einverständnis** anlernst
  (Name, Häkchen, 5 Webcam-Bilder mit leicht gedrehtem Kopf). Gespeichert werden nur Zahlenmerkmale
  (Gesichts-Embeddings von YuNet/SFace aus dem OpenCV Zoo, lokal mit onnxruntime), **nie Bilder**;
  Fremde bleiben „unbekannt“ und werden nie gespeichert. Erkennt sie jemanden, sagt sie „Hallo …“ und
  winkt – höchstens alle 30 Minuten je Person, nicht in Ruhe und nicht in den zwei Minuten nach einem
  Not-Aus. „Wer ist da?“ fragt sie auch direkt. Einzeln oder alle **löschen** jederzeit. Einrichtung:
  zwei kleine Pakete (≈ 60 MB) und einmal die zwei Modelle (≈ 39 MB).
- **Nur am PC:** Sehen, Personen und Begrüßen ein- oder ausschalten, die Augen wählen, Personen anlernen
  und löschen. Begrüßungen mit Namen erscheinen nur in den Fenstern am PC, und „Wer ist da?“ beantwortet
  die Ente einem Handy nicht – auch nicht über Tailscale. „Was siehst du?“ geht vom Handy, wenn Sehen am
  PC eingeschaltet ist.

## Punktwolke des Tiefensensors

Die Microduck hat keinen Lidar, sondern einen 8 × 8-Tiefensensor (ToF) im Kopf: 64 Entfernungen auf
einmal, etwa 45° Öffnungswinkel, bis etwa 2 m. duckpilot rechnet jedes Bild mit Position, Blickrichtung,
Kopfneigung und Sensorhöhe in Punkte im Raum um (`tof_points()` in `api.py`, für Simulator und Roboter)
und sammelt sie eine Minute lang, höchstens vier Bilder pro Sekunde. Steht die Ente still, kommt nichts
doppelt dazu. Alte Punkte verblassen.

- **System → Zustand → Tiefensensor → Punktwolke:** mit der Maus drehen und zoomen, die Kamera folgt der Ente.
  Farbe = Höhe (grau = Boden, dann Blau bis 50 cm), orange die Ente mit ihrem Sichtfächer. Im Simulator
  sind die Möbel als feine Umrisse eingezeichnet. „Leeren“ beginnt von vorn.
- **Steuern → Haken „Punktwolke“:** dieselben Punkte in der großen 3D-Ansicht.
- Am echten Roboter fallen ungültige Zonen (tofd-Status ≠ 5/9) weg. Die Punkte stehen im
  Odometrie-Rahmen und verschieben sich mit der Zeit etwas, wie die Orte.

## Gestaltung

Die Oberfläche folgt dem **IBM Carbon Design System** im dunklen Theme **Gray 90**: sehr dunkles Grau
statt Schwarz, Ebenen #262626 → #393939 → #525252, Schrift **IBM Plex**, Abstände, Bewegungskurven und
Größen der Bedienelemente wie in Carbon v11, weißer Tastaturfokus.

Darüber liegt eine dünne **duckpilot-Ebene**:

- **Schnabel-Orange** (#f0962c) ist der einzige Markenakzent: Hauptaktion, Auswahl, Sprechen.
- **Flach mit feiner Kontur:** volle Flächen, 1-px-Konturen, keine Verläufe und Schatten. Ebenen
  entstehen aus dem Grauwert. Befehle tragen Symbole, die Sprechtaste ist eine breite Taste mit
  Mikrofon und Pegelanzeige.
- **Not-Aus** unten in der Leiste, gestaltet wie an einer Maschine: roter Pilztaster auf gelbem Schild,
  immer gleich und immer bereit. Bewegt sich die Ente oder führt etwas aus, leuchtet der Ring um den
  Taster rot. Nach dem Drücken rastet der Pilz kurz sichtbar ein. Esc und die Gamepad-Taste B wirken
  genauso. Der Taster ist die einzige bewusst plastische Stelle der Oberfläche.
- **Radien nach Rang:** Bedienelemente 6 px, Kacheln 8 px, schwebende Flächen 10 px, und am weichsten
  (14 px), wo die Ente selbst agiert: Gesten-Kacheln, Gesprächsblasen, Sprechtaste, Persönlichkeitsfläche.
- Messwerte in Carbon-Blau (#4589ff), Sollwerte in Magenta (#ee5396), geprüft auf Farbsehschwächen.
- Statusfarben (gut, Warnung, ernst, kritisch) und Stopp (#da1e28) sind reserviert.
- **Ein Raster für alle Seiten** nach Carbons 2x Grid: 16 Spalten ab 1056 px Fensterbreite, 8 ab 672 px, darunter
  4, mit 16 px Abstand. Es wächst fließend bis 1584 px und steht darüber mittig. Kacheln belegen ganze Spalten
  (Hälften, Viertel, Haupt + Seite 10 + 6). Ihre Kanten liegen deshalb auf jeder Seite auf denselben Linien.
- **Carbon-Werte überall:** Abstände, Schriftgrade, Farben, Dauern und Kurven kommen nur aus `ds/tokens.css` – mit
  Carbons Namen (`--spacing-05`, `--duration-moderate-02` …). Ein Test schlägt an, wenn irgendwo ein freier Wert
  auftaucht. Bewusst anders als Carbon sind nur Orange als Akzent, die Radien und der Not-Aus.

Alle Farben, Schriftgrade, das Raster und die Bausteine mit ihren Zuständen zeigt die Übersicht unter
System → Einstellungen → Über → Designsystem.

## Barrierefreiheit

duckpilot wird gegen **WCAG 2.2 Stufe AA** geprüft. Das deckt BITV 2.0 und EN 301 549 (heute auf WCAG 2.1, ab der
Fassung V4.1.1 auf WCAG 2.2) mit ab. Rechtlich muss ein privates, freies Projekt das nicht erfüllen. Es soll aber
für alle bedienbar sein.

- **Tastatur:** Alles geht ohne Maus. Ein Sprunglink führt zum Inhalt, und der Fokus ist immer sichtbar (weißer
  Rahmen, in Feldern blau). Wo die 3D-Ansicht Ziehen verlangt, gibt es Regler oder Tasten daneben, z. B. bei der
  Gliederpuppe, im Kollisionsmodus und bei der Auswahl im Erfahrungsnetz.
- **Sehen:** Text hat mindestens 4,5 : 1 Kontrast, Bedienelemente und Felder mindestens 3 : 1. Farbe trägt nie
  allein eine Bedeutung. Die kleinste Schrift ist 12 px. Bei 320 px Breite scrollt keine Seite waagrecht. Im
  Kontrastmodus von Windows bekommen Kacheln und Knöpfe echte Ränder.
- **Screenreader:** Jede Seite hat einen eigenen Fenstertitel und lückenlose Überschriften. Landmarken sind
  benannt, Zeichenflächen (3D, Karten, Kurven) beschriftet. Meldungen kommen über Live-Regionen.
- **Zeit und Bewegung:** Animationen folgen „Bewegung reduzieren“ des Systems. Das Stopp-Fenster nach einem
  Sturz ist einstellbar (2 bis 10 s).
- **Sprache:** Was per Sprache geht, geht auch per Text, und was die Ente sagt, steht auch im Gespräch.

Geprüft wird mit axe-core über alle Seiten bei 1440 und 320 px. Dazu kommen Tastatur-Durchläufe, Reflow und
Textabstände. Stand und bekannte Lücken stehen in [`docs/barrierefreiheit.md`](../docs/barrierefreiheit.md).

## Projektstruktur

Lageplan, Regeln und „wo kommt was hin“ für Entwickler: [ARCHITECTURE.md](../ARCHITECTURE.md). Leitplanken prüft
`tests/test_codebase.py` (ruff sauber, Module überschaubar, Server aus Routen-Modulen).

```
duckpilot/
  api.py                 gemeinsames Interface, Grenzen, Zustand
  aio.py                 spawn(): Hintergrund-Aufgaben mit Referenz und Fehlerprotokoll
  laser.py               Laserpunkt im Kamerabild finden, auf den Boden umrechnen (echter Roboter)
  mcp_server.py          MCP-Server: Werkzeug-Auswahl, Schlüssel im Tresor, JSON-RPC (Route server/routes/mcp.py)
  mcp_bridge.py          stdio-Brücke für Claude Desktop (holt den Schlüssel aus dem Tresor)
  backends/sim.py        Lite-Simulator (Kinematik, Skills, Stürze, ToF)
  backends/world.py      Wohnzimmer, Raycasting, Ball-Physik
  backends/robotd.py     JSON-RPC-Client für den echten Roboter
  backends/fake_robotd.py  Simulator als robotd-Server (zum Testen)
  backends/physics.py    Simulator mit echter Physik (erbt Wohnung, Sensor, Ereignisse vom Lite-Simulator)
  physics/core.py        MuJoCo + ONNX-Policy-Schleife nach Pollens infer_policy.py (BAM optional)
  physics/policies.py    Pollens Policy-Satz und einzelne Policies vom Hub (Rollen aus dem Manifest)
  physics/practice.py    Üben: Choreografie unsichtbar in der Physik durchspielen und bewerten (auch: sieht man sie?)
  physics/twist.py       Totzone von Pollens Geh-Policy: gleich für sichtbare Physik und Üben
  physics/course.py      Parcours: Elemente → MuJoCo-Geometrie, Wegfolger, Versuche, Aufzeichnung
  physics/lernen.py      Lernen am PC: PPO, Physik in Rechenprozessen, Netz mit PyTorch (ROCm/CUDA/CPU), ONNX ↔ PyTorch
  lernschleife.py        Lernschleife: Runde lernen → auf dem Parcours prüfen → vom besten Stand weiter
  kaggle_training.py     kostenloses Training auf Kaggle (privates Notebook, Lernkurve, Ergebnis holen)
  mission.py             Auftrag: Ziel → Parcours → Basis-Test → Vorschlag → Training → Bewertung
  physics/microduck.xml  nur private Fassung: fertiges Physik-Modell (tools/bake_physics.py, CC BY-NC-SA 4.0)
  modell/                Pollens Robotermodell von GitHub laden (quellen.json: fester Stand, Prüfsummen) und auf dem PC bauen:
                         ansicht.py (3D, DPM2), physik.py (MuJoCo), service.py (Fortschritt); `python -m duckpilot.modell`
  motion/engine.py       Schichten, Reflexe, Warteschlange, Leerlauf
  motion/behaviors.py    Verhalten, Gefühle, Goofy-Einlagen, Choreografie
  motion/mood.py         Stimmungsmodell: Freude, Frust, Schreck, Mitgefühl
  motion/character.py    Charakter im Leerlauf: Mimik und Gesten je Persönlichkeit
  motion/sounds.py       Gesten-Laute und Schnabel-Hüllkurven
  brain/agent.py         Claude-Tool-Use-Schleife, System-Prompt (Plaudern, Entenlaute)
  brain/local.py         eigenes Sprachmodell über Ollama (gleiche Persönlichkeit und Werkzeuge)
  brain/tools.py         die 26 Werkzeuge (18 Bewegung, 6 Gedächtnis, Goofy-Schalter, Hub-Tricks)
                         plus `bewegung_ueben`, `parcours_bauen` und `parcours_testen`, sobald die Physik bereitsteht
  brain/memory.py        Gedächtnis: Tricks mit Fassungen und Notizen, Orte, Vorlieben, Wissen, Protokoll
  brain/fallback.py      einfache Befehle ohne Claude, Kurzbefehle ohne Tokens
  brain/usage.py         Tokenzähler je Tag (Cache-Anteil, Befehle ohne Claude)
  hub.py                 Suche im Hugging Face Hub nach Microduck-Policies
  training.py            Training auf Hugging Face Jobs nach Pollens hf_jobs.py (Plan und Kosten prüfen, Start von
                         Pollens Stand oder eigenem Lauf, Lernkurven lesen, Stillstand, Zwischenstand exportieren)
  vision.py              Kamera (mediad media.frame, UYVY) und Enten-Erkenner (YOLO, ONNX)
  care.py                Roboter-Pflege: robot.health, robot.vetbook, system.*, net.status, update.* über Pollens Dienste
  joints.py              Gelenk-Check (Soll, Ist, Nachlauf, Last, Ampel), Pflegeheft, Abgleich Training ↔ Roboter
  buddy.py               Alltagsbuddy: deutsche Zeitangaben, Planer (Timer, Erinnerungen, Termine, To-dos), .ics
  acrobatics_service.py  Akrobatik: Prüfen, Üben im Hintergrund, Fähigkeitsheft akrobatik.json
  physics/acrobatics.py  Gliederpuppe in MuJoCo: Stützfläche, Schwerpunkt, Haltetest, Übungen
  skills/                Skill-Pakete: Registry und Kataloge (__init__.py), alltag.py (Alltagsbuddy, Ruhe/Aktiv), app_moves.py,
                         talent.py (Got a Talent + Abspielen), gaits.py (Gangarten), detector.py (Enten-Erkenner)
  motion/pollen_emotions.json  Pollens 14 Emotionen (aus tools/import_emotions.py)
  motion/stabilizer.py   Kopf-Stabilisator (Huhn/Taube): Ausgleich aus der Rumpflage, Blick halten und nachziehen
  voice/whisper_stt.py   lokale Spracherkennung (optional)
  voice/tts.py           Sprachsynthese: Piper, Qwen3-TTS (entwerfen + klonen), Entenfilter, Schnabelspur
  voice/speech.py        Antwort → Sätze und Entenlaute, Hintergrund-Erzeugung, Stimmen laden
  voice/describe.py      Stimmbeschreibung Deutsch → Englisch (Vorlagen, Claude, lokales Modell)
  voice/install.py       Zusatzpakete per Knopf (feste Listen; PyTorch für AMD/NVIDIA/CPU)
  settings.py            Einstellungen aus der App, Schlüssel im Tresor
  desktop.py             eigenes Programmfenster (Edge/Chrome im App-Modus), Autostart mit Windows
  remote.py              Handy-Fernbedienung: Kopplung per Einmal-Code, Gerätezeichen, Heimnetz-Prüfung, zweiter Zugang
  qr.py                  kleiner QR-Code-Erzeuger (ohne Zusatzpaket)
  tailscale.py           https-Adresse im eigenen Tailnet (tailscale serve) für Handy-Mikrofon und unterwegs
  augen.py               Augen der Ente: Bild von Roboterkamera, PC-Webcam oder Simulator – nur für eine Claude-Runde
  faces.py               Personen erkennen (YuNet + SFace, onnxruntime), nur Embeddings angelernter Personen
  server/app.py          setzt den Server zusammen (FastAPI); Einstieg für Aufrufer
  server/runtime.py      Laufzeit: Körper, Engine, Claude, Stimme, Training, Zustand an die Fenster
  server/security.py     Herkunftsschutz: Host, Origin, Handys, Weiterleiter
  server/routes/         Endpunkte je Bereich (basis, fernzugang, beenden, stimme, physik, training, parcours, …)
  server/static/         Oberfläche: app.js, duck3d.js (3D), duckmodel.js (Originalmodell),
                         dashboard.js (Diagramme, Lagebild, 3D-Tiefengelände, Punktwolke), pointcloud.js, personality.js
                         (X/Y-Regler), skills.js (Skill-Pakete), stimme.js (Seite Stimme & Gespräch), training.js (Kosten, Varianten, Lernkurven),
                         parcours.js (Seite Parcours mit 3D-Wiederholung), akrobatik.js (Gliederpuppe), alltag.js (Alltag),
                         fernbedienung.js (Handy koppeln, Geräte, Tailscale), lernen.js (Lernen am PC, Lernschleife),
                         augen.js (Webcam, Personen anlernen), laser.js (Laserpointer), mcp.js (MCP-Zugang), splash.jpg (früheres Startbild, nur privat),
                         voice.js (Erkennung, Abspielen, Gesprächsfenster), style.css
  server/static/ds/      Designsystem (Carbon Gray 90 + duckpilot-Ebene): tokens.css, components.css
  server/static/model/   nur private Fassung: fertiges 3D-Modell (CC BY-NC-SA 4.0); sonst baut duckpilot/modell es im Datenordner
  server/static/sounds/  Emotions-Töne, Gesten-Laute und Entenstimme
tools/                   make_icons.py (App-Icons aus assets/icon-quelle.png), make_public_art.py (eigene Icons für GitHub), export_public.py (öffentliche Fassung mit Geheimnis-Scan), bake_model.py, bake_physics.py, import_emotions.py, render_voice.py, render_gestures.py – erzeugen die Dateien
                         oben aus Pollens Repos neu
tests/                   359 Tests: Simulator, Verhalten, Werkzeuge, Gedächtnis, Claude (gemockt),
                         robotd-Pfad, Einstellungen, Schlüssel, Herkunftsschutz, Handy-Fernbedienung und QR-Code, Goofy, Gefühle,
                         Pollen-Emotionen, Stimme, 3D-Modell, Hub-Tricks, Charakter, Gesten-Laute,
                         Punktwolke, Skill-Pakete (mit gefälschtem Hub), Sprachsynthese und Abfolge,
                         eigenes Modell (gemockt), Wissen und Trick-Übung, Physik (Modell, Beobachtung,
                         Policy-Satz, Stürze, Hub-Tricks, Üben – mit Test-Policies), Kamera, Erkenner,
                         Pflege und Training (gegen Test-Roboter und gefälschten Hub), Parcours
                         (Geometrie per Raycast, Versuche, Auftrag, Werkzeuge, Server), Kopf-Stabilisator,
                         Gelenk-Check und Pflegeheft, Akrobatik (Gleichgewicht, Üben), Alltagsbuddy (Zeiten,
                         Planer, .ics, Alarme, Ruhe/Aktiv, Not-Aus-Sperre), Tailscale-Zugang, Augen und Bilder für
                         Claude, Personen erkennen (opt-in mit eigenen Fotos), Kaggle, Lernen am PC (PPO,
                         ONNX ↔ PyTorch) und Lernschleife
```

Tests laufen mit `pip install pytest` und `python -m pytest`.

## Grenzen

- Der Lite-Simulator ist kinematisch: Gangbild und Stürze sind nachgebildet. Mit „Echte Physik“
  rechnet MuJoCo – Ball, Socke und Klötzchen bleiben aber auch dort einfach nachgebildet.
- Im Simulator ist die Beinstellung aus Haltung, Gangphase und Geschwindigkeit abgeleitet; am echten
  Roboter zeigt das Originalmodell die gemessenen Gelenkwinkel.
- Hub-Tricks sind neuronale Policies und laufen auf dem Roboter und im Physik-Simulator, nicht im
  einfachen Simulator.
- Der Parcours ist eine gerade Bahn aus einfachen Formen; Objekte aus Blender oder FreeCAD wie in
  NVIDIAs Vorführung gibt es nicht. Trainiert wird auf Pollens eigenen Umgebungen (eben, „Rough“ mit
  Stufen und Schrägen), nicht auf dem gebauten Parcours selbst.
- Akrobatik ist Simulation: Beinhaltungen gehen am echten Roboter nur über eine trainierte Policy.
- Die Last im Gelenk-Check am Roboter ist eine Näherung aus dem Motorstrom (Blockierstrom ≈ 1,8 A).
- Der Alltagsbuddy meldet sich nur, solange duckpilot läuft; Kalender kommen nur als Datei (kein Abo).
- Stand der Protokollanbindung: `duck-ipc-proto` API v44 (Oktober 2026). robotd lehnt andere
  Versionen nicht ab, neue Felder werden ignoriert.
