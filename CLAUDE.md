# Hinweise für Claude (Entwicklung an Knowlin)

- Sprache: Deutsch – Code-Kommentare, Docstrings, Oberfläche, Antworten. Im Code nie Namen von Personen; wer etwas
  gewünscht hat, heißt „Maintainer“.
- Dieses Repo ist der einzige Stand (seit 0.38.42). Private Notizen gehören nicht hierher; Pollens Modelle (.dpm,
  MJCF-Hüllen, Porträts) nie einchecken – die App lädt sie beim ersten Start von Pollens Quellen.
- Erst `ARCHITECTURE.md` lesen (Lageplan, Regeln, „wo kommt was hin“), dann gezielt suchen statt große Dateien ganz
  zu lesen. Große Dateien (`style.css`, `app.js`, `CHANGELOG.md`) nur mit grep oder Zeilenbereich.
- Sicherheitsregeln aus `ARCHITECTURE.md` nie aufweichen: Not-Aus gewinnt (stromlos), Sperre danach 15 s bis 10 min
  (Standard 120 s), Selbst-Aufstehen nur nach dem Stopp-Fenster und nie hochgehoben, bezahltes Training nur per
  Zwei-Klick, Geheimnisse nur im Tresor, Personen nur am PC.
- Nach jeder Änderung `ruff check duckpilot tests tools` und die betroffenen Tests; neue Funktionen bekommen Tests,
  gemeldete Fehler einen Regressionstest.
- **Vor jedem Push:** `python tools/pruefen_alles.py <ordner> --axe <axe.min.js> --eslint <eslint-ordner>` – nur pushen,
  wenn der Bericht „bestanden“ sagt. Die Kette überspringt Bereiche („Code“, „Website“), deren Dateien seit dem letzten
  Bestehen gleich sind; **vor jedem Release mit `--alles`**. Der Wächter (`tools/waechter.py`) braucht die private
  Namensliste unter `~/.config/knowlin/privat_namen.txt`.
- Körper nie über ihren Namen abfragen (`== "reachy_mini"`), sondern über `eigenschaften()` oder das Profil
  (`duckpilot/koerper.py`).
- Version in `duckpilot/__init__.py` und `pyproject.toml` gemeinsam erhöhen; `CHANGELOG.md` (Neu / Geändert / Behoben /
  Sicherheit / Nicht geprüft) und `docs/releases/v<version>.md` (englisch und deutsch) schreiben.
- Nach einem Release: `python tools/release_nachpruefen.py <version>`.
- Icons kommen aus `tools/make_public_art.py`, nicht von Hand bearbeiten.
