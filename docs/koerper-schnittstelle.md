# Körperschnittstelle 1.0 – ein Kopf, viele Körper

*English: [body-interface.md](body-interface.md)*

Knowlin trennt das **Gehirn** von seinen **Körpern**. Zum Gehirn gehören Gedächtnis, Erfahrungsnetz, Charakter, Gespräch
und Raumwissen. Ein Körper ist alles, was das Gehirn bewegen kann: ein Simulator, eine Microduck, ein Reachy Mini, ein SO-101-Arm, ein
Roboter aus dem LeRobot-Ökosystem oder dein eigener Bau. Die Körperschnittstelle legt fest, wie ein Körper sich vorstellt
und welche Pflichten er hat. So kann ein neuer Roboter Knowlin bekommen, ohne dass jemand den Kern anfasst.

## Einordnung: Was es schon gibt

Knowlin erfindet die unteren Ebenen nicht neu, sondern setzt auf ihnen auf:

| Ebene | Standard | Wie Knowlin ihn nutzt |
|---|---|---|
| Einheiten und Richtungen | ROS REP-103 | Meter, Sekunden, Radiant; x vorwärts, y links, z oben |
| Beschreibung des Roboters | URDF, MJCF, USD | Simulatoren laden MJCF (MuJoCo); Isaac Lab nutzt USD |
| Treiber | ros2_control, Viam, **LeRobot `Robot`** | LeRobot-Roboter sind eingebaut (Adapter, siehe unten) |
| Trainingsdaten | LeRobot-Datensätze, Open X-Embodiment | Grundlage für spätere Aufnahmen |
| KI ↔ Werkzeuge | MCP | Knowlin ist selbst ein MCP-Server |

Was fehlt, ist ein Vertrag für die Frage: *Was bedeutet ein Körper für einen Kopf, der bleibt?* Dazu gehören ein
**Wortschatz der Fähigkeiten**, den das Gehirn versteht, **Sicherheitspflichten** und ein **gemeinsames Format für
Wahrnehmung**, damit Gedächtnis und Raumwissen von Körper zu Körper wandern. Genau das regelt diese Schnittstelle.

## Das Profil

Jeder Körper beschreibt sich mit einem `duckpilot.koerper.Koerper`:

| Feld | Bedeutung |
|---|---|
| `id` | Wert der Einstellung `modul`, bleibt für immer gleich (2–40 Zeichen, `a–z0–9_`) |
| `name`, `hersteller` | für die Oberfläche |
| `familie` | `ente`, `stationaer`, `fahrend`, `arm`, `vierbeiner`, `humanoid`, `andere` |
| `faehigkeiten` | was er kann, nur aus dem Wortschatz (eigene Wörter mit `x-`) |
| `fabrik` | `"modul:funktion"` oder eine Funktion; bekommt Knowlins Einstellungen, liefert ein `DuckBackend` |
| `zustand` | was `state().koerper` meldet (Standard: `id`) |
| `skills` | gelernte Bewegungen, die er ohne Zusatz kann |
| `echt`, `simulator` | wie der echte Roboter angebunden ist; ob es einen Simulator gibt |
| `quelle`, `lizenz` | Projektseite (https) und Lizenz |

## Wortschatz

**Fähigkeiten des Körpers:** `beine`, `raeder`, `kopf`, `koerperdrehung`, `schnabel`, `arm`, `greifer`, `antennen`,
`augen_leds`, `gesicht` (seit 0.38.58), `stimmbank`, `tiefensensor`, `kamera`, `mikrofon`, `lautsprecher`,
`pollen_bewegungen`.
Jedes Wort ist in `duckpilot/koerper.py` mit Bedeutung und Methode beschrieben. `GET /api/koerper/wortschatz` liefert
die Liste.

**Betrieb**, den ein Körper zur Laufzeit dazumeldet: `simulator`, `zuruecksetzen`, `physik`, `policies`.

Das Gehirn prüft Vorbedingungen mit diesen Wörtern. Ohne `beine` bietet es zum Beispiel kein „lauf zur Küche“ an, ohne
`tiefensensor` kein „erkunde den Raum“. Die Oberfläche blendet entsprechend aus.

Seit 0.38.47 brauchen auch die Kopf-Werkzeuge ihr Wort: Kopf drehen, Gefühle, Tanzen und Choreografie nur mit `kopf`;
Drehen mit `beine`, `raeder` oder `koerperdrehung`. Ein Arm ohne Kopf (SO-101) bekommt stattdessen das Werkzeug `arm`.

**Aktionen statt Bewegungen** (seit 0.38.43, `duckpilot/aktionen.py`): Das Gehirn sagt eine Absicht („grüßen“), der
Körper antwortet mit `kann`, `ersatz` oder `nein` – je nachdem, welche Umsetzung zu seinen Fähigkeiten passt (Kopf,
Arm, Laute). Ein neuer Körper braucht dafür keinen Code: Er meldet seine Fähigkeiten, der Katalog wählt.

## Das Laufzeit-Objekt

Ein Körper ist zur Laufzeit ein `duckpilot.api.DuckBackend`. Das Vokabular stammt von Pollens `robotd`:

- **Laufend** (die Bewegungs-Engine sendet mit 20 Hz): `move(Twist)`, `head(Head)`, `mouth(0…1)`, `pose(Pose)`
- **Einzeln:** `init()`, `enable(an)`, `stop()`, `do(skill)`, `haltung(gelenke, sekunden)`, `sound(tag)`, `rest()`,
  `relax()`
- **Lesen:** `state() → DuckState` (Lage, Geschwindigkeit, Kopf, Strom, Sturz, Wahrnehmung), `eigenschaften()`,
  `skills()`

Wahrnehmung kommt in einem gemeinsamen Format: `Perception.objects` mit `{name, art, entfernung_m, richtung_grad}`,
dazu Tiefenpunkte. Damit kann Raumwissen von Körper zu Körper wandern. Ein gemeinsames „Zuletzt gesehen“ für alle
Körper ist der nächste Schritt; heute gilt es noch je Körper.

## Sicherheitspflichten

| | Pflicht |
|---|---|
| P1 | Profil gültig, Fähigkeiten nur aus dem Wortschatz |
| P2 | `eigenschaften()` ⊆ Profil ∪ Betrieb |
| P3 | `connect()` in höchstens 5 s; `state()` wirft nie und meldet `connected` |
| P4 | Zustand lässt sich als JSON senden, `koerper` passt zum Profil |
| P5 | **Not-Aus:** `relax()` macht sofort stromlos (Motoren aus, nicht nur anhalten) |
| P6 | Stromlos bewegt sich nichts |
| P7 | Fortbewegung und Kopf bleiben in `api.LIMITS`, auch bei viel zu großen Befehlen |
| P8 | `stop()` hält an, ohne stromlos zu machen |
| P9 | `close()` in höchstens 5 s |
| E1 | Unbekannter Skill oder Ton wird abgelehnt statt zu werfen (empfohlen) |

Prüfen lässt sich das mit `python -m duckpilot.koerper_pruefung [id]`. Am echten Roboter geht es mit
`pruefen(körper, profil, echt=True)`; dabei fährt der Roboter kurz an, also nur mit freier Umgebung und mit der Hand am
Not-Aus.

Alle weiteren Regeln setzt Knowlins Bewegungs-Engine für jeden Körper durch:

- die Sperre nach dem Not-Aus,
- kein Aufstehen, solange er hochgehoben ist, und erst nach dem Stopp-Fenster,
- keine eigenständige Fortbewegung am echten Roboter,
- Personen nur am PC,
- Geheimnisse nur im Tresor.

Ein Körper kann diese Regeln nicht abschalten.

## Eigene Körper als Paket

Ein fremder Körper kommt als eigenes Python-Paket mit einem Entry Point. Diesen Weg nutzt auch Pollens Reachy-Mini-App-Store:

```toml
[project.entry-points."knowlin.koerper"]
rollbot = "mein_paket:profil"
```

`profil()` liefert ein `Koerper`. Knowlin lädt Erweiterungen beim Start. Ein kaputtes Paket stört nicht, es erscheint
unter „abgelehnt“ (`GET /api/koerper`). Eingebaute Körper gewinnen immer, eine Erweiterung kann sie nicht überschreiben.
Knowlin installiert Pakete nie selbst, und Knowlets enthalten nie Code.

Die Vorlage liegt unter [`examples/knowlin-koerper-vorlage`](../examples/knowlin-koerper-vorlage): ein simulierter
Rollbot, fertig mit Prüfung.

## LeRobot-Roboter

**SO-101** (seit 0.38.47) hat ein eigenes Profil `so101`: im Simulator mit dem offenen Modell von TheRobotStudio
(Apache-2.0) an einer eigenen Werkbank – Haltungen und Gesten in Grad (`duckpilot/arm.py`), Greifen und Ablegen mit
eigener Kinematik (`duckpilot/arm_kinematik.py`, `backends/werkbank.py`); am echten Arm über LeRobot mit dem Typ
`so101_follower` (noch ungeprüft).

Das Profil `lerobot` bindet jeden anderen LeRobot-`Robot` an (LeKiwi, Koch …). Die Fähigkeiten liest Knowlin aus
`action_features`:

- Gelenke `*.pos` ergeben `arm`, `gripper.pos` ergibt `greifer`.
- `x.vel`, `y.vel` und `theta.vel` ergeben `raeder`.
- Bilder ergeben `kamera`.

Fahren läuft in m/s und rad/s, für LeRobot in Grad/s umgerechnet. Haltungen fährt Knowlin in Schritten an und springt
nie. Werte stehen in LeRobots Einheiten (meist −100…100) und werden abgeschnitten.

**Not-Aus:** LeRobots eigener Vertrag kennt keinen. Knowlin ergänzt ihn: Geschwindigkeit null, dann
`bus.disable_torque()`, ohne Bus wird die Verbindung getrennt.

Einstellungen (nur am PC): `modul = "lerobot"`, `backend = "robotd"`,
`koerper_optionen = {"typ": "so101_follower", "port": "COM5", "id": "mein_arm"}`. Das Paket `lerobot` installierst du
selbst. Ohne das Paket sagt der Körper ehrlich, was fehlt.

## Versionen

Die Schnittstelle trägt eine Version (`SCHNITTSTELLE = "1.0"`). Neue Wörter und Pflichten heben die zweite Stelle. Was
bestehende Körper bricht, hebt die erste Stelle, und dann lehnt Knowlin Profile mit anderer erster Stelle ab.

## Noch nicht drin (nächste Schritte)

- Gehirn-Werkzeuge für Räder: heute verlangen „lauf“, „folg mir“ und Co. noch `beine`.
- Einstellungen für LeRobot in der Oberfläche; heute nur über die Einstellungsdatei oder die API.
- Policies aus LeRobot als gelernte Bewegungen (`do(skill)`).
- Eine Brücke zu ROS 2 als weiteres Profil.
