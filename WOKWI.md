# Reopen the simulator from local files

The prototype was compiled and run successfully in Wokwi during development.
No persistent Wokwi project was saved: the browser was signed out, and the user
chose local delivery. The authoritative source files are in `prototype/`.

## Open it again

1. Open [Wokwi's ESP32 MicroPython template](https://wokwi.com/projects/new/micropython-esp32).
2. Replace the contents of `main.py` and `diagram.json` with the corresponding
   local files in `prototype/`.
3. Use the file menu next to the editor tabs and **New file...** to create these
   four files, preserving their exact names, then paste the corresponding code:
   - `gps.chip.c`
   - `gps.chip.json`
   - `modem.chip.c`
   - `modem.chip.json`
4. Press Play. Wokwi compiles both custom chips and boots ESP32 MicroPython.
5. Use the simulation menu's **Fit** option to see all components.
6. The Serial Monitor shows telemetry acknowledgements and assessments.
   The Chips Console shows the emulated modem receiver's JSON messages.

The file menu also offers **Upload file(s)...**. This failed in the automated
browser session, so the verified loading method was New file followed by paste.
You do not need to save online or sign in to run an unsaved simulation.

The firmware image selected in `diagram.json` is the MicroPython environment
offered by Wokwi's template during this session. The ESP32, MPU6050, both UART
models and normal GPS/sensor/telemetry operation were observed running there.
Sustained speed exceedance was also observed producing a `review_driving`
assessment with `alert: true` and an acknowledgement from the modem emulator.
See `evidence/` for screenshots and `README.md` for demonstration scenarios.

Uploading these files to Wokwi sends the source to that service for simulation.
For an entirely local behavioral demonstration, run `run-demo.cmd` instead.
The desktop replay exercises the same Python firmware classes without a browser,
cloud account, actual modem, or actual GPS receiver.
