# Barrierefreiheit von Knowlin

Stand: 0.38.16, November 2026 (Ziel WCAG 2.2 AA – automatisch geprüft, Screenreader-Test steht aus)

Knowlin ist ein freies, nicht-kommerzielles Projekt. Die BITV 2.0 und das Barrierefreiheitsstärkungsgesetz gelten
dafür rechtlich nicht. Knowlin soll trotzdem für alle bedienbar sein. Maßstab ist deshalb **WCAG 2.2 Stufe AA**.
Das deckt BITV 2.0 und EN 301 549 mit ab: EN 301 549 V3.2.1 verweist auf WCAG 2.1, die Fassung V4.1.1 vom
September 2026 auf WCAG 2.2.

## Wie geprüft wird

- **Automatisch:** axe-core 4.10 mit den Regeln für WCAG 2.0, 2.1 und 2.2 (A und AA) sowie Best Practice. Geprüft
  werden alle 15 Seiten und Reiter bei 1440 px und 320 px Fensterbreite, mit und ohne reduzierte Bewegung.
- **Halbautomatisch:**
  - Tab-Reihenfolge und sichtbarer Fokus auf jeder Seite.
  - Reflow bei 320 px: Die Seite darf nicht waagrecht scrollen.
  - Textabstände nach WCAG 1.4.12: Es darf nichts abgeschnitten werden.
- **Im Code festgehalten:** Ein Test prüft, dass das CSS nur Werte aus dem Designsystem nutzt. Feste Kontraste,
  Schriftgrade ab 12 px und Bedienhöhen sind damit nicht unbemerkt änderbar.

## Ergebnis

Der axe-Lauf zeigt **keine Verstöße**. Behoben wurden dafür unter anderem:

| WCAG | Was | Wie |
|---|---|---|
| 1.3.1, 2.4.6 | Überschriften mit Lücken (h1 → h3) | sichtbare oder nur für Screenreader lesbare h2 ergänzt |
| 1.3.1 | Landmarken in Landmarken (`aside` in `main`) | benannte Bereiche (`section` mit Namen) |
| 1.1.1 | Zeichenflächen ohne Rolle | `role="img"` mit Beschriftung an allen 3D-Ansichten, Karten und Kurven |
| 1.4.3 | Hilfetext auf gewählten Kacheln 3,3 : 1, Achsfarben als Text 3,4 : 1, Mikrofon-Hinweis 4,0 : 1 | hellere Textfarben, eigene Text-Tokens für die Achsfarben |
| 1.4.11 | Felder, Schalter und Regler kaum vom Grund zu unterscheiden | Unterkante der Felder, Spur der Regler und Schalter „aus“ mit mindestens 3 : 1 |
| 1.4.10 | Waagrechtes Scrollen bei 320 px (Alltag, Stimme, Gedächtnis) | Gerüst darf nicht breiter werden als das Fenster, Kartenköpfe und Listenzeilen brechen um |
| 1.4.12 | Gelenknamen bei größeren Textabständen abgeschnitten | Umbruch statt Abschneiden |
| 2.1.1 | Knoten im Erfahrungsnetz nur per Maus wählbar | Auswahlliste daneben |
| 2.1.1 | Ereignislisten und Tabellen scrollen, sind aber nicht per Tastatur erreichbar | fokussierbar und benannt |
| 2.2.1 | Stopp-Fenster nach einem Sturz fest 3 s | einstellbar von 2 bis 10 s |
| 2.4.1 | kein Weg an Leiste und Kopfzeile vorbei | Sprunglink „Zum Inhalt springen“ |
| 2.4.2 | Fenstertitel immer gleich | Titel je Seite, z. B. „Tricks – Quacki“ |
| 2.4.7 | Fokus auf einem Feld mit Fehler nicht zu erkennen | 2 px Fokusrahmen in jedem Feld |
| 2.4.11 | Fokus konnte unter der Leiste unten verschwinden | Scroll-Abstand unten |
| 4.1.2 | Regler ohne Namen (Designsystem-Seite) | Beschriftung |
| – | Kontrastmodus von Windows: Konturen sind Schatten und verschwinden | echte Ränder in `forced-colors` |

## Bekannte Lücken

- **3D-Ansicht:** Was in der 3D-Ansicht passiert, steht als Text daneben: Haltung, Tätigkeit, Messwerte und
  Ereignisse. Die Szene selbst ist für Screenreader nur ein beschriftetes Bild.
- **Laserpointer und „Folg mir“ im Simulator** brauchen ein Zeigegerät. Ohne Maus geht dasselbe über Befehle
  wie „Lauf zum Sofa“ und über die Fahrtasten.
- **Anfassen und Ziehen im Kollisionsmodus** braucht ein Zeigegerät. Ohne Maus gehen Schubsen, Hinlegen, Werfen,
  Rollen und Wegräumen über Tasten im Bedienfeld; frei ziehen geht dann nicht. Die Hinweise am Zeiger sind nur
  sichtbar (aria-hidden), dieselben Erklärungen stehen im Bedienfeld.
- **Controller fürs Handy:** Sticks, Ziehen und Bewegungssensor brauchen Finger oder Zeigegerät. Dieselben
  Funktionen gibt es im Cockpit über Tasten (`W` `A` `S` `D`, Sprechtaste, Schnellbefehle). Vibrieren ist nur eine
  Zugabe; jede Erschütterung steht auch im Ereignisprotokoll oder als Zustand oben. Der Controller selbst hat in
  axe-core keine Verstöße (Dialog mit Namen, alle Knöpfe beschriftet, Zielgrößen ≥ 48 px).
- **Kurven** (Stimmung, Geschwindigkeit, Drehrate) zeigen den aktuellen Wert als Text, aber keine Tabelle des
  Verlaufs.
- **Nicht geprüft** mit echten Screenreadern (NVDA, JAWS, VoiceOver, TalkBack) und mit Sprachsteuerung des
  Betriebssystems. Das steht als Nächstes an.
- **Leichte Sprache und Gebärdensprache** (BITV § 4) gibt es nicht. Das ist nur für öffentliche Stellen
  vorgeschrieben.

## Rückmeldung

Hinweise zu Barrieren bitte als Issue im GitHub-Repository, sobald es veröffentlicht ist.
