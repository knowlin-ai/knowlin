# Vorlage: ein eigener Körper für Knowlin

*English below.*

Knowlin trennt das Gehirn (Gedächtnis, Charakter, Gespräch, Raumwissen) vom Körper. Diese Vorlage zeigt, wie ein
weiterer Roboter Knowlin bekommt – ohne Knowlin selbst zu ändern. Sie enthält einen kleinen simulierten „Rollbot“
(Räder und Kopf). Die Spezifikation steht in [`docs/koerper-schnittstelle.md`](../../docs/koerper-schnittstelle.md).

1. Ordner kopieren und umbenennen (Paketname, `id` im Profil, Entry Point in `pyproject.toml`).
2. In `Rollbot` die Anbindung an deinen Roboter schreiben (oder einen Simulator).
3. Im Profil nur Fähigkeiten aus dem Wortschatz nennen (`duckpilot.koerper.FAEHIGKEITEN`, eigene mit `x-`).
4. Installieren und prüfen:

   ```
   pip install -e .
   python -m duckpilot.koerper_pruefung rollbot
   pytest tests
   ```

5. In Knowlin erscheint der Körper als eigenes Modul auf der Startseite.

**Pflichten:** Not-Aus (`relax()`) macht sofort stromlos, `stop()` hält an, Befehle bleiben in den Grenzen, stromlos
bewegt sich nichts. Alle anderen Sicherheitsregeln (Sperre nach dem Not-Aus, nie hochgehoben aufstehen, keine
eigenständige Fortbewegung am echten Roboter) setzt Knowlins Bewegungs-Engine für jeden Körper durch.

## English

Knowlin separates the mind (memory, character, conversation, spatial knowledge) from the body. This template shows how
another robot gets Knowlin without changing Knowlin itself: copy it, replace `Rollbot` with your robot's connection,
list only capabilities from the vocabulary, then `pip install -e .` and run
`python -m duckpilot.koerper_pruefung rollbot`. Duties: `relax()` cuts motor power immediately, `stop()` halts,
commands stay within limits, nothing moves without power. Spec: [`docs/body-interface.md`](../../docs/body-interface.md).
