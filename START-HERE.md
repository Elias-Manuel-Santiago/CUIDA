# CUIDA first prototype

Everything in this folder is saved locally. No online Wokwi project was saved.

**To see the circuit:** open `circuit/wiring-preview.png`.

**To edit the circuit:** open `circuit/CUIDA-v0.1.fzz` in Fritzing and select
Breadboard view. Custom parts are included. Native opening in Fritzing still
needs checking because Fritzing is not installed on the development computer.

**To demonstrate the behavior immediately:** double-click `run-demo.cmd`.
It replays eight scenarios and writes the results into `results/`.

| Scenario | Expected result |
|---|---|
| Normal driving | Normal |
| One isolated sharp maneuver | Normal; no alert |
| Repeated aggressive maneuvers | Review driving; alert |
| Sustained speed above baseline | Review driving; existing alert cooldown applies |
| Network outage | Keep assessing; queue messages |
| Network recovery | Deliver queued messages to the simulated receiver |
| GPS fix lost | Insufficient data |
| Motion sensor disconnected | Insufficient data |

**To run the ESP32 visually:** follow `WOKWI.md`. All six required source files
are in `prototype/`. They were loaded and tested in a temporary Wokwi session.

**To change assessment settings:** edit the `CONFIG` section near the top of
`prototype/main.py`. The initial thresholds are demonstration values, not a
trained assessment of safe driving.

`evidence/wokwi-alert.png` shows the ESP32 simulation producing a driving alert.
`README.md` explains the wiring, firmware, assumptions and limitations in detail.

The cellular connection is emulated: no real server or phone receives messages.
The app, accident detection and battery are deferred. Your original document
has not been modified.
