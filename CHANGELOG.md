# Änderungen

Alle nennenswerten Änderungen an Knowlin (Python-Paket duckpilot), die neuesten oben. Aufbau nach
[Keep a Changelog](https://keepachangelog.com/de/1.1.0/), Versionen nach [Semantic Versioning](https://semver.org/lang/de/)
(vor 1.0 darf sich noch alles ändern). Alle Versionen bis 0.27 sind im Oktober 2026 entstanden.

Jede Version nennt auch, was **nicht** geprüft ist. Die Microduck wird erst ausgeliefert, deshalb ist vieles nur im
Simulator, in der Physik und gegen einen Test-Roboter geprüft, der wie `robotd` antwortet.

Abschnitte je Version: **Neu**, **Geändert**, **Behoben**, **Sicherheit**, **Nicht geprüft**.

## 0.38.43 – 2026-11-12 – Absicht statt Bewegung, Selbstbild, verständliche Update-Hinweise

### Neu
- **Aktionskatalog (Etappe G2):** Knowlin kennt Gesten nach ihrer Absicht – grüßen, zustimmen, ablehnen, freuen,
  neugierig sein, sich umsehen, auf sich aufmerksam machen, traurig sein, staunen, ausruhen. Das Sprachmodell sagt, was
  es meint (Werkzeug `absicht`); der Körper antwortet mit **kann**, **Ersatz** (z. B. Reachy freut sich ohne Beine mit
  dem Kopf) oder **nein** mit Grund (liegt, Sperre nach dem Not-Aus, wird gehalten, keine passende Fähigkeit) – und das
  Modell sagt es ehrlich weiter. Neue Aktionen sind Daten in `duckpilot/aktionen.py`.
- **Selbstbild:** „Wie geht's dir?“ und „Was kannst du?“ beantwortet Knowlin aus den Daten seines Körpers (Werkzeug
  `selbstbild`: Haltung, Fähigkeiten, Sperre, Akku, was er hält) und sagt, was unsicher ist.

### Behoben
- **Update-Hinweise verständlich:** „Letztes Update“ steht in Worten („am 11.11.2026 um 22:41 ohne Fehler
  installiert“ statt „fertig, Code 0“). Ist ein Release schon da, aber der Installer noch im Bau, heißt es „kommt
  gleich“ statt „herunterladen“, und Knowlin schaut nach einer Viertelstunde wieder nach statt erst am nächsten Tag.

### Nicht geprüft
- Wie oft die Sprachmodelle von sich aus `absicht` und `selbstbild` nehmen (geprüft sind die Werkzeuge im Simulator mit
  Microduck und Reachy Mini).

## 0.38.42 – 2026-11-12 – Wertekern, Tanzposen, die in der Physik stehen

### Neu
- **Wertekern (Etappe G1):** Knowlin hat feste Werte – ehrlich sein, Sicherheit vor Neugier, Privatsphäre achten, nicht
  manipulieren, begründet ablehnen, und sie gelten immer. Jedes Sprachmodell bekommt sie gleich (Claude, lokal, anderes
  Modell, auch Knowlin auf der Startseite). Unter Charakter → Persönlichkeit zeigt die neue Karte „Werte und Grenzen“
  die Werte und „Was Knowlin nie tut“ – Grenzen, die im Code stecken und die kein Modell verschieben kann. Jede Grenze
  ist mit einem Test belegt.

### Behoben
- **Tanzposen fallen nicht mehr um:** Vor dem Tanz prüft Knowlin jede gespeicherte Haltung in einer unsichtbaren
  Physik-Welt (Schwerpunkt über der Stützfläche und Halteprobe). Zu wackelige Haltungen werden Richtung Grundstellung
  abgeschwächt, bis sie stehen; geht das nur fast bis zur Grundstellung, deutet die Ente sie nur an.

### Geändert
- **Für Mitwirkende:** Knowlin entsteht nur noch in diesem öffentlichen Repo. Vor jedem Push prüft `tools/waechter.py`,
  dass keine Schlüssel, privaten Namen oder Pollens Modelldateien im Repo landen; die Prüfkette läuft ohne Export mit
  einem Testlauf inklusive echter Physik. `CLAUDE.md` beschreibt die Arbeitsregeln.

### Nicht geprüft
- Wie sich die Werte bei Überredungsversuchen mit echten Sprachmodellen bewähren (geprüft ist, dass jedes Modell sie
  bekommt und die Grenzen im Code greifen).
- Tanzposen am echten Roboter (geprüft in der Physik am PC).

## 0.38.41 – 2026-11-12 – Handyansicht mit Platz, LM Studio unter „Lokales Modell“, neutral gegenüber dem Sprachmodell

### Neu
- **Handyansicht neu verteilt:** Das Cockpit füllt genau den Bildschirm – die Bühne gut ein Drittel, der Gesprächsverlauf
  den ganzen freien Platz (vorher etwa ein Achtel), darunter die Schnellbefehle als Wischreihe und die Eingabe. Die Seite
  rollt nicht mehr. „Antworten vorlesen“ ist ein Lautsprecher-Knopf neben der Eingabe, „Senden“ ein Symbol; über das
  WLAN steht im Feld „Schreiben oder diktieren …“ statt eines eigenen Hinweises.
- **Untere Leiste am Handy:** höchstens vier Bereiche mit vollem Namen und „Mehr“ (Charakter, System, Knowlin) – wie
  bei üblichen Apps. Der Not-Aus bleibt groß und rot rechts daneben.
- **LM Studio unter „Lokales Modell“:** Dort wählst du jetzt Ollama oder LM Studio – beides läuft auf diesem PC. „Anderes
  Modell“ ist für Anbieter mit Schlüssel (OpenAI, Gemini, Mistral, OpenRouter). Wer LM Studio bisher dort hatte, behält
  Modell und Adresse.

### Geändert
- **Neutral gegenüber dem Sprachmodell:** „An Claude“ heißt „An Knowlin“, Texte wie „Vorschlag von Claude“ oder „Claude
  kann bezahlte Läufe nur vorschlagen“ nennen das Sprachmodell – egal ob Claude, lokal oder ein anderes. Die Kopfzeile
  zeigt bei LM Studio das gewählte Modell.
- Die Deko-Tasse steht in der Tischecke statt in der Mitte – dort stand sie in Reachys Sockel.
- **Schnellere Prüfungen vor dem Hochladen (für Mitwirkende):** `tools/pruefen_alles.py` überspringt Bereiche, deren
  Dateien seit dem letzten Bestehen gleich sind, und rechnet die Tests auf allen Kernen (`pytest-xdist`); `--alles`
  prüft alles. Dazu `tools/oeffentlich_abgleichen.py` und `tools/release_nachpruefen.py`.

### Nicht geprüft
- Die Handyansicht auf echten Handys (geprüft im Browser mit 390 × 760 px, mit Touch).
- LM Studio unter „Lokales Modell“ gegen ein laufendes LM Studio (geprüft mit Tests der Einstellungen).

## 0.38.40 – 2026-11-11 – Qwen auf der Grafikkarte, Fehler mit Ort, Website mit Pollens Originalmodellen

### Neu
- **Qwen3-TTS nutzt die Radeon wirklich:** Auf PC (RX 9070 XT) war PyTorch in der Fassung für den Prozessor
  installiert – Qwen brauchte 12–40 s je Sekunde Sprache. Die Stimm-Seite erkennt das jetzt und bietet „Für die
  Grafikkarte einrichten“ an. Die AMD-Installation holt PyTorch mit ROCm aus AMDs aktueller Paketquelle in festen
  Fassungen (torch 2.12.0, ROCm 7.14.1, auch für Python 3.13) und ersetzt so ein vorhandenes Prozessor-PyTorch.
- **„Immer mit dieser Stimme sprechen – auch wenn sie länger braucht“:** Für PCs ohne passende Grafikkarte (etwa normale
  Laptops). Der Text steht sofort da, der Ton folgt Satz für Satz; ohne den Schalter spricht bei langen Antworten wie
  bisher Piper oder die Browser-Stimme.
- **Fehler sagen, wo sie liegen:** bei dir (Internet/WLAN), beim Anbieter (Server) oder in Knowlin – statt roher
  Fehlertexte über eine halbe Seite.

### Behoben
- **Stimme entwerfen:** Ein abgebrochener Download (schwaches WLAN) hinterließ ein halbes Entwurfsmodell; danach kamen
  „Unrecognized model“ oder „no file named model.safetensors“. Abbrüche werden jetzt bis zu dreimal fortgesetzt, und vor
  dem Laden prüft Knowlin jede Datei des Modells gegen Hugging Face und lädt nur nach, was fehlt oder zu kurz ist.
- **Reachy Mini, 3D-Modell: „HTTP Error 404“** – GitHub liefert Pollens `reachy_mini.xml` nicht mehr über
  media.githubusercontent.com aus. Knowlin weicht auf raw.githubusercontent.com aus, mit derselben Prüfsumme.
- **Lokales Modell schrieb Befehle in die Antwort** („[emote: staunen] [head: yaw deg=15 …]“) – sie werden jetzt
  ausgeführt und weder gezeigt noch vorgelesen; das Modell wird außerdem gebeten, das zu lassen.
- **LM Studio: „400 Bad Request“** – Modelle auf dem eigenen PC bekommen wie bei Ollama nur die wichtigsten Werkzeuge
  (passt in den Kontext), und der Fehler nennt den Grund – meist „Kontextlänge in LM Studio auf 16 384 stellen“.
- Hinweis beim Stimmentwurf ohne Übersetzung behauptete „ohne lokales Modell“, auch wenn eins eingestellt war.
- Umschalter (z. B. im Training „Mit Lernschleife | Am Stück“) sind mit dem Finger 44 px hoch statt 40.

### Geändert
- **Website und README zeigen Microduck und Reachy Mini mit Pollens Originalmodellen** statt der eigenen, einfachen
  Gestalten. Unter jedem solchen Bild steht der Bildnachweis „© Pollen Robotics, CC BY-NC-SA 4.0“ mit Link zur Lizenz;
  diese Bilder stehen selbst unter CC BY-NC-SA 4.0 (siehe NOTICE). Die Modelldateien liefert Knowlin weiterhin nicht
  mit – sie werden wie bisher auf dem PC geladen.
- **Vitrine:** ohne Handy-Kachel; die Einzelkacheln sind quadratisch und so hoch wie ihre breite Nachbarin, die
  Körperschnittstelle geht über die ganze Breite.
- `tools/website_bilder.py` nimmt aus dem vollen Stand auf und wartet, bis die 3D-Vorschau gezeichnet ist und die
  Kopfleiste „verbunden“ zeigt; die Handy-Szene entfällt.
- Die Website-Prüfung prüft den Bildnachweis: jedes Bild mit Pollens Modell nennt Urheber, Lizenz und Link, auch unter
  der Bühne je nach Körper.

### Nicht geprüft
- PyTorch mit ROCm auf einer echten Radeon: geprüft ist, dass AMDs Quelle die festen Fassungen für das Python des
  Installers anbietet (Installer-Workflow), nicht das Rechnen auf der Karte selbst.

## 0.38.39 – 2026-11-09 – Website mit Vitrine, neue Bilder, Oberfläche in Teilen

### Neu
- **Website knowlin.de:** neuer Abschnitt „Was in ihr steckt“ – eine dunkle Vitrine mit Kacheln für Tanzen zu deiner
  Musik, Handy als Fernbedienung, Akrobatik in echter Physik, ein ganzes Entenrudel, Lernen wie echte Roboter und die
  Körperschnittstelle für deinen eigenen Roboter. „Funktionen“ in der Leiste führt dorthin.
- **Neue Bilder** für Website und README, alle als ganzes Programmfenster aufgenommen (Gedächtnis, Persönlichkeit,
  Cockpit, Reachy, Odi, Startseite) – keine Ausschnitte mehr, die mit Rand aufs Format gebracht wurden.
- **`tools/website_bilder.py`** nimmt alle Bilder reproduzierbar aus dem laufenden Programm auf, auf Deutsch und Englisch.
  Es startet die öffentliche Fassung ohne Pollens Ansichtsmodelle, sodass diese nie auf der Website erscheinen; für
  die Akrobatik rechnet die Physik mit Pollens Physikmodell, gezeigt wird das eigene Modell.

### Geändert
- **Oberfläche in Teilen (Architektur-Etappe A2, erster Bereich):** Tricks, Tanzen, Team, Vom Hub und Kamera-Spiele
  stehen in `static/teile/tricks.html`, ihre eigenen Stile in `static/bereiche/tricks.css`. Der Server setzt die Seite
  zusammen. Sichtbar ändert sich nichts – geprüft mit `tools/oberflaeche_vergleich.py` (berechnete Stile aller
  Ansichten vorher/nachher, zwei Körper, PC und Handy) und der Abnahme.
- `tools/bilder_rahmen.py` entfällt (ersetzt durch `tools/website_bilder.py`).

### Behoben
- **Handy, Kopfzeile:** „Knowlin getrennt“ (englisch noch länger) lag über „Aktiv“. Die Meldung wird jetzt gekürzt,
  ganz steht sie im Tooltip.
- **Cockpit:** der Text unter dem Zustand („tanzen (party, 110 bpm …)“) war vor der weißen Ente kaum lesbar – er hat
  jetzt einen engen Schatten.

### Nicht geprüft
- Die Website auf echten Handys (geprüft mit der Website-Prüfung in Chromium, PC und Handybreite).

## 0.38.38 – 2026-11-09 – Updates und Downloads mit Fortschritt

### Neu
- **Update mit Fortschritt:** Beim Herunterladen zeigt die Leiste einen Balken mit „… MB von … MB“, dann
  „Prüfe die Prüfsumme …“. Danach führt eine Schrittliste durch das Update (Herunterladen, Prüfsumme prüfen,
  Installieren, Knowlin startet, Fertig) – mit mitlaufender Zeit, damit man sieht, dass sich etwas tut.
- **Knowlin meldet sich beim Start sofort:** Das startende Knowlin belegt seinen Port gleich mit einem kleinen
  Statusdienst und sagt, wobei es ist („Körper, Stimme und Gedächtnis werden aufgebaut“). Das offene Fenster zeigt das
  nach einem Update oder Neustart an und lädt sich neu, sobald alles bereit ist; ein normaler Start öffnet das Fenster
  gleich mit „Knowlin startet …“ statt erst nach dem langsamen Teil.
- **Nachinstallieren mit Fortschritt:** Physik, Stimmen, Gesichter und PyTorch zeigen beim Herunterladen Datei,
  „… MB von … MB“ und einen Balken (pip ab 24.1; ältere pip-Fassungen ohne Balken).

### Behoben
- Nach einem Update stand nach 90 Sekunden „Das Update wird noch installiert …“, obwohl der Installer längst fertig war
  und Knowlin schon startete (bei Alex: Installer 70 s, erster Start danach zwei Minuten). Das Fenster wusste nicht,
  was passiert; jetzt sagt es der neue Knowlin selbst. Ist das Update nicht durchgelaufen, sagt das Fenster das auch.

### Geändert
- Startschritte stehen mit Zeit im Protokoll (`duckpilot.log`: „Start nach … s: …“), damit sich ein langsamer Start
  nachvollziehen lässt. Die Update-Probe bei GitHub misst die Startdauer nach dem Installer und schreibt die gemeldeten
  Schritte mit.
- Vorbereitung für das Aufteilen der Oberfläche (Architektur-Etappe A2): Tests und Werkzeuge lesen die Seite über
  `duckpilot/server/oberflaeche.py`; ein Vertragstest prüft, dass jede ID, die ein Skript holt, auf der Seite steht.
  An der Oberfläche selbst ändert sich dadurch nichts.

### Nicht geprüft
- Wie viel der Statusdienst den ersten Start nach einem Update unter Windows tatsächlich verkürzt – er macht ihn
  sichtbar, nicht schneller. Die Startzeiten im Protokoll zeigen beim nächsten Update, wo die Zeit bleibt.

## 0.38.37 – 2026-11-09 – Auf einem Bein klappt wieder, Tricks-Vorschau läuft mit

### Behoben
- **Akrobatik „Auf einem Bein“** blieb mit Pollens Modell, wie Knowlin es beim ersten Start lädt, bei 0 %. Die Suche
  begann mit einer Vorlage, die nur nach der statischen Reserve gewählt wurde – Unterschiede von einem Millimeter
  entschieden, und mit dem geladenen Modell gewann ein nach vorn gestrecktes Bein, aus dem sie nicht herausfand. Auch
  mit dem eingebauten Modell klappte es nur mit Glück (linkes Bein, ein bestimmter Startwert). Jetzt wird jede Art, das
  Bein zu heben, unter den Schwerpunkt gerückt (Hüfte rollen und drehen) und in der Probe geprüft; die Suche bekommt
  außerdem Punkte dafür, wie lange eine Haltung steht, bevor sie fällt. Ergebnis: beide Beine, beide Modelle, 16 von 16
  Läufen ab 52 %.
- **Tricks:** Die Vorschau läuft beim Blättern mit, statt oben stehen zu bleiben. Auf schmalen Bildschirmen ist sie ein
  kleiner Streifen oben, unter dem die Kacheln durchlaufen.

### Geändert
- **Prüfung bei GitHub** hat einen Lauf mit echter Physik (MuJoCo, ONNX Runtime und Pollens geladenes Modell); bisher
  übersprangen sich dort alle Physik-Tests. Die Prüfkette `tools/pruefen_alles.py` macht das lokal genauso.

### Nicht geprüft
- Haltungen auf einem Bein am echten Roboter (dort nimmt robotd für die Beine nur Policies an).

## 0.38.36 – 2026-11-09 – Fremde Körper bleiben sie selbst, eine Prüfkette vor jedem Push

### Geändert
- **Körper ohne eigenen Eintrag** (Erweiterungen, LeRobot) bekommen Namen, Weckwort und Gruß aus ihrem Profil und sind
  keine Ente, wenn ihr Profil das nicht sagt. Vorher hieß jeder fremde Körper „Quacki“, hörte auf „ente“ und beschrieb
  sich der KI gegenüber als Microduck. Die KI bekommt jetzt „Dein Körper kann: …“ aus dem Wortschatz.
- **Knowlets** gehen für jeden Körper mit Profil, auch für Erweiterungen.
- **Trainingshalle** (Policies vom Hub, Parcours, Training, Posen aus der Akrobatik) richtet sich nach dem Profil
  (`lab`) statt nach dem Namen „microduck“.
- **Leitplanke:** Körper werden nicht mehr neu über ihren Namen abgefragt; ein Test hält fest, wo das heute noch steht
  (70 Stellen, meist Inhalte je Körper wie Stimmen und Figuren), und lässt die Liste nur kleiner werden.
- **Prüfkette** `python tools/pruefen_alles.py`: ruff, eslint, Sprachkatalog, pytest, öffentliche Fassung samt Tests,
  Paket-Rauchtest, Abnahme gegen das installierte Paket und Website in einem Lauf, mit Bericht. Vor jedem Push Pflicht.

### Nicht geprüft
- Erweiterungs-Körper mit echter Hardware (geprüft mit der Vorlage „Rollbot“ und einem nachgebauten LeRobot).

## 0.38.35 – 2026-11-09 – Körperschnittstelle 1.0, LeRobot-Roboter, verständliche Policy-Auswahl

### Neu
- **Körperschnittstelle 1.0** – ein Geist, viele Körper. Jeder Körper beschreibt sich mit einem Profil (`duckpilot/koerper.py`):
  wer er ist, was er kann (fester Wortschatz: Beine, Räder, Kopf, Arm, Greifer, Antennen, Tiefensensor, Kamera …, eigene
  Wörter mit `x-`) und wie er gebaut wird. Spezifikation: `docs/koerper-schnittstelle.md` (englisch `docs/body-interface.md`).
  Sie baut auf vorhandenen Standards auf (ROS REP-103, MJCF, LeRobot, MCP) und regelt, was dort fehlt: Wortschatz für das
  Gehirn, Sicherheitspflichten, gemeinsames Wahrnehmungsformat.
- **Konformitätsprüfung** `python -m duckpilot.koerper_pruefung [id]`: Not-Aus macht stromlos, stromlos bewegt sich nichts,
  Stopp hält an, Grenzen, Verbinden und Schließen, Profil passt (P1–P9). Microduck, Reachy Mini und Open Duck Mini bestehen.
- **Eigene Körper als Paket** über den Entry Point `knowlin.koerper`; kaputte Pakete werden abgelehnt statt Knowlin zu
  stören, eingebaute Körper lassen sich nicht überschreiben. Erweiterungen erscheinen als Modul auf der Startseite.
  Vorlage mit simuliertem „Rollbot“: `examples/knowlin-koerper-vorlage`.
- **LeRobot-Roboter** (SO-101, LeKiwi, Koch …) als eingebauter Körper `lerobot`: Fähigkeiten aus den Merkmalen des Roboters,
  Fahren in m/s und rad/s, Haltungen werden schrittweise angefahren. Einstellungen `modul`, `backend = "robotd"`,
  `koerper_optionen` (typ, port, id) – vorerst über Einstellungsdatei oder API, nur am PC.
- `GET /api/koerper` (alle Profile, aktiver Körper, abgelehnte Erweiterungen) und `GET /api/koerper/wortschatz`.

### Geändert
- Körper werden über ihr Profil gebaut statt über eine feste Liste; die Einstellung `modul`, `--modul` und der Körperwechsel
  vom Handy kennen damit auch Erweiterungen. Das Gehirn liest die Fähigkeiten aus dem Profil (vorher eine eigene Liste, in
  der z. B. die Stimmbank der Microduck fehlte).
- **Lernen → Training → Policies aus Isaac Lab** (Fragen „Was ist das beste aktuell?“, „Warum laden wir nicht die
  Standard-Policy von Pollen?“, „wie man wieder die Standard-Policy aktiviert“): Oben steht jetzt, was im Physik-Simulator
  läuft – Pollens Standard-Gangart oder eine übernommene Policy –, mit „Zurück auf Pollens Standard“ direkt daneben.
  Pollens Paket ist in der Liste als „Standard · läuft schon in der Physik“ markiert, seine Dateien haben Klarnamen
  (velstand = Gehen & Stehen, roulade = Purzelbaum, roller = Rollen …). Übernehmen ändert nichts am Körper; nach jedem
  Neustart läuft wieder Pollens Standard. Ein Satz erklärt, dass es die Rampen-Policy aus NVIDIAs Vorführung nicht als
  Datei gibt.

### Behoben
- Website: Der Text im Knopf „Kopieren“ stand um 20 px nach rechts versetzt (der unsichtbare Haken nahm Platz ein).
- Sichtbare Texte der Erweiterungen „Community-Tricks“ und „Got a Talent“ nannten noch „duckpilot“ statt Knowlin –
  sichtbar, seit die Pakete von Anfang an eingeschaltet sind.

### Sicherheit
- Not-Aus für LeRobot-Roboter ergänzt (LeRobots eigener Vertrag kennt keinen): Geschwindigkeit null, dann Drehmoment aus;
  ohne Bus-Zugriff wird die Verbindung getrennt. `koerper_optionen` nur am PC, ohne Geheimnisse, eine Zeile je Angabe.

### Nicht geprüft
- LeRobot an echter Hardware (geprüft mit einem nachgebauten LeKiwi: Arm, Greifer, Räder, Kamera). Das Paket `lerobot`
  ist keine Abhängigkeit von Knowlin.
- Gehirn-Werkzeuge für Räder („lauf“, „folg mir“ verlangen noch Beine) und Einstellungen für LeRobot in der Oberfläche
  folgen.

## 0.38.34 – 2026-11-09 – Update aus der App, das wirklich durchläuft

### Behoben
- **„Jetzt aktualisieren“ lief nicht durch** (erstes echtes Update 0.38.32 → 0.38.33: „Neustart dauert länger“, danach
  wieder 0.38.32). Das Fenster gab nach 90 Sekunden auf und bat, Knowlin neu zu starten – während der stille Installer
  noch arbeitete. Jetzt:
  - wartet das Fenster nach einem Update bis zu 5 Minuten („Das Update wird noch installiert …“),
  - beendet der Installer vor dem Kopieren selbst jedes Knowlin, das noch aus seinem Ordner läuft, und schließt belegte
    Programme (`/CLOSEAPPLICATIONS /FORCECLOSEAPPLICATIONS`),
  - schreibt der Ablauf ein Protokoll (`%LOCALAPPDATA%\duckpilot\updates\update.log` und `setup.log`); wie das letzte
    Update ausging, steht unter Einstellungen → Über.
- Der Installer-Start ist ohne Konsolenfenster, in eigener Prozessgruppe und kodiert übergeben (Pfade mit Leerzeichen).
- **„Stopp“ unter Tanzen löste den Not-Aus aus** – samt Sperre, danach wurde „Probe tanzen“ abgelehnt. Jetzt hält
  „Stopp“ (und „Musik und Tanz stoppen“) nur Tanz und Musik an; mittanzende Enten hören mit auf. Neu dafür:
  `choreo aktion=stopp`, `POST /api/choreo/stopp`. Der Not-Aus bleibt links, wie er ist.
- **„Weitere Enten tanzen mit“** schaltete beim Wechsel zwischen einfachem Simulator und Physik nicht zwischen frei und
  gesperrt um – jetzt sofort.
- **Tanzen:** Die Vorschau klebte beim Scrollen fest, „Nach Gehör“ schob sich darüber.
- **Tricks:** Die Vorschau sitzt auf Höhe der ersten Überschrift; Hinweis, dass es weitere Tricks als Erweiterung gibt.
- **Vom Handy den Körper wechseln** geht jetzt, solange nur der Simulator läuft (vorher nur „wecken“ der zuletzt
  aktiven Verkörperung). Mit echtem Roboter bleibt der Wechsel beim PC.
- **Punkt am System-Knopf:** nur noch, wenn gar kein KI-Modell eingerichtet ist (auch nicht lokal oder ein anderes), und
  mit Erklärung beim Darüberfahren.
- **Linke Leiste:** „Einstellungen“ ragte über den hervorgehobenen Knopf hinaus.
- **Tailscale nicht installiert:** jetzt mit Link „Tailscale für Windows laden“ – es ist ein eigenes Programm, das
  Knowlin nicht selbst installieren kann.
- **Update-Ablauf:** wartet nur noch auf den Installer selbst – „-Wait“ wartete auch auf das danach gestartete Knowlin
  und hätte nie „fertig“ gemeldet (gefunden von der neuen Update-Probe).
- **Nachinstallieren hinter einem Proxy** (Firma, Schule): pip bekommt jetzt den Proxy aus den Windows-Einstellungen
  mit und wartet länger (60 s, 8 Versuche). Vorher liefen Downloads von AMDs Paketquelle in „Read timed out“.
- **Hugging Face nicht erreichbar:** statt „<urlopen error _ssl.c:1015 …>“ eine verständliche Meldung und der Link
  „Auf Hugging Face suchen“ – die Adresse lässt sich dann von Hand eintragen.
- **Tricks auf einem neuen PC leer:** Pollens App-Bewegungen und die Community-Tricks (mit Vorschauvideos) sind jetzt von
  Anfang an eingeschaltet, nicht erst unter Steuern → Erweiterungen.
- **Gedächtnis → Was Knowlin über deine Welt weiß:** Spalten ziehen sich nicht mehr über die ganze Kachel (der
  Gefühlston stand weit weg vom Namen), mehr Luft zum Einleitungstext.

### Sicherheit
- **Sperre nach dem Not-Aus wählbar von 15 Sekunden bis 10 Minuten** (Entscheidung des Maintainers: „überall kürzer
  wählbar … ist ja kein Elefant“). Standard bleiben 2 Minuten. Die Sperre betrifft nur, was sie von selbst tut –
  „Steh auf“ geht jederzeit, nie während sie hochgehoben ist. Vorher nur 2, 5 oder 10 Minuten.

### Neu
- **Installer im Design der App:** Seitenleiste und kleines Bild mit dem Knowlin-Zeichen auf dunklem Grund.

### Geändert
- **Update-Probe auf Windows bei GitHub:** Vor jedem Installer wird die vorige Fassung still installiert und gestartet,
  dann „Jetzt aktualisieren“ über den Code der App ausgelöst – danach muss die neue Version installiert sein und von
  selbst wieder laufen.

### Nicht geprüft
- Das Update 0.38.33 → 0.38.34 aus der App: Der Start-Weg von 0.38.33 läuft nachweislich nicht durch (Testlauf bei
  GitHub) – einmal den Installer von Hand laden und drüber installieren, die Daten bleiben.

## 0.38.33 – 2026-11-08 – Fehler aus dem ersten Abend mit dem Installer

### Neu
- **Tricks mit Live-Vorschau** (Frage: „Wo sind die Tricks mit der Vorschau?“): Rechts neben den Kacheln läuft die
  Figur live mit wie beim Tanzen – antippen, sehen, weiter antippen, ohne Sprung ins Cockpit. Im schmalen Fenster
  steht die Vorschau oben.
- **Die Raumkarte lernt beim Fahren von Hand mit** (Frage: „Wieso erkennt er nicht weiter, wenn er manuell was
  sieht?“): bisher nur im Modus „Raum erkunden“. Nie, wenn sie hochgehoben oder umgefallen ist.

### Behoben
- **Pollens Emotionen fehlten im Installer und bei pip/pipx:** Die Datei `motion/pollen_emotions.json` stand nicht in
  der Paketliste. Ein Test prüft jetzt, dass jede Datei aus dem Quellordner im Paket landet.
- **Lokales Modell (Ollama) und andere Anbieter gingen im Installer nicht:** `httpx` kam früher mit `anthropic` mit,
  seit anthropic 2.x nicht mehr. Jetzt ist es eine eigene Pflichtabhängigkeit; ein Test prüft, dass jedes importierte
  Fremdpaket entweder Pflicht ist oder per Knopf nachinstalliert wird. Gefunden von der neuen Abnahme gegen das
  installierte Paket.
- **Hugging-Face-Vorschläge und -Laden gingen im Installer nicht** („Hugging Face war nicht erreichbar“): Sie brauchten
  das Paket `huggingface_hub`, das erst mit Training oder Qwen3-TTS kommt. Jetzt geht es auch direkt über
  huggingface.co.
- **Raumkarte: freie Zellen hinter der Wand.** Treffer genau am Fuß einer Wand fielen in die Zelle dahinter. Was schon
  in einer gespeicherten Karte steht, verschwindet mit Umgebung → Karte leeren.
- **Flimmernde Ecken im 3D-Raum:** Die Fußleisten zweier Wände überlappten mit gleich hoher Oberkante (Z-Fighting).
- **Treppenkanten trotz Kantenglättung:** Die Umgebungsverdeckung entstand ungeglättet. Am Ende der Darstellung glättet
  jetzt zusätzlich FXAA.
- **Aussehen: Die Ente stand im Farbbild hinter dem Blumentopf.** Die Bilder zeigen sie jetzt frei auf ihrem Boden.
- **Rauschen an Möbelkanten:** Die Umgebungsverdeckung rechnet wieder mit 16 Proben und glättet stärker (0.38.18 war
  sie aus Tempogründen gesenkt worden). Langsame Rechner schalten unter „Auto“ ohnehin auf „schnell“.
- **Umgebung im Leerzustand:** Die Karte steht direkt neben dem Text statt ganz rechts mit großer Lücke;
  „Erkundetes löschen“ erscheint erst, wenn es etwas zu löschen gibt.
- **Stimmung im Gedächtnis:** „freudig“ und „frustriert“ schwebten ohne Linie neben der Kurve – jetzt mit Hilfslinien.
- **„Pollens App-Katalog ansehen“ führte auf eine 404-Seite** (Pollen hat den Space umgezogen) – jetzt die
  Reachy-Mini-Apps auf Hugging Face (Spaces mit „reachy_mini“), auch auf der Website. Externe Links prüft GitHub ab jetzt jede Woche.
- **Einstellungen → KI-Modell → „Anderes Modell“ bot keine Anbieter an** (Frage: „Geht auch LM Studio? Und bei andere
  Anbieter wird nichts angeboten“): Der Abschnitt steht seit 0.38.0 unter Einstellungen, geladen wurde er aber nur auf
  der Seite „Knowlins Stimme“. Jetzt lädt er auch dort – mit OpenAI, Gemini, Mistral, OpenRouter, LM Studio und eigener
  Adresse. Aus demselben Grund blieb beim eigenen Modell „Prüfe Ollama …“ stehen.
- **Qwen3-TTS und Lernen auf AMD-Grafikkarten ließen sich mit dem Windows-Installer nicht installieren** („pip endete
  mit Code 1“, im Protokoll „No module named 'setuptools'“ beim Paket `rocm`): Das mitgelieferte Python übergeht
  PYTHONPATH, über das pip Quellpakete in einer abgeschotteten Umgebung baut. Knowlin legt dort jetzt erst die
  Bauwerkzeuge (setuptools, wheel, packaging) in die eigene Umgebung und baut ohne Abschottung. Betrifft alle
  Nachinstallationen (Stimmen, Spracherkennung, Physik, Lernen), nur in der Installer-Fassung.
- **LM Studio ohne laufenden Server:** statt einer technischen Fehlermeldung der Hinweis, in LM Studio unter
  „Developer“ den lokalen Server zu starten (Port 1234) und ein Modell zu laden.

### Geändert
- **„Eigenes Modell“ heißt jetzt „Lokales Modell“** – das sagt besser, dass es mit Ollama auf diesem PC läuft. Dort
  gibt es „Erneut prüfen“, wenn Ollama noch nicht lief, und den Hinweis, wo LM Studio zu finden ist.
- Texte zum Lernen und zu Ollama nennen allgemein „die Grafikkarte“ statt einer bestimmten Karte.
- **Prüfungen:** Die Abnahme läuft zusätzlich gegen das installierte Paket in einer frischen Umgebung ohne
  Zusatzpakete (`tools/abnahme.py --installiert`); GitHub prüft bei jedem Push das gebaute Paket und im
  Installer-Ablauf das eingebettete Python samt Bau eines Quellpakets.
- Dependabot schlägt Paket-Updates nur noch vor, wenn eine neue Version aus dem erlaubten Bereich fällt – statt jede
  Untergrenze auf die neueste Version zu ziehen (das hätte pip-Nutzer ohne Not zu den neuesten Paketen gezwungen).

### Nicht geprüft
- LM Studio mit einem echten Modell (nur gegen eine nachgebildete Schnittstelle getestet).
- Die AMD-Installation von Qwen3-TTS auf Windows nach dem Fix (der Fehler ist nur dort nachstellbar).
- Das stille Update auf einem echten Windows-PC (erstmals mit dem Schritt von 0.38.32 auf 0.38.33).

## 0.38.32 – 2026-11-08 – Updates aus dem Programm

### Neu
- **Update-Hinweis** (Frage: „Bekommen die Leute eine Update-Info und können aus dem Programm heraus aktualisieren?“):
  Knowlin sieht höchstens einmal am Tag bei GitHub nach, ob es eine neue Version gibt, und zeigt dann oben „Knowlin
  0.38.xx ist da“ mit „Was ist neu“. Abschaltbar unter Einstellungen → Über; dort auch „Jetzt nach Updates suchen“.
- **„Jetzt aktualisieren“**: Mit dem Installer lädt Knowlin den neuen Installer aus dem Release, prüft die Prüfsumme
  gegen die Angabe von GitHub, beendet sich, installiert still und startet neu. Mit pipx/pip aktualisiert es das Paket
  und startet neu. Aus dem Quellcode (start.bat) gibt es nur den Hinweis.

### Geändert
- GitHub-Abläufe auf neue Versionen (CodeQL 4, Pages 5) und `fast-simplification` ab 0.2.0 – Vorschläge von Dependabot.

### Behoben
- Nach einem stillen Update öffnete sich ein zweites Fenster – jetzt lädt sich das offene neu.
- Der Download-Knopf der Website folgt dem neuesten veröffentlichten Release (zeigte zwischen zwei Releases sonst auf
  einen Installer, den es noch nicht gab).
- Einstellungen → Über: Abstand zwischen Schalter und Text im Update-Block.

### Sicherheit
- Geladen wird nur aus den Releases von knowlin-ai/knowlin, nur mit passender SHA-256-Prüfsumme; nie mit dem echten
  Roboter verbunden, nur am PC, nur im Programmfenster. Die Suche schickt nur die übliche Anfrage an GitHub.

### Nicht geprüft
- Das stille Update auf einem echten Windows-PC (erstmals mit dem Schritt von 0.38.31 auf 0.38.32).

## 0.38.31 – 2026-11-08 – Windows-Installer und pip

### Neu
- **Knowlin-Setup.exe** (Hinweis: „das mit der start.bat ist das Einzige, was ich komisch finde“): ein Installer für
  Windows mit eigenem Python, ohne Administratorrechte, mit Einträgen im Startmenü und auf dem Desktop und sauberem
  Deinstallieren über „Apps“. Er wird bei jedem Release auf GitHub gebaut, kurz probeweise gestartet und ans Release
  gehängt. Gedächtnis und Einstellungen bleiben bei Updates und beim Deinstallieren erhalten.
- **`pipx install knowlin`** für Windows, macOS und Linux; `knowlin --verknuepfung` legt unter Windows die Einträge im
  Startmenü und auf dem Desktop an.
- **Website: „Für Windows herunterladen“** oben auf der Startseite lädt direkt den Installer der aktuellen Version (die
  Website baut bei jedem Release neu, der Link stimmt immer).
- **Einheitliche Bildschirmfotos** (Hinweis: „die Screenshots sind immer unterschiedlich groß“): alle Fotos in README und
  auf der Website im selben Format 1600 × 965; Ausschnitte stehen mittig auf ihrer nahtlos verlängerten Fläche
  (`tools/bilder_rahmen.py`). Download-Knopf kurz „Download“, darunter klein Windows-Version und der Weg für macOS/Linux.
- README und Website: Schnellstart mit dem Installer zuerst, `pipx` für alle mit eigenem Python, `start.bat` für den
  Quellcode.

### Sicherheit
- Herausgeber im Installer ist „Knowlin“. Der Installer ist noch nicht signiert – Windows warnt beim ersten Start vor
  einem unbekannten Herausgeber; die Anleitung erklärt das.

### Nicht geprüft
- Der Installer auf einem echten Windows-PC (geprüft wird er beim Bauen auf GitHubs Windows-Rechnern).

## 0.38.30 – 2026-11-08 – Policies direkt von Hugging Face, Feinschliff vor dem Launch

### Neu
- **Policies direkt von Hugging Face laden** (Frage: „kann ich die Policies nicht OTA laden?“): Unter Lernen → Training →
  Policies aus Isaac Lab wählst du jetzt die Quelle – **Von Hugging Face** (vorgewählt) oder **Datei von diesem PC**.
  Adresse eingeben (`besitzer/repo`, `besitzer/repo/pfad.onnx` oder ein huggingface.co-Link), Knowlin lädt die Datei und
  schickt sie durch dieselbe Prüfung und denselben Prüfstand. Liegen im Repo mehrere Policies, kommt eine Auswahl statt
  einer geratenen Datei. Repo, Pfad, Stand und Lizenz laut Modellkarte stehen danach an der Policy.
- **Policies werden vorgeschlagen** (Frage: „kann das nicht schon automatisch aufgelistet werden?“): Mit der Quelle
  „Von Hugging Face“ sucht Knowlin öffentliche Microduck-Repos mit ONNX-Dateien – meistgeladene zuerst, mit Downloads,
  Lizenz, Anzahl der Policies und Stand. „Auswählen“ übernimmt Adresse und Datei; geladen wird erst beim Prüfen.

### Geändert
- **Website: „Odi ausprobieren“ vorerst abgeschaltet** (Hinweis: „enttäuscht ggf. die Erwartungen – die App kann ja viel
  mehr“). Startseite wieder mit „So startest du“; Seite und Demo bleiben im Repo und kommen zurück, wenn sie mehr zeigen.
- **Website für Suchmaschinen** (Wunsch: „kannst du Knowlin noch SEO-optimieren?“): aussagekräftiger Titel und
  Beschreibung, strukturierte Daten (Software, kostenlos, Open Source, ohne Personennamen), `robots.txt` und
  `sitemap.xml`, vollständige Vorschau für soziale Netze. Behoben: Vorschaubild der Rechtsseiten zeigte auf eine falsche Adresse.
- Karte „Policies aus Isaac Lab“: Abstand zur Karte „Robustheit gegen Stöße“, kein leerer Platz mehr unter dem Knopf,
  Überschrift und Text so eng wie in den anderen Karten, „Noch keine Policy übernommen.“

### Sicherheit
- Geladen wird nur von huggingface.co, nur `.onnx`-Dateien bis 60 MB, fremde Adressen und `..` im Pfad werden
  abgewiesen; heruntergeladen wird genau der angesehene Stand. Nur am PC, nicht vom Handy aus. Im Offline-Modus nichts.

### Nicht geprüft
- Laden aus echten Community-Repos mit dem Prüfstand auf PC (geprüft mit nachgebautem Hugging Face).

## 0.38.29 – 2026-11-08 – Odi im Browser ausprobieren

### Neu (Website)
- **Odi ausprobieren** (T4, Hinweis: „Ausprobieren ohne Installation auf knowlin.de – stark für den Launch“): Eine
  eigene Seite `knowlin.de/ausprobieren.html`, verlinkt in der Navigation und im Startbereich. Odi (Open Duck Mini v2,
  Apache-2.0) läuft ganz im Browser – ohne Installation, Konto, KI-Schlüssel oder Anfragen nach draußen. Laufen per
  Steuerkreuz, Pfeiltasten oder WASD, Tricks (hinsetzen, nicken, Kopf schütteln, umschauen, tanzen, zum Ball) und ein
  paar Wörter auf Deutsch und Englisch („geh zum Ball“, „dance“). Der Ball rollt, wenn Odi ihn anstößt.
- Odi lädt erst auf Klick (etwa 4 MB), die Seite zeigt vorher ein Bild. Dieselbe 3D-Ansicht wie in Knowlin
  (Modell-Lader, Licht, Boden) und dieselbe Gangformel wie der einfache Simulator – geprüft: gleiche Gelenkwinkel.
- Pollens Modelle (Microduck, Reachy Mini) kommen nie auf die Website; der Bau bricht ab, wenn eines dabei wäre.
- Die Seite sagt offen, was fehlt: keine Physik, kein Claude – das gibt es in Knowlin auf dem PC.

### Behoben
- **start.bat startete Knowlin nicht mehr** (seit 0.38.27, Hinweis: „es startet nicht – die start batch“): Beim
  Umbenennen der Verknüpfungen fielen die Zeile, die Knowlin startet, und eine Sprungmarke weg – nach dem Doppelklick
  passierte nichts. Wieder da; ein Test prüft jetzt, dass start.bat Knowlin startet und jede Sprungmarke existiert.
- Odi ausprobieren: Das Modell lädt ohne Umweg über eine blob-Adresse (manche Umgebungen sperren die); klappt es nicht,
  steht der Grund auf der Seite.

### Nicht geprüft
- Auf echten Handys und Tablets (geprüft in Chromium mit Software-Grafik, hell/dunkel, 320–1280 px).

## 0.38.28 – 2026-11-08 – Handy und Tablet ohne Hürde

### Neu
- **Auf Handy oder Tablet** (T2, Hinweis: „viele werden das Ganze evtl. lieber auf Tablet oder Smartphone nutzen“): Die
  Startseite hat eine eigene Karte. Ein Klick schaltet die Handy-Fernbedienung ein und zeigt den QR-Code – vorher lag
  das tief unter System → Einstellungen.
- **Kurzer Code zum Eintippen:** Neben dem QR-Code gibt es einen sechsstelligen Code (ohne 0/O und 1/I). Wer die
  Adresse von Hand öffnet, tippt ihn auf der Koppelseite ein. Er gilt wie der QR-Code 5 Minuten, für ein Gerät, nach
  5 Fehlversuchen ist er verbraucht.
- **knowlin.local:** Solange die Fernbedienung an ist, sagt Knowlin seinen Namen im Heimnetz an (mDNS/Bonjour, Paket
  `zeroconf`). iPhone, iPad, Mac und Windows öffnen dann `knowlin.local:8766`, ohne die Zahlenadresse des PCs zu
  kennen. Der Name gilt nur, solange dieser PC ihn selbst ansagt; Koppeln bleibt Pflicht.

### Behoben
- Meldungen der Fernbedienung (z. B. „Kein Heimnetz gefunden“) wurden vom Status überschrieben und kamen nicht an.

### Nicht geprüft
- `knowlin.local` in einem echten Heimnetz mit iPhone, iPad und Android (der Testrechner hat kein WLAN; die Ansage
  selbst ist geprüft).

## 0.38.27 – 2026-11-08 – Policies aus Isaac Lab, überall Knowlin, Tablet, Gedächtnis mit Themen, Odi merkt sich Stöße

### Neu
- **Policies aus Isaac Lab übernehmen** (Hinweis: „3. fänd ich sehr wichtig“ – NVIDIA trainiert die Microduck in Isaac
  Lab): Lernen → Training nimmt die dort exportierte Gang-Policy (`exported/policy.onnx` der Aufgaben
  `IsaacContrib-Velocity-Flat/Rough-MicroDuck`) an. Knowlin prüft, ob sie zur Microduck passt (61 Beobachtungswerte,
  14 Gelenke in derselben Reihenfolge, gleiche Grundstellung, 50 Hz), und schickt sie durch einen Prüfstand in der Physik:
  stehen, vorwärts, seitwärts, drehen und ein Schubs – wie trainiert und mit der Glättung des echten Roboters, auf Wunsch
  gemessen an Pollens Gangart. Nur bestanden ist sie für die echte Ente frei; im Physik-Simulator lässt sie sich immer
  ausprobieren. Befehle bleiben in den trainierten Bereichen.
- **Was Knowlin über deine Welt weiß** (Hinweis: „beim Gedächtnis muss noch mehr der Nutzen der Funktion zum Tragen
  kommen … Kategorien (Positives, Negatives, Umfang des Wissens zu bestimmten Themen)?“): Über dem Netz stehen
  Themenkarten – Menschen (nur am PC), Orte, Dinge, Tätigkeiten – mit Umfang, Gefühlston als Zeichen und Wort („+ eher
  schön“, „− eher heikel“, „± gemischt“), wann zuletzt erlebt, wie sicher und womit verknüpft. Ein Klick öffnet das Thema
  im Netz. Unter dem Netz steht in Worten, was Punkte, Linien und Leuchten bedeuten.
- **Odi merkt sich, wo er angestoßen ist** (Odi O1): Ganz ohne Tiefe (Odi ohne Kamera, echte Open Duck) merkt sie sich
  Stellen, an denen sie festsaß, anstieß, gegen etwas fiel oder einen Ruck von vorn bekam (nicht von der Hand), zwei
  Minuten lang, setzt weiter zurück und läuft beim nächsten Anlauf daran vorbei. Im Test: nach einem Sturz am Couchtisch
  kommt sie beim zweiten Anlauf ans Ziel (ohne Merken bleibt sie hängen).
- **Website: Impressum und Datenschutz** als eigene Seiten, zweisprachig, aus der Fußzeile verlinkt. Name und
  Anschrift stehen nie im Repository – sie kommen beim Bauen aus einer Repo-Variablen; fehlen sie, veröffentlicht die
  Website nicht.

### Geändert
- **Überall Knowlin** (Hinweise: „Gibt es einen richtigen Launcher?“, „manchmal steht auch noch duckpilot“): Die
  Verknüpfungen heißen „Knowlin“ (Startseite, mit dem Knowlin-Zeichen) und „Knowlin - Microduck“ (direkt zur Ente);
  alte Verknüpfungen („duckpilot“, „Reachy Mini“, „Open Duck Mini“, der Autostart) benennt Knowlin beim Start einmal um
  und zieht Symbol, Ziel und Arbeitsordner auf den aktuellen Stand nach – nur die eigenen, und nicht aus einem Stand unter
  „Zweige“. Die installierbare Web-App heißt Knowlin. Das Python-Paket heißt weiter `duckpilot`.
- **Tablet** (Hinweis: „viele werden das evtl. lieber auf Tablet oder Smartphone nutzen“): Mit dem Finger sind Knöpfe,
  Reiter, Auswahlfelder und Häkchen mindestens 44 px hoch, Tastatur-Hinweise fallen weg. Die Abnahme prüft Tablet hochkant
  (820 px) und quer (1180 px).
- **Urheberangabe:** „The Knowlin Authors“ in LICENSE, NOTICE, README und App; Website „© 2026 Knowlin“.

### Behoben
- **Abstände** (Hinweis: „du solltest doch Abstände/Design prüfen“): Der Hinweis unter „Weitere Enten tanzen mit“ klebt
  nicht mehr an der Zahlenreihe, gewählt und ausgegraut ist neutral statt halb leuchtend, die Vorschläge auf der
  Startseite haben am Handy Luft. Die Abstandsprüfung schaut jetzt auch auf Zahlenreihen und Hinweise und auf Tanzen und Team.

### Nicht geprüft
- Eine echte Policy aus Isaac Lab (es gibt keine veröffentlichten; der Testrechner kann sie nicht trainieren). Geprüft
  sind der Vertrag (Beobachtung, Gelenke, Ausgabe) gegen den Quelltext von Isaac Lab, das Abweisen falscher Dateien und
  ein Prüfstand, der eine nutzlose Policy ehrlich durchfallen lässt.
- Umbenennen und Nachziehen der Verknüpfungen unter Windows (der Testrechner hat kein Windows).
- Anstoßen merken an der echten Open Duck.
- Tablet an einem echten Gerät (geprüft mit Finger-Emulation im Browser).

## 0.38.26 – 2026-11-08 – Aussehen mit Vorschaubildern, Hub-Tricks mit Standbild, Abstände geprüft

### Neu
- **Aussehen mit Vorschaubildern** (Hinweis: „bei Aussehen ist eine riesen freie Kachel – dann mach doch da bei der
  Farbauswahl Vorschaubilder rein“): Jede der vier Farben zeigt die eigene Microduck in dieser Farbe in ihrem Zimmer,
  gerendert im Browser aus dem Modell auf der Bühne (es wird kein Bild von Pollens Modell mitgeliefert).
- **Hub-Tricks mit Standbild** (Hinweise: „die Vorschaubilder bei Tricks laden oft erst spät oder gar nicht“, „da wo
  möglich wäre gut, wenn es Vorschau gäbe“): Jede Kachel zeigt ein Standbild aus dem Vorschauvideo, sobald sie in Sicht
  kommt – nur der Anfang wird geladen, höchstens drei gleichzeitig. Mit der Maus darüber läuft es stumm an, ein Klick
  spielt es in Schleife. Auch die Tricks unter „Vom Hub“ zeigen ihr Standbild statt eines Vorschau-Knopfs; ohne Video
  steht „keine Vorschau“ da.

### Behoben
- **Abstand der Gestalt-Schalter** (Hinweis: „hier scheint der Abstand nicht zu stimmen“): Die Eigenschaften der Gestalt
  sind jetzt Zeilen mit Luft und Trennlinie wie alle Schalterlisten.

### Geändert
- **Abnahme prüft Abstände** (Hinweis: „das sollte bei den Design-Tests auffallen. Und UX/UI“): Schalter, Knöpfe und
  Felder übereinander brauchen Luft (Schalter ≥ 10 px, sonst ≥ 6 px zwischen den Inhalten) – auf Persönlichkeit und
  Einstellungen, am PC und am Handy.

### Nicht geprüft
- Wie schnell die Hub-Standbilder über eine echte Internetleitung erscheinen (der Testrechner hat keinen Zugang zum Hub).

## 0.38.25 – 2026-11-07 – Erkundeter Bereich und Spur gut sichtbar, Trainingsfeld im Raster, Kamera nach Größe der Figur

### Geändert
- **Erkundeter Bereich gut sichtbar** (Hinweise: „der erkundete Bereich lässt sich auf dem Boden nicht mehr gut
  erkennen“, dann „das mit den Kästchen fand ich besser, halt nur zu wenig sichtbar“ und „im Bereich des Teppichs sieht
  es nicht gut aus“): die Kästchen bleiben, jetzt hell und kühl statt blassblau, Hindernisse kräftiger blau; über dem
  Teppich flimmern sie nicht mehr (lagen auf derselben Höhe).
- **Gelaufene Spur passt zum Rest** (Hinweise: „die gelaufene Spur sieht auch nicht so gut aus“, „kann leicht
  interpoliert werden – das Gezitter muss nicht so deutlich sein“): statt einer dünnen Linie von Dunkelgrau nach Blau ein
  weiches helles Band wie Kreide auf Holz, das nach hinten ausblendet und dem Mittel des Gangs folgt statt jedem
  Schrittwackeln.
- **Trainingsfeld im klaren Raster** (Hinweis: „noch etwas kreuz und quer – ggf. wie in der Keynote in einem klaren
  Raster bzw. mit festen Winkeln zueinander“): alle Übungsfelder parallel im Raster, Reihe für Reihe gegenläufig.
- **„Spielen“ immer auffindbar** (Frage: „Wo finde ich den Modus, Objekte zu platzieren?“): Der Knopf für den
  Kollisionsmodus (Dinge hinlegen, schubsen, werfen) steht jetzt auch ohne echte Physik in den Werkzeugen über der Bühne,
  etwas zurückgenommen; ein Klick schaltet die echte Physik ein, danach öffnet ein zweiter Klick den Modus.
- **Kamera nach Größe der Figur** (Hinweis: „Odi ist ja etwas größer und der Kopf ist schon Oberkante vom
  Kameraausschnitt“): Startperspektive, Blickpunkt beim Folgen und Anfahrt richten sich nach der Höhe der Figur – Odi
  steht ganz im Bild, die Kamera schaut auf die Mitte statt auf die Füße.
- **Kamera springt nicht mehr dicht heran** (Hinweis: „wenn quasi hinter der Kamera zu nah ein Objekt ist, zoomt er viel
  zu nah ran“): Steht ein Möbelstück nah an der Kamera statt nah an der Figur, wird es halb durchsichtig, statt dass die
  Kamera davor springt; näher als ein Mindestrahmen (doppelte Figurhöhe) fährt sie nie.

- **Odi umläuft Hindernisse mit der Kamera** (Hinweis: „Odis Kamera kann doch Objekte erkennen und die Laufbahn
  berechnen – sollte doch gehen“): Mit Kamera schätzt die Open Duck im Simulator die Abstände aus dem Kamerabild (bis
  etwa 1,5 m, mit Schätzfehler) und nutzt dieselbe Ausweich-Schicht wie die Microduck. Ohne Kamera bleibt es ehrlich aus.

### Behoben
- **Die Socke sieht aus wie eine Socke** (Hinweise: „die Socke sieht fehlerhaft aus“, „nicht mal wie eine Socke“): statt
  eines halben Rings ein flach liegender Stoff im typischen Umriss – Schaft, Ferse, Fuß mit runder Spitze –, Ferse und
  Spitze abgesetzt, zwei Ringel unter dem Bündchen. Im Schnabel saß Getragenes vorher nur mit seinem Mittelpunkt an der
  Spitze und steckte halb im Kopf; jetzt hängt die Socke am Bündchen senkrecht vor dem Schnabel und dreht sich mit,
  Klötzchen und Figuren sitzen knapp vor der Spitze.
- **Mit vollem Schnabel spricht sie nicht** (Frage: „Wenn sie was im Mund hat, kann sie den Mund nicht bewegen zum
  Reden, oder?“): Hält sie etwas, bleibt der Schnabel beim Sprechen und bei Gesten zu – sonst fiele es herunter. Nur das
  Ablegen öffnet ihn.
- **Anwählen bot an, was der Körper nicht kann** (Frage: „Manche Funktionen wie Aufheben kann sie doch gar nicht,
  oder?“): Das Menü am angeklickten Ding zeigt bei der Open Duck kein „Aufheben“ und kein „Bring es mir“ mehr (kein
  Schnabel), bei Reachy Mini keine Handlungen, die Beine brauchen. Auch per Chat sagt sie ehrlich, dass ihr der Schnabel
  fehlt.

### Nicht geprüft
- Wie Kästchen und Spur auf echter Grafik wirken (geprüft im Software-Renderer des Testrechners).
- Das Durchsichtigwerden von Möbeln hinter der Kamera im echten Browser (Logik per Test, Bild nur am Start geprüft).

## 0.38.24 – 2026-11-07 – Übungsfelder, Sicherungspunkte, Knowlin wacht auf, Not-Aus stromlos

### Neu
- **Team mit bis zu acht weiteren Enten und Vorschau** (Hinweis: „die Einstellung ist per Dropdown – das kann man schöner
  lösen; wieso auf 4 begrenzt? gern mit Vorschaufenster daneben“): Steuern → Team und Tanzen wählen die Zahl mit einer
  Zahlenreihe „keine/allein, 1 … 8“ statt einer Auswahlliste; daneben zeigt Team das Zimmer live wie im Cockpit. Vier neue
  Namen (Fiete, Nele, Jojo, Hugo) und eine größere Formation.
- **Sicherungspunkte – wie im Leben, nur mit Rückweg** (Wunsch aus dem Test: „bestimmte Sachen wieder resetten …
  Zwischenstände exportieren oder mehrere Versionen mit Historie – manchmal will man bestimmte Erlebnisse rückgängig
  machen“): Einstellungen → Sicherungspunkte. Knowlin legt jeden Tag einen Punkt an (die letzten 14 bleiben) und vor
  jedem Zurücksetzen, Wiederherstellen und „Alles vergessen“ noch einen. Eigene Punkte mit Namen anlegen, einzelne
  Bereiche zurücksetzen (Gedächtnis, Erfahrungsnetz, Charakter, Übungen, Tänze, Raum), einen früheren Stand ganz oder
  bereichsweise wiederherstellen, als ZIP exportieren und wieder importieren. Zurücksetzen, Wiederherstellen und Löschen
  brauchen einen zweiten Klick. Nur am PC; Personen, Schlüssel und Einstellungen sind nie in einem Sicherungspunkt.

### Geändert
- **Cockpit ohne Überdeckungen** (Hinweise: „das Entenbild als kleines Bild ist hinter dem Dialogfenster – ggf. reicht das
  kleine Fenster links unten; sowas sollte dir bei der UI-Prüfung auffallen“ und „bei Reachy steht Drehung, aber die Anzeige
  zeigt nichts“): Das kleine Entenblick-Bild entfällt (die Kachel unten links zeigt das Kamerabild); „Drehung“ gibt es nur
  noch bei Körpern mit Beinen, am Handy fällt die leere Anzeige bei Reachy ganz weg. Bei schmaler Bühne neben dem Gespräch
  rückt der Zustand unter die Werkzeuge, Meldungen nach oben rechts, der Tastenhinweis endet vor dem Gespräch; am Handy
  stehen die Werkzeuge über dem Zustand. Der Abnahmetest prüft das jetzt bei 1440, 1100 und 390 px für Quacki und Reachy.
- **Öffentliche Bilder ohne Pollens Reachy-Modell:** Cockpit- und Reachy-Bilder in README und Website neu (mit der
  einfachen Gestalt und dem neuen Cockpit); die README-Animation endet beim Einzug, bevor Reachy erscheint. Pollens
  Modelle (CC BY-NC-SA) bleiben damit aus allen öffentlichen Bildern heraus.
- **Website und README sagen, was Knowlin ist** (Hinweis: „wieso nur für PC – einfach virtuell, dann physisch in meiner
  realen Umgebung, nicht nur Tisch“): „ein lernender Begleiter … heute virtuell im Simulator, bald in deiner echten
  Umgebung“ statt „Begleiter für deinen PC … morgen auf deinem Schreibtisch“; Titel- und Vorschaubild neu.
- **Trainingsfeld: volle Modelle, echter Gang** (Funde aus dem Test: „bei Training sehen die 3D-Modelle fehlerhaft aus“,
  „dieses Gruppentraining ist von der Bewegung völlig unsinnig“): Die vereinfachten Netze hatten Löcher und die Originale
  liefen seitwärts, die Beine schwangen nur an der Hüfte, die Enten glitten und schrumpften nach einem Sturz. Jetzt wird
  die Figur – Original oder einfache Ente – einmal in acht Gangphasen und aus 16 Richtungen in voller Auflösung
  gezeichnet; im Feld steht jede Ente als ausgerichtetes Bild (für die Grafik so leicht wie 144 Rechtecke, der fertige
  Bogen bleibt im Browser). Die Gelenkwinkel kommen aus dem Simulator, Schrittfrequenz und Tempo passen zueinander, die
  Enten schauen in Laufrichtung. Stürze wie im echten Training: stolpern, zur Seite kippen, kurz liegen, dann wird die
  Welt zurückgesetzt und die Ente beginnt am Start neu. Die Sturzgefahr ist so gewählt, dass genau der genannte Anteil
  ohne Sturz ankommt. Die leichte Modellfassung vom Server (`/api/modell/feld/…`) ist dafür entfallen.
- **Jede Ente auf ihrem eigenen Übungsfeld – wie im Bild von NVIDIA zur Microduck** (Hinweise: „würde besser aussehen,
  wenn nicht alle in die gleiche Richtung laufen“, dazu der NVIDIA-Beitrag „Using AI agents to teach robots like
  Microduck to walk in simulation“, und „jede Ente beim Lernen soll ja auf ihrem Testfeld lernen – nun laufen sie
  einfach durcheinander“): In einer hellen Halle mit Rasterboden liegen 144 einzelne Übungsfelder mit Abstand, jedes
  quer im Raum gedreht – Holzrampe, Stufen, Podest, Wellen oder eine flache Matte. Jede Ente läuft auf ihrem Feld vom
  Start zum Ende, korrigiert, bevor sie seitlich herunterfiele, und beginnt am Ende (oder nach einem Sturz) einen neuen
  Durchgang; schwieriger Boden lässt öfter stürzen. Zum Auftakt steht die Kamera nah an einer Ente und zieht dann auf
  die Halle auf.
- **Tänze merken sich ihr Klangbild** (Takt für Takt Tonklassen und Bänder): Neuplanen im Editor nutzt es weiter, und
  eine bessere Erkennung von Strophe und Refrain kann später ohne erneutes Laden der Musik prüfen.
- **Trainingsfeld sagt, was es ist** (Frage aus dem Test: „lernen sie automatisch dort oder ist das nur eine
  Vorschau?“): ein Schild „Vorschau – hier lernt nichts“ bzw. „Gemessene Quote, Bewegung nachgestellt“ und darunter in
  einem Satz, wo gelernt wird (in einem gestarteten Lauf, am PC oder auf Kaggle) und dass gerade ein Lauf läuft.
- **Jeder Start beginnt mit einer Ente** (Hinweis: „beim Öffnen waren direkt mehrere Microducks – per Default starten
  wir erstmal mit einer“, dann „wieso startet die Microduck gleich wieder mit mehreren Enten?“): Weitere Enten bleiben
  bis zum Beenden oder zum Wechsel in einen anderen Körper, danach steht wieder nur die eigene im Zimmer. Die Zahl hing
  auch im Profil der Verkörperung und kam beim Körperwechsel zurück – jetzt nicht mehr, alte Profile werden beim Start
  bereinigt.
- **Weitere Enten in Pollens Farben** (Wunsch: „andere Enten können immer zufällig die Farben bekommen, meine möchte ich
  wählen können“): Jede weitere Ente bekommt zufällig Cream, Graphite, Lavender oder Sky – erst die Farben, die im Zimmer
  noch fehlen. Die eigene Ente behält die gewählte Farbe, das Trainingsfeld zeigt nur sie („da geht es ja um das
  Training meiner Ente“).
- **Beim Start lädt Knowlins Bewusstsein** (Wunsch: „statt meinem Splashscreen mach auch wie bei dem Übergang zu den
  Körpern, dass Knowlins Bewusstsein lädt“): Statt des Startbilds laufen Funken ins Knowlin-Zeichen, bis die
  Verbindung steht; dann leuchtet es auf – „Knowlin ist wach“ –, wie beim Einzug in einen Körper. Einmal je Sitzung,
  Klick oder Taste überspringt, ohne Bewegung bei „Bewegung reduzieren“.
- **Parcours: wo gelernt wird** (Frage aus dem Test: „Parcours schaffen geht nur auf meinem PC? Welcher Parcours?“):
  Der Hinweis unter Training sagt jetzt, dass es um deinen Parcours aus Lernen → Parcours geht, dass Knowlin ihn nur am
  PC in der Physik nachbaut und nach jeder Runde prüft, und dass Kaggle und Hugging Face Grundfähigkeiten lernen.
- **Hirnaktivität ohne Kreise:** Die Bahnen und Umrisslinien um das Netz sind weg, das weiche Licht dahinter bleibt.
- Website- und README-Bilder von Hirnaktivität und Charakterfeld neu (vorher noch im alten Grau und mit den Bahnen).
- **Öffentliche Fassung: Icons aus dem Knowlin-Zeichen.** App-Icon, Homescreen-Bild und `duckpilot.ico` zeigen das
  Knowlin-Zeichen auf der dunklen Kachel statt eines gezeichneten Entenkopfs; ein Startbild geht nicht mehr mit.
  Favicon und Homescreen-Bild der Website liegen jetzt ebenfalls auf der Kachel (auf hellen Browser-Tabs war das helle
  Zeichen kaum zu sehen).

### Behoben
- Einstellungen am Handy waren ein paar Pixel breiter als der Bildschirm (der Umschalter „Still, bis ich sie
  anspreche“ beim Not-Aus brach nicht um) – Umschalter brechen am Handy jetzt um (Rundgang durch alle Körper und Seiten).
- Ein Bildbogen hielt die Seite beim Zeichnen zeilenweise an – jetzt nach jedem Teilbild eine Pause, die Seite bleibt
  bedienbar. Bei frischer Installation entsteht kein leerer „täglicher“ Sicherungspunkt mehr.
- Gedächtnis: „Alles vergessen“ sagt, dass vorher gesichert wird; daneben führt „Sicherungspunkte“ direkt in die
  Einstellungen.

### Sicherheit
- **Not-Aus macht sofort stromlos** (Hinweis: „Not-Aus dachte ich legt den Roboter sofort lahm – bricht aber nur die
  aktuelle Aufgabe ab“, entschieden: sofort stromlos): Knopf, Esc, Controller und „Stopp“ brechen alles ab und schalten die
  Motoren aus – am echten Roboter mit Pollens `robot.relax`, beim Reachy Mini über den Daemon (Motoren „disabled“), im
  Simulator und in der Physik sackt die Ente zusammen, weitere Enten im Zimmer ebenso. Sperre und Aufstehen nur auf Befehl
  bleiben. Gelingt das Abschalten nicht, ist trotzdem alles angehalten und es kommt eine Meldung. Claudes Stopp-Werkzeug
  hält weiterhin nur an.
- Sicherungspunkte nur am PC (Handy und Fernzugang bekommen 403); importierte ZIPs werden streng geprüft (nur bekannte
  Dateinamen, gültiges JSON, Größen begrenzt, kein Pfad außerhalb). „Alles vergessen“ legt vorher einen Punkt an.

### Nicht geprüft
- Not-Aus am echten Roboter: `robot.relax` nur gegen den Test-robotd geprüft; der Reachy-Daemon nur gegen Pollens
  Schnittstelle gelesen. Erst auf dem Ständer ausprobieren.
- Wie schnell der Bildbogen auf echter Grafik entsteht (in der Software-Grafik des Testrechners zwei bis drei Minuten
  für das volle Microduck-Modell, bis dahin stehen die einfachen Enten im Feld).

## 0.38.23 – 2026-11-07 – Trainingsfeld wie in der Keynote, Tanz nach Strophe und Refrain

### Neu
- **Trainingsfeld wie in der Keynote** (Wunsch aus dem Test: „es soll so wie in der Keynote aussehen“ und „nutze bei
  Training auch Originalmodelle, wenn sie auch sonst aktiviert sind“): 144 Enten (am Handy 40) auf einem weiten Feld aus
  Übungskacheln – eben, Rampe, Stufen, Wellen, rauer Boden – mit leuchtendem Raster, das im Dunst verschwindet; die
  Kamera gleitet langsam darüber, wer fällt, kippt zur Seite und fängt neu an. Sind in der 3D-Ansicht die Originale
  gewählt, laufen dort die Originalmodelle (Microduck in ihrer Farbe, Odi als Open Duck): eine leichte Fassung mit
  7 000 bis 13 000 Dreiecken je Ente (statt bis zu 370 000), einmal auf dem PC gebaut (`/api/modell/feld/…`, Pollens Modell bleibt auf dem PC).
  Auf schwacher Grafik spart das Feld selbst: erst ohne Schattenkarte, dann weniger Enten und Bildpunkte.
- **Tanzen: Strophe, Refrain und Bridge aus dem Klang** (Hinweis: „die Erkennung der Passagen, Refrain etc., ist noch
  nicht perfekt“): Die Analyse im Browser liefert je Takt ein Klangbild (zwölf Tonklassen, sechs Frequenzbänder).
  Grenzen liegen dort, wo sich das Klangbild deutlich ändert (bevorzugt auf Phrasengrenzen), wiederholte Teile bekommen
  denselben Buchstaben, und der wiederholte, laute Teil ist der Refrain – auch wenn er einmal leiser ist. Einmalige
  Teile mittendrin heißen Bridge. Ohne Klangbild (ältere Tänze) bleibt die Einteilung nach Lautstärke.
- **Tanzeditor:** Die Schrittliste ist nach Teilen gegliedert („Refrain 2 · 0:56 · 8 Takte“), jeder Teil lässt sich
  umbenennen (sein Tanz wird dann neu geplant, die übrigen bleiben, wie man sie eingestellt hat), und „Wie der erste
  tanzen“ übernimmt den Tanz des ersten gleichnamigen Teils. Die Zeitleiste zählt gleiche Teile durch.
- **Farbe der Microduck auch unter Charakter → Persönlichkeit** (Frage aus dem Test: „wo sehe ich die neuen Farben?“) –
  bisher nur unter System → Einstellungen → 3D-Darstellung.

### Geändert
- **Knowlins Netz kleiner und wieder auf einer Scheibe** (Wunsch: „das Netz kann etwas kleiner sein“, „fand ich gut,
  dass es zuvor so eine Blase/Kreis war … nur auf einer Art Halo oder Bezugsfläche“): Der Plexus bleibt, liegt aber auf
  einer ruhigen, flachen Scheibe wie früher; etwa ein Fünftel kleiner – ausgewählt aus drei Vorschlägen.
- **Moves passen besser zum Song** (Hinweis: „die Moves passen noch nicht immer gut zum Song“): Jeder Refrain beginnt
  mit dem Höhepunkt (Einsatz), leise Phrasen in einem lauten Teil werden kleiner getanzt, Gesten folgen der Energie
  der Phrase, und langsame Stücke (unter 92 BPM) werden gewiegt statt geschritten.
- **Tempo und Eins genauer:** Das Tempo wird über das ganze Stück nachgemessen (Gerade durch die Schläge), die erste Eins
  aus den Einsätzen bestimmt – vorher lag ein Testsong um ein BPM daneben, nach einer Minute saßen die Takte falsch.
- **Startperspektive flacher** (Hinweis: „ziemlich steil von oben“, auch bei Odi): Der Einflug endet näher und etwa in
  Augenhöhe am Boden; die Figur ist groß im Bild.
- **Handerkennung bei Reachys Spielen ruhiger und schöner** (Hinweis: „wenn nur der Punkt ist, flimmert er zu sehr“):
  Handpunkte und Bewegungsschwerpunkt werden geglättet, kurz fehlende Erkennung blendet weich aus statt zu springen;
  mit Handerkennung Handfläche, Fingerknochen und leuchtende Fingerspitzen in voller Auflösung. Das Kamerabild wird
  weiterhin nie gezeigt.

### Behoben
- Hinweise zu Reachys und Odis Originalmodell in den Einstellungen waren im Microduck-Feld versteckt und erschienen nie.
- Gedächtnis → Hirnaktivität: Der Hinweis „Noch nichts erlebt …“ lag über den ersten Knoten – jetzt unten in der Bühne.
- Englische Oberfläche: Auf den Kacheln der Startseite blieben Charakter und Trickzahl („Ausgeglichen · 0 eigene
  Tricks“) deutsch, wenn die Übersetzung erst nach dem Zeichnen ankam.
- README-Animation, Titelbild und Vorschaubild zeigten noch die Oberfläche vor 0.38.19 – neu aufgenommen.

### Nicht geprüft
- Bildrate des Trainingsfelds mit Originalmodellen auf echten Grafikkarten (im Testbrowser ohne Grafikkarte spart es
  bis zur letzten Stufe); Erkennung der Teile an echten Songs (geprüft mit einem gebauten Teststück).

## 0.38.22 – 2026-11-07 – Plexus und glatte Flächen (Hauptstand)

### Geändert
- **Knowlins Netz auf der Startseite neu** (Hinweis aus dem Test: „an vielen Stellen so komisch verbogen und nach innen
  hohl – wie ein Obstnetz“): ein räumlicher Plexus wie auf der Website – rund dreihundert Neuronen füllen die ganze
  Gehirnform (innen dichter), gerade, feine Synapsen, keine Hülle mehr. Zustände (ruhe, hört, denkt, spricht), Impulse
  und Kettenreaktionen bleiben; Linien nach Tiefe gebündelt, höchstens 30 Bilder je Sekunde.
- **Glatte Flächen an den Originalmodellen** (Hinweis: „teilweise immer noch zerknitterte Teile oder Flächen“): Die
  Normalen werden jetzt nach dem Winkel an der Ecke gemittelt statt nach Fläche – die langen, dünnen Dreiecke aus dem
  CAD-Export zogen sonst Schlieren über Rundungen. Gilt für Microduck, Reachy und Open Duck; gebaute Modelle werden
  einmal neu gebacken.

### Nicht geprüft
- Bildrate des neuen Netzes auf schwachen Laptops und Handys (im Testbrowser 60 Bilder je Sekunde, gezeichnet 30).

## 0.38.21 – 2026-11-07 – Hin, herum und schöner

### Neu
- **„Lauf um den Tisch“:** einmal ringsum mit Abstand (abgerundetes Rechteck um Kästen, Kreis um Hocker und Pflanze),
  Kopf zum Ziel, links oder rechts herum. Steht etwas an der Wand, kehrt sie um und läuft die freien Seiten ab – und
  sagt das ehrlich. Neues Werkzeug `umrunden`, auch ohne Claude („lauf um den Tisch“, „umrunde die Kiste“, „walk
  around the table“).
- **Odi schießt** im Simulator – nachgestellt; die echte Open Duck hat dafür noch keine gelernte Bewegung.
- **Abgeben neben Dingen und Möbeln:** „bring sie zum Ball“ legt neben den Ball (vorher „Keinen Ort namens 'Ball'“).
- **Suchen wie ein Lebewesen:** Wer etwas nicht sieht, schaut sich einmal ganz um, geht zur letzten Sichtung oder ein
  Stück in eine neue Richtung und schaut wieder – an bis zu drei Stellen, dann ehrlich „nicht gefunden“.

### Geändert
- **Originalmodelle wieder in voller Auflösung** (Hinweis aus dem Test: „sehen teilweise nicht gut aus“): Die
  Vereinfachung aus 0.38.18 machte gedruckte Halterungen zerknittert. Sichtbare Teile bleiben jetzt ganz, nur
  Innenliegendes (Lager, Platinen) wird vereinfacht. Leicht bleibt es durch das Zusammenfassen je Gelenk (Zeichenaufrufe
  wie in 0.38.18). Schon gebaute Modelle werden einmal neu gebacken.
- **Spiele mit Reachy veredelt:** Karten mit Bildmarke und ruhiger Auswahl (Spielanzeigen erst im Spiel); im Spiel die
  Bühne zuerst – Reachy groß, die Karte schwebt als Glas darüber, der Zustand („Grünes Licht – los!“) groß.

### Behoben
- **„Lauf zum Ball“** lief ohne Claude nur 40 cm geradeaus – jetzt läuft sie hin (Ball, Socke, Möbel, andere Enten).
- **Entenblick verdeckt** bei Odi und den einfachen Gestalten: Die Kamera saß im Kopf, jetzt vor den Augen.

## 0.38.20 – 2026-11-07 – Klarer Not-Aus

### Geändert
- **Not-Aus neu gestaltet** (Hinweis aus dem Test: „gefällt mir nicht – schon gar nicht mit der gestrichelten Linie“):
  ein klarer roter Knopf mit weißem Stopp-Zeichen statt Pilztaster auf gelb gestricheltem Schild. Läuft etwas, zeigt
  ein durchgehender roter Ring, der leise atmet, dass Esc jetzt etwas anhält (bei „Bewegung reduzieren“ ruhig). Gleich
  am PC, in der Leiste am Handy und im Handy-Controller; Name für Screenreader und Sprachsteuerung unverändert.

### Behoben
- Am Handy schien der Inhalt durch die feste Leiste unten durch (seit 0.38.19) – sie ist jetzt dichtes Glas.

## 0.38.19 – 2026-11-06 – Bühne zuerst

### Neu
- **Microduck in vier Farben wie bei Pollen:** Cream, Graphite, Lavender, Sky (Einstellungen → System → 3D-Darstellung).
  Gilt für das Originalmodell (nur die hellen Schalen, das Orange bleibt) und die einfache Gestalt; sofort zu sehen.
- **Pollens Apps für Reachy Mini aus Knowlin:** Unter Steuern → Tricks die auf dem Reachy installierten Apps starten und
  anhalten, weitere aus Pollens Katalog (Hugging Face, beliebteste zuerst) installieren – mit zweitem Klick, nur am PC.
  Knowlin nutzt dafür Pollens Daemon (`/api/apps/…`); die App läuft beim Reachy. Im Simulator steht ehrlich, dass es sie
  dort nicht gibt, mit Link zu Pollens Katalog.
- **Trainingsfeld:** Unter Lernen → Training üben 50 kleine Enten gleichzeitig auf Rampen, Stufen und Wellen – wer
  fällt, fängt neu an. Ohne Lauf eine Lernkurve im Zeitraffer; mit einem Lauf bleiben so viele Enten stehen, wie er
  Durchgänge ohne Sturz geschafft hat (gemessen, die Bewegungen sind nachgestellt). Vier Zeichenaufrufe, gleich wie viele
  Enten; rechnet nur, solange es zu sehen ist; bei „Bewegung reduzieren“ ein stehendes Bild.

### Geändert
- **Hochwertigere Oberfläche („Bühne zuerst“):** Im Cockpit füllt die 3D-Bühne die ganze Fläche, das Gespräch schwebt
  als Glasfläche rechts darüber (ab 1056 px; schmaler wie bisher untereinander). Wärmeres Graphit, Glas mit Unschärfe
  für Kopfleiste, Leisten und Hinweise, Display-Schrift (Bricolage Grotesque) für Gruß, Titel und Haltung, Karten mit
  leichtem Licht von oben, Reiter als Pillen mit Punkt, Startseite mit großem Gruß, Eingabe als Pille und vollständigen
  Kacheltexten, Hinweise („Toasts“) als Glaspille mit Farbpunkt.

### Sicherheit
- Solange eine von Pollens Apps läuft, schickt Knowlin keine eigenen Ziele an den Reachy; **der Not-Aus hält auch die
  App an**. Starten geht nicht während der 120-s-Sperre und nicht mitten in einer eigenen Bewegung. Installiert wird nur,
  was in Pollens Katalog steht, mit genau dessen Angaben – nie eine beliebige Adresse.

### Nicht geprüft
- Pollens Apps an einem echten Reachy Mini (geprüft gegen einen nachgebauten Daemon nach reachy-mini 1.13).
- Bildrate des Trainingsfelds und der Glasflächen auf echten Grafikkarten und Handys.

## 0.38.18 – 2026-11-06 – Schöner in 3D, leichter im Bild

### Neu
- **Wohnlicher Raum im Simulator:** Dielenboden mit leisem 10-cm-Raster, Wände mit Fußleiste wie im Puppenhaus (die Wand
  zur Kamera tritt zurück und lässt Klicks durch), Teppich unter dem Couchtisch, ruhiger Verlauf als Hintergrund statt
  Schwarz, Möbel mit gebrochenen Kanten, wärmeres Licht.
- **Neue einfache Gestalten** (eigene Entwürfe, ohne CAD-Daten – zu sehen ohne Netz, vor dem ersten Laden und in der
  öffentlichen Fassung): Microduck als kleiner Roboter mit Visier, zwei Kameraaugen und orangem Unterkiefer statt
  Comic-Ente; Open Duck Mini mit Trapezkopf und Antennen; Reachy Mini mit Eiform und Brillenaugen.

### Geändert
- **Originalmodelle leichter:** Beim Bauen auf dem PC werden die CAD-Teile nach Fläche vereinfacht (neue Abhängigkeit
  `fast-simplification`) und je Gelenk und Material zusammengefasst – Microduck ein Drittel, Reachy Mini gut die Hälfte
  weniger Dreiecke, Reachy 97 statt 173 Zeichenaufrufe. Aus der Nähe sieht man keinen Unterschied. Ein schon gebautes
  Modell wird einmal neu gebacken (auch ohne Netz, die Quelldateien liegen schon da).
- Umgebungsverdeckung mit 12/8 statt 16/16 Proben – kaum sichtbar, weniger Rechenzeit.
- **Oberfläche:** Text wird komprimiert ausgeliefert (gzip), Hover-Farben nur noch mit Maus (am Handy bleibt nichts
  hängen), Knöpfe geben beim Drücken leicht nach (nicht bei „Bewegung reduzieren“).
- Licht und 3D-Bausteine als eigene Module (`licht3d.js`, `raum3d.js`, `formen3d.js`, `ente3d.js`).

### Behoben
- Hintergrund der 3D-Ansicht war schwarz: Das Tonwert-Mapping (Khronos Neutral) drückt sehr dunkle Töne fast auf null –
  jetzt zurückgerechnet.
- Englische Hirnaktivität zeigte „imprint: a little livelier (viel Spiel und Lob)“ – der Grund ist jetzt übersetzt.
- Not-Aus: Der sichtbare Text „Not-Aus Esc“ steht jetzt auch im Namen für Screenreader und Sprachsteuerung (WCAG 2.5.3).

### Sicherheit
- Reachy Mini: Körper und Kopf bleiben beim Vereinfachen in voller Auflösung – aus ihnen rechnet die Prüfung, ob der Kopf
  in den Körper taucht, bevor ein Befehl an den echten Roboter geht.

### Nicht geprüft
- Bildrate auf echten Grafikkarten und Handys (gemessen sind Dreiecke und Zeichenaufrufe; der Testbrowser rechnet ohne
  Grafikkarte). Linux x86_64 mit Python 3.14: noch ohne Rad für fast-simplification – dort volle Auflösung.

---

## 0.38.17 – 2026-11-06 – Schlank und modular

### Geändert
- **Oberfläche in Modulen:** `app.js` setzt nur noch zusammen (98 → 67 KB). Einstellungen, Kopfleiste, Tricks-Seite,
  Gedächtnis, Ereignisse, Sensor-Kachel und Touch-Steuerkreuz sind eigene Module; gemeinsame Helfer in `ui.js`.
  Toter Code entfernt. Neue Leitplanken: JS-Module höchstens 64 KB, `app.js` höchstens 72 KB, kein Modul ohne Verwender.
- **Laufzeit und Bewegung aufgeteilt:** Gespräch als eigener Teil der Laufzeit (`runtime_gespraech.py`), Choreografie
  und Gesten-Kataloge als `motion/choreografie.py` (bestehende Importe aus `behaviors` gelten weiter).
- GitHub-Dateien liegen in `tools/github/` statt im Export-Skript.
- **PyPI vorbereitet:** Das Paket heißt dort `knowlin` (`pip install knowlin`, Befehle `knowlin` und `duckpilot`); ein
  Workflow baut und prüft es bei jedem Release und lädt es per Trusted Publishing hoch – ohne API-Schlüssel, erst nach
  der Freischaltung. Das Python-Paket heißt weiter `duckpilot`.

### Sicherheit
- GitHub: Dependabot (Python-Pakete und Actions, wöchentlich), CodeQL für Python und JavaScript (sobald das Repo
  öffentlich ist) und eine Prüfung der Abhängigkeiten auf bekannte Lücken (pip-audit) bei jedem Push. Stand heute:
  keine bekannten Lücken.

### Nicht geprüft
- Nichts Neues am echten Roboter; das Verhalten der Oberfläche ist unverändert (Abnahmetest wie in 0.38.16).

---

## 0.38.16 – 2026-11-06 – Bereit für den echten Roboter, ehrlich vor dem Launch

### Neu
- **Verbindungstest vor dem ersten Start am echten Roboter:** In „Erste Schritte“ und in den Einstellungen prüft
  „Verbindung prüfen“ die Adresse der Microduck (robotd) bzw. von Pollens Reachy-Mini-Daemon – erreichbar, Version,
  Akku. Der Test liest nur, es bewegt sich nichts. Jeder Befund steht mit Zeichen und Text da. Open Duck Mini am echten
  Roboter: ehrlich „noch nicht unterstützt“.
- Englische Bilder in der englischen README.
- Befehl `knowlin` zusätzlich zu `duckpilot` (nach `pip install`).

### Geändert
- Barrierefreiheit ehrlich beschrieben: Ziel ist WCAG 2.2 AA, automatisch mit axe-core geprüft; ein Test mit echten
  Screenreadern steht noch aus.
- `start.sh` (macOS/Linux) arbeitet wie `start.bat`: prüft Python ≥ 3.11, installiert Pakete nach, wenn sich
  `requirements.txt` ändert, und sagt klar, wenn unter Debian/Ubuntu `python3-venv` fehlt. Es legt keine `.env` mehr an –
  den Schlüssel trägt man in der App ein (Tresor des Betriebssystems).
- `--help` erklärt Knowlin und die Optionen `--port`/`--host`.
- Verhaltensregeln: privater Meldeweg über GitHub (Titel „Conduct:“) oder conduct@knowlin.de.
- Handbuch: Datenordner auch für macOS und Linux; README nennt beide Verknüpfungen und den Linux-Hinweis zur
  Spracherkennung.

### Behoben
- Englische Oberfläche: Was die Figur gerade tut („looking around“), die Herkunft der Antwort („simple commands“), die
  Bedienhinweise bei Reachy und die Namen im Erfahrungsnetz (Tageszeiten, Gefühle, Erlebnisse) blieben deutsch.

### Sicherheit
- Der Verbindungstest ist nur am PC erreichbar, liest nur und nimmt für Reachy nur http(s)-Adressen.
- Der Export-Scan sucht private Namen aus einer eigenen Liste, die selbst nie veröffentlicht wird.

### Nicht geprüft
- Verbindungstest gegen eine echte Microduck und einen echten Reachy Mini (geprüft gegen den Test-Roboter und einen
  nachgebauten Daemon).

---

## 0.38.15 – 2026-11-06 – Feinschliff vor dem Launch

### Neu
- **Einfache Open Duck:** Die einfache 3D-Darstellung passt jetzt auch zu Odi – grau, höher, mit Antennen – statt der
  einfachen Microduck.
- README (englisch) mit kurzer Animation der Startseite; bei „Bewegung reduzieren“ ein Standbild.

### Geändert
- Die Konsole und `--version` sagen „Knowlin“ (das Python-Paket heißt weiter duckpilot).
- Das Knowlin-Zeichen aus dem eigenen Entwurf ist jetzt auch das öffentliche Zeichen.

### Behoben
- Riss die Verbindung zum Server genau beim Senden ab, ging die Nachricht still verloren. Jetzt schickt der Browser sie
  nach dem Wiederverbinden erneut, der Server nimmt sie nur einmal.

---

## 0.38.14 – 2026-11-06 – Eigenleben, Spiele mit Handerkennung, Inhalte je Körper geprüft

### Neu
- **Von sich aus beschäftigen:** Ohne Befehle sucht sich die Verkörperung nach einer Weile selbst etwas – passend zu
  Charakter und Körper. Ruhige Charaktere warten länger und setzen sich auch mal hin, lebhafte erkunden, tanzen oder
  zeigen Tricks; Reachy schaut sich um, spielt mit den Antennen oder wendet sich Dingen zu. Am echten Roboter nur
  Gesten, nie Ortsbewegung. Einstellbar unter Persönlichkeit → Verhalten: aus, ab und zu (Standard), oft.
- **Kamera-Spiele ausgebaut:** Handerkennung (MediaPipe) – lädt erst auf Klick (≈ 14 MB, geprüft per Prüfsumme) und
  rechnet nur im Browser. Neue Spiele „Mach mir nach“ (Richtungen nachzeigen, ab „mittel“ als Merkspiel) und „Schere,
  Stein, Papier“; „Rotes Licht, grünes Licht“ mit Stufen, Punkten und Bestzeit. Ohne Roboter gleitet beim Spielstart
  Reachy im Simulator neben die Spielkarte.
- **Stimme entwerfen je Körper:** eigene Vorlagen, Beispieltexte und Probesätze für Reachy (z. B. „Freundlicher
  Tischroboter“) und die Open Duck; bei Reachy keine Enten-Vorlagen.
- **Charakter je Verkörperung frei:** Knowlins Grundcharakter wirkt nur noch auf Knowlin. Die Verkörperungen stehen
  als Punkte im Knowlin-Feld und lassen sich einzeln ziehen (auch mit den Pfeiltasten).
- **Einstellungen zeigen nur, was gebraucht wird:** Felder für ein anderes oder eigenes Sprachmodell, Handy-Kopplung,
  Weckwort und Stopp-Zeit nach einem Sturz erscheinen erst, wenn die Wahl sie braucht.
- **Kamera-Kachel bei Reachy und Open Duck:** das kleine Bild aus Sicht des Körpers („Reachys Blick“).

### Geändert
- **Knowlin statt duckpilot** überall, wo man es liest (Fenster, Beenden, Fernbedienung, Handy-Seite, „Über“).
  duckpilot bleibt nur Codename des Enten-Moduls, Python-Paket und Ordnername.
- **Texte je Körper:** 3D-Darstellung „Einfaches Modell“ bei Reachy, Ansicht-Menü nur mit dem, was der Körper hat,
  bei Reachy keine Enten-Wörter mehr (Schnabel, Laufen, „Ente nicht verbunden“ …).
- Handbuch erklärt die Takte: die Microduck regelt mit 50 Hz, die MotionEngine gibt 20-mal pro Sekunde Befehle.
- **Dauerhafte Inhaltsprüfung:** `tests/test_inhalte.py` und im Abnahmetest der Schritt „Inhalte je Körper“ (alle drei
  Körper und Knowlin, deutsch und englisch).

### Behoben
- Bei Reachy und Open Duck standen oben unter „Was gesteuert wird“ alle Optionen; „Einfacher Simulator“ machte aus der
  Open Duck die Microduck.
- Bei Reachy war der gewählte Blick (Ansicht) nicht als aktiv erkennbar.
- Im Knowlin-Modus stand „Beenden“ nicht mehr rechts.
- Die Beschwerden nach dem Not-Aus rechneten fest mit zwei Minuten statt mit der eingestellten Sperre.
- Bei einem frischen Start als Reachy oder Open Duck konnte die Verkörperung „Quacki“ heißen und auf „Ente“ hören.
- Englisch: halb übersetzte Sätze in Stimme, Charakter-Vergleich und Leerlauf-Liste; Odis Gruß kam deutsch.

### Sicherheit
- Eigenständiges Verhalten nie während der Not-Aus-Sperre, bei „still“, in Ruhe, hochgehoben, gefallen, im Gespräch,
  Spiel oder bei Handsteuerung; jeder Kontakt unterbricht es. Am echten Roboter lehnt die Bewegungsschicht von selbst
  gestartete Ortsbewegung zusätzlich ab.
- Handerkennung: nur feste, geprüfte Dateien aus dem Datenordner, nur am PC ausgeliefert, kein Bild verlässt den Browser.

### Nicht geprüft
- Handerkennung mit einer echten Hand (die Test-Webcam zeigt keine), vor allem „Schere“.
- Die Prüfsumme des Handerkennungs-Modells ist gegen eine unveränderte Kopie gerechnet, nicht direkt gegen Googles
  Server; passt sie nicht, lädt Knowlin nichts und sagt das.
- Kopf- und Antennenbewegungen der neuen Spiele und das Eigenleben am echten Reachy.

## 0.38.13 – 2026-11-05 – Reachy tanzt, wippt mit und spielt; Open Duck aufgeräumt; Not-Aus neu

### Neu
- **Reachy tanzt eigen:** Im Tanzmodus tanzt Reachy Mini mit Kopf, Antennen und Körperdrehung im Takt – 13 eigene
  Tanzbewegungen nach Energie gestuft (nicken, wiegen, kreisen, hoch und runter, Antennen-Schlag, bei Refrain und viel
  Energie dreht sich der ganze Körper). Keine Posen, keine Entenlaute; auch „Mit KI choreografieren“ und „Nach Gehör“
  nutzen nur Reachys Bewegungen.
- **Mitwippen** (wie Pollens App „Reachy Mini Radio“): ein Stück vom PC oder ein Webradio im Browser abspielen, Reachy
  wippt ruhig im erkannten Takt mit. Lässt ein Sender das Mitlesen nicht zu, wippt er ehrlich im ruhigen Grundtakt.
  Gespeichert werden nur die letzten fünf Radio-Adressen.
- **Begrüßung beim Aufwecken** (wie „Reachy Mini Greetings“): Antennen hoch, Kopf heben, nicken – und ein kurzer Gruß
  mit Tageszeit und deinem Namen. Abschaltbar unter Persönlichkeit → Verhalten.
- **Kamera-Spiele mit Reachy** (Steuern → Spiele): „Rotes Licht, grünes Licht“ und „Hand folgen“. Die Webcam läuft nur
  während eines Spiels und wird nur im Browser ausgewertet – 64 × 48 graue Punkte, heraus kommen nur „wie viel“ und
  „wo“ sich etwas bewegt. Kein Bild verlässt den PC, keine Gesichts- oder Personenerkennung.
- **Verhalten nach dem Not-Aus einstellbar** (Einstellungen → Not-Aus): Sperre 2 (Standard), 5 oder 10 Minuten – nie
  kürzer – und danach „weiter wie vorher“ oder „still, bis ich sie anspreche“.
- **Open Duck Mini:** in Einstellungen → Körper wählbar; die Antennen schlagen im Tanz im Takt mit.

### Geändert
- **Not-Aus in neuem Design:** der rote Pilz sitzt rund in einem dunklen Gehäuse mit schmalem Warnring statt auf der
  gelben Platte; läuft etwas, leuchtet der Ring.
- „Auf GitHub melden“ und die Vorlagen zeigen auf `knowlin-ai/knowlin`; Maintainer `@knowlin-dev`.
- Abnahmetest mit Fake-Webcam: neue Schritte für Spiele und Open Duck (47 Prüfungen).

### Behoben
- **Open Duck sagte zu, was sie nicht kann:** Auf „schieß den Ball“ antwortete Odi „ja klar, mach ich!“. Gelernte
  Bewegungen, die der Körper nicht hat, lehnt das Werkzeug jetzt vorher ehrlich ab.
- Open Duck: „Echter Roboter“ war wählbar, obwohl es für sie noch keine Anbindung gibt – jetzt ausgeblendet mit Hinweis.

### Nicht geprüft
- Am echten Reachy: Tanz, Mitwippen, Begrüßung (kann in Pollens Aufwachbewegung fallen), Kamera-Spiele.
- Webradio: hängt davon ab, ob der Sender das Mitlesen erlaubt (CORS).

## 0.38.12 – 2026-11-05 – Synapsen räumlich und ruhig, sachlichere Worte

### Geändert
- **Synapsen bei Knowlin wirken räumlich:** Knoten als Kugeln mit Lichtpunkt, hinten im Nebel, etwas stärkere
  Perspektive und zwei feine Bahnen um die Mitte, die sich mitdrehen.
- **Aktivität leuchtet ruhig statt zu blitzen:** Die angezeigte Aktivität gleitet zum gemeldeten Wert (bei Knowlin
  langsam), frisch gestärkte Verbindungen schwellen an und ab, Impulse sind seltener, langsamer und leiser.
- **Wie Knowlin über die Roboter spricht:** sachlich – „Wenn es um Bewegung geht – laufen, tanzen, etwas zeigen –, nutze
  ich einen meiner Roboter“ statt „Körper bewohnen“ oder „alles Körperliche“ (klang zweideutig).

## 0.38.11 – 2026-11-05 – Ruhe für Reachy, Charakterfeld und lebendige Synapsen bei Knowlin

### Neu
- **Grundcharakter als Feld mit Quadranten:** Bei Knowlin (Einstellungen → Knowlin) dasselbe Feld wie in der
  Verkörperung – ruhig ↔ lebhaft, seriös ↔ verspielt, eigene Namen von „Besonnen“ bis „Übermütig“, ohne Goofy-Bereich.
  Die Verkörperungen stehen als kleine Punkte mit ihrer Ausprägung darum herum und wandern mit. Per Maus, Finger und
  Pfeiltasten bedienbar.
- **Synapsen bei Knowlin leben:** Unter Wissen → Gedächtnis dreht sich das Erfahrungsnetz langsam von selbst, die Knoten
  schweben, Impulse laufen die Verknüpfungen entlang und lassen Knoten kurz aufglühen, dahinter eine weiche, wabernde
  Hülle wie die Mind-Form der Startseite. In der Verkörperung bleibt es sachlich; „Bewegung reduzieren“ hält es an.
- **Abnahmetest:** neue Schritte für das Charakterfeld (auch per Tastatur) und die Synapsen bei Knowlin.

### Behoben
- **Reachy machte im Leerlauf Entenlaute** (5.11.): Im Leerlauf liefen noch die Enten-Gesten des Charakters
  (gähnen, Gefieder putzen …) mit Pollens Entenaufnahmen. Reachy zeigt jetzt eigene ruhige Regungen mit Antennen, und
  auf Reachy spielt keine Choreografie mehr Töne oder Aufnahmen – egal, woher sie kommt.
- **Entengeschnatter bei Knowlin** (5.11.): Solange du bei Knowlin bist, spielt die Oberfläche keine Laute des
  Körpers im Hintergrund und liest seine Meldungen nicht mit Entenstimme vor (Erinnerungen aus dem Alltag schon).

### Nicht geprüft
- Am echten Reachy: der Leerlauf mit den eigenen Regungen.

## 0.38.10 – 2026-11-05 – Verkörperungen: ein Charakter, eigene Stimme, Herkunft, Übergänge

### Neu
- **Abnahmetest im Browser** (`tools/abnahme.py`): spielt die Testschritte eines Zweigs automatisch durch – Startseite,
  Gespräch mit Knowlin, Vorschlag und Wechsel in den Körper, Namen, Ausprägung und Gestalt, Grundcharakter, Knowlins
  Stimme, Herkunft, Übergang zurück, Reachy, Englisch, Not-Aus, Barrierefreiheit (axe) – und schreibt einen Bericht mit
  Bildschirmfotos.
- **Codenamen nach Bauart:** duckpilot für die laufenden Enten (Microduck, Open Duck Mini), deskpilot für
  stationäre Roboter auf dem Tisch (Reachy Mini).
- **Charakter übergeordnet bei Knowlin:** Den Grundcharakter (ruhig–lebhaft, seriös–verspielt, Gefühle zeigen) wählst
  du unter Einstellungen → Knowlin; er gilt für Knowlin selbst und alle Verkörperungen. Knowlin ist anfangs seriös. Jede
  Verkörperung ist eine leichte **Ausprägung** darum herum (Charakter → Persönlichkeit zeigt z. B. „Quacki ist etwas
  lebhafter und etwas verspielter als Knowlin“) und hat **Eigenschaften ihrer Gestalt** zum An- und Abwählen –
  Microduck: Schnabelklappern, Watscheln, neugieriges Umsehen, anschmiegsam; Reachy: Antennenspiel, Kopf neigen beim
  Zuhören, trockener Humor, aufmerksamer Beobachter; Odi: tollpatschig, Bastlerstolz, Antennenspiel. Sie wirken über
  das Gehirn.
- **Knowlins Stimme wählbar und entwerfbar** – direkt von Knowlin aus, ohne Körper (Einstellungen → Knowlins Stimme):
  Piper-Stimme wählen oder mit Qwen3-TTS eine eigene entwerfen (Vorlage „ruhig, tief, ein wenig geheimnisvoll,
  seriös“), probehören.
- **Herkunft:** Erfahrungsnetz und Gedächtnis merken sich, wo etwas gelernt wurde – Knowlin ohne Körper oder welche
  Verkörperung, im Simulator oder echt. Die Hirnaktivität hat einen Filter nach Herkunft, im Knotendetail steht z. B.
  „Gelernt: 3× Quacki (Simulator), 1× Knowlin (ohne Körper)“, die wache Verkörperung ist leicht markiert. Im Gedächtnis
  steht „gemerkt von …“. Ältere Einträge haben keine Herkunft.
- **Übergang zurück zu Knowlin** („Body to Mind“, etwa 1 s): die Verkörperung tritt zurück, der Strahl läuft nach
  oben, Knowlin leuchtet auf; bei „Bewegung reduzieren“ nur kurz.
- **Gespräch im Körper nach Verkörperung getrennt:** Jede Antwort trägt den Namen der Verkörperung, beim Wechsel steht
  eine Trennzeile („Jetzt in Reachy · Reachy Mini · Simulator“). Der Verlauf läuft weiter.
- **Reachy steht auf dem Couchtisch** (bis er Räder hat) und lässt sich umstellen: Klick auf ein Möbelstück →
  „Reachy hierhin stellen“ (Tisch, Hocker, Kiste, Regal … – wenn sein Fuß passt und die Höhe stimmt), „Reachy auf den
  Boden stellen“ beim Möbel, auf dem er steht. Gast-Enten sehen ihn dort, stoßen aber nicht mehr an ihn.
- **Eigene Gefühlsgesten für Reachy** mit Antennen statt der Enten-Gesten (ohne Gackern und Schütteln); ab und zu
  nimmt er stattdessen eine passende Aufnahme von Pollen.
### Geändert
- Systemmeldungen im Gespräch tragen „Knowlin“ statt „duckpilot“.
- **„Verkörperungen“ statt „Figuren“** in Oberfläche, Doku und Hinweisen (englisch „embodiments“).
- Knowlin ist eine „intelligente, **selbstlernende** Lebensform“.
- Startseite: Der Vorschlag „Tanz für mich“ ist raus – Körperliches gehört zu den Verkörperungen. Stattdessen „Was
  kannst du?“.
- Knowlins Stimme wird nicht mehr künstlich abgesenkt (klang wie ein zu langsam abgespieltes Band); fehlt die gewählte
  Stimme, spricht er mit der Browser-Stimme in normaler Lage.
- „Gefühle zeigen“ gehört jetzt zum Grundcharakter und gilt für alle.
- Der Link „Wie sie klingt: Stimme“ in den Einstellungen weckt im Kopf keine Verkörperung mehr, sondern führt zu
  Knowlins Stimme.

### Behoben
- **Weitere Enten bei der Microduck:** Standard sind wieder keine weiteren Enten; alte Profile mit „2 weiteren“ (aus der
  Zeit vor 0.38.3) werden einmalig auf 0 gesetzt – im Team lassen sie sich wieder dazuholen. Gäste haben jetzt dasselbe
  Modell wie die Hauptente, auch wenn das Originalmodell erst später lädt.
- **Reachys Kopf tauchte bei Bewegungen in den eigenen Körper** (5.11., z. B. „freuen“): Jede Kopflage wird
  jetzt im Simulator und vor dem Senden an den echten Reachy auf Erreichbarkeit geprüft – alle sechs Stangen, Abstand zur
  Körperschale – und sonst Richtung Grundstellung zurückgenommen. Das 3D-Modell behält die letzte gültige Lage.
### Nicht geprüft
- Die Eigenschaften der Gestalt wirken über die KI (Claude oder ein anderes Modell) – ohne KI-Modell ändern sie nichts.
- Reachys Kopfprüfung am echten Gerät; ob einzelne Aufnahmen von Pollen durch die Begrenzung leicht gedämpft werden.
  Ohne Pollens Modell (öffentliche Fassung ohne Nachladen) gilt eine bewusst enge Ersatzgrenze.

## 0.38.9 – 2026-11-05 – Knowlin selbst: seriös, eigene Stimme, erst fragen, dann in den Körper

### Neu
- **Erst fragen, dann in den Körper:** Bei physischen Wünschen („tanz“, „lauf vor“, „zeig mir einen Purzelbaum“)
  nennt Knowlin den Körper, den er dafür braucht, und fragt, ob er ihn nutzen soll. Auf „ja“ (oder den Knopf
  „Quacki nutzen“) geht er in die Figur und gibt ihr den Wunsch weiter; auf „nein“ bleibt er ohne Körper. Der Vorschlag
  gilt drei Minuten. Gewählt wird ein Körper, der es wirklich kann – Purzelbaum nur die Microduck, Laufen nicht Reachy.
- **Eigene, tiefe Stimme für Knowlin:** ruhig und etwas tiefer als die Figuren, ohne Entenfilter und nie albern
  (Piper „Thorsten“, wenn geladen; sonst die geladene Piper-Stimme oder die Browser-Stimme, jeweils tief gestellt).
- **Namen:** Knowlins Name und deiner lassen sich im Gespräch vergeben („Ich nenne dich Nova“, „Ich heiße …“) oder
  unter Einstellungen → Knowlin setzen. Bis dahin grüßt er mit „Hallo Mensch“. Dein Name bleibt auf diesem PC.

### Geändert
- **Knowlin ist seriöser:** ruhig, klar, ein wenig geheimnisvoll – „eine intelligente, lernende Lebensform“. Erst im
  Körper wird er zu einer Figur mit eigenem Charakter.
- Vorschläge unter dem Feld: „Wer bist du?“, „Tanz für mich“, „Was weißt du über mich?“.

### Sicherheit
- In einen Körper geht Knowlin nur nach deiner Zustimmung oder auf ausdrücklichen Wunsch – und nur am PC.

### Nicht geprüft
- Die tiefe Piper-Stimme ist mit Tests geprüft (Länge, Tonhöhe), aber nicht am PC angehört.

## 0.38.8 – 2026-11-05 – Startseite als Schnelleinstieg: Hallo Mensch

### Neu
- **Mit Knowlin selbst sprechen:** Oben auf der Startseite steht „Hallo Mensch“, darunter das Dialogfeld zum Schreiben
  oder Sprechen (Halten und sprechen). Es antwortet Knowlin, der gemeinsame Kopf aller Figuren – ruhig, ohne
  Entenlaute, mit eigenem Gesprächsverlauf und demselben KI-Modell wie die Figuren. Ohne KI-Modell versteht er einfache
  Sätze (Gruß, „Wie heißt du?“, „Was kannst du?“, Timer und Uhrzeit).
- **Der Kopf als wabernde Form** links neben dem Dialog: weiche Hüllen mit Synapsen wie im Knowlin-Zeichen. Sie zeigt,
  ob der Kopf ruht, zuhört, nachdenkt oder spricht – nur, solange sie zu sehen ist; mit „Bewegung reduzieren“ steht
  sie still.
- **Figur wecken aus dem Gespräch:** „Weck Quacki“, „Reachy wecken“ oder ein Klick auf den Vorschlag – derselbe
  Übergang wie auf den Kacheln. Wer etwas Körperliches möchte („tanz“), bekommt die passende Figur angeboten; Reachy
  wird zum Laufen nicht vorgeschlagen.
- Vorschläge unter dem Feld zum Loslegen: „Was kannst du?“, „Quacki wecken“, „Was weißt du über mich?“.

### Geändert
- Startseite neu geordnet: oben das Gespräch mit dem Kopf, dann die Figuren, dann, was alle teilen, dann Werkzeuge.
  Der bisherige Kopfbereich mit Zeichen und Satz entfällt – das Zeichen steht weiter oben links.
- Auf Knowlins Seiten geht Gesprochenes an den Kopf, im Körper an die Figur.

### Sicherheit
- „Stopp“ wirkt auch im Gespräch mit dem Kopf sofort auf jeden Körper.
- Der Kopf hat keine Körperwerkzeuge; Tricks und Orte merkt sich nur eine Figur. Eine Figur wecken geht nur am PC.
- Was der Kopf sich merkt, folgt denselben Regeln wie bei den Figuren: nichts über Dritte, nie Passwörter, Bank-,
  Ausweis- oder Gesundheitsdaten.

### Nicht geprüft
- Der Kopf mit eigenem Modell (Ollama) und anderen Anbietern ist nur mit Tests geprüft, nicht mit echten Modellen.
- Die Stimme des Kopfes ist vorerst die Stimme der zuletzt wachen Figur, ohne Entenfilter.

## 0.38.7 – 2026-11-05 – Vor dem Release: Prüfungen, Anwendersicht, GitHub

### Neu
- **Doku für GitHub:** README neu und kurz, auf Deutsch und Englisch: Knowlin, Körper, Schnellstart, Sicherheit,
  Rechtliches. Die Einzelheiten stehen jetzt im Handbuch `docs/handbuch.md`. Release-Notes `docs/releases/v0.38.7.md`.
  CONTRIBUTING (eine Regel für das, was ein Körper kann), SECURITY (Knowlets, Hugging Face), Vorlagen für Fehler und
  Berichte mit allen Körpern sowie NOTICE mit Reachy Mini und Open Duck Mini v2 sind ergänzt.
- **Automatische Prüfung (CI)** der öffentlichen Fassung mit Python 3.11, 3.12 und 3.13.
- Nach dem Namen fragen („Wie heißt du?“) geht jetzt auch ohne Claude.

### Geändert
- **Erste Schritte** sprechen von Knowlin statt von der Ente und führen zum Schluss auf die Startseite. Die
  Hinweise zu anderen KI-Modellen zeigen auf Einstellungen → KI-Modell.
- Auf der Startseite heißt die zuletzt geweckte Figur „zuletzt wach“ statt „aktiv“ – im Kopf ist ja niemand wach.
- Fenstertitel im Kopf: „Umgebung – Knowlin“ statt mit dem Namen einer Figur.
- Die Eigenschaften der Figuren auf der Startseite (z. B. „Ausgeglichen“) erscheinen auch auf Englisch übersetzt.
- Porträts, die es in der öffentlichen Fassung nicht gibt, werden gar nicht erst geladen.

### Behoben
- **Frische Installation ohne Physik:** Die Seiten zum Kollisionsmodus und zur Stoßreihe liefen ohne MuJoCo in einen
  Importfehler. MuJoCo wird jetzt erst geladen, wenn wirklich gerechnet wird.
- Die Entwickler-Pakete (`pip install -e ".[dev]"`) brachten `httpx` nicht mit, ohne das die Tests nicht starten.
  Tests, die Pillow oder Pollens Modell brauchen, überspringen sich jetzt ohne diese.
- Die öffentliche `.gitignore` schloss alle Modelle aus, auch die mitgelieferte Open Duck. Jetzt bleiben nur Pollens
  Modelle und die daraus gerenderten Porträts außen vor.
- Eine Auswahlliste („Modell“ bei anderen KI-Anbietern) hatte keine Beschriftung für Screenreader.
- Bei Reachy begann eine Antwort nach entferntem „Quak“ klein („mach ich!“).

### Sicherheit
- Der Geheimnis-Scan der öffentlichen Fassung fand einen echten Windows-Benutzernamen in einem Test – ersetzt.
- Bekannte Sicherheitslücken in den Abhängigkeiten (pip-audit): keine.

### Nicht geprüft
- Windows-Start (`start.bat`) nur unverändert übernommen, nicht auf Windows getestet.
- Meldungen des Servers (z. B. Ablehnungen von Werkzeugen) sind teils nur deutsch.

---

## 0.38.6 – 2026-11-05 – Gesamtprüfung: jeder Körper zeigt nur, was er kann

### Neu
- **Gesamtprüfung** von Oberfläche, Funktionen, rotem Faden, Aufbau und Technik, mit einer Übersicht, welche Funktion im
  Kopf und in welchem Körper da ist (Prüfbericht in Notion).
- **Stimme gehört der Figur**: Die Stimmseite sagt, wessen Stimme sie gerade einstellt („Stimme von Reachy (Reachy Mini) –
  gilt nur für diese Figur“), und zeigt bei entworfenen Stimmen, welche Figur sie nutzt. Bei Reachy heißt es „Stimme
  entwerfen“ statt „Entenstimme entwerfen“.

### Geändert
- **Menüs nach Kontext**:
  - Auf Knowlins Seiten (im Kopf) gibt es keine Aktionen für einen Körper. Die Umgebung zeigt nur, was bekannt ist, und
    in den Einstellungen fehlen „Körper“ und „3D-Darstellung“. Das Gedächtnis heißt dort „Was Knowlin weiß“, ohne
    Stimmung und Tricks einer Figur.
  - Im Körper zeigt die Oberfläche nur, was er kann. Reachy Mini und Open Duck haben keinen Bereich „Umgebung“
    (Erkunden braucht Beine und Tiefensensor) und keine Pollen-Erweiterungen der Microduck. Ohne Beine fehlen
    „Kopf ruhig“, „Nach Sturz aufstehen“ und die Gelenk- und Geschwindigkeitsanzeigen, ohne Tiefensensor
    „Vor Hindernissen bremsen“ und „Ausweichen“. Die Leerlauf-Gesten und der Klang gibt es nur bei Enten.
- **Das Gehirn bietet nur an, was der Körper kann** – nach derselben Regel wie die Oberfläche. Der Open Duck bietet es
  kein Apportieren, Erkunden, Schießen, Team, Hub-Tricks und Training mehr an; ihre Bewegungsliste ist nur „hinsetzen“.
  Reachy bekommt keine Entenlaute und kein „Kopf ruhig“.
- Namen wie bei den Herstellern: Microduck und Reachy Mini (Pollen Robotics und Hugging Face), Open Duck Mini v2
  (Antoine Pirrone). Der Name der Figur (z. B. Quacki) ist ihr Spitzname.

### Behoben
- **Reachy hatte die Einstellungen der Microduck-Figur geerbt**: Wer vor 0.38.3 schon auf Reachy Mini gestellt hatte, bei dem landeten
  Name, Entenlaute, weitere Enten im Zimmer und Entenfilter bei Reachy statt bei der Microduck. Deshalb liefen bei Reachy
  Microducks herum und er „jaulte“ zwischendurch. Beim ersten Start richtet Knowlin das einmal: Die Microduck-Figur
  bekommt ihre Werte zurück, Reachy seine Startwerte.
- Entenlaute und Entenfilter gibt es jetzt hart nur bei Enten, egal, was in den Einstellungen steht.

### Sicherheit
- Ein Trick aus einem Knowlet bleibt unter Probe, auch wenn er nachbearbeitet wird (die Sperre ging beim Neuspeichern
  verloren).
- Nur am PC: Stimmen entwerfen, übernehmen, löschen und Sprachmodelle laden sowie den Fehlerbericht erstellen und
  ansehen.

### Nicht geprüft
- Wie sich die Reparatur der Figuren an deinem echten Datenordner verhält, ist nur mit nachgebauten Fällen geprüft
  (Reachy aktiv mit den Werten der Ente, Microduck aktiv mit geerbtem Reachy-Profil).

---

## 0.38.5 – 2026-11-05 – Knowlets: Figuren, Tricks und Tänze teilen

### Neu
- **Knowlets** (`.knowlet`): Charakter einer Figur (Name, Persönlichkeit, Sprechweise, Piper-Stimme, Klang), ihre
  selbst gebauten Tricks und Tänze als Paket speichern und laden – unter Wissen → Knowlets (auch im Körper unter
  Charakter) und über die neue Kachel „Knowlets“ auf der Startseite. Ein Knowlet ist eine ZIP-Datei mit Steckbrief
  (Name, Beschreibung, Urheber, Lizenz, für welchen Körper) und reinen Daten.
- **Laden mit Vorschau**: Erst zeigt Knowlin, was drin ist; übernommen wird nur, was ausgewählt ist. Gibt es einen
  Trick oder Tanz schon, kommt er als Kopie („Winken 2“). Ein Knowlet für einen anderen Körper landet bei dessen Figur,
  ohne den Körper zu wechseln.
- **Sicherung**: Bevor ein Knowlet den Charakter einer Figur ersetzt, legt Knowlin die bisherige Figur als Knowlet ab
  (Wissen → Knowlets → Sicherungen) – so lässt sich alles zurückholen.
- **Hugging Face**: geteilte Knowlets suchen und laden (Dataset-Repos mit Tag `knowlet`, ohne Konto); eigene hochladen
  mit dem Hugging-Face-Schlüssel aus dem Tresor – nur mit zweitem Klick, privat, solange nicht „öffentlich“ gewählt ist.

### Behoben
- Open Duck Mini: In die beiden runden Öffnungen vorn am Kopf sitzen jetzt dunkle Gläser – man schaut nicht mehr in die
  Hülle hinein. Das Porträt ist neu gerendert.

### Sicherheit
- Ein Knowlet enthält nur Daten: nie Code, nie Gedächtnis über Personen, Orte, Karte oder Sichtungen, nie Gespräche,
  Schlüssel, Geräteeinstellungen, entworfene Stimmen oder Musikstücke. Beim Laden gilt eine Positivliste (unbekannte
  Dateien, Pfade außerhalb des Pakets und zu große Pakete werden abgelehnt), Tricks gehen durch dieselbe Formprüfung wie
  eigene, fremde Texte werden gekürzt und nie ausgeführt.
- Tricks aus Knowlets laufen am echten Roboter erst, nachdem sie einmal im Simulator liefen.
- Knowlets gehen nur am PC.

### Nicht geprüft
- Hochladen auf Hugging Face nur gegen eine nachgebaute Schnittstelle; Suche und Laden nur mit nachgebauten Antworten
  (im Chat kein Zugang zum Hub).

---

## 0.38.4 – 2026-11-05 – Open Duck Mini, Kopf zuerst, Raumklang

### Neu
- **Open Duck Mini** als drittes Modul: der offene Selbstbau-Vorgänger der Microduck (Antoine Pirrone und Community,
  Apache-2.0) im Simulator, mit dem offenen 3D-Modell (fester Stand des Repos, mitgeliefert mit Lizenzhinweis). Die
  Gelenkwinkel des Simulators werden auf die Open Duck umgerechnet; die Antennen zeigen Gefühle und wackeln beim
  Sprechen. Eigene Figur **Odi** (Ente, größer und tiefer als Quacki, eigener Weckruf „odi“, eigener Gruß), eigene
  Sprechweise im Gehirn, Verknüpfung „Open Duck Mini“ (`--modul open_duck_mini`).
- **Kopf zuerst**: Nach dem Start ist Knowlin nur im Kopf – die Leiste zeigt Knowlin, Alltag, Umgebung, Wissen und
  Einstellungen; keine Figur steht auf oder spricht, niemand läuft im Zimmer herum. Erst beim Wecken einer Figur
  (Kachel, Verknüpfung, Lesezeichen, Handy-Controller) betritt Knowlin den Körper; dann kommen Steuern, Charakter und
  System dazu, die Figur steht auf und grüßt in ihrer Art.
- **Raumklang**: Laute anderer Roboter im Simulator kommen von dort, wo sie stehen (Richtung und Entfernung, im
  Kopfhörer räumlich) und unterbrechen die eigene Figur nicht mehr.
- **Porträts** der Figuren auf der Startseite, aus den 3D-Modellen gerendert (gleicher Ausschnitt für alle).

### Geändert
- **Startseite ruhiger**: alle Kacheln gleich gebaut – Porträt, Roboter-Modell als Titel, Stand oben rechts, darunter
  Spitzname und Charakter der Figur, ein kurzer Text, Knöpfe unten auf gleicher Höhe („Reachy wecken“, „Verknüpfung“).
  Jede Figur wird mit demselben Übergang geweckt.
- **Körpermodus nach einer Logik für alle Körper**: Was ein Körper nicht hat (Beine, Tiefensensor, Schnabel,
  Antennen, Kamera), blendet die Oberfläche aus; Pollens gelernte Bewegungen prüft jede Fähigkeit am Körper.
- **Figuren, die keine Ente sind, quaken nicht** – auch nicht in festen Sätzen der einfachen Befehle; beim Sprechen
  ins Mikrofon gibt es bei Reachy kein Entengeräusch mehr, und die Entenstimme-Einstellungen sind bei ihm ausgeblendet.

### Sicherheit
- Unverändert: Not-Aus mit 120 s Sperre gilt für jeden Körper; aufstehen nach dem Start erst beim Betreten des Körpers
  und nie innerhalb der Sperre.

### Nicht geprüft
- Open Duck Mini nur im einfachen Simulator; Gangart angenähert, keine Physik mit ihrer eigenen Policy. Kein echter
  Roboter.
- Raumklang nur in Chromium geprüft.

---

## 0.38.3 – 2026-11-05 – Figuren: Knowlin teilt das Wissen, jede Figur hat ihren Charakter

### Neu
- **Figuren je Körper** (Bild: „Menschen sind verschieden in Sprache, Aussehen, Verhalten, können aber
  gleiches Wissen und Umgebung haben“): Quacki ist die Microduck, Reachy ist Reachy Mini – jede Figur hat ihren
  eigenen Namen, ihr Aussehen, ihre Stimme, Sprechweise, Persönlichkeit, Stimmung, ihr Verhalten im Leerlauf, ihre
  Tricks und wer im Simulator mit ihr im Zimmer ist. **Gemeinsam** haben sie das Wissen über die Umwelt (Personen,
  Dinge, Abläufe, Situationen), die Umgebung, den Alltag und die Erlebnisse. Bisherige Einstellungen gehören Quacki.
- **Reachy ist keine Ente**: eigene Sprechweise (ruhig, neugierig, trockener Humor), keine Entenlaute und keine
  Entenstimme, eigener Weckruf („reachy“), eigene Art von verspielt; im Leerlauf ab und zu eine ruhige Bewegung aus
  Pollens Bibliothek (leise). Er weiß, wer die anderen Figuren sind, und spricht von ihnen wie von Mitbewohnern.
- **Knowlin-Startseite neu**: oben „Was alle Figuren teilen“ (Wissen über die Umwelt, Umgebung, Alltag,
  Einstellungen – mit Zahlen), darunter die Figuren mit Name, Bild, Art und Charakter; „Zu Reachy wechseln“.
- **Knowlin-Zeichen**: die Synapsen-Grafik aus Splash-Entwurf – in der Leiste, auf der Startseite und im
  Übergang (die öffentliche Fassung zeichnet ein eigenes, schlichtes Zeichen).
- **Knowlin-Splash** beim Start (Entwurf „knowlin-splash-v3“) und **Mind to Body**: beim Wechsel zu einer
  Figur weckt Knowlin sie in ihrem Körper (animierter Übergang, ohne Bewegung bei „Bewegungen reduzieren“) – auch beim
  Direktstart über eine Verknüpfung. Neue Verknüpfung „Reachy“ (`--modul reachy_mini`).
- **Körpermodus passt sich an** (gleicher Aufbau, eigene Befehle – angelehnt an Pollens und die Community-Apps für
  Reachy Mini): eigene Schnellbefehle für Reachy (Aufwachen, Schlafen, Hallo sagen, Umschauen, „Ein Gefühl von Pollen“,
  Tanzen), eigene Beispiele im Gespräch, „Reachys Blick“ statt „Entenblick“, Hinweise ohne Laufen; Doppelklick auf
  den Boden dreht Reachy hin, statt ihn laufen zu lassen.
- **Gäste im Zimmer**: Standardmäßig ist nur die eigene Art im Simulator; bei Reachy lassen sich Enten als Besuch
  zuschalten (Einstellungen → Körper).

### Geändert
- Kopfzeile „Knowlin › Quacki · Microduck“ – ein Klick auf „Knowlin“ führt zur Startseite; das Leistenzeichen heißt
  „Knowlin“. Die Startseite „Geist“ aus 0.38.2 ist in der neuen Startseite aufgegangen.
- Open Duck Mini rückt auf 0.38.4, Knowlets auf 0.38.5.

### Nicht geprüft
- Pollens Bewegungsdatensätze weiter nur mit nachgebauten Aufnahmen; am echten Reachy weiter ungetestet.

---

## 0.38.2 – 2026-11-05 – Reachy Mini Teil 2: Geist und Körper, Pollens Originalmodell, Ausdruck

### Neu
- **Geist und Körper** (Bild: „als ob ich meinem Geist einen Körper zuweise“): Die Knowlin-Startseite zeigt
  jetzt den Geist selbst – Name, Persönlichkeit, Stimmung, Gedächtnis, womit er denkt. Darunter stehen die Körper als
  Plätze: „Quacki diesen Körper geben“, der jetzige ist markiert („Quacki ist hier“), geplante stehen ausgegraut da.
  Lab und „Eigenes Modul“ stehen getrennt unter „Außerdem in Knowlin“. Das Zuweisen ist ein kurzer Übergang
  („Quacki zieht in Reachy Mini ein …“), danach ist man im Körper.
- **Rückweg zum Geist**: Oben steht „Quacki › Reachy Mini“ (bzw. „› Microduck“); ein Klick auf den Namen führt zum
  Geist, der Körper bleibt dabei verbunden. Das Zeichen oben in der Leiste heißt jetzt „Geist“.
- **Pollens Originalmodell von Reachy Mini** in der 3D-Ansicht – wie bei der Microduck nachgeladen statt mitgeliefert
  (Pollens Hardware-Dateien stehen unter CC BY-NC-SA): aus Pollens installiertem Paket `reachy_mini` oder von GitHub
  (fester Stand v1.13.0, jede Datei mit Prüfsumme), auf diesem PC gebacken. Der Kopf sitzt auf der Stewart-Plattform:
  die sechs Motorwinkel rechnet die Ansicht selbst, gegen Pollens eigene Kinematik geprüft (gleich auf 0,001 rad),
  die sechs Stangen folgen. Bis das Modell da ist, steht die gezeichnete Figur.
- **Pollens Emotionen und Tänze** (Datensätze `reachy-mini-emotions-library` und `reachy-mini-dances-library`, wie in
  Pollens eigenen Apps): unter Steuern → Tricks zum Antippen, fürs Gehirn als Werkzeug `pollen_bewegung`. Im
  Simulator spielt duckpilot Kopf, Antennen und Körperdrehung selbst ab und den Ton im Browser, am echten Reachy
  spielt Pollens Daemon sie mit Ton aus dem Lautsprecher. Geladen aus Pollens Hugging-Face-Zwischenspeicher, wenn
  Pollens SDK schon lief, sonst von Hugging Face (fester Stand des Datensatzes).
- **Ausdruck im Gespräch**: Reachy atmet im Leerlauf, neigt beim Zuhören den Kopf und stellt die Antennen auf, schaut
  beim Nachdenken schräg nach oben und lässt die Antennen spielen, und beim Sprechen wippt der Kopf mit der Lautstärke
  (wie Pollens „speech tapper“). Simulator und echter Reachy gleich.

### Geändert
- Echter Reachy Mini: Die Kopfdrehung geht jetzt wie bei Pollen in der Welt (Körperdrehung + Kopf), damit der Kopf
  beim Drehen mitkommt; vorher blieb er stehen und Pollens Grenze von 65° bremste die Drehung.
- Im Reachy-Modus verschwinden die Microduck-Emotionen und Skill-Pakete unter Tricks; dafür stehen dort Pollens
  Reachy-Bewegungen.
- Open Duck Mini rückt auf 0.38.3, Knowlets auf 0.38.4.

### Sicherheit
- Pollens Dateien kommen nur von festen Ständen (GitHub mit Prüfsummen, Hugging Face mit fester Revision), Dateinamen
  werden geprüft; Nachladen geht nur am PC. Not-Aus bricht eine laufende Aufnahme ab (Simulator) bzw. hält sie über
  Pollens `/api/move/stop` an (echter Reachy).

### Nicht geprüft
- Pollens Bewegungsdatensätze auf Hugging Face waren beim Bauen nicht erreichbar: das Format ist nach Pollens SDK
  (`recorded_move.py`) gebaut und mit nachgebauten Aufnahmen getestet. Erster echter Abruf passiert auf deinem PC.
- Am echten Reachy Mini weiter ungetestet; Blick zur Person über die Webcam folgt dem Kopfbefehl wie bei der Ente.

---

## 0.38.1 – 2026-11-04 – Suite Knowlin Teil 2: Reachy Mini im Simulator

### Neu
- **Reachy Mini als zweites Modul**: Pollens Desktop-Roboter bekommt denselben Kopf wie die Ente – Gedächtnis,
  Persönlichkeit, Stimme und Sicherheitsregeln bleiben, nur der Körper wechselt. Die Kachel auf der Knowlin-Startseite
  ist jetzt „fertig (im Simulator)“; „Öffnen“ schaltet den Körper um, die duckpilot-Kachel schaltet zurück. Oben im
  Körper-Menü gibt es „Reachy Mini im Simulator“, unter Einstellungen → Körper „Welcher Roboter“.
- **Simulator-Körper** (`backends/reachy.py`): Reachy Mini steht fest im Wohnzimmer und dreht nur den Körper (bis
  ±160°). Kopf auf der Stewart-Plattform mit Pollens Grenzen (nicken und neigen ±38°, drehen ±60° zum Körper,
  2 cm hoch/runter), zwei Antennen, die beim Sprechen mitwackeln. Schlafen klappt die Antennen ein und senkt den Kopf.
- **3D-Figur** (`reachy3d.js`): fester Fuß, drehbarer Körper, sechs Stangen zum Kopf, Gesicht mit zwei Kameraaugen,
  Antennen. Der Entenblick schaut durch Reachys Kamera.
- **Werkzeug „antennen“** für das Gehirn; das Gehirn weiß, welcher Körper dranhängt („KEINE Beine“) und bietet
  Laufen, Apportieren, Schuss, Erkunden, Folg mir und Hub-Tricks gar nicht erst an. Fähigkeiten lehnen sauber mit
  „fehlt: beine“ ab.
- **Pollens Daemon** (`ReachyMiniDaemon`): Anbindung an den echten Reachy Mini über Pollens REST-Schnittstelle
  (Zustand, Kopf-/Antennen-/Körperziel, Aufwachen, Schlafen). Adresse unter Einstellungen → Körper.

### Geändert
- Ohne Beine verschwinden Lernen, Team, Vom Hub, Laser, Folg mir, Spielen, Controller, Erkunden und „Ball schießen“
  aus der Oberfläche, statt anklickbar zu sein und dann abzulehnen.
- Der Zustand trägt jetzt `koerper`, `antennen` und `kopf_lage` (für die 3D-Figur).

### Sicherheit
- Die Daemon-Adresse darf nur ins eigene Netz zeigen (localhost, `*.local`, private Adressen). Körper und Adresse
  lassen sich nur am PC ändern, nicht vom Handy. Not-Aus hält bei Reachy Mini die Körperdrehung sofort an der
  gemessenen Stelle an (die Motoren bleiben an, sonst fiele der Kopf); die 120-s-Sperre gilt unverändert.

### Nicht geprüft
- Am echten Reachy Mini – nur gegen Pollens `reachy-mini-daemon --mockup-sim` 1.13 und einen nachgebauten Daemon im
  Test. Kamera, Mikrofon und Lautsprecher des echten Reachy Mini sind noch nicht angebunden.
- Pollens MuJoCo-Modell von Reachy Mini ist nicht eingebaut; der Simulator zeichnet ihn selbst.

---

## 0.38.0 – 2026-11-04 – Suite Knowlin Teil 1: Startseite, neue Gliederung, Fähigkeiten

### Neu
- **Knowlin-Startseite**: duckpilot ist jetzt das erste Modul der Suite Knowlin („ein Kopf, viele Körper“). Beim
  Start erscheint die Startseite mit einer Kachel je Modul. duckpilot ist die eine fertige Kachel und zeigt, woran es
  gerade hängt (Simulator, Physik, echter Roboter). Reachy Mini (0.38.1), Open Duck Mini (0.38.2), Knowlin Lab, Ohne
  Körper (0.44) und Eigenes Modul stehen schon da, ehrlich als „geplant“ und nicht anklickbar. Darunter die
  Kern-Bereiche, die für jeden Körper gelten: Charakter, Gedächtnis, Umgebung, Alltag, Einstellungen. Das Knowlin-Zeichen
  oben in der Leiste führt jederzeit zurück; der Fenstertitel heißt jetzt „… · duckpilot – Knowlin“.
- **Direktstart je Modul**: Die Verknüpfung „Knowlin“ öffnet die Startseite, „duckpilot“ startet direkt in
  duckpilot (`--modul duckpilot`). `start.bat` legt beide an; die gewohnte duckpilot-Verknüpfung wird beim nächsten
  Start so umgestellt, dass sie wie bisher direkt in duckpilot öffnet. Auf der Kachel gibt es „Verknüpfung anlegen“
  (Desktop und Startmenü; ans Taskleiste-Anheften erlaubt Windows nur von Hand). Läuft Knowlin schon, öffnet eine
  Verknüpfung nur ein weiteres Fenster desselben Knowlin – ein Kern, ein Gedächtnis.
- **Fähigkeiten-Schnittstelle** (`motion/faehigkeit.py`): Apportieren, gezielter Schuss, Purzelbaum und Erkunden
  bauen auf derselben Grundklasse auf – Vorbedingung, Ausführen, Ergebnisprüfung, Plan B, einheitlicher Bericht
  (erfolg, fehlschlag, abgelehnt, abgebrochen). Jede Fähigkeit sagt, was der Körper dafür braucht (Beine, Schnabel,
  Tiefensensor); fehlt etwas, lehnt sie sauber ab. Grundlage für Reachy Mini.
- **Körper-Eigenschaften**: Jeder Körper sagt, was er kann (Simulator: zurücksetzen; Physik: Policies; echter Roboter:
  Tiefensensor nur mit tofd) – statt einzelner Sonderprüfungen im Code.

### Geändert
- **Neue Gliederung** (Entscheidungen zum Befund vom 4.11.):
  - **Umgebung** ist ein eigener Bereich in der Leiste: erkundeter Bereich, Ansicht von oben, Bring mir, Wo zuletzt
    gesehen. Später kommen hier Karten, Sperrzonen und der Wohnungs-Import dazu. Bisher: Steuern → Tricks.
  - **Steuern → Team** statt „Mehrere Enten“ auf der Tricks-Seite.
  - **Stimmung und Hirnaktivität** stehen jetzt oben unter Charakter → Gedächtnis („Innenleben“), auch wenn das
    Gedächtnis aus ist.
  - **KI-Modell** (Claude, eigenes Modell, anderes Modell) liegt jetzt unter Einstellungen, weil es für jeden Körper
    gilt; Charakter → Gespräch zeigt nur noch Zuhören und Antworten und verweist dorthin.
  - **System → Körper** heißt die bisherige Seite „Zustand“ (Lagebild, Sensoren, Gelenke, Pflege).
- `brain/tools.py` aufgeteilt (1362 → 1073 Zeilen): Werkzeuge der Trainingshalle in `tools_lab.py`, Raum, Team und
  gezielter Schuss in `tools_raum.py`.
- Szene zurücksetzen und Verknüpfungen anlegen gehen nur am PC, nicht vom Handy.

### Nicht geprüft
- Verknüpfungen unter Windows (in der Testumgebung nur die Absage außerhalb von Windows).
- Knowlin-Splash: der Entwurf `knowlin-splash-v3.png` braucht noch volle Auflösung und eine Lizenzprüfung des
  Bildgenerators – bis dahin bleibt der duckpilot-Splash.

---

## 0.37.14 – 2026-11-04 – Befehle werden ausgeführt, Purzelbaum mit Platzprüfung, Szene zurücksetzen

### Behoben
- **Angekündigt, aber nicht ausgeführt** (Befund: „mehrmals den Befehl für Purzelbaum gegeben, er hat immer nur
  geantwortet, aber nicht ausgeführt“): Verlangt man eine Vorführung („mach einen Purzelbaum“, „tanz“, „schieß zum
  Sofa“) oder kündigt die Antwort eine Bewegung an („ich rolle ab“), ohne dass ein Werkzeug lief, fragt duckpilot das
  Sprachmodell einmal nach. Läuft danach immer noch nichts, führt duckpilot den Befehl selbst aus – mit denselben
  Werkzeugen und Sicherheitsregeln wie ohne KI – und sagt das. Eine ehrliche Absage („geht gerade nicht, ich liege“)
  bleibt eine Absage; Fragen und Verneinungen („kannst du …?“, „mach keinen …“) lösen nichts aus. Eine Choreografie gilt
  nicht als Purzelbaum. Die Anweisungen ans Modell sagen jetzt auch: Pollens gelernte Bewegungen werden nur durch
  Training besser, nicht durch eine Choreografie davor.
- **„Purzelbaum nochmal“** wiederholt jetzt den Purzelbaum statt der letzten Choreografie („nochmal“ allein wiederholt
  weiter das Letzte, „wiederhole den Steptanz“ die gespeicherte Vorführung).
- **Purzelbaum dreht sich weg und stößt an** (Befund): Gemessen in der Physik mit Pollens Policy landet sie
  90–150° verdreht. Jetzt prüft sie vorher, ob vorn ≈ 50 cm frei sind (sonst dreht sie sich zur freieren Seite oder
  lehnt ehrlich ab), wartet nach der Landung kurz und dreht sich dann in die alte Blickrichtung zurück. In acht
  Physik-Läufen: am Ende 3–18° statt 98–134° neben der alten Richtung (ein Lauf gedreht, weil vorn kein Platz war).
- **Trainierte Fassung kam nicht an**: Ein ausprobierter Trainingslauf lief nur bis zum Neustart, danach wieder Pollens
  Original, ohne dass es jemand merkte. Jetzt merkt sich duckpilot ausprobierte eigene Policies und lädt sie beim Start
  wieder. Beim Skill steht dabei, welche Fassung läuft (Pollens Original, eigene, vom Hub, einfacher Simulator) – mit
  Hinweis, wenn es eine selbst trainierte gibt.
- **„Auswertung ging nicht“**: `training_auswerten` sagt jetzt klar, dass es noch keinen Lauf gibt bzw. welche Läufe
  es gibt, und liefert ohne Lernkurve wenigstens Stand und Aufgabe.
- **Ball steckte in der Wand** (Bildschirmfoto): In einer Ecke wurde nur eine der beiden Wände berücksichtigt.
  Jetzt werden mehrere Stöße nacheinander aufgelöst, Dinge bleiben immer im Zimmer, und die Ente drückt beim Schubsen
  nichts mehr in Wände oder Möbel.
- **Füße der Folg-mir-Figur „ganz komisch, teils sehr versetzt“**: echte Schuhform statt durchsichtiger Ovale,
  Blickrichtung geglättet (kein Umklappen bei kleinen Mausbewegungen), Schrittweite nach Weg – und bleibt die Maus
  stehen, stellt die Figur die Füße wieder nebeneinander.
- **Blaue Kästchen in der Luft**: Hindernis-Zellen des erkundeten Bereichs sind jetzt flache Kacheln am Boden statt
  2,5-cm-Klötze, die wie schwebende Dinge aussahen.
- **Akku zeigt im Simulator 0 %**: Der simulierte Akku leert sich nur beim Laufen und bei Tricks, nie unter 25 %, und
  lädt im Stehen, Sitzen und in Ruhe wieder. Für Claude steht „(simuliert)“ dabei.

### Neu
- **Szene zurücksetzen** (Wunsch: „Für den Simulator wäre ein Reset sinnvoll“): Knopf im Ansicht-Menü des
  Cockpits, per Sprache („Szene zurücksetzen“, „leg den Ball zurück“) und je Ding „Zurücklegen“ im Anwählen-Menü. Dinge
  kommen an ihre Startplätze, die Ente zurück an den Start – nur wenn sie steht; liegt oder ruht sie, bleibt sie, wo sie
  ist (aufgestellt wird sie hier nie). Erkundeter Bereich und Gedächtnis bleiben. Am echten Roboter gibt es das nicht.
- **Ansicht-Menü: „Erkundeter Bereich“** ein- und ausblenden (derselbe Schalter wie auf der Karte „Raum kennenlernen“).
- **Befund zu Architektur und Design** vor 0.38 (`docs/befund-architektur-design.md`): heutige Gliederung, was auffällt,
  Vorschlag mit Knowlin-Startseite und eigenem Bereich „Umgebung“, fünf offene Entscheidungen.

### Geändert
- **Gezielter Schuss genauer, ohne Abräumen** (Befund „sehr ungenau, rammelt andere Objekte weg“): Sie läuft
  über einen Vorpunkt auf der Schusslinie hinter dem Ball, plant den Weg um Ball und alle gesehenen Dinge herum (auch
  ohne erkundeten Bereich, dann mit dem, was der Tiefensensor gerade sieht), kommt das letzte Stück gerade und langsam
  heran, richtet sich auf 5° genau aus (bis zu zwei Nachdrehungen, Ball höchstens 20° seitlich statt 35°) und plant neu,
  wenn unterwegs ein Ding im Weg auftaucht oder sie nicht ankommt. Plan B läuft nicht mehr geradeaus zum Ball.
  Prüfstand mit zehn Schüssen (Regal, Kiste, Hocker, Pflanze, links, rechts, verschiedene Lagen): einfacher Simulator
  9/10 Treffer, kein Ding verschoben (vorher 9/10, eins verschoben); vollgeräumt um den Ball 5/6 (vorher 3/6 in einer
  Zwischenfassung); Physik mit Pollens Schuss-Policy 7/10 (vorher 6/10), in zwei von zehn Läufen noch ein Ding
  angestoßen.

### Sicherheit
- Die neue Absicherung führt Befehle nur mit den vorhandenen Werkzeugen aus; Not-Aus-Sperre, Stopp-Fenster und alle
  Regeln gelten dort unverändert. Szene zurücksetzen stellt eine liegende Ente nie auf.

### Nicht geprüft
- Am echten Roboter: Purzelbaum mit Platzprüfung (nur mit Tiefensensor-Gedächtnis), gezielter Schuss.
- Die Absicherung mit echten Antworten von Claude (geprüft mit nachgestellten Antworten, die nur Text enthalten).
- Füße der Folg-mir-Figur und flache Hindernis-Kacheln nur im Browser ohne Grafikkarte angesehen.

---

## 0.37.13 – 2026-11-02 – Gründlicher erkunden, „erkundeter Bereich“ statt „Karte“

### Geändert
- **Gründlicher erkunden** (Hinweis „beim Kartieren nicht so sehr gründlich“): Statt frei herumzulaufen geht sie
  gezielt an die Ränder des schon Erkundeten – dorthin, wo es noch Unbekanntes zu sehen gibt –, um Hindernisse herum,
  und sieht sich dort um. Stellen dicht an Wänden und Möbeln, an denen sie nur festhinge, lässt sie aus. Im
  Wohnzimmer des Simulators: in zwei Minuten 8,9–9,9 m² von ≈ 10 m² freier Fläche (vorher 6,8–9,4 m²).
- **Begriffe** (Hinweis „Karte ist für den explorierten Bereich missverständlich“): „Raum erkunden“ statt
  „Kartieren“, „erkundeter Bereich“ statt „Karte“, „Erkundetes löschen“. „Karte“ bleibt frei für das spätere
  Kartenmanagement. Per Sprache geht neben „Kartiere das Zimmer“ jetzt auch „Erkunde das Zimmer“.

---

## 0.37.12 – 2026-11-02 – Hirnaktivität in 3D, Karte im Lagebild

### Neu
- **Hirnaktivität drehen und zoomen** (Wunsch): Das Erfahrungsnetz hat jetzt Tiefe. Ziehen dreht es,
  Mausrad oder zwei Finger zoomen; vorne liegende Knoten sind größer und heller. Nach vier Sekunden Ruhe kehrt die
  Ansicht sanft in die Ausgangslage zurück. Ein Klick auf einen Knoten zeigt weiter seine Einzelheiten.
- **Gelernte Karte im Lagebild** (Frage): Was sie beim Kartieren erkundet hat, erscheint jetzt auch im Lagebild
  unter System → Zustand – im Simulator unter den bekannten Möbeln, am echten Roboter als eigentliches Bild des Raums.

---

## 0.37.11 – 2026-11-02 – Karte von oben beim Kartieren

### Neu
- **2D-Vorschau beim Kartieren** (Wunsch): Auf „Steuern → Tricks“ wächst die Karte jetzt direkt neben den
  Knöpfen – von oben gesehen: freie Fläche, Hindernisse, die Ente mit Blickrichtung und ein Maßstab.
- **Dinge und Möbel mit Piktogramm** (Wunsch): Alles, was sie gesehen hat, ist markiert und beschriftet – Ball,
  Socke, Klötzchen, Klemmbaustein, Schachfigur, Sofa, Regal, Kiste, Couchtisch, Pflanze, Hocker, andere Enten.

### Geändert
- „Kartieren“ bleibt auf der Seite (statt ins Cockpit zu springen); „Im Cockpit in 3D ansehen“ wechselt bei Bedarf.

---

## 0.37.10 – 2026-11-02 – Kartieren sichtbar, Musikstück wählen

### Behoben
- **Kartieren schien im Simulator nichts zu tun** (Hinweis): Der Knopf liegt auf „Steuern → Tricks“, wo die
  3D-Ansicht nicht zu sehen ist (sie ruht dort). Die Ente lief und die Karte wuchs, man sah es nur nicht. Jetzt wechselt
  „Kartieren“ ins Cockpit und sagt kurz, dass die Karte dort auf dem Boden wächst.
- **Musikstück wählen ging nicht mehr** (Hinweis): Wer dasselbe Stück ein zweites Mal wählte, bekam keine
  Reaktion (der Browser meldet eine unveränderte Auswahl nicht). Jetzt ein echter Knopf, der die Auswahl jedes Mal neu
  öffnet; das Stück lässt sich auch auf die Karte ziehen. Kann der Browser ein Format nicht lesen (z. B. kopiergeschützt
  oder WMA), steht das jetzt da statt „EncodingError“.

### Geprüft
- Alle Seiten im Browser geöffnet (keine Skriptfehler), Kartieren von „Tricks“ aus, Musikstück (mp3, wav) laden und
  analysieren, Chat-Befehle (gezielt schießen, „wo zuletzt gesehen“, tanzen).

---

## 0.37.9 – 2026-11-02 – Gezielt schießen, Stimme mit Tempomessung und Piper als Rückfall

### Neu
- **Gezielt schießen** (Wunsch): „Schieß den Ball zum Regal“, „schieß zu Kiki“, „schieß nach links“ – oder in
  der 3D-Ansicht den Ball anklicken → „Schießen auf …“ → Ziel anklicken. Die Ente stellt sich hinter den Ball auf die
  Linie zum Ziel (läuft außen herum, statt ihn vorher wegzuschubsen), richtet sich aus, schießt und prüft: Ist der Ball
  angekommen? Rollte er in die richtige Richtung, kam aber nicht an (zu weit oder etwas im Weg), sagt sie genau das.
  Daneben: einmal nachkorrigieren und noch ein Schuss. Die Abweichung des Beins lernt sie dabei nach. Werkzeug
  `schiessen` (ziel oder richtung); ohne Ziel bleibt „schieß den Ball“ der einfache Schuss.
- **Tempo der eigenen Stimme:** duckpilot misst, wie lange ein Satz zum Rechnen braucht (Sekunden je Sekunde Sprache),
  zeigt es auf der Stimme-Seite und schreibt es ins `qwen-arbeiter.log`. Nach dem Laden rechnet Qwen einen kurzen
  Aufwärmsatz, damit nicht der erste echte Satz das Übersetzen der Rechenprogramme abbekommt.

### Geändert
- **Je Antwort eine Stimme** (Hinweis „springt wegen geringer Leistung auf die Browserstimme zurück“): Schafft
  Qwen eine Antwort auf diesem Gerät nicht flüssig, spricht die ganze Antwort **Piper** (falls geladen), sonst die
  Browser-Stimme – kein Wechsel mehr mitten in der Antwort. Auch solange das Sprechmodell lädt, springt Piper ein.
  Die Wartezeit auf den ersten Satz richtet sich nach dem gemessenen Tempo (15–45 s statt fest 15 s).
- Stimme-Seite: Läuft Qwen auf dem Prozessor, steht dort, dass Piper auf diesem Gerät die bessere Wahl ist.

### Nicht geprüft
- Tempo und Aufwärmen mit dem echten Qwen-Modell (hier nicht ladbar); gezielter Schuss in der echten Physik und am
  Roboter (nur im einfachen Simulator geprüft).

---

## 0.37.8 – 2026-11-02 – Qwen im eigenen Prozess, kein Entenfilter für entworfene Stimmen

### Behoben
- **Aktivieren der Qwen-Stimme ließ duckpilot hängen** (Hinweis „reagiert nicht mehr“): Qwen3-TTS rechnet jetzt
  in einem eigenen Arbeitsprozess. Laden von PyTorch und Modell, das erste Übersetzen der Grafikkarten-Programme und ein
  hängender oder abstürzender Grafiktreiber blockieren die Oberfläche nicht mehr – Chat, Mikrofon und Not-Aus bleiben
  bedienbar. Antwortet Qwen 5 Minuten nicht, wird der Arbeiter beendet und beim nächsten Satz neu gestartet; stürzt er
  ab, steht der Grund in `qwen-arbeiter.log` im App-Datenordner und in der Meldung auf der Stimme-Seite.

### Geändert
- **Kein Entenfilter für entworfene Stimmen** (Hinweis): Mit Qwen3-TTS bleibt der Regler „Wie sehr nach Ente“
  aus – die Stimme klingt so, wie sie beim Entwerfen klang. Für Piper und die Browser-Stimme gilt er weiter.

### Nicht geprüft
- Der Arbeitsprozess mit dem echten Qwen-Modell auf der Radeon unter Windows (hier nicht ladbar); geprüft sind Start,
  Protokoll, Fortschritt, Fehler und Beenden mit einem echten Kindprozess.

---

## 0.37.7 – 2026-11-02 – Download-Fortschritt und Fortsetzen

### Neu
- **Fortschritt beim Herunterladen der Qwen-Modelle** (Wunsch): Die Stimme-Seite zeigt beim Sprechmodell einen
  Balken und „1,2 von 2,4 GB (50 %)“, beim Entwerfen steht der Fortschritt des Entwurfsmodells im Statustext.
- **Fortsetzen:** Bricht der Download ab (duckpilot beendet, PC aus, Netz weg), bleiben die halben Dateien liegen. Beim
  nächsten Start geht es an derselben Stelle weiter („setzt den Download des Sprechmodells fort …“) statt von vorn.
  Dafür lädt duckpilot Modelle auf dem klassischen Weg von Hugging Face (der neuere Xet-Weg lässt sich nicht messen).
- Ein halb geladenes Modell gilt nicht mehr als „geladen“.

### Nicht geprüft
- Fortsetzen gegen den echten Hugging-Face-Server unter Windows (hier gesperrt); geprüft mit nachgestelltem Download.

---

## 0.37.6 – 2026-11-02 – Entworfene Stimme spricht, Möbel zum Wiedererkennen

### Behoben
- **Die entworfene Stimme klang nur beim Anhören der Fassungen, nicht im Gespräch – und danach schien das Programm zu
  hängen** (Hinweis): Die Fassungen beim Entwerfen kommen vom Entwurfsmodell. Gesprochen wird mit einem zweiten,
  kleineren Sprechmodell, das beim ersten Mal ≈ 2,4 GB nachlädt – ohne Anzeige. Bis dahin warteten alle Sätze still,
  und weil die Ente „sprach“, blieb das Mikrofon aus.
  - Das Sprechmodell lädt jetzt gleich nach dem Übernehmen sichtbar im Hintergrund („lädt das Sprechmodell herunter
    (einmalig ≈ 2,4 GB) …“ auf der Stimme-Seite). Bis es da ist, spricht die Browser-Stimme; danach die eigene.
  - Kommt ein Satz nicht innerhalb von 15 Sekunden vom PC, spricht ihn die Browser-Stimme – das Gespräch hängt nie mehr.
  - Gibt der Browser den Ton nicht frei (wer nur per Stimme spricht, hat nie geklickt), spricht ebenfalls die
    Browser-Stimme; der erste Tastendruck oder Klick schaltet den Ton frei.
  - Stopp beendet das Sprechen jetzt sauber: Das Mikrofon geht wieder an.
- Begrüßung („Hallo Alex!“) und Meldungen der Ente sprechen jetzt auch mit der eigenen Stimme statt immer mit der
  Browser-Stimme.

### Geändert
- **Möbel zum Wiedererkennen** (Wunsch): Sofa mit Kissen, Lehne und Armlehnen, Regal mit Böden und Büchern,
  Holzkiste mit Latten, Couchtisch mit Beinen, Ablage und Tasse, Topfpflanze, Barhocker mit Fußring. Jedes Möbel besteht
  aus wenigen einfachen Körpern, die je Farbe zu einem verschmolzen werden – insgesamt ≈ 2000 Dreiecke und 23
  Zeichenaufrufe für alle Möbel. Zusammenstöße, Tiefensensor und Wege rechnen weiter mit den bisherigen Maßen;
  Anwählen und die ausweichende Kamera funktionieren wie vorher. Unbekannte Möbel bleiben schlichte Kästen.

### Nicht geprüft
- Das Laden des Qwen-Sprechmodells und das Sprechen damit auf der Radeon (das Modell lässt sich hier nicht laden);
  geprüft sind Ablauf, Anzeige und Rückfall mit nachgestelltem Modell.

---

## 0.37.5 – 2026-11-02 – Vorsichtig am Ziel, Nacharbeiten, Weckwort

### Behoben
- **Enten schoben abgelegte Dinge wieder vor sich her** (Hinweis): Nach dem Ablegen treten sie jetzt erst einen
  Schritt zurück, bevor sie sich umdrehen; auf den letzten 30 cm gehen sie langsamer; ihre Wege planen sie um liegende
  Dinge herum, und frei herumlaufend weichen sie ihnen sanft aus. Im Probelauf lag nach dem Aufräumen und einer Minute
  freiem Herumlaufen noch alles am Ziel.
- **Nacharbeiten:** Rollt während des Aufräumens etwas Gebrachtes weg (weiter als ≈ 45 cm vom Ziel), holt eine Ente es
  zurück und sagt es („Kiki: Socke ist weggerollt – ich hole es zurück“) – je Ding höchstens zweimal.
- Bringt die Hauptente ihr Ding nicht hin, übernimmt eine andere Ente; sie bleibt 15 cm davor stehen, damit es nicht
  am Möbel landet.
- **Weckwort reagierte nicht richtig** (Hinweis):
  - Erst „Ente“, kurze Pause, dann der Befehl: Der Befehl brauchte bisher noch einmal das Weckwort und wurde
    verschluckt. Jetzt gilt der nächste Satz innerhalb von 6 Sekunden als Befehl; die Sprechtaste zeigt „Ich höre zu …“.
  - Das Weckwort zählt nur als ganzes Wort am Satzanfang („Ente, lauf vor“, „Hey Ente, …“) – nicht mehr in „Rente“ oder
    „alle Enten tanzen“. Häufige Verhörer der Spracherkennung („Ende, …“) werden erkannt.
  - Sprechtaste bei eingeschaltetem Weckwort: Das abgelöste Dauerhören startete sich nach 250 ms neu und brach die
    Sprechtaste ab.
  - Auf Englisch steht jetzt auch „duck“ neben dem Häkchen. Mit lokaler Erkennung (Whisper) erklärt der Hinweis, dass
    das Weckwort die Erkennung von Edge oder Chrome braucht.

### Nicht geprüft
- Das Weckwort mit echtem Mikrofon (geprüft sind die Worterkennung und der Ablauf ohne Ton).

## 0.37.4 – 2026-11-01 – Teamarbeit: Aufräum-Team und Suchtrupp

### Neu
- **Die anderen Enten um Hilfe bitten** (Wunsch: „dass bei mehreren Gegenständen die anderen helfen, sie von
  A nach B zu transportieren – oder beim Suchen helfen, und wer sie gefunden hat zuerst, meldet sich“):
  - **Aufräum-Team:** „Räumt alle Socken zum Sofa“, „Bringt alle Klötzchen zu mir“, „Räumt alles ins Regal“. Jede
    Ente nimmt sich das ihr nächste freie Ding (keine nimmt eines, das eine andere schon holt), trägt es hin, legt es
    an ihrem Fleck ab, meldet sich mit eigener Stimme („Kiki: Socke ist bei Sofa!“) und holt das nächste. Die
    Hauptente packt selbst mit an. Kommt eine nicht heran, sagt sie es; am Ende eine Zusammenfassung.
  - **Suchtrupp:** „Helft mir die Schachfigur suchen“ – jede Ente sucht in ihrem Teil des Zimmers und schaut sich um.
    Wer es zuerst sieht, ruft „Gefunden – liegt beim Couchtisch!“, die anderen kommen gucken, die Finderin bringt es.
    Sieht die Hauptente es selbst zuerst, sagt sie das.
  - Die Enten planen ihre Wege um die Möbel herum (dieselbe Rasterkarte und A* wie die Hauptente) und tragen Dinge
    sichtbar im eigenen Schnabel.
  - Steuern → Tricks → Mehrere Enten zeigt, was das Team gerade tut, mit „Auftrag beenden“ (sie legen ab, was sie
    tragen). Englisch: „everyone bring the socks to the sofa“, „help me find the chess piece“. Werkzeug `team`.

### Sicherheit
- Not-Aus gilt wie immer für alle und beendet die Teamarbeit: Alle bleiben stehen und legen ab, was sie tragen.

### Nicht geprüft
- Mehrere echte Enten (es gibt weiterhin nur eine im echten Haushalt); nur im einfachen Simulator.

## 0.37.3 – 2026-11-01 – Anwählen und Handeln, Umweg ums Hindernis

### Neu
- **Anwählen und Handeln** (Wunsch: „Sachen anwählen und dann einen Befehl äußern oder auswählen – aufheben,
  reden, ärgern, schießen“): Ein Klick in der 3D-Ansicht auf ein Ding, ein Möbelstück oder eine andere Ente wählt es
  an – Ring am Boden, daneben ein Menü mit dem, was die Ente damit tun kann:
  - Ball: schießen, hinlaufen, anschauen · Socke, Klötzchen, Klemmbaustein, Schachfigur: aufheben, bring es mir,
    hinlaufen, anschauen · Möbel: hinlaufen, anschauen
  - **Andere Enten:** begrüßen (sie grüßt zurück), **ärgern** (frech „nä-nä-nä“ – sie schüttelt den Kopf, quakt
    empört und weicht zurück), hinterherlaufen, anschauen
  - Solange etwas angewählt ist, meint „das“ im Chat genau dieses Ding: „heb das auf“, „schieß den“, „ärger sie“.
    Auch ohne Claude: „ärgere Kiki“, „begrüß Pip“, „folg Bruno“, englisch „tease Kiki“, „say hello to Pip“.
  - Kleine Dinge muss man nicht genau treffen: knapp daneben zählt auch.
  - Werkzeug `handeln` für Claude und andere Modelle. Erstes Stück der Fähigkeiten-Schnittstelle aus 0.38.
- Die Hauptente sieht die anderen Enten jetzt (wie Dinge) – Grundlage für Begegnungen und Folgen.

### Geändert
- **Apportieren findet einen Weg um Hindernisse** (Hinweis „wenn auf dem Weg ein Hindernis ist, probiert er
  nicht wirklich, einen Weg zu finden“): Unterwegs trägt sie ein, was der Tiefensensor sieht. Kommt sie nicht näher
  oder ist das Ding verdeckt, plant sie einen Umweg zur letzten bekannten Stelle (aus „Wo zuletzt gesehen“) und setzt
  neu an – notfalls von einer anderen Seite, bis zu dreimal.

### Nicht geprüft
- Anwählen am Handy-Controller; am echten Roboter braucht es die Kamera mit Objekterkennung (R2).

## 0.37.2 – 2026-11-01 – Körper oben umschalten, Enten mit Bodenkontakt

### Neu
- **Körper direkt oben umschalten** (Wunsch): Der Chip „Simulator“ neben dem Namen öffnet ein Menü – einfacher
  Simulator, echte Physik, echter Roboter, gewählt mit Häkchen. Ist die Physik noch nicht eingerichtet, ist sie
  ausgegraut und sagt, wo es weitergeht. Am Handy nur Anzeige (wohin duckpilot sich verbindet, ändert nur der PC).

### Behoben
- **Weitere Enten wirkten schwebend** (Hinweis): Der Schatten des Hauptlichts reicht nur etwa 1,2 m um die
  Hauptente; Enten weiter weg standen ohne Schatten da, obwohl ihre Füße den Boden berühren (nachgemessen: höchstens
  3 mm Abweichung). Unter jeder weiteren Ente liegt jetzt ein weicher Kontaktschatten.

## 0.37.1 – 2026-11-01 – Musik stoppen, weitere Enten sichtbar

### Behoben
- **Musik lief nach dem Tanz weiter** (Hinweis „wie kann ich Musik im Tanzmodus stoppen?“): Not-Aus, Esc,
  „Stopp“ oder ein anderer Befehl hielten die Ente an, die Musik im Browser spielte aber bis zum Ende des Stücks. Jetzt
  endet die Musik mit dem Tanz. Solange sie spielt, steht oben unter Tanzen eine Leiste „Läuft: … · Musik und Tanz
  stoppen“ – auch für gespeicherte Tänze, die bisher keinen sichtbaren Stopp hatten.
- **„Weitere Enten“ unter Tanzen → Vorschau zeigte beim Start „Sie tanzt allein“**, obwohl Enten eingestellt waren
  (sie wurde erst nach dem Besuch von Tricks aktualisiert). In der echten Physik und am Roboter ist die Auswahl jetzt
  ausgegraut und sagt, warum: weitere Enten gibt es nur im einfachen Simulator.

## 0.37.0 – 2026-11-01 – Apportieren, Kartierungsmodus, Wo zuletzt gesehen (Simulator-Teil)

### Neu
- **Apportieren** – „Bring mir die Socke“: hinlaufen (sucht notfalls durch Drehen), aufheben, **prüfen**, ob das
  Richtige im Schnabel ist, zurückbringen, ablegen, freuen. Geht etwas schief, gibt es einen **Plan B**: einen Schritt
  zurück, neu ansetzen – höchstens drei Versuche, das Falsche erwischt wird wieder hingelegt; dann sagt sie ehrlich,
  dass es nicht geklappt hat. Bringt zum Menschen (≈ 25 cm davor), zu einem gemerkten Ort oder zurück zum Start.
  Aufgebaut wie eine Fähigkeit der kommenden Suite-Schnittstelle (Vorbedingung, Ergebnisprüfung, Plan B).
  Per Sprache „bring mir …“, „hol mir … her“, „apportier …“, englisch „bring me …“, „fetch …“; Werkzeug `apportieren`;
  Knöpfe unter Steuern → Tricks → Raum kennenlernen.
- **Neue Dinge im Wohnzimmer:** ein roter **Klemmbaustein** und eine **Schachfigur** – beide aufhebbar.
- **„Wo hast du … zuletzt gesehen?“** Sie merkt sich, wo sie Dinge und Möbel gesehen hat – **nur Dinge und Orte, nie
  Menschen** – und antwortet mit Zeit und Stelle: „Die Socke habe ich zuletzt vor 3 Minuten gesehen, beim Sofa.“ Auch
  englisch, auch ohne Claude; Werkzeug `wo_gesehen` (mit `hingehen` läuft sie gleich hin und sucht).
- **Kartierungsmodus:** „Kartiere das Zimmer“ – sie läuft herum und zeichnet mit dem Tiefensensor eine Rasterkarte
  (5 cm, Belegungskarte). Gemerkte Orte erreicht sie danach **auf der Karte um Hindernisse herum** (A*); unterwegs
  lernt die Karte dazu, festgefahren plant sie neu. Die Karte erscheint auf Wunsch auf dem Boden der 3D-Ansicht.
  Steuern → Tricks → **Raum kennenlernen**; Werkzeug `karte`.
- **3D-Kamera weicht Möbeln aus:** Steht ein Möbelstück zwischen Kamera und Ente, rückt die Kamera davor und gleitet
  danach zurück. Dreht oder zoomt man selbst, hält sie still.
- **Stoßreihe genauer:** jeder Stoß wahlweise drei- oder fünfmal, leicht gestreut (±6°, ±6 %). Das Profil zeigt
  **Grenzfälle** (mal stehen, mal fallen) und **Ausfallschritte** (steht, hat sich aber mehr als 4 cm versetzt).
- **Zwilling vorbereitet** (für 0.37 Teil 2 mit der echten Ente): Plan für den Messlauf der Beingelenke (im Sitzen,
  kleine Auslenkungen) und der Abgleich mit dem Simulator – Verzögerung, Verstärkung, Versatz und Restfehler je Gelenk.

### Behoben
- **Tanzen nach Gehör bewegte sich kaum** (Hinweis): Jede Messung (alle 1,5 s) setzte den Schlagzähler zurück,
  sie blieb im ersten Abschnitt hängen – leise nur Wiegen, laut nur Seitschritte, nie Drehung oder Tanzgesten. Der
  Zähler läuft jetzt durch, Messungen gleichen nur sanft die Phase an; auch leise Musik bekommt Schritte und Drehung.
- **Tricks vom Hub in der Physik wie auf dem Roboter** (Hinweis, abgeglichen mit Pollens robotd): im Fenster
  Befehl 0 statt fälschlich `command.idle`; danach `unwind_s` lang `idle`; ungeglättet und nicht aufs Fahrtempo
  begrenzt; mit Befehl 0 „standing tuned“ (Ausschlag 1,0 ohne eigenen `action_scale`, Motorstärke 0,8) – das gilt auch
  für die Schüsse, der Purzelbaum bleibt bei vollen Werten. „Vorführen“ erscheint jetzt auch bei Namen mit
  Großbuchstaben oder Leerzeichen.
- **Beim Start fehlte die Leiste Cockpit / Tricks / Tanzen / Vom Hub** – sie kam erst nach dem ersten Klick links.

### Sicherheit
- Karte und Sichtungen bleiben am PC (`/api/raum` nur am PC) und kommen nie in Knowlets oder Fehlerberichte.
  Menschen werden nie als Sichtung gespeichert.
- Der Zwilling-Abgleich rechnet nur; der Messlauf bewegt nichts, bevor er mit der echten Ente kommt.

### Nicht geprüft
- Tanzen nach Gehör mit echtem Mikrofon und PC-Ton; Hub-Tricks mit Pollens echten Policies (der Hub war beim Bauen
  nicht erreichbar) – geprüft gegen eine Test-Policy und den Ablauf von robotd.
- Apportieren, Sichtungen und Karte in der echten Physik und am Roboter (dort fehlt noch die Objekterkennung).

## 0.36.3 – 2026-11-01 – Mehrere Enten

### Neu
- **Mehrere Enten im Simulator – eigenständig, nicht mehr als Kopie** (Wunsch: „unabhängig von der Musik,
  Interaktion untereinander“): bis zu vier weitere Enten (Kiki, Pip, Lotte, Bruno), jede ein eigener Simulator-Körper
  mit eigener Position, Blickrichtung und eigenem Gang – in derselben Welt (Möbel, Ball). Steuern → Tricks →
  **Mehrere Enten**; die Anzahl bleibt gespeichert.
  - **Frei herumlaufen:** eigene Ziele, stehen bleiben, die anderen anschauen. Treffen sich zwei, wendet sich die eine
    zu, nickt und quakt – höchstens einmal je Paar und Minute; die Begegnung steht in der Ereignisliste.
  - **Mir folgen:** lockere Formation hinter der Hauptente, jede läuft selbst hin.
  - **Tanzen:** jede an ihrem Platz. Tanzt die Hauptente, tanzen die anderen von selbst mit – im selben Takt und mit
    ihrer Bewegung (wie der Chor-Modus der Community), abschaltbar.
  - **Hinsetzen**; per Sprache „alle tanzen“, „alle mir nach“, „alle hinsetzen“, „alle frei“ (auch englisch) und für
    Claude/andere Modelle das Werkzeug `enten`.
  - **Eigene Stimme je Ente:** feste Klangsignatur aus ihrer Kennung (Idee aus „Microduck audio identity“).
  - Sie weichen einander aus und gehen nicht ineinander; fallen sie, stehen sie nach einer Weile selbst wieder auf.

### Geändert
- Die Tanzgruppe aus 0.36.1 (Kopien in der Ansicht) ist ersetzt: Unter Tanzen → Vorschau stellt „Weitere Enten“ jetzt
  die echten weiteren Enten ein.

### Sicherheit
- Not-Aus gilt für alle Enten: 120 s Stillstand, auch für die Begleiter.

### Nicht geprüft
- In der echten Physik und am Roboter gibt es weiterhin eine Ente (jede weitere kostet dort viel Rechenzeit).
  Fußball miteinander kommt mit den Spielen.

## 0.36.2 – 2026-11-01 – Launch-Paket

### Neu
- **Tanzen: mehr von Bein zu Bein und Drehungen** (Hinweis): neue Schritte **Bein zu Bein** (je Schlag ein
  kleiner Seitschritt, abwechselnd links und rechts, Gewicht aufs Standbein), **Wiegen** (Gewicht verlagern, ohne zu
  treten) und **Drehen** als ganze Drehung (so schnell sie darf, Richtung wechselt von Schritt zu Schritt). Der Planer und
  das Tanzen nach Gehör setzen sie in jedem Teil ein.
- **Nach Gehör auch mit dem Ton des PCs** (Wunsch): Quelle „Ton dieses PCs“ – über „Bildschirm teilen“ mit
  Systemaudio (Edge/Chrome unter Windows); das Bild wird sofort beendet, nur der Ton zählt.
- **„Das lief schief“ – Fehlerbericht mit Aufzeichnung:** System → Zustand oder Einstellungen → Über. Hält die letzten
  30 Sekunden fest (Zustand fünfmal pro Sekunde, Ereignisse, Version, Körper, Einstellungen, Warnungen aus dem
  Protokoll), speichert die Datei im Datenordner (`fehlerberichte/`) und öffnet auf Wunsch ein vorausgefülltes
  GitHub-Issue – die Datei hängt man selbst an.
- **Community-Dateien:** CONTRIBUTING (mit den Sicherheitsregeln, DCO), Code of Conduct, SECURITY, Vorlagen für
  Fehlerberichte, Ideen und „Bericht von einer echten Ente“, Pull-Request-Vorlage, `docs/good-first-issues.md`.
- Der Export der öffentlichen Fassung (`tools/export_public.py`) erzeugt eine öffentliche Roadmap (`docs/ROADMAP.md`)
  aus den Geplant-Kacheln und lässt private Planungsdateien weg.

### Behoben
- **Die Ente lief beim Tanzen langsam rückwärts weg** (Hinweis): Sie merkt sich ihren Startplatz; driftet sie
  mehr als 3 cm ab, holt ein kleiner Fahrbefehl (höchstens 6 cm/s) sie zurück – beim einstudierten Tanz und nach Gehör.

### Sicherheit
- Der Fehlerbericht arbeitet mit einer Erlaubt-Liste: nur genannte Felder gehen hinein. Nie dabei: Gespräche,
  Personen, Bilder, Schlüssel, Gedächtnis. Der Name der Ente wird ersetzt, Pfade mit dem Benutzernamen gekürzt. Nichts
  wird automatisch verschickt.
- Der Geheimnis-Scan des Exports sucht zusätzlich nach privaten Bezügen.

### Nicht geprüft
- Ob das Zurückholen in der echten Physik und am Roboter ganz ohne Wackeln geht (im einfachen Simulator bleibt sie
  innerhalb von 2 cm). Am Roboter hängt es an der Odometrie.

## 0.36.1 – 2026-11-01

### Neu
- **Tanzschritte aus den Tricks** (Hinweis: „die Tanzmoves müssen anhand der Tricks deutlich besser und
  passender werden“): neuer Schritt **Tanzgeste** – Pollens Emotionen und eigene Gesten aus Tricks, **im Takt
  gestreckt** (jede Wiederholung dauert ganze Schläge, zwischen halb und doppelt so schnell wie das Original). Der
  Planer wählt sie passend zum Teil des Stücks: ruhig (wippen, trällern, Haltung …), mittel (hibbeln, umherspähen,
  jep …), laut (begeistert, Freude, schütteln, jawohl, lachen …). Jeder Refrain bekommt dieselben Gesten. Auch Claude
  und andere Modelle können sie beim „Mit KI choreografieren“ einsetzen.
- **Tanzen nach Gehör:** Steuern → Tanzen → „Mithören und tanzen“. Sie hört übers Mikrofon mit – Radio, Spotify,
  YouTube, jede Musik im Raum – und tanzt spontan: alle zwei Takte ein neuer Schritt passend zur Lautstärke, mit
  Tanzgesten im Takt. Hört sie 8 s nichts mehr, hört sie auf.
- **Tanzgruppe im Simulator:** bis zu vier weitere Enten tanzen in Formation synchron mit (Tanzen → Vorschau →
  Tanzgruppe). Nur in der Ansicht, ohne eigene Physik – Fußball mit mehreren Enten kommt mit den Spielen.
- **Klangsignatur je Ente:** Charakter → Stimme → Klang: Tonhöhe und Klangfarbe aller Quaklaute und Gesten-Töne,
  mit „Probe“ und „Zufällig“.
- **Sprachauswahl als Dropdown** mit Flaggen (Wunsch), per Tastatur bedienbar.

### Sicherheit
- Beim Tanzen nach Gehör bleibt das Audio im Browser; an duckpilot gehen nur Tempo, Abstand zum letzten Schlag und
  Lautstärke. Das Mikrofon geht aus, sobald der Tanz endet (Stopp, Not-Aus, Stille).
- Tanzgesten laufen ohne ihre Skills (kein Hinsetzen oder Hinlegen im Tanz), am Platz.

### Nicht geprüft
- Tanzen nach Gehör mit echtem Mikrofon und echter Musik (hier mit künstlichen Taktspuren und nachgespielten
  Messungen geprüft). Laute Räume oder sehr leise Musik können das Tempo verfehlen.
- Wie die Tanzgesten am echten Roboter wirken.

## 0.36.0 – 2026-11-01

### Neu
- **Erste Schritte:** Beim ersten Start (oder unter System → Einstellungen → „Erste Schritte noch einmal“) führt ein
  Assistent in vier Schritten durch Sprache, Körper (Simulator, Simulator mit echter Physik oder die echte Ente mit
  kurzer Checkliste), Gehirn (Claude, anderes Modell, lokales Modell oder erst mal ohne) und die wichtigsten
  Sicherheitsregeln. Nur am PC.
- **Tanzen zu Musik (Choreomodus):** Steuern → **Tanzen**. Ein Musikstück (mp3, m4a, ogg, wav, flac) wählen – der
  Browser hört Tempo, ersten Schlag und Lautstärke je Takt heraus. Aufgebaut wie Roboter-Choreografie
  (Boston Dynamics Choreographer) und Licht-Sequenzer (xLights, Vixen):
  - **Zeitleiste** mit Wellenform, Taktraster, den Teilen des Stücks und zwei Spuren (Bewegung; Pose und Geste).
    Klick setzt die Startmarke, „Ab Marke proben“ spielt Musik und Tanz ab dort.
  - **Teile des Stücks** (Intro, Strophe, Refrain, Drop, Breakdown, Outro) aus der Lautstärke je Phrase – wie die
    Phrasenerkennung von DJ-Lichtsteuerungen. Jeder Teil hat sein Bewegungsmuster, **jeder Refrain wird gleich
    getanzt**, an Höhepunkten eine Pose oder Geste, im letzten Takt die Schlusspose. Alles auf Taktanfängen.
  - **Mit KI choreografieren:** Das eingestellte Gehirn (Claude, anderes oder lokales Modell) bekommt die Teile, die
    Posen und die Gesten aus Tricks und legt mit dem Werkzeug `choreo` einen eigenen Tanz an – sichtbar im Gespräch;
    der Editor öffnet ihn danach.
  - **Gesten aus Tricks:** Schritte „Gefühl“ spielen die echten Gesten (Pollens Emotionen und eigene Gesten) am Platz.
  - Schritte anpassen (Bewegung, Länge in Takten, Pose/Geste), proben, unter einem Namen speichern. Die Musik läuft
    in der Oberfläche, die Ente tanzt im Takt.
  - Per Sprache: „Tanz den Ententanz“ – das Gehirn kennt die gespeicherten Tänze (Werkzeug `choreo`).
  - **Posen:** gespeicherte Haltungen aus Lernen → Akrobatik (z. B. auf einem Bein, das andere nach hinten). Im
    Simulator mit echter Physik fährt sie die Haltung wirklich an, hält sie und kehrt in die Grundstellung zurück. Im
    einfachen Simulator und am Roboter deutet sie die Pose mit Kopf und Haltung an (robotd nimmt für die Beine nur
    Policies an).
  - Musikdateien bleiben im Datenordner dieses PCs (`musik/`), Tänze in `choreos.json` – nie in OneDrive oder im Netz.

- **Sprachwahl mit Flaggen** im Assistenten und in den Einstellungen (Umschalter statt Auswahlliste).
- **Tanzen:** gestaltete Dateiauswahl und eine **Live-Vorschau** der Ente neben „Probe tanzen“ (dieselbe 3D-Ansicht wie
  im Cockpit, sie zieht beim Wechsel mit um – ein Renderer für beide).

### Geändert
- **Designsystem – klickbar, gewählt, scharf** (Hinweis): Darüberfahren färbt keinen Akzent-Rand mehr (sah aus
  wie gewählt). Gewählt = getönte Akzentfläche, kräftiger Rand, Häkchen, fett – für Chips, Knöpfe und Umschalter
  gleich. Neu „scharf“ (`.is-armed`): volle Akzentfläche mit ↓, wenn der nächste Klick woanders hingehört (Ding
  hinlegen). Im Kollisionsmodus ist kein Ding mehr still vorausgewählt. Die Designsystem-Seite zeigt die drei Zustände.
- Eigene Sätze der Ente (Reflexe wie „Angehalten.“, Alltag, Beschwerden, Systemmeldungen) werden auf Englisch nicht nur
  angezeigt, sondern auch gesprochen – der Server übersetzt sie mit demselben Katalog wie die Oberfläche.

### Sicherheit
- Ein Tanz läuft über dieselbe Bewegungs-Engine wie jeder Befehl: „Stopp“ und der Not-Aus beenden ihn sofort (die
  Musik in der Oberfläche hält mit an). Posen gibt es nie im Liegen, schlaff, ohne Strom oder während eines Tricks;
  die Gelenkwinkel werden auf die erlaubten Bereiche begrenzt.
- Hochladen nimmt nur Musikdateien bis 40 MB an; Dateinamen werden bereinigt, Pfade aus dem Ordner heraus abgelehnt.
- Gesten im Tanz laufen ohne ihre Skills (kein Hinsetzen oder Hinlegen mitten im Tanz). Entwürfe der KI gehen durch
  dieselbe Prüfung wie alles von außen: unbekannte Schritte fliegen raus.

### Behoben
- Englisch: rund 220 Texte, die erst zur Laufzeit kommen, waren noch deutsch – Beschreibungen der Gesten und des
  Leerlaufs unter Tricks, Erweiterungen und geplante Kacheln, Modellauswahl, Akrobatik-Übungen, Trainings-Hinweise,
  Haltung und laufende Bewegung, Begriffe im Erfahrungsnetz, Gründe der Stimmung, Quellen im Gespräch, Fenstertitel,
  Platzhalter in Textfeldern. Antworten anderer KI-Modelle trugen im Gespräch fälschlich „einfache Befehle“.
  Englische Texte mit typografischen Anführungszeichen galten fälschlich als „fehlt“.

### Nicht geprüft
- Musik-Analyse mit echten Stücken in allen Browsern (hier mit künstlichen Taktspuren von 72–174 BPM geprüft). Sie
  findet Schläge, aber nicht, welcher Schlag der erste im Takt ist – Teile können um einen Schlag versetzt beginnen.
  Die Teile richten sich nur nach der Lautstärke, nicht nach Melodie oder Wiederholung.
- Posen am echten Roboter und wie lange sie im Physik-Simulator auf einem Bein stehen bleibt, ohne zu kippen.
- Gleichlauf von Musik und Tanz auf dem Handy (Wiedergabe startet dort evtl. erst nach einem Tippen).
- Die Tanzschritte sind noch schlicht (Nicken, Wippen, Wackeln, Drehen). In 0.36.1 entstehen sie aus den Tricks
  (Pollens Moves, Gesten im Takt gestreckt, Hub-Tricks) – passend zum Teil des Stücks.
- Wie gut Claude und andere Modelle tanzen entwerfen (hier mit einem nachgespielten Gehirn geprüft). Gesten in der
  Choreo-Liste tragen ihre deutschen Namen auch in der englischen Oberfläche.

## 0.35.0 – 2026-11-01

### Neu
- **Andere KI-Modelle statt Claude:** Charakter → Gespräch → „Womit sie denkt“ → **Anderes Modell** (nur am PC).
  OpenAI, Google Gemini, Mistral, OpenRouter, LM Studio auf dem PC oder eine eigene OpenAI-kompatible Adresse
  (`brain/anbieter.py`). Schlüssel je Anbieter nur im Tresor; „Modelle laden“ fragt die Liste beim Anbieter ab und
  prüft dabei die Verbindung. Dieselben Werkzeuge, dieselbe Persönlichkeit und dasselbe Gedächtnis.
- **Englisch überall:** Alltag, Charakter (Persönlichkeit, Stimme, Gedächtnis, Gespräch), Lernen (Akrobatik,
  Parcours, Training) und Zustand sind jetzt auch englisch. Nur die Designsystem-Seite bleibt deutsch.

### Sicherheit
- Die Sicherheitsregeln gelten bei jedem Modell gleich – sie stecken in den Werkzeugen und der Bewegungs-Engine.
  „Stopp“ und die Kurzbefehle laufen ohne Modell. Fällt der Anbieter aus (Schlüssel abgelehnt, keine Verbindung,
  Guthaben), übernehmen die einfachen Befehle.
- Anbieter, Schlüssel, Modell und Adresse lassen sich nur am PC ändern, nicht vom Handy. Eine eigene Adresse muss https
  sein; http nur auf diesem PC oder im Heimnetz – der Schlüssel geht nie unverschlüsselt ins Internet. Der Schlüssel
  wird nie an die Oberfläche zurückgegeben.

### Geändert
- Der Leerlauf nutzt in Tests denselben Zufall wie die Engine (reproduzierbar). Der Test zum Hinlaufen prüft jetzt eine
  feste Quote über zwölf Varianten statt einzelner Glücksfälle.

### Nicht geprüft
- Mit echten Konten der Anbieter (hier nur mit einem nachgespielten Anbieter getestet). Wie gut ein Modell Bewegungen
  plant und ob jeder Anbieter alle Werkzeug-Beschreibungen annimmt, zeigt erst der echte Lauf.
- Bilder („Was siehst du?“) kann vorerst nur Claude ansehen.
- Bekannt: An der Kistenecke, die der Tiefensensor nie gesehen hat, stößt sie beim Umlaufen selten an (gemessen 2 von 12
  festen Varianten; im einfachen Simulator fällt sie dabei). Besserung mit der Karte (0.37).

## 0.34.0 – 2026-11-01

### Neu
- **Englisch, Teil 1:** System → Einstellungen → **Sprache · Language**. Auf Englisch sind Steuern (Cockpit, Tricks,
  Vom Hub, Erweiterungen), der Handy-Controller, die Einstellungen, der Kollisionsmodus, Kopfzeile, Navigation und
  Meldungen. Der Rest (Alltag, Charakter, Lernen, Zustand) folgt in 0.35 und bleibt bis dahin deutsch.
  - Die Oberfläche wird über einen Katalog übersetzt (`duckpilot/i18n/ui_en.json`: deutscher Text → Englisch, auch mit
    Zahlen und Namen als Platzhalter). Was Skripte später schreiben, wird ebenfalls übersetzt. `tools/i18n_texte.py`
    zeigt, was im HTML noch fehlt; ein Test hält die übersetzten Bereiche vollständig.
  - **Die Ente spricht und denkt Englisch:** Claude (und das lokale Sprachmodell) antworten auf Englisch, die
    Spracherkennung hört Englisch (Browser en-US bzw. Whisper), Vorlesen mit englischer Browser-Stimme oder Qwen3-TTS
    auf Englisch. Eine deutsche Piper-Stimme wird für Englisch nicht benutzt. Standard-Weckwort auf Englisch: „duck“.
  - **Einfache Befehle ohne Claude auf Englisch:** „walk forward“, „turn left“, „dance“, „sit down“, „kick the ball“,
    „follow me“, „look around“ … – deutsch geht weiter. **„Stop“ wirkt in beiden Sprachen sofort.**
- **README auf Englisch** (`README.en.md`).

### Geändert
- **Ausweichen kennt das Ziel der Aufgabe** (Hinweis aus dem Test von 0.33): Beim Ball schießen, Annähern und Aufheben
  ist das Ding, das sie erreichen soll, kein Hindernis – sie weicht ihm nicht aus und meldet auch kein Ausweichen.
  Andere Hindernisse auf dem Weg umläuft sie weiter. Claudes Anweisung sagt das ebenso (und nicht mehr „Hindernis
  voraus → erst drehen“ – das erledigt das Ausweichen selbst).

### Behoben
- In 0.33 wich sie beim Ball schießen dem Ball selbst aus (Notiz „weicht aus“), bevor sie dann doch trat.
- Ein Test zum Hinlaufen hing vom Zufall im Leerlauf davor ab und schlug manchmal fehl; jetzt mit fester Saat.

### Nicht geprüft
- Englische Spracherkennung und Vorlesen im echten Edge-Fenster (hier nur im Testbrowser).
- Bekannt: Beim Umlaufen kann sie selten eine Ecke streifen, die der Tiefensensor nie gesehen hat (gemessen an der
  Kiste: 3 von 12 Varianten, ohne Sturz). Besser wird das mit der Karte aus dem Kartierungsmodus (0.37).

## 0.33.0 – 2026-11-01

### Neu
- **Hindernissen ausweichen und sie umlaufen – in allen Modi** (Folg mir, Laser, Hinlaufen, Erkunden, Annähern und
  beim Steuern von Hand). Bisher bremste der Hindernis-Reflex nur, und sie lief auf der Stelle dagegen. Jetzt:
  - ein **kurzes Hindernisgedächtnis** (ToF-Punkte der letzten 4 s im Raum, Bodenpunkte zählen nicht), damit sie ein
    Hindernis nicht vergisst, sobald es beim Drehen aus dem 45°-Blickfeld rutscht;
  - **lenken statt nur bremsen:** die nächstgelegene freie Richtung bis ±90°; ist es eng, dreht sie auf der Stelle zur
    einmal gewählten Seite (kein Hin und Her); Richtungen, in die sie gerade nicht schaut, gelten nicht als frei;
  - **Umlaufen:** nach dem Ausweichen geht sie am Hindernis entlang, bis die Richtung zum Ziel frei ist, und schaut
    dabei in die Kurve; neben Kanten dreht sie nicht hinein und geht nah dran langsamer;
  - **Festsitzen erkennen:** 2,5 s vorwärts gewollt und nicht weitergekommen → kurz zurück und frei drehen (nicht beim
    Steuern von Hand – dort hilft sie nur beim Lenken und Bremsen).
  - Hinlaufen gibt erst nach 8 statt 5 s ohne Fortschritt auf, weil ein Umweg sie erst einmal vom Ziel entfernt.
  - Abschaltbar unter Charakter → Persönlichkeit → Verhalten: **„Hindernissen ausweichen“** (Standard an). Aus =
    nur bremsen wie bis 0.32.
- **Schwebende Dinge fallen lassen** (Kollisionsmodus): Doppelklick auf ein Ding in der Luft, „Fallen lassen“ (Taste F)
  fürs gewählte, „Alle fallen lassen“, und der Schalter „Dinge bleiben in der Luft“ lässt beim Ausschalten alles fallen.
- **Geplant** unter System → Erweiterungen: Kacheln mit dem, was als Nächstes kommt, jeweils mit geplanter Version
  (nicht einschaltbar). Ein Test hält die Liste aktuell.
- **„Kopf ruhig“ auch im Handy-Controller** (Menü des Controllers) – für ein ruhigeres Livebild.
- **Gerüst für mehrere Sprachen:** Textkataloge je Sprache (`duckpilot/i18n`, Deutsch als Grundsprache, Lücken
  fallen auf Deutsch zurück), `GET /api/i18n/{sprache}` und `i18n.js` für die Oberfläche. Neue Texte laufen schon
  darüber; Englisch zum Umschalten folgt in 0.34.

### Geändert
- **Interner Schnitt Kern / Motorik / Lab / Körper** als Vorbereitung auf weitere Körper: jedes Modul hat eine
  Schicht (`duckpilot/schichten.py`), ein Test prüft die Import-Regeln (die Motorik kennt weder Gehirn noch Körper,
  das Gehirn keinen bestimmten Körper, das Lab kein Gehirn). Keine neuen Funktionen.
- Große Dateien aufgeteilt: die Laufzeit nach Bereichen (`runtime_kern.py`, `runtime_lab.py`, runtime.py von 1 387 auf
  ≈ 920 Zeilen), die Oberfläche um `pflege.js` und `designsystem.js` (app.js von 99 auf 84 KB).
- **Folg mir:** Statt einer 1,7-m-Figur neben der 25-cm-Ente zeigt der Simulator nur, was die Ente vom Menschen sieht –
  zwei Schuhe mit Knöcheln in echter Größe, nach oben ausgeblendet; die Füße setzen beim Gehen abwechselnd vor.
- Controller: „Kippen = fahren“ heißt jetzt „Kippen = laufen“ – sie läuft; fahren kann sie erst auf Rollen (Zubehör).
- **Gangart laden:** im Physik-Simulator ohne Rückfrage (gefahrlos). Am Roboter heißt die Rückfrage jetzt „Wirklich
  laden? Zum Bestätigen nochmal tippen“ mit dem Hinweis, sie erst auf dem Ständer auszuprobieren (vorher: „Ente auf dem
  Ständer? Nochmal“).

### Behoben
- **Rolle vorwärts in der echten Physik:** mit „Kopf ruhig“ fiel sie nach dem Purzelbaum oft ein zweites Mal um. Die
  Geh-Policy übernimmt mitten in der Rolle (wie am Roboter) und richtet sie selbst auf; der Kopf-Ausgleich störte das.
  Jetzt gibt es eine Landephase ohne Kopf-Stabilisator und ohne Kopfbefehle, bis sie 0,3 s aufrecht steht. Mit
  Pollens Policies nachgemessen: vorher umgefallen, jetzt 6 von 6 Rollen gelandet (≈ 1,9 s), auch mit gedrehtem Kopf.
- **Purzelbaum sah in der 3D-Ansicht falsch aus:** Die Lage des Rumpfs ging als Euler-Winkel an die Oberfläche. Kopfüber
  springen die um 180°, und die Ansicht setzte sie zudem in der falschen Reihenfolge zusammen – die Ente klappte mitten in
  der Rolle sichtbar um. Jetzt kommt die Lage als Quaternion (`state.body_q`) und wird genau so gezeichnet.
- Startbild: wurde es weggeklickt, bevor die Ente verbunden war, gab es einen Skriptfehler beim Start.

### Geprüft
- Ausweichen im einfachen Simulator aus 27 Startlagen gegen Regal, Kiste, Sofa, Hocker und Wände: nie im Möbel,
  nie umgefallen, nie stehen geblieben. Hinlaufen hinter Couchtisch und Kiste mit drei Zufallsständen: 9 von 9
  angekommen, ohne anzustoßen. Laser und Folg mir um eine Ecke, Erkunden je 30 s: ohne Kontakt.
- In der echten Physik mit Pollens Policies aus 8 Startlagen: kein Kontakt, kein Sturz.

### Nicht geprüft
- Am echten Roboter. Dort nutzt das Ausweichen vorerst nur die drei ToF-Sektoren (die den Boden selbst
  herausrechnen); das Punktgedächtnis kommt dazu, sobald die Kopf-Kalibrierung am Gerät geprüft ist – eine falsche
  Blickneigung würde den Boden als Hindernis zeigen.
- Rolle am echten Roboter (dort steuert robotd die Übergabe selbst) und mit BAM-Antrieben.

## 0.32.0 – 2026-10-29

### Neu
- **Controller fürs Handy** (Cockpit → „Controller“): Vollbild im Querformat mit dem **Live-Bild der Kopfkamera** als
  Hintergrund – im Simulator der Entenblick, am Roboter das Kamerabild (verkleinert, damit es durchs WLAN passt).
  - Links Fahr-Stick und „Sprechen“ (halten), rechts vier frei belegbare Tasten (Quaken, Sitzen ↔ Stehen, Kicken,
    Freuen, Tanzen, Purzelbaum …), oben der Not-Aus und „Ton an diesem Gerät“.
  - **Umschauen wie in Street View:** das Bild ziehen dreht den Kopf, am Anschlag dreht sich der Körper mit.
  - **Bewegungssensor:** „Handy = Kopf“ – wohin das Handy zeigt, schaut sie (auch über den Kopfanschlag hinaus,
    dann dreht sie sich mit). „Kippen = fahren“ – nur solange der Daumen auf dem Stick liegt (Totmann).
  - **Vibrieren** bei Stößen, Treffern, Anstoßen und Stürzen – stärker, je fester. Am Android-Handy über den
    Vibrationsmotor, am iPhone blitzt stattdessen der Rand. Ein **Gamepad am PC rüttelt** mit, auch ohne Controller.
- Physik: Erschütterungen von außen (Ding, Hand, Möbel, Stoß) als `state.ruck` {n, Stärke, Quelle}, gemessen am
  Anstieg der Kontaktkraft – nicht an der IMU, die beim Gehen genauso ausschlägt.
- `/api/kamera/bild?breite=…` liefert das Kamerabild verkleinert.

### Sicherheit
- Fahrbefehle verfallen nach 0,35 s: Funkloch, gesperrter Bildschirm oder losgelassener Daumen halten sie an.
- Tasten lösen nur Bewegung, Ausdruck und Laute aus, nie Einstellungen.
- Bewegungssensor und Mikrofon gibt der Browser nur über https frei – am Handy also mit Tailscale.

### Nicht geprüft
- auf echten Handys (Android, iPhone): Bewegungssensor, Vibrieren, Vollbild und Querformat-Sperre
- Rütteln mit einem echten Gamepad
- Kamerabild und Erschütterung am echten Roboter (dort vibriert bisher nur der Sturz)

---

## 0.31.0 – 2026-10-29

### Neu
- **Stoßreihe mit Robustheitsprofil** (Lernen → Training, Karte „Robustheit gegen Stöße“; aus dem Kollisionsmodus
  verlinkt): 48 gleichmäßig verteilte Stöße – 8 Richtungen × 3 Stärken × Rumpf/Kopf – in einer unsichtbaren
  Physik-Welt, rund 7 s für alle. Ergebnis als Tabelle (steht / wackelt / fällt mit Neigung, Wort und Symbol),
  gespeichert als Profil mit Prüfsumme der Policy. Ein älteres Profil lässt sich daneben legen (vorher → jetzt),
  so zeigt sich, ob ein Training sie wirklich stabiler gemacht hat. Jeder Versuch ist auch eine Trainings-Episode
  (`quelle: reihe`). Nur am PC.
  - Mit Pollens Geh-Policy: 42 von 48 bleiben stehen; sie fällt nur bei Stößen an den Kopf (kräftig von vorn,
    vorn-links, links, hinten-links, vorn-rechts; mittel von vorn-links).
- **Zielwurf (Schleuder):** Unter „Werfen“ auf „zielen“ stellen, Ding anfassen und nach hinten ziehen. Zuglänge =
  Tempo (50 cm = 6 m/s), Gegenrichtung = Richtung, Winkel vom Regler. Der Bogen zeigt vorher, ob und wo er die
  Ente trifft („trifft Kopf mit 2,9 m/s (0,17 N·s)“). `Esc` bricht ab.
- Wurf- und Roll-Episoden halten den ersten Treffer fest: Körperteil, Punkt, Aufpralltempo, Impuls.

### Behoben
- Stöße wirkten einen Physik-Teilschritt zu kurz, also etwa 12 % schwächer als angegeben.

---

## 0.30.2 – 2026-10-29

### Neu
- **Dinge in der Luft abstellen:** Schalter „Dinge bleiben in der Luft, wo ich sie loslasse“. Ohne Schwung
  losgelassen bleibt ein Ding dann stehen, wo es ist – zum Beispiel ein Ball auf Kopfhöhe, gegen den sie läuft,
  oder ein Kissen als Hindernis. Wieder anfassen oder wegräumen löst es. Mit Schwung wird weiter geworfen.
- **Landepunkt sichtbar:** Beim Halten zeigen Lot und Ring, wo das Ding landen würde – auf dem Boden oder einem
  Möbel senkrecht darunter (am Zeiger „landet auf 45 cm“).

---

## 0.30.1 – 2026-10-29

### Neu
- **Sie beschwert sich beim Spielen** – ab und zu, nicht jedes Mal (35–75 % je nach Stärke, nach einem Sturz 80 %,
  höchstens eine je Stoß, mindestens 5 s Abstand): ein Quak, eine Kopfgeste wie „grummelig“, „Wer sagt das?“ oder
  „nö“, manchmal ein Satz wie „Hey!“, „Na hör mal!“, „Hey, nicht ziehen!“ oder nach dem Aufstehen „Puh. Quak!“.
  Passend zum Charakter (Goofy: „Wheee – nochmal?“, ruhig: „Hm.“). Gesten nur mit Kopf und Schnabel, frühestens
  1,2 s nach dem Stoß; gemessen bleibt sie dabei stehen (12 von 12). Stimmung, Persönlichkeit, Gedächtnis und
  Erfahrungsnetz bleiben unverändert. Abschaltbar: „Beschwert sich beim Spielen“.
- **Wegräumen wie in CAD:** Das zuletzt angefasste Ding ist gewählt (blauer Pfeil, Zeile im Bedienfeld).
  `Entf` oder „Wegräumen“ nimmt es weg.

### Behoben
- Ein Ding direkt neben der Ente ließ sich nicht anfassen („Würfel ist 0.28 m von der Hand weg“): Die Hand
  erschien pauschal 30 cm höher, sobald das Ziel weniger als 20 cm vom Rumpf entfernt war. Jetzt nur noch, wenn
  sie wirklich in der Ente stecken würde.

### Sicherheit
- Im Stopp-Fenster (Mikrofon offen) quakt und spricht sie nicht, damit die Spracherkennung „Stopp“ hört. Nicht
  nach Not-Aus, nicht hochgehoben, nicht in Ruhe.

---

## 0.30.0 – 2026-10-29

### Geändert
- **Kollisionsmodus bedient sich wie CAD und Robotik-Simulatoren** (Vorbilder: Onshape, SketchUp, MuJoCo
  `simulate`, Gazebo „Mouse Drag“):
  - Zeigen bewegt nichts mehr. Was sich anfassen lässt, leuchtet auf, der Zeiger wird zur Hand, und ein Hinweis am
    Zeiger sagt, was Ziehen dort tut. Die schwebende Hand, die schon beim Bewegen schubste, entfällt.
  - Dinge gleiten beim Ziehen in ihrer Höhe über den Boden. Mit Umschalttaste oder am blauen Pfeil darüber geht es
    nur senkrecht (blaue Achse). Lot, Bodenring und Maße am Zeiger (Höhe, Weg).
  - Werfen: Richtung und Tempo aus dem Schwung über den Boden, Winkel aus dem neuen Regler „Wurfwinkel“ (0–60°).
    Der Bogen zeigt Landepunkt, Tempo und Weite. Ohne Schwung loslassen legt ab.
  - Die Regler „Abstand der Hand“ und die Ebene quer zur Kamera für Dinge entfallen.

### Neu
- **Ente ziehen:** an einer Stelle anfassen und ziehen. Sie hängt dort an einer Feder zur Maus (60 N/m, kritisch
  gedämpft, höchstens 6 N – weniger als ihr Gewicht). Gestrichelte Feder, Kraft am Zeiger. Episoden „zug“ mit
  Körperteil fürs Training; zählt als Spiel (kein Ärger).
  - Gemessen mit Pollens Policies: Zupfen am Rumpf lässt sie kaum wackeln. Seitwärts oder nach hinten am Kopf
    läuft sie der Hand nach, statt zu fallen. Bein hochziehen oder Rumpf anheben wirft sie um (nach 0,7–0,9 s).

### Behoben
- Ein frisch hingelegtes Ding war unsichtbar und ließ sich nicht anfassen, bis sich irgendetwas bewegte (ruhende
  Dinge kamen nie im Strom an). Jetzt kommt die Lage auch aus dem Status, und nach dem Ausrollen wird die Endlage
  geholt.
- Bälle rollten nach einem leichten Wurf mehrere Meter (Rollreibung 0,0002 m). Jetzt Rollwiderstand 0,1: aus
  1 m/s rollt der Ball 0,8 m, der Wasserball 1,4 m.
- Bei langsamer 3D-Ansicht wurde ein Wurf manchmal als Ablegen erkannt. Der Schwung zählt jetzt über 150 ms.

### Nicht geprüft
- BAM-Antriebsmodell.

---

## 0.29.0 – 2026-10-29

### Neu
- **Werfen aus der Mausbewegung:** Loslassen wirft ein Ding so, wie die Maus zuletzt ging, aus Sicht der Kamera.
  Seitwärts bleibt flach, nach oben fliegt es vom Bildschirm weg in den Raum (bei 30° Kameraneigung etwa 41°,
  von oben flacher, von der Seite steiler), diagonal alles dazwischen.
- **Flugbogen:** Beim Halten und Schwingen zeigt ein gestrichelter Bogen mit Aufschlagring, wo das Ding landen
  würde, daneben Höhe, Tempo und Winkel.
- Neben der Hand steht, wie hoch sie bzw. das gehaltene Ding über dem Boden ist.

### Geändert
- **Die Hand geht nicht mehr durch die Ente.** Sie ist jetzt ein Körper in der Physik, der dem Zeiger mit einer
  Feder folgt (17 ms). An der Ente drückt sie mit höchstens 3 N, statt einzudringen (gemessen höchstens 5 mm, vorher
  bis 35 mm an Hüften und Beinen). Ein blasser Ring zeigt, wohin der Zeiger will.
- **Gehaltene Dinge** hängen fest an der Hand (Weld in MuJoCo) und gehen ebenfalls nicht durch die Ente; damit
  anstoßen schubst sie.
- **Hand quer zum Blick statt in fester Höhe:** Die Hand bewegt sich auf einer Ebene quer zur Kamera durch die Ente
  (oben auf dem Bildschirm ist der Kopf), ein gehaltenes Ding auf einer Ebene durch sich selbst (Maus hoch hebt
  es). Mausrad beim Halten, Umschalttaste und Rad, `[`/`]` oder der Regler „Abstand der Hand“ schieben die Ebene
  näher oder weiter. Der Regler „Höhe der Hand“ entfällt.
- Die Hand gleitet zwischen zwei Zeiger-Meldungen, statt im 30-Hz-Takt zu springen, und wird in der Ansicht weich
  nachgezogen.
- Klick ins Leere greift nicht mehr ins Nichts (keine Fehlermeldung „Nichts in Reichweite“).

### Behoben
- Die Hand ging durch Hüften und Beine der Ente: Das Kontaktbit stand nur an den Formen, nicht an den Körpern.

### Nicht geprüft
- BAM-Antriebsmodell. Ob 3 N richtig sind: Langsames Drücken schiebt sie, kippt sie aber nicht um; schnelle
  Wische werfen sie manchmal um.

---

## 0.28.1 – 2026-10-29

### Neu
- **Kollisionsmodus mit Hand:** Die Maus ist eine Hand im Raum (Kugel mit Ring und Lot). Fährt sie gegen die
  Ente, schubst sie sie aus der Richtung, aus der sie kommt, so kräftig, wie sie schnell ist (höchstens 2,5 m/s).
  Höhe 3 bis 30 cm über Regler oder `[` und `]`.
- **Dinge in die Wohnung legen:** Ball, Würfel, Kegel, Wasserball, Kissen und Klotz. Wählen, auf den Boden
  klicken, greifen, ziehen, werfen oder damit gegen die Ente stoßen.
- Kamera im Kollisionsmodus: rechte Maustaste dreht, Mausrad zoomt; am Touchscreen drehen zwei Finger.
- Berührungen mit der Hand werden als Episoden mit Körperteil gespeichert.

### Geändert
- Das Bedienfeld des Kollisionsmodus ist kleiner und steht unten links: Dinge und Höhe der Hand sind sichtbar,
  Hilfe, Tasten ohne Maus und „steht selbst auf“ liegen unter „Hilfe, ohne Maus, Aufstehen“. Fahrwerte und die
  Zeile „Klick hinschauen …“ sind im Modus ausgeblendet. Vorher lag das Feld bei 1100 px Fensterbreite über der
  Ente, und die Hand ging dort aus.

### Behoben
- Greifen ging mit der Maus kaum: Die Hand schwebte 12 cm hoch, und der Zeiger auf einem Ding traf die
  Handebene gut 20 cm davor. Jetzt greift die Hand über einem Ding in seine Mitte.
- **Sie stand nach einem Sturz nicht auf.** Ursache: Sie lag mit fast stromlosen Motoren, und die Policy übernahm
  ohne Übergang aus der liegenden Haltung. Jetzt wie in Pollens `robotd`: schwach fallen (ein Viertel der Kraft),
  warten bis sie liegt, in 0,6 s in die Grundstellung, Policy neu starten. Gemessen mit Pollens Policies aus der
  aufgezeichneten Sturzlage: vorher 0 von 6 Versuchen, jetzt 6 von 6 (etwa 1,8 s). Aus Rücken-, Bauch- und
  Seitenlage und kopfüber: 30 von 30.
- Klappt das Aufrichten nicht, legt sie sich nach 6 s wieder hin und versucht es neu (bis zu dreimal).

### Sicherheit
- Unverändert: Not-Aus, 120 s Sperre, stromlos und hochgehoben verhindern das Aufstehen.

### Nicht geprüft
- BAM-Antriebsmodell (gemessen mit MuJoCo-Positionsantrieben).
- Am echten Roboter (den Kollisionsmodus gibt es dort nicht; das Aufstehen nach Sturz ja).

---

## 0.28.0 – 2026-10-29

### Neu
- **Kollisionsmodus im Simulator** (Cockpit → „Spielen“, nur mit echter Physik):
  - Die Ente antippen schubst sie, Wischen schubst sie in Wischrichtung (je länger, desto kräftiger). Kopf, Rumpf
    und Beine sind einzeln zu treffen.
  - Ball und Würfel greifen, ziehen und loslassen – geworfen mit dem Schwung der Hand. „Auf sie werfen“ und „zu
    ihr rollen“ zielen von selbst.
  - Alles auch ohne Maus über Tasten: Stärke, „Schubsen von“ vorn/hinten/links/rechts, Werfen, Rollen, Wegräumen.
  - Grenzen: Stoß höchstens 0,6 N·s, Wurf 6 m/s, Rollen 3 m/s, Dinge bleiben in der Wohnung.
  - Am echten Roboter gibt es den Modus nicht, über MCP auch nicht.
- **Trainingsdaten aus dem Spiel:** Jeder Stoß und Wurf wird als Episode gespeichert
  (`kollision/episoden.jsonl`: Reiz, Zustand vorher und nachher, Zeitreihe, Ausgang steht/wackelt/fällt/steht
  wieder auf). Das Lernen am PC nutzt die gemessenen Stöße als Störungen.
- **Selbst aufstehen nach einem Sturz**, mit Stopp-Fenster: Oben erscheint „Gestürzt“ mit Countdown, das
  Mikrofon ist kurz offen. „Stopp“ oder „Liegen lassen“ halten sie liegen, sonst steht sie auf (bis zu drei
  Versuche). Einstellbar unter System → Einstellungen → Körper: an/aus und 2 bis 10 s.
- Designsystem-Seite: Abschnitt „Raster“ mit Spalten und Mustern, live aus denselben Klassen.
- Erfahrungsnetz: Knoten lassen sich auch über eine Auswahlliste ansehen (ohne Maus).
- `docs/barrierefreiheit.md`: Stand der Barrierefreiheit, Prüfweg und bekannte Lücken.

### Geändert
- **Carbon konsequent:**
  - Abstände heißen und messen wie in Carbon (`--spacing-01` bis `-13`). Den 6-px-Abstand, den Carbon nicht kennt,
    gibt es nicht mehr.
  - Dauern sind Carbon-Tokens (`--duration-fast-01` bis `-slow-02`).
  - Farben kommen nur noch aus Bedeutungs-Tokens; über 130 freie Farbwerte sind ersetzt.
  - Schnitte nur 300/400/600, Knöpfe in 400 wie Carbon. Kleinste Schrift 12 px statt 10 px. Symbole 16/20/24/32 px.
  - Ein Test schlägt an, sobald ein freier Wert auftaucht.
- **Raster:**
  - Es wächst jetzt fließend bis 1584 px (Carbon max) und steht darüber mittig. Vorher endete es bei 1232 px
    links, und rechts blieb im Vollbild viel frei.
  - Die Reiter stehen auf derselben Kante wie der Inhalt.
  - Umbruchpunkte nur noch nach Carbon: 672, 1056, 1312 und 1584 px. Darunter wird die Leiste zur Leiste unten.
  - Die Sprungleiste der Einstellungen gibt es ab 1056 px.
- **Sicherheitsregel geändert (Entscheidung):** Nach einem Sturz steht sie selbst wieder auf, auch am
  Roboter. Bei der Größe der Microduck besteht keine Verletzungsgefahr. Dafür gibt es das Stopp-Fenster.

### Barrierefreiheit (WCAG 2.2 AA)
- axe-core findet auf allen Seiten keine Verstöße mehr (vorher: Kontraste, Überschriften, Landmarken,
  Formular-Beschriftung, scrollbare Bereiche).
- Neu: Sprunglink „Zum Inhalt springen“ und ein Fenstertitel je Seite. Zeichenflächen haben `role="img"`.
- Felder, Schalter und Regler haben mindestens 3 : 1 Kontrast zum Grund (Nicht-Text-Kontrast).
- Bei 320 px scrollt keine Seite mehr waagrecht. Gelenknamen werden bei größeren Textabständen nicht mehr
  abgeschnitten.
- Der Fokus ist auch in Feldern mit Fehler deutlich und verschwindet nicht unter der Leiste unten.
- Der Kontrastmodus von Windows bekommt echte Ränder.

### Sicherheit
- Weiter gilt: Der Not-Aus gewinnt immer. Nach einem Not-Aus bewegt sie sich 120 s nicht von selbst, auch kein
  Aufstehen. Hochgehoben bewegt sie sich nicht.
- Spiel-Stöße verändern weder Stimmung, Persönlichkeit, Gedächtnis noch Erfahrungsnetz (höchstens ein kurzer
  Schreck).

### Nicht geprüft
- Ob sie mit Pollens echten Policies Stöße abfängt und wieder hochkommt. Hier liefen nur Test-Policies, mit denen
  sie nicht stehen kann.
- Barrierefreiheit mit echten Screenreadern (NVDA, JAWS, VoiceOver).
- Das kurz offene Mikrofon im Stopp-Fenster am Handy.

---

## 0.27.2 – 2026-10-29

### Geändert
- **Ein Raster für alle Seiten** nach Carbons 2x Grid. Vorher hatten die Seiten rund 20 eigene Raster mit sechs
  verschiedenen Umbruchpunkten. Viele davon füllten nach Mindestbreite auf („so viele Kacheln wie passen“), deshalb
  sprangen die Kachelbreiten von Seite zu Seite. Jetzt gilt:
  - Ein Container je Seite (`.page-inner`, höchstens 1232 px). Die Spaltenzahl richtet sich nach seiner Breite und
    nicht nach dem Fenster.
  - 16 Spalten ab 1024 px, 8 ab 640 px, darunter 4. Überall 16 px Abstand.
  - Kacheln belegen ganze Spalten in festen Mustern: Hälften (8/4/4), Kacheln (4 je Reihe, auf dem Tablet 2, auf
    dem Handy 1), kleine Kacheln (4/4/2), Haupt + Seite (10 + 6, darunter übereinander) und Sprungleiste + Inhalt
    (Einstellungen).
  - Gesten, Hub-Tricks, Erweiterungen und Sprachmotoren stehen jetzt in Viererreihen. Vorher waren es je nach Seite
    3 oder 6 je Reihe.
  - Alltag, Persönlichkeit, Gespräch und Gedächtnis teilen sich die Hälften. Akrobatik, Parcours und Zustand nutzen
    Haupt + Seite.
  - Gemessen bei 1920, 1440, 1176, 1100, 900, 700, 600 und 390 px: alle Kachelkanten liegen auf Spaltenlinien.
- Die Seite „Designsystem“ zeigt das Raster live mit Spalten und Mustern.
- Die Sprungleiste der Einstellungen bleibt bis 640 px Inhaltsbreite sichtbar. Vorher verschwand sie unter 900 px
  Fensterbreite.

### Nicht geprüft
- Das Raster nutzt Container-Abfragen und `:nth-child(… of …)`. Das können Edge/WebView2 und aktuelle Browser
  (Chrome ab 111, Safari ab 16, Firefox ab 113). Sehr alte Handy-Browser zeigen alle Kacheln untereinander.

---

## 0.27.1 – 2026-10-29

### Geändert
- Die Einstellungen haben dieselbe Breite und dasselbe 12-Spalten-Raster wie alle anderen Seiten: 2 Spalten für die
  Sprungleiste, 10 für den Inhalt. Vorher war der Inhalt auf 760 px begrenzt und wirkte schmaler. Lange Hilfetexte
  bleiben auf höchstens 80 Zeichen begrenzt.
- Fehler von Claude erscheinen im Gespräch als Klartext mit Handlungshinweis, zum Beispiel „Claude nimmt den
  API-Schlüssel nicht an. Unter System → Einstellungen → Claude neu eintragen.“ Die technische Meldung steht weiter im
  Protokoll. Klartexte gibt es für ungültigen Schlüssel, fehlende Berechtigung, aufgebrauchtes Guthaben, zu viele
  Anfragen, Überlastung und fehlende Verbindung.

### Behoben
- Hirnaktivität: Kamen die ersten Daten, während das Dashboard verborgen war, klebten alle Knoten am linken Rand.
  Jetzt verteilen sie sich neu, sobald die Fläche ihre Größe ändert.

---

## 0.27.0 – 2026-10-29 · Bereit für GitHub

Ausführliche Release-Notes zur ersten öffentlichen Fassung: [docs/releases/v0.27.1.md](docs/releases/v0.27.1.md).

### Neu
- **Pollens Robotermodell wird nachgeladen statt mitgeliefert** (`duckpilot/modell`). Pollens 3D-Teile stehen unter
  CC BY-NC-SA 4.0 (nicht-kommerziell), deshalb verteilt duckpilot sie nicht selbst. Beim ersten Start geschieht
  Folgendes:
  - duckpilot lädt genau die 41 gebrauchten Dateien (rund 22 MB) aus
    [pollen-robotics/microduck_rl](https://github.com/pollen-robotics/microduck_rl).
  - Es gilt ein fester Stand (`b02fdea`), jede Datei wird gegen ihre sha256-Prüfsumme aus `modell/quellen.json`
    geprüft. Passt eine Prüfsumme nicht, bricht der Download ab und es wird nichts gespeichert.
  - Daraus entstehen im Datenordner das Modell für die 3D-Ansicht (`ansicht.dpm`, byte-gleich mit dem bisher
    mitgelieferten) und, wenn MuJoCo installiert ist, das Physik-Modell (`physik.xml`). Dieses nutzt Pollens STL als
    Kollisionskörper und verhält sich wie bisher.
  - Bis das Modell da ist, zeigt die 3D-Ansicht die einfache Ente, der Physik-Simulator bleibt aus.
- Pollens Modell lässt sich auch ohne Oberfläche laden: `python -m duckpilot.modell` (mit `--neu` erzwingt es einen
  frischen Download).
- „Physik laden“ holt das Physik-Modell mit, falls es noch fehlt.
- Mit `DUCKPILOT_OFFLINE=1` lädt duckpilot nichts nach. Die Tests setzen das immer.
- **Über** (System → Einstellungen):
  - Hinweis, dass duckpilot ein freies, nicht-kommerzielles Hobbyprojekt ist, ohne Verbindung zu Pollen Robotics
    oder Hugging Face.
  - Stand von Pollens Modell (mitgeliefert, geladen oder fehlt), mit „Von GitHub neu laden“ (nur am PC).
  - Alle Quellen mit Lizenz verlinkt.
- `LICENSE` (Apache-2.0) und `NOTICE` mit Herkunft, Lizenz und Änderungen aller fremden Bestandteile. In der README
  steht der neue Abschnitt „Rechtliches und Quellen“.
- **`tools/export_public.py`** baut die öffentliche Fassung in einen leeren Ordner:
  - ohne Pollens Modell, ohne private Bilder und ohne Arbeitsnotizen;
  - mit eigenem, schlichtem Icon und Startbild (`tools/make_public_art.py`);
  - mit `.gitignore` und einer GitHub-Prüfung (ruff, Modell laden, pytest);
  - zum Schluss mit einem Geheimnis-Scan nach API-Schlüsseln, Tokens, privaten Schlüsseln, Windows-Benutzerpfaden
    und E-Mail-Adressen. Findet er etwas, bricht der Export ab.
- Tests: Prüfsummen, Abbruch bei falscher Prüfsumme, kein doppelter Download, Offline-Modus, Rückfall auf das Paket,
  Endpunkte. Ein Vergleich gegen Pollens Originaldateien zeigt: 3D-Modell byte-gleich, Physik mit gleicher Masse und
  Kollisionskörpern.

### Geändert
- `numpy` ist jetzt eine Grundabhängigkeit, weil es beim ersten Start das 3D-Modell baut.
- Die 3D-Ansicht holt das Modell unter `/api/modell/ansicht.dpm`. Sobald es fertig gebaut ist, tauscht sie die
  einfache Ente gegen das Originalmodell, ohne dass die Seite neu geladen werden muss.
- Physik-Tests suchen das Modell über `core.model_xml()` und werden übersprungen statt rot, wenn es noch nicht
  geladen ist.

### Sicherheit
- „Modell laden“ geht nur vom PC aus (`remote.PC_ONLY`), nicht vom Handy.
- Dateinamen aus der Quellenliste werden streng geprüft (nur `assets/…stl` und `…xml`, keine Pfade), höchstens 8 MB
  je Datei.

---

## 0.26.0 · Folg mir

### Neu
- **Folg mir:** Die Ente läuft dir hinterher.
  - Sie hält etwa 0,55 m Abstand und kommt nie näher als 0,35 m, sonst macht sie einen kleinen Schritt zurück.
  - Sie schaut zu dir hoch, sucht dich, wenn du aus dem Blick bist, und hört nach 20 s ohne Menschen von selbst auf.
  - Im Simulator und in der Physik führt die Maus oder der Finger eine Menschen-Figur über den Boden. Das nutzt
    denselben Zeiger-Baustein wie der Laser, beide schließen sich gegenseitig aus.
  - Auslösen über den Knopf „Folg mir“, per Sprache mit „folg mir“, „komm mit“ oder „folg mir 2 Minuten“, als Werkzeug
    `mir_folgen` (auch über MCP).

### Geändert
- Cockpit: Bei mittlerer Fensterbreite (901–1400 px) zeigen die Werkzeuge nur Symbole, damit sie die Zustandsanzeige
  nicht mehr überdecken.

### Nicht geprüft
- Am echten Roboter fehlt noch die Erkennung, *dass* ein Mensch im Kamerabild ist. Wer es ist, wird dabei nicht
  erkannt.

---

## 0.25.0 · Erfahrungsnetz und Hirnaktivität

### Neu
- **Erfahrungsnetz:** Die Ente verknüpft, was zusammen passiert.
  - Knoten sind Personen (nur angelernte), Orte, Dinge, Tageszeit und Wochentag, Tätigkeiten, Gefühle,
    Sinneseindrücke (Stimme gehört, angestoßen, hochgehoben, gestürzt) sowie Lob und Kritik.
  - Lernen nach Hebb: Was gleichzeitig aktiv ist, verbindet sich stärker (Δw = η·s·aᵢ·aⱼ·(1−w)).
  - Unbenutzte Verbindungen verblassen mit einer Halbwertszeit von 14 Tagen. Nach einer Stunde Ruhe festigt und
    räumt das Netz auf.
  - Erinnern durch Aktivierungsausbreitung in zwei Schritten: Claude bekommt bei jeder Nachricht einen kleinen
    Ausschnitt dessen, was ihr gerade einfällt.
  - **Prägung:** Erfahrung verschiebt das eingestellte Temperament um höchstens ± 0,1. Das beginnt erst nach 40
    Erlebnissen, die volle Wirkung kommt nach 200.
  - Das Netz ist ein kleines, nachvollziehbares Assoziationsnetz, kein Deep Learning und kein Bewusstsein. Claude
    selbst lernt dabei nichts dazu.
- **Hirnaktivität** im Zustand-Dashboard:
  - Das Netz als lebendiger Graph: aktive Knoten leuchten, frisch gestärkte Verbindungen blitzen kurz auf.
  - Ein Klick auf einen Knoten zeigt, womit er verknüpft ist und warum, und bietet „Vergessen“ an.
  - Die Farben der vier Gruppen sind für alle Paare auf Unterscheidbarkeit geprüft, die Namen stehen immer am Knoten.
- **Einheitliches Raster:**
  - 12 Spalten mit einem Abstand für alle Seiten, Muster 6/6, 8/4 und 4/8.
  - Kacheln einer Reihe sind gleich hoch, eine einzelne letzte Kachel geht über die ganze Breite.
  - Umbrüche bei 1100 und 900 px.

### Sicherheit
- Das Netz lernt nur bei eingeschaltetem Gedächtnis und bleibt lokal.
- Personen-Knoten gehen nie an ein Handy, und in Antworten an ein Handy fallen der Ente keine Personen ein.
- „Alles vergessen“ leert auch das Netz. „Netz zurücksetzen“ verlangt zwei Klicks.

---

## 0.24.0 · Oberfläche aus einem Guss, NFC-Tags

### Neu
- **NFC-Tags** (Alltag): Ein Tag wird an seiner Seriennummer erkannt, beschrieben werden muss er nicht. Ihm ist ein
  Satz zugeordnet („setz dich“, „tanz“ …).
  - Berühren schickt den Satz durch dieselbe Verarbeitung wie einen getippten Befehl, mit allen Sicherheitsregeln.
  - Gelesen wird am Handy mit Chrome unter Android (Web NFC, nur über https, also mit Tailscale). Zum Ausprobieren
    gibt es „Auslösen“.

### Geändert
- **Design-Durchgang** nach einer unabhängigen Design-Kritik:
  - Jede Seite beginnt mit einem Satz, lange Erklärungen stehen zugeklappt darunter.
  - Einheitliche Titel: Kacheln 16 px halbfett, Abschnitte 20 px.
  - Farben mit fester Bedeutung: gewählt oder an ist überall Schnabel-Orange, Grün steht nur für Zustand, Blau nur für
    Messwerte. Links sind hell und unterstrichen. Für alles Aufklappbare gibt es ein Muster.
  - Einstellungen mit Sprungleiste links. Die Schlüssel-Warnung erscheint nur noch, wenn es wirklich keinen gibt.
  - „Gespräch“ (Zuhören, Antworten, Plaudern, womit sie denkt) liegt jetzt unter Charakter, der Name der Ente unter
    Persönlichkeit.
  - Erweiterungen als ruhige Kacheln. Parcours: links bauen, rechts 3D.
  - Hub-Fehler in Klartext. Am Handy stehen Namen unter den Symbolen.

---

## 0.23.0 · Community-Tricks, Bewegungen und Töne wie bei Pollen

### Neu
- **Community-Tricks** (System → Erweiterungen): Salto, Flamingo, Moonwalk, Verbeugung und andere von
  Microduck-Besitzern.
  - „Prüfen“ spielt einen Trick unsichtbar in Pollens MuJoCo-Modell durch. Das Urteil lautet „sicher“,
    „akrobatisch“ oder „bleibt liegen“.
  - Am Roboter läuft nur Geprüftes, „bleibt liegen“ nur nach „Trotzdem zeigen“.
- **Lernen in drei Schritten:** Was soll sie lernen? → Wo und wie? → Lernen starten. Dazu ein Satz, was gleich passiert,
  und ein großer Start-Knopf. Zeigt ein Parcours-Test, dass sie es noch nicht kann, wird „Jetzt lernen“ zum
  Hauptknopf.

### Geändert
- **Bewegungen wie am Roboter**, abgeglichen mit Pollens Code (robotd, microduck_emotions):
  - Gelenkziele werden wie in robotd geglättet (Kopf 0,5, Beine 0,7).
  - Fahr-, Kopf- und Haltungsbefehle laufen als Rampe in die Policy (0,2 je Takt bei 50 Hz).
  - Ausgabe-Faktor 0,9. Drehen höchstens mit 1,0 rad/s, wie trainiert.
  - Größerer Kopfbereich: Hals bis −1,1, Nicken ±1,1.
  - Pollens Emotionen laufen als Einlage in Originalgröße und nur im Stehen.
  - Während eines Ausdrucks folgt der Kopf verzögert wie am Roboter.
- **Töne wie bei Pollen:**
  - Die Stimmbank hat 10–12 Varianten je Ton und keine zufällige Verstimmung mehr.
  - Ein neuer Laut beendet den vorigen.
  - Alle Töne werden vorgeladen, der erste kommt nicht mehr zu spät.

### Behoben
- Purzelbaum und Stürze zappelten in der Physik und gelangen oft erst im zweiten Anlauf. Ursache war die fehlende
  Glättung der Gelenkziele.

### Nicht geprüft
- Am echten Roboter gehen kleine Fahrbefehle ohne Totzonen-Anhebung raus. Das muss am Gerät gemessen werden.
- Emotions-Töne kommen am Roboter noch aus dem PC.

---

## 0.22.1

### Behoben
- **Neustart unter Windows hing:** Die Startmeldung enthielt ein Emoji, und beim Ausgeben in die Windows-Codierung
  cp1252 stürzte der neue Prozess ab. Ausgaben können jetzt nie mehr abstürzen.
- **Purzelbaum in der Physik:** Kopfüber zählte sofort als Sturz, das brach Purzelbaum und Tricks mittendrin ab. Jetzt
  hat sie während solcher Bewegungen Zeit zum Landen.
- Parcours: „1×, 2×, 4×“ ist das Abspieltempo der Wiederholung. Das steht jetzt dabei, ebenso „Durchgang 1 von 3“.

## 0.22.0 · duckpilot als MCP-Server

### Neu
- **MCP-Server** unter `POST /mcp` (Streamable HTTP), damit Claude Desktop, Claude Code oder eigene Agenten die Ente
  steuern können.
  - Standardmäßig aus, nur vom PC selbst, nur mit eigenem Schlüssel (`dp_…`) aus dem Tresor des Betriebssystems.
  - Freigegeben sind 23 ausgewählte Werkzeuge (seit 0.26: 24) für Bewegung, Ausdruck und Status. Personen, Kamera,
    Gedächtnis-Schreiben, Training und Einstellungen sind nie dabei.
  - Jeder Aufruf erscheint in der Oberfläche als „Von außen (MCP)“.
- Brücke für Claude Desktop: `python -m duckpilot.mcp_bridge`. Der Schlüssel kommt aus dem Tresor, nicht aus der
  Konfiguration.
- Startprotokoll `neustart.log` im Programmordner.

### Sicherheit
- Der MCP-Server prüft die Herkunft der Anfragen (Origin), damit fremde Webseiten ihn nicht über DNS-Rebinding
  erreichen.

---

## 0.21.2

### Behoben
- Fehler 400 „Invalid signature in thinking block“: Denkblöcke früherer Runden waren an einen inzwischen geänderten
  Systemtext gebunden. Sie werden jetzt vor jeder neuen Runde entfernt. Lehnt die API den Verlauf trotzdem ab,
  versucht duckpilot es einmal bereinigt und notfalls ohne Verlauf.
- Pollens Skills, App-Moves, Hub-Tricks und Vorführungen haben jetzt passende Laute.
- Zustand, Ereignisse und Antworten wurden gleichzeitig auf dieselbe Verbindung geschickt. Scheiterte das, fiel das
  Fenster still aus der Verteilerliste. Jetzt sendet je Verbindung immer nur eine Aufgabe.

## 0.21.1

### Behoben
- Ein neues App-Icon wurde nicht angezeigt, weil Browser und Windows Symbole nach Adresse bzw. Pfad zwischenspeichern.
  Icons bekommen jetzt eine Prüfsumme in der Adresse, und die eigenen Verknüpfungen werden nachgezogen.

## 0.21.0 · Laserpunkt, weniger Tokens, aufgeräumte Architektur

### Neu
- **Laserpunkt folgen:** Die Ente hält 12 cm Abstand zum Punkt, sucht ihn erst mit dem Kopf, dann mit dem Körper, und
  hört nach 15 s ohne Punkt auf.
  - Im Simulator ist die Maus der Pointer.
  - Am Roboter findet `laser.py` den roten Punkt im Kamerabild: klein, hell, rot. Große rote Flächen wie der Ball
    zählen nicht.
- Verbrauchszähler für Claude in den Einstellungen.

### Geändert
- **Weniger Tokens:**
  - Werkzeuge und Systemtext bleiben 1 h im Cache, dazu eine rollende Cache-Marke auf dem Verlauf.
  - Werkzeug-Ergebnisse werden gekürzt.
  - Kurze, eindeutige Befehle erledigt duckpilot ohne Claude.
- **Architektur:**
  - Der Server ist aufgeteilt in `runtime.py`, `security.py` und Routen-Module mit `register(app, runtime)`.
  - Hintergrund-Aufgaben laufen nur noch über `aio.spawn`.
  - ruff-Regeln, Leitplanken-Tests (`tests/test_codebase.py`) sowie `ARCHITECTURE.md` und `CLAUDE.md` für Mitwirkende.
- Handys bekommen 10 statt 20 Zustandsbilder pro Sekunde, ein langsames Gerät bremst die anderen nicht mehr.

### Behoben
- Abgeschnittene Werkzeugaufrufe ließen einen kaputten Verlauf zurück (Fehler 400 „tool_use ohne tool_result“). Der
  Verlauf wird jetzt vor jeder Anfrage repariert.
- Die einfache Steuerung las „wiederhole“ als „hol“.
- Probeläufe in der Physik verhielten sich anders als die sichtbare Ente. Jetzt melden sie auch, ob eine Bewegung
  überhaupt sichtbar ist.
- „quaaak!“ spielte ein schrilles 3-Sekunden-Jauchzen.

---

## 0.20.6 · Aufräum-Durchgang

Drei unabhängige Prüfungen: Bewegungen in allen Ausgangslagen, Code, Oberfläche auf PC und Handy.

### Sicherheit
- Der Sturz-Reflex ließ die Ente auch nach einem Not-Aus, hochgehoben oder in Ruhe selbst aufstehen. Das passiert
  nicht mehr.
- Ein laufendes Aufstehen bricht ein Not-Aus jetzt ab.
- Ein Wechsel des Körpers behält Sperre und Ruhemodus.
- „Wer ist da“ verrät einem Handy keine Namen mehr.

### Behoben
- Befehle, die gerade nicht laufen können, werden sofort ehrlich abgelehnt, statt „gestartet“ zu melden.
- „hingehen“ gibt nach 5 s ohne Fortschritt auf.
- Im Sitzen bleiben Kopf-Gesten im Sitzen.
- Neustart: Der neue Prozess startet zuerst und wartet auf den freien Port.
- Handy: Die Reiterleiste verdeckte den Seitenanfang, die Training-Seite war zu breit.

## 0.20.5

### Behoben
- **Totzone von Pollens Geh-Policy:** Unter etwa 0,2 m/s Gehen und 0,8 rad/s Drehen auf der Stelle steht die Policy
  still. Das wurde auf einem Windows-PC gemessen. Der Physik-Körper hebt gewollte Bewegungen jetzt darüber.

## 0.20.4

### Behoben
- Das Mikrofon öffnete sich auch nach getippten Befehlen.
- Annähern: Das Ziel wird jetzt geglättet, das Mindesttempo beachtet. Wer 5 s nicht näher kommt, gibt auf.
- Tritt: Die Ente tritt, sobald der Ball in Reichweite ist, und sucht ihn sonst.
- Kopf ruhig in der Physik: Vor- und Zurück wird jetzt richtig ausgeglichen, Kopf und Hals werden direkt gestellt.

## 0.20.1 bis 0.20.3

### Neu
- Beenden-Knopf wie bei Windows: Neu starten, Im Hintergrund weiterlaufen oder Beenden.
- Hinweis, wenn eine neue Version bereitliegt.
- Verhalten „Ball schießen“: Die Ente geht die letzten Zentimeter selbst.

### Behoben
- Aus der Ruhe heraus brach das Aufstehen wartende Befehle ab. Das galt auch, wenn Claude `power stand_up` aufrief.
- Ein Tritt aus dem Stand ins Leere.
- Der Simulator-Akku lud nie nach.
- Das „?“ im HUD überdeckte einen Messwert.

---

## 0.20.0 · Kostenlos lernen, Sehen, Personen, Tailscale

### Neu
- **Training an drei Orten:**
  - *Dieser PC*: kostenlos. Eigenes PPO-Nachtraining, die Physik rechnet auf dem Prozessor, das Netz auf der
    Grafikkarte (auch AMD über ROCm-PyTorch für Windows).
  - *Kaggle*: kostenlos, etwa 30 GPU-Stunden pro Woche, mit Pollens Original-Training.
  - *Hugging Face Jobs*: bezahlt.
  - Ein- und Ausgänge bleiben in ONNX gleich, sodass die gelernte Policy wie die alte eingesetzt werden kann.
- **Lernschleife „Lernen, bis sie es kann“:**
  - Eine Runde lernen, dann 3 Durchgänge auf dem Parcours prüfen und vom besten geprüften Stand aus weiterlernen.
  - Das endet, wenn alle Durchgänge im Ziel sind oder das Zeitbudget um ist.
- Claude darf kostenlose Läufe selbst starten (`training_kostenlos`), bezahlte nur vorschlagen.
- **Akrobatik wie im CAD:** Drehringe nur für die echten Motorachsen, eine Karte je Gelenk mit seinen Grenzen.
- **Sehen:** „Was siehst du?“ und „Lies mir das vor“. Ein Bild geht genau für diese eine Runde an Claude und wird nie
  gespeichert.
- **Personen erkennen:** nur angelernte, mit Einverständnis, lokal.
  - Gespeichert werden nur Gesichtsmerkmale (YuNet/SFace), nie Bilder. Fremde werden nie gespeichert.
  - Begrüßen höchstens alle 30 min je Person.
- **Tailscale:** https im eigenen Tailnet für das Handy-Mikrofon und den Zugriff von unterwegs.

### Sicherheit
- Unabhängige Sicherheitsprüfung vor der Auslieferung:
  - Jede weitergeleitete Anfrage (Tailscale, andere Proxys) zählt als entfernt.
  - Sehen und Personen lassen sich nur am PC einschalten.
  - Namen gehen nie an ein Handy.

### Nicht geprüft
- Lernen auf einer Radeon unter Windows.
- Kaggle mit echtem Konto.
- Das Tailscale-Zertifikat.
- Die Webcam-Freigabe in Edge.

## 0.19.1

### Behoben
- Am Handy: Fahr-Joystick und feste Eingabezeile.
- Die Werte im HUD flackerten nicht mehr.
- Die Kachel lässt sich zwischen Tiefe und Kamera umschalten.

## 0.19.0 · Fünf Bereiche, Handy-Fernbedienung

### Neu
- Startbild beim Start, einmal je Sitzung, mit Klick überspringbar.
- **Fünf Bereiche:** Steuern, Alltag, Charakter, Lernen, System.
- **Handy-Fernbedienung** im eigenen WLAN:
  - Kopplung per QR-Code mit Einmal-Code: 5 Minuten gültig, ein Gerät, höchstens 5 Fehlversuche.
  - Gespeichert wird nur die Prüfsumme des Gerätezeichens. Geräte lassen sich einzeln abmelden.
  - Nur am PC: Schlüssel, bezahltes Training, Installationen.
- „Mit Windows starten“: duckpilot startet im Hintergrund, die Ente im Ruhemodus.

### Sicherheit
- Unabhängige Prüfung: strengere Prüfung der Host-Zeile, Zugriffsregeln nach dem echten Pfad.
- PC-Einstellungen sind vom Handy aus nicht mehr änderbar.

### Nicht geprüft
- Abfrage der Windows-Firewall.
- QR-Scan mit einer echten Handykamera.

---

## 0.18.0 · Pollen-Abgleich, Akrobatik, Alltagsbuddy, Ruhe/Aktiv

### Neu
- **Gelenk-Check:** je Gelenk Sollwert, Nachlauf und Last mit Ampel.
- Pflegeheft der Motoren.
- Karte „Abgleich Training ↔ Roboter“.
- Fähigkeit je Trainingslauf.
- **Akrobatik:** die Ente als Gliederpuppe mit Gleichgewichts-Ampel, Probe in der Physik und Üben (z. B. auf einem
  Bein).
- **Alltagsbuddy:** Uhr, Timer, Erinnerungen, Termine (auch als .ics), To-dos. Deutsche Zeitangaben.
- **Ruhe/Aktiv:** In Ruhe sitzt die Ente mit abgeschalteten Motoren. Ansprechen oder etwas Fälliges weckt sie.
- Nach einem Not-Aus steht sie 2 Minuten lang nicht von selbst auf.

### Geändert
- Kopf ruhig mit Vorhalt und Ausgleich des Vor und Zurück:
  - Drehzittern −60 %.
  - Vor und Zurück −35 %.

### Behoben
- Unabhängige Prüfung mit 16 Befunden:
  - Uhrzeiten über die Zeitumstellung.
  - Not-Aus ließ sich umgehen.
  - Ganztägige Termine meldeten sich nie.
  - „jeden Tag um 8“ wurde 20 Uhr.
  - Serientermine aus .ics werden jetzt aufgelöst.
  - und weitere.

## 0.17.0

### Neu
- **Kopf ruhig** wie bei Huhn und Taube.
- Klick = hinschauen, Doppelklick = hinlaufen.
- Entenblick als ganze Bühne, Ziehen zum Umschauen.

### Behoben
- Die Ente schwebte in der Physik 12 cm über dem Boden.
- Alte Skripte aus dem Zwischenspeicher nach einem Update.

## 0.16.0

### Neu
- Training auf Pollens veröffentlichtem Stand oder auf einem eigenen Lauf. Das spart meist zwei Drittel der
  Iterationen.
- Kosten vorab, harte Obergrenze, Lernkurven, Abbruch bei Stillstand mit Export.
- Bis zu drei Varianten parallel.

### Geändert
- Oberfläche neu geordnet: Bereiche mit Reitern, Menü „Ansicht“ und Anzeige der laufenden Aufgaben.

## 0.14.0 · Parcours und Aufträge

### Neu
- Parcours aus einfachen Formen in Pollens MuJoCo-Welt: Rampe, Stufen, Schwelle, unebener Boden, Slalom, Engstelle.
- Auftrag in sechs Schritten: Ziel → Parcours → Basis-Test → Vorschlag → Training → Bewertung, mit 3D-Wiederholung.
- Fertige Trainings werden automatisch auf demselben Parcours geprüft.

### Behoben
- Eine unabhängige Prüfung fand acht Fehler, alle behoben (u. a. die Bildrate der Wiederholung, Ergebnisse im
  falschen Auftrag, ein zu enger Slalom).

## 0.13.1 und 0.13.2

### Geändert
- Die Entenstimme lässt sich auf Deutsch beschreiben. Für das Modell wird ins Englische übersetzt.
- Not-Aus als roter Pilztaster auf gelbem Schild, nach EN ISO 13850.

### Behoben
- Die Installation von Qwen3-TTS läuft in vier Schritten, mit „Reparieren“, wenn etwas fehlt.
- Konflikt der huggingface_hub-Versionen zwischen Qwen und Training.

## 0.13.0 · Training, Kamera, Pflege

### Neu
- Training auf Hugging Face Jobs: ohne Kommandozeile, Start nur mit zwei Klicks durch den Menschen.
- Kamerabild des Roboters im Entenblick.
- Pollens Enten-Erkenner als Erweiterung.
- Roboter-Pflege: Zustand, WLAN, Updates mit Probelauf, Protokolle.

## 0.12.0 · Echte Physik

### Neu
- Simulator mit echter Physik: Pollens MuJoCo-Modell mit Pollens Policies, 200/50 Hz, Beobachtung und Aktion wie am
  Roboter.
- Pollens offizieller Policy-Satz per Knopf.
- Entenblick aus der Kopfkamera.
- Claude übt neue Bewegungen erst unsichtbar in der Physik (`bewegung_ueben`).

## 0.11.0 · Stimme und Gespräch

### Neu
- Eigene Stimme: Piper oder Qwen3-TTS mit entworfener Entenstimme, ein Entenfilter, und der Schnabel bewegt sich mit.
- Echte Entenlaute im Satz.
- Plaudern mit Gegenfragen.
- Wissen im Gedächtnis. Zugangs-, Bank-, Ausweis- und Gesundheitsdaten werden abgelehnt.
- Eigenes Sprachmodell über Ollama, auch als Ersatz, wenn Claude nicht erreichbar ist.

## 0.10.0

### Geändert
- 3D-Modell in voller Auflösung mit Materialien je Teil.
- Neuer Renderer: Umgebungslicht, scharfe Schatten, Umgebungsverdeckung, Qualitätsstufen.

## 0.9.0 · Skill-Pakete

### Neu
- Erweiterungen einzeln an- und abschaltbar.
- Bewegungen aus der MicroDuck-App.
- Got a Talent.
- Gangarten aus Arena und Community.

## 0.8.0

### Neu
- Punktwolke des 8 × 8-Tiefensensors im Dashboard und in der 3D-Ansicht.

## 0.7.0 bis 0.7.2

### Geändert
- Designsystem IBM Carbon (Theme Gray 90) mit einer dünnen eigenen Ebene. Schnabel-Orange ist der einzige Akzent.
- Flache Bedienelemente.

## 0.6.0

### Neu
- Laute für die eigenen Gesten im Stil von Pollens Sound-Design.
- Charakter im Leerlauf: 16 neue Gesten.
- Die App heißt wie die Ente.

## 0.5.0 · Pollens Quellen

### Neu
- Originales 3D-Modell aus Pollens CAD.
- Pollens 14 Emotionen mit ihren Original-Tönen.
- Entenstimme aus Pollens Stimm-Synthese.
- Tricks vom Hugging Face Hub.
- Eigenes Designsystem.

## 0.4.0

### Neu
- Goofy-Modus.
- Situative Gefühle.
- Persönlichkeit auf einer X/Y-Fläche mit zwölf Charakteren.

## 0.3.0

### Neu
- Eigenes Programmfenster.
- Dunkle Oberfläche mit Dashboard und 3D.
- Einstellungen in der App.

### Sicherheit
- Befehle nur aus der eigenen Oberfläche, Schutz gegen DNS-Rebinding.
- Der API-Schlüssel geht nie an die Oberfläche.

## 0.2.0

### Neu
- Gedächtnis: Tricks, Orte (je Körper), Vorlieben und ein Pannen-Protokoll. Lokal, einsehbar und löschbar.

## 0.1.0

### Neu
- Lite-Simulator, der auch unter Windows läuft.
- Bewegungs-Engine in Schichten: Reflexe → Hand → Verhalten → Leerlauf.
- Claude per Tool-Use.
- Sprachsteuerung: im Browser oder lokal mit Whisper.
- Einfache deutsche Befehle ohne Schlüssel.
- Backend für `robotd` und ein Test-Roboter (`--fake-robotd`).

