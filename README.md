# CUIDA virtual device prototype

First working milestone: ESP32 firmware, a GPS serial model, an A7670SA modem
emulator, an editable Fritzing breadboard design, and repeatable driving scenarios.
The original project document has not been changed. The React Native application,
accident detection and backup battery remain outside this version.

## Start here

1. Open `circuit/wiring-preview.png` to inspect the connections.
2. Open `circuit/CUIDA-v0.1.fzz` in Fritzing. Use **Breadboard** view.
3. Follow `WOKWI.md` to load the saved local source into a fresh Wokwi session.
4. To replay all eight scripted scenarios locally, double-click `run-demo.cmd`
   on this Windows computer, or run `python demo/replay.py` from this folder.
   The replay takes seconds rather than waiting four real minutes.
5. Read `results/assessments.jsonl` and `results/replay.log` for the results.

The Fritzing archive contains its custom parts. Individual `.fzpz` files are also
included in `circuit/parts/` for reuse through Fritzing's Import Part command.
The custom board outlines and unused header positions are illustrative: connect
by pin labels. They are not PCB fabrication footprints. The Fritzing archive has
been checked for valid XML, matching connector graphics, reciprocal links and
net continuity; this computer does not have Fritzing installed, so native opening
and rendering remain to be verified in Fritzing. The PNG was rendered separately
from the same part graphics, coordinates and wire routes.

## Pin assignments

| Device signal | ESP32 signal | Notes |
|---|---|---|
| MPU6050 SDA | GPIO21 | I2C data |
| MPU6050 SCL | GPIO22 | I2C clock |
| MPU6050 VCC | 3V3 | AD0 tied to GND: address 0x68 |
| GPS TX | GPIO27 / UART1 RX | GPS sends NMEA to ESP32 |
| GPS RX | GPIO26 / UART1 TX | Reserved; firmware does not configure GPS |
| Modem TXD | GPIO16 / UART2 RX | Assumed 3.3 V board-level UART |
| Modem RXD | GPIO17 / UART2 TX | Assumed 3.3 V board-level UART |
| ESP32 VIN | Regulated 5 V | DevKit VIN, not bare ESP32 supply |
| GPS VCC | Regulated 5 V | Assumes a GY-NEO6MV2 breakout with onboard regulator |
| Modem VIN | Regulated 5 V | User-approved assumption for this carrier board |
| All grounds | Common GND | Both breadboard ground rails bridged |
| Capacitor + | Modem VIN | 1000 uF, polarized, at least 10 V rating selected |
| Capacitor - | Modem GND | Across the board input, not bare modem VBAT |

GPS UART is assumed to use 3.3 V signals. The GY-NEO6MV2 breakout's regulator,
header ordering and electrical levels need checking against the exact purchased
board. Only GPS TX is required to receive positions. Unused modem EN, PWRKEY,
and DTR pins are intentionally not controlled until the carrier schematic is known;
the virtual model starts powered on. A real carrier may require an enable/power-on
sequence. The selected ESP32 is the classic 30-pin DevKit V1 wiring model; a
different NodeMCU/ESP32 board can have a different physical pin arrangement.

## What the firmware does

- Reads MPU6050 registers over I2C at a target 20 samples/s. Acceleration is
  configured for +/-4 g and the gyroscope for +/-500 degrees/s.
- Reads checksum-validated GPS RMC sentences at 9600 baud. Extracts latitude,
  longitude, UTC/date and ground speed; converts knots to km/h. Invalid or stale
  fixes are not represented as a stopped vehicle.
- Evaluates non-overlapping 30-second windows and sends a telemetry message
  every 5 seconds, with no blocking modem waits inside the sensor loop.
- Sends a window summary and a proposed driving alert through a subset of
  SIMCom AT/HTTP commands over 115200-baud UART.
- Retries failed modem operations after 5 seconds, retaining queued messages.
  The bounded queue holds 24 messages; routine telemetry is discarded before
  existing alert messages when space is needed. The queue is RAM-only and
  cannot survive power loss. If all slots contain alerts, a new message is
  dropped and the loss is reported in logs/counters.

## Provisional assessment rules

These are demonstration settings in `prototype/main.py`, **not values learned
from drivers, legal speed limits, or validated boundaries of safe driving**.

| Setting | Initial demonstration value |
|---|---|
| Speed baseline threshold | 60 km/h |
| Lateral magnitude threshold | 0.30 g |
| Forward/braking magnitude threshold | 0.30 g |
| Yaw magnitude threshold | 30 degrees/s |
| Assessment duration | 30 seconds |
| Minimum joint GPS/sensor coverage | 90% |
| Sustained exceedance | At least 20% of observed time |
| Repeated exceedance | At least 3 separated episodes, each >=250 ms |
| Alert cooldown | 60 seconds |
| GPS stale after | 3 seconds without a valid RMC fix |

Any one channel can contribute an exceedance. Measurements do not need to
exceed every threshold simultaneously. A window returns `review_driving` when
sustained or repeated exceedances meet the rule, `normal` when they do not,
and `insufficient_data` when joint coverage is too low. Cooldown suppresses new
alerts but preserves the window's status. Alerting does not imply an accident.

RMS acceleration uses magnitudes so left and right turns cannot cancel out.
The report also includes mean speed, yaw RMS, peak lateral g, episode count,
coverage and exceedance fraction. No single instantaneous value automatically
produces a notification. Episodes spanning a window boundary can contribute
to both windows; tuning boundary handling is a later refinement.

Mount the model with X forward, Y left, Z up. The current calculation assumes
rigid, level mounting and zero sensor bias. Real hardware needs stationary bias
calibration, gravity/tilt compensation and road-test validation before interpreting
these values. The gyroscope's yaw contribution is provisional. Urban versus
highway driving, road conditions and low-speed turns are not separately modelled.

Future training should use reviewed representative driving sessions to establish
separate channel baselines and margins. Keep that baseline fixed during a trip;
continuously learning from the current driver could normalize aggressive behavior.
No machine-learning training or automatic baseline fitting is implemented yet.

## Wokwi demonstration

`prototype/main.py` is the actual ESP32 MicroPython program. The `.chip.c` and
`.chip.json` files are Wokwi-only peripherals, never firmware to flash onto the
physical GPS or modem. The simulator uses the same signal pin assignments as
the Fritzing design. Its simplified diagram omits the physical capacitor and
breadboard because it does not calculate their electrical behavior.

Start with the defaults for one full window. Click the MPU6050 to change its
acceleration/rotation controls. Its slider units are g and degrees/s. Click the
GPS model to adjust speed or fix validity; click the modem model to change
network availability. The custom GPS generates a synthetic northbound path
near Buenos Aires, not an actual recorded trip and not a road-following route.

Suggested live demonstration:

1. Wait 35 seconds with speed 32 km/h and level MPU: expect `normal`.
2. In a fresh run, set lateral acceleration (Y) to 0.65 g for one second, then
   return it to zero: expect no alert for that isolated maneuver.
3. In a fresh run, keep Y at 0.65 g for more than 6 seconds of a 30-second
   window, or create three separated episodes: expect `review_driving`.
4. Set network to 0. Messages remain queued. Return it to 1 and allow the
   registration timeout/retry cycle to finish (up to about 25 seconds).
5. Set GPS fix to 0 for a full window: expect `insufficient_data`.

Stop/start resets RAM state and cooldown. The scripted desktop replay exercises
the same drivers, GPS parser, assessment and modem state machine; it replaces
only the physical UART and I2C objects with deterministic peripheral models.

## What is simulated and what is not

The modem emulator implements only the commands the firmware uses: AT, ATE0,
CPIN, LTE-only CNMP, CEREG, CGDCONT, HTTPINIT, HTTPTERM, HTTPPARA, HTTPDATA,
and HTTPACTION. It accepts JSON and prints it in Wokwi's **Chips Console**.
`SIMULATED ACK` means the model accepted the message. **Nothing is sent to a
real server, Claro network, SIM card, phone, or notification service.**

The URL uses the reserved `.invalid` domain and the APN is `SIMULATION_ONLY`.
Changing `simulation` to false alone is insufficient to operate real hardware.
Production integration needs a confirmed carrier/APN, endpoint, TLS/certificate
validation, device authentication, board startup control, timeouts matched to
real firmware, receiver-side message deduplication and physical validation.

The radio is LTE Cat 1. A Claro IoT plan must permit Cat 1 data; an LTE-M/NB-IoT
only service is a different radio technology. No network compatibility is
established by this simulation.

The 5 V / 2 A adapter and 1000 uF capacitor are the agreed virtual arrangement,
not a verified power budget. No simulated result proves startup/transmit stability,
regulator efficiency, capacitor ESR/inrush, automotive transient protection or
breadboard current capacity. The bare modem itself is a 3.4-4.2 V / 1.8 V UART
device; do not apply the carrier-board assumptions directly to its pins.

## Included verification

Run `python -m unittest discover -s tests -v` from this folder.
Checks cover NMEA fragmentation/checksums/staleness, MPU register scaling,
signed lateral forces, isolated versus repeated maneuvers, alert cooldown,
missing data, sampling gaps, transmission recovery, server errors, bounded
queue behavior and circuit continuity/archive references.

Eight replay phases: normal, isolated maneuver, repeated aggressive maneuvers,
sustained speed exceedance, network outage, network recovery, lost GPS fix,
and disconnected motion sensor. See `results/` for generated evidence.

## Technical references

- [Wokwi ESP32 simulation](https://docs.wokwi.com/guides/esp32)
- [Wokwi custom chip UART API](https://docs.wokwi.com/chips-api/uart)
- [Wokwi custom chip definitions](https://docs.wokwi.com/chips-api/chip-json)
- [Wokwi MPU6050 model](https://docs.wokwi.com/parts/wokwi-mpu6050)
- [MicroPython ESP32 reference](https://docs.micropython.org/en/latest/esp32/quickref.html)
- [SIMCom A76XX AT manual V1.09](https://files.waveshare.com/wiki/A7670E-Cat-1-GNSS-HAT/A76XX_Series_AT_Command_Manual_V1.09.pdf)
- [Fritzing public format examples](https://github.com/fritzing/fritzing-app/tree/develop/sketches/core)

The user-supplied SIMCom A7670 Hardware Design V1.00 manual was consulted for
bare-module power and UART requirements. Carrier-board assumptions remain
separately recorded above. No project source document was edited.
