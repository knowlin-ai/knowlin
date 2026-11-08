"""Zahlen von Pollens robotd, die die Physik genauso nutzen muss (ohne Abhängigkeiten, überall importierbar).

Quelle: pollen-robotics/microduck, robotd/src/control.rs (Tuning::default) und deploy/robotd.toml.
"""

# Ausgabe-Faktor: Gehen und Skills ohne eigene Angabe 0,9 (kein Steh-Netz geladen), Hinsetzen und Aufheben 1,0.
ROBOT_ACTION_SCALE = 0.9
# Glättung der Gelenkziele – „the alpha policies are trained with 0.5 / 0.7 … it must match training“.
HEAD_LOWPASS = 0.5
LEGS_LOWPASS = 0.7
# Glättung der eingehenden Befehle je 50-Hz-Takt: `cmd += alpha * (ziel - cmd)` (robotd.toml cmd_alpha/head_alpha).
# Ein Sprung am Steuerknüppel wird so zur Rampe, der die Gangart folgen kann. Fahren: cmd_alpha, Kopf und Haltung: head_alpha.
CMD_ALPHA = 0.2
HEAD_ALPHA = 0.2
