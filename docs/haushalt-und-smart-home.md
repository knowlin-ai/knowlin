# Haushalt und Smart Home – Plan und Optionen

Stand: 1. November 2026 · Status: **geplant, noch nicht gebaut** (ab 0.46, am echten Roboter in R6)

Diese Seite beschreibt, was duckpilot im Haushalt können soll, welchen Weg wir zuerst gehen und welche Optionen es
daneben gibt. Der erste Schritt bleibt bewusst allgemein: Die Funktionen kommen erst einmal grundsätzlich, die
Community kann danach einzelne Geräte, Marken und Wege genauer ausarbeiten.

## Grundsätze

- **Lokal zuerst.** duckpilot spricht mit der Smart-Home-Zentrale im eigenen Netz, nicht mit Herstellerwolken.
- **Nur freigegebene Gerätearten.** Licht, Saugroboter, Szenen, Benachrichtigungen. **Nie** Türschlösser,
  Alarmanlagen, Heizung, Garagentore oder Steckdosen mit unbekannten Verbrauchern – auch nicht, wenn Claude es
  vorschlägt.
- **Schlüssel nur im Tresor** des Betriebssystems, wie alle anderen Zugänge.
- **Not-Aus gewinnt immer.** Eine Haushaltsaufgabe bricht bei Not-Aus, Sturz, Hochheben oder schwachem Akku ab.
- **Keine Bilder speichern ohne ausdrückliches Einschalten.** Die heutige Regel (Bilder gehen nur für eine Runde an
  Claude und werden nie gespeichert) bleibt der Standard.
- **Kein Sicherheitsversprechen.** Die Ente ersetzt keine Alarmanlage.

## Die Funktionen

| Funktion | Was sie tut | Braucht | Geplant |
|---|---|---|---|
| Aufräumen vor dem Saugroboter | Sammelt Kleines (z. B. Socken) ein, bringt es an einen Platz, startet danach den Sauger | Karte, Apportieren, Kamera am Roboter | 0.46 im Simulator, R6 am Roboter |
| Heimkehr zum Ladeplatz | Geht bei schwachem Akku zum „Ladeplatz“, setzt sich, bittet um Akkuwechsel; setzt die Aufgabe danach fort | Karte, Akkustand | 0.46 |
| Rundgang | Läuft eine Runde, meldet Auffälliges (Fenster offen, Wasser am Boden, etwas im Weg) aufs Handy | Karte, Kamera am Roboter | 0.47 im Simulator, R6 am Roboter |
| Licht folgt der Ente | Schaltet Licht im Raum an, in dem sie läuft, und wieder aus, wenn sie ihn verlässt | Karte mit Räumen, Smart Home | 0.47 |
| Besuchsmodus (Vorher-nachher) | Fotografiert feste Stellen vor und nach einem Termin und sagt, was sich verändert hat | Karte, Kamera, Termine, Bilder speichern | R6 |

## Anbindung ans Smart Home

**Erster Schritt: Home Assistant.** Eine Anbindung an die lokale Zentrale Home Assistant deckt die meisten Marken auf
einmal ab. duckpilot nutzt dort nur allgemeine Gerätearten (`light`, `vacuum`, `scene`, `notify`) und kennt keine
einzelne Marke.

| Weg | Vorteil | Nachteil | Status |
|---|---|---|---|
| **Home Assistant** (REST/WebSocket, Zugangsschlüssel im Tresor) | lokal, kostenlos, Hunderte Marken, Räume („Bereiche“) schon gepflegt | braucht eine laufende Home-Assistant-Installation | **Standard, ab 0.46** |
| Matter direkt (duckpilot als Matter-Steuerung) | gemeinsamer Standard von Amazon, Google, Apple; ohne Zentrale | aufwendiger, nicht jedes Gerät kann es | Option für die Community |
| Die Ente als Matter-Gerät (Modi wie Aufräumen, Rundgang, Ruhe) | erscheint direkt in Alexa, Google Home, Apple Home | Matter-Zertifizierung und Geräteklassen noch zu klären | Option für die Community |
| Hue direkt (Hue Bridge, lokal) | einfach, ohne Home Assistant | nur Licht von Hue | Rückfallweg, falls gewünscht |

### Alexa, Google, Apple

Sprachassistenten steuern die Ente **über Home Assistant**, nicht direkt:

| Weg | Hinweis |
|---|---|
| Matter-Brücke in Home Assistant (z. B. „Matter Hub“, Matterbridge) | lokal; laut Community-Berichten können Saugroboter darüber teils nur „starten“ und „stoppen“, nicht einzelne Räume |
| Home Assistant Cloud | einfach, kostet ein paar Euro im Monat |
| Eigener Alexa-Skill | viel Aufwand, nur wenn ein Bedarf besteht, den die beiden anderen Wege nicht decken |

Sprachbefehle an Alexa laufen immer über Amazons Server. Das muss jeder bewusst einschalten.

### Saugroboter

Allgemein über die Geräteart `vacuum` in Home Assistant: starten, anhalten, zur Station schicken. Das funktioniert mit
Dreame, Roborock, Ecovacs und anderen, soweit Home Assistant sie kennt. Neuere Dreame-Modelle sprechen auch Matter.
Einzelne Räume reinigen ist markenabhängig und eine Aufgabe für die Community.

## Meldungen aufs Handy

| Weg | Wann | Status |
|---|---|---|
| **duckpilot-Oberfläche auf dem gekoppelten Handy** | im WLAN oder mit Tailscale | **Standard** |
| Benachrichtigung über Home Assistant (`notify`, z. B. die Home-Assistant-App) | wenn Home Assistant da ist – erreicht das Handy auch unterwegs | **Standard, sobald Home Assistant verbunden ist** |
| ntfy (eigener Server oder ntfy.sh) | ohne Home Assistant, auch unterwegs | Option |
| Telegram, Signal u. a. | auf Wunsch | Option für die Community |

Meldungen enthalten Text. Ein Bild hängt nur dran, wenn der Rundgang mit Bildern gestartet wurde; es wird nirgends
gespeichert.

## Laden

Pollen bietet keine Ladestation. Die Microduck hat einen herausnehmbaren Kamera-Akku (NP-F550, 2600 mAh, etwa eine
Stunde Laufzeit); das „Charger Pack“ enthält zwei Ersatzakkus und ein Ladegerät.

- **Erster Schritt:** Ort „Ladeplatz“ festlegen. Bei etwa 15 % geht sie dorthin, setzt sich und bittet um einen
  Akkuwechsel. Aufgaben starten nur, wenn der Akku reicht.
- **Vorbereitet:** Gibt es später eine Ladestation (von Pollen oder der Community), bestätigt ein NFC-Tag am
  Ladeplatz, dass sie richtig steht – die Ente hat NFC-Leser in Kopf und Schnabel.
- **Nicht empfohlen:** eine kabellose Ladespule selbst einbauen (Lithium-Akku, Brandgefahr, Garantie).

## Bilder und Datenschutz im Besuchsmodus

Standard, solange niemand etwas anderes entscheidet:

- **Aus**, bis man ihn ausdrücklich einschaltet.
- Bilder werden **nur lokal** gespeichert, **höchstens bis nach dem Termin, spätestens nach 24 Stunden** gelöscht.
- **Nie während des Besuchs** fotografieren. Sind Personen im Bild, bricht sie ab, statt zu speichern.
- Der Vergleich durch Claude schickt die Bilder an Anthropic – auch das nur nach ausdrücklichem Einschalten.

## Wo die Community helfen kann

- Erfahrungen mit einzelnen Saugrobotern und Raumreinigung über Home Assistant
- Matter direkt oder die Ente als Matter-Gerät
- weitere Benachrichtigungswege
- eine Ladestation oder ein Andock-Halter für die Microduck
- Regeln, was beim Rundgang als „auffällig“ gilt
