# Verification record

Verified on 25 October 2026.

- The final MicroPython firmware was run on Wokwi's ESP32 DevKit V1 model.
- Both custom C peripheral models compiled in Wokwi.
- MPU6050 I2C measurements were observed in firmware telemetry.
- GPS UART sentences produced valid positions and speed in the firmware.
- The modem UART emulator exchanged SIMCom AT/HTTP commands and acknowledged
  JSON telemetry, without actual cellular or internet transmission.
- A live speed-control test at approximately 85 km/h produced `review_driving`
  and `alert: true`; the acknowledgement is visible in `evidence/wokwi-alert.png`.
- Ten local automated tests passed. Full output: `results/tests.log`.
- The eight scripted replay scenarios completed. Fifty-six messages were
  acknowledged by the desktop modem model; full results are in `results/`.
- The Fritzing archive's XML, SVG connector references, reciprocal connections,
  normal-wire flags and electrical net continuity were checked. Distinct power
  and signal nets were checked for accidental shorts.
- The circuit PNG was rendered and inspected from the same part graphics and
  routes used to generate the editable Fritzing archive.

Not verified: native Fritzing opening/rendering, physical power delivery,
carrier-board UART conversion, actual modem startup/enable control, GPS board
electrical details, carrier registration, internet delivery or notifications.
The simulated models cannot validate those physical or service properties.

No persistent Wokwi project was saved. Files remain local as requested.
No project source document was changed.
