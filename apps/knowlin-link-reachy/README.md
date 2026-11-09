---
title: Knowlin Link
emoji: 🧠
colorFrom: gray
colorTo: yellow
sdk: static
pinned: false
short_description: Connect your Reachy Mini to Knowlin – one mind, many bodies
tags:
  - reachy_mini
  - reachy_mini_python_app
---

# Knowlin Link for Reachy Mini

[Knowlin](https://knowlin.de) is an open-source companion that runs on your PC: memory, character, conversation and
spatial knowledge – one mind for several robots (Reachy Mini, Microduck, Open Duck Mini, LeRobot robots). It drives
Reachy Mini through Pollen's daemon and simulates it first, so you can try everything before your robot arrives.

This app is the link on the robot side. Start it from **Reachy Mini Control → Applications**. It does not move the
robot by itself; it shows the address to enter in Knowlin and how to connect.

1. Install Knowlin on your PC: <https://knowlin.de> (Windows installer) or `pipx install knowlin`.
2. In Knowlin choose **Reachy Mini → Real robot** and enter the address shown by this app
   (Wireless: `http://reachy-mini.local:8000`, Lite: `http://localhost:8000`).
3. The emergency stop in Knowlin switches the motors off immediately (`motors/set_mode/disabled`).

Knowlin is a free, non-commercial community project and is not affiliated with Pollen Robotics or Hugging Face.
License: Apache-2.0. Source: <https://github.com/knowlin-ai/knowlin>.

---

**Deutsch:** Knowlin Link verbindet deinen Reachy Mini mit Knowlin auf dem PC. Die App bewegt den Roboter nicht selbst;
sie zeigt die Adresse und wie du in Knowlin „Reachy Mini → Echter Roboter“ einrichtest.
