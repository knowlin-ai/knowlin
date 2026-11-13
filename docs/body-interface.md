# Body interface 1.0 – one mind, many bodies

*Deutsch: [koerper-schnittstelle.md](koerper-schnittstelle.md)*

Knowlin separates the **mind** (memory, experience graph, character, conversation, spatial knowledge) from its
**bodies**. A body is anything the mind can move: a simulator, a Microduck, a Reachy Mini, an SO-101 arm, a LeRobot robot, or your own
build. The body interface defines how a body introduces itself and what it must guarantee, so a new robot can get
Knowlin without touching the core.

## Where it sits

Knowlin builds on existing standards instead of replacing them. It uses ROS REP-103 units and axes (metres, seconds,
radians; x forward, y left), loads MJCF for simulation, integrates **LeRobot's `Robot` class** as a built-in profile, and
exposes itself as an MCP server. What none of these define is what a body means to a *persistent mind*:

- a **capability vocabulary** the mind understands,
- **safety duties**,
- a **shared perception format**, so that memory and spatial knowledge travel between bodies.

## Profile

`duckpilot.koerper.Koerper` has these fields:

- `id`: the `modul` setting, stable forever.
- `name`, `hersteller` (maker).
- `familie` (family): `ente`, `stationaer`, `fahrend`, `arm`, `vierbeiner`, `humanoid`, `andere`.
- `faehigkeiten` (capabilities): from the vocabulary only; custom ones start with `x-`.
- `fabrik` (factory): `"module:function"` or a callable taking Knowlin's settings and returning a `DuckBackend`.
- `zustand`: the value `state().koerper` reports.
- `skills`, `echt` / `simulator`, `quelle` (https), `lizenz`.

**Vocabulary:** `beine` (legs), `raeder` (wheels), `kopf` (head), `koerperdrehung` (body turn), `schnabel` (beak), `arm`,
`greifer` (gripper), `antennen`, `augen_leds`, `stimmbank` (own sounds), `tiefensensor` (depth), `kamera`, `mikrofon`,
`lautsprecher`, `pollen_bewegungen`. Runtime flags: `simulator`, `zuruecksetzen`, `physik`, `policies`. The full
descriptions are in `GET /api/koerper/wortschatz`.

Since 0.38.47 head tools need their word too: head, emotions, dance and choreography only with `kopf`; turning with
`beine`, `raeder` or `koerperdrehung`. An arm without a head (SO-101) gets the `arm` tool instead.

**Actions instead of movements** (since 0.38.43, `duckpilot/aktionen.py`): the mind states an intention ("greet"); the
body answers `kann` (can), `ersatz` (substitute) or `nein` (no, with a reason), depending on which implementation fits
its capabilities (head, arm, sounds). A new body needs no code for this – it reports its capabilities, the catalogue
chooses.

## Duties

| | Duty |
|---|---|
| P1 | Valid profile, capabilities only from the vocabulary |
| P2 | `eigenschaften()` ⊆ profile ∪ runtime flags |
| P3 | `connect()` within 5 s; `state()` never raises and reports `connected` |
| P4 | State serialises to JSON; `koerper` matches the profile |
| P5 | **Emergency stop:** `relax()` cuts motor power immediately |
| P6 | Without power nothing moves |
| P7 | Locomotion and head stay within `api.LIMITS`, even for oversized commands |
| P8 | `stop()` halts without cutting power |
| P9 | `close()` within 5 s |
| E1 | Unknown skill or sound is rejected, not raised (recommended) |

Run the checks with `python -m duckpilot.koerper_pruefung [id]`. Everything else is enforced by Knowlin's motion engine
for every body: lockout after the emergency stop, no standing up while picked up, no autonomous locomotion on real
robots, people only on the PC, secrets only in the OS keyring.

## Your own body as a package

```toml
[project.entry-points."knowlin.koerper"]
rollbot = "my_package:profil"
```

Broken packages are listed as rejected and never stop Knowlin. Built-in bodies always win. Knowlin never installs
packages itself, and Knowlets never contain code. Template: [`examples/knowlin-koerper-vorlage`](../examples/knowlin-koerper-vorlage).

## LeRobot

**SO-101** (since 0.38.47) has its own profile `so101`: in the simulator with TheRobotStudio's open model (Apache-2.0)
at its own workbench – poses and gestures in degrees (`duckpilot/arm.py`), picking and placing with its own kinematics
(`duckpilot/arm_kinematik.py`, `backends/werkbank.py`); on the real arm via LeRobot with type `so101_follower` (not
yet tested).

The `lerobot` profile wraps any other LeRobot `Robot` (LeKiwi, Koch …). It reads capabilities from the action
features:

- `*.pos` joints become `arm`, and `gripper.pos` becomes `greifer`.
- `x.vel`, `y.vel` and `theta.vel` become `raeder`.
- Images become `kamera`.

Driving uses m/s and rad/s, converted to deg/s for LeRobot. Poses are interpolated and clipped to −100…100.

LeRobot's contract has no emergency stop, so Knowlin adds one: zero velocity, then `bus.disable_torque()`. Without a bus,
Knowlin disconnects.

To use it, set `modul = "lerobot"`, `backend = "robotd"` and
`koerper_optionen = {"typ": "so101_follower", "port": "COM5"}`, and install `lerobot` yourself.
