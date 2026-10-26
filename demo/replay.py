"""Run the actual firmware classes against simulated I2C and UART peripherals.

Usage: python demo/replay.py --out results
No network requests, package installs, or physical hardware required.
"""
import argparse
import json
import math
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "prototype"))
from main import CONFIG, GPS, MPU6050, DrivingWindow, Modem


def nmea(speed=32, valid=True, second=0):
    t = int(second) % 86400
    # Intentionally synthetic coordinates, not anyone's recorded location.
    body = ("GPRMC,%02d%02d%02d.00,%s,3436.2220,S,05822.8960,W,%.2f,000.0,251026,,,A"
            % (t // 3600, t // 60 % 60, t % 60, "A" if valid else "V", speed / 1.852))
    check = 0
    for char in body:
        check ^= ord(char)
    return ("$%s*%02X\r\n" % (body, check)).encode()


class Serial:
    def __init__(self):
        self.incoming = bytearray()
        self.writes = []

    def read(self, size=512):
        result = bytes(self.incoming[:size])
        del self.incoming[:size]
        return result or None

    def write(self, data):
        self.writes.append(data)
        return len(data)

    def feed(self, data):
        self.incoming.extend(data)


class SensorBus:
    def __init__(self):
        self.x, self.y, self.z, self.yaw = 0, 0, 1, 0
        self.failed = False

    def writeto_mem(self, *_):
        pass

    def readfrom_mem(self, address, register, length):
        if self.failed:
            raise OSError("synthetic sensor disconnected")
        if register == 0x75:
            return b"\x68"
        values = [int(self.x * 8192), int(self.y * 8192), int(self.z * 8192), 0, 0, 0, int(self.yaw * 65.5)]
        return struct.pack(">7h", *values)


class ModemSerial(Serial):
    def __init__(self):
        super().__init__()
        self.connected = True
        self.initialized = False
        self.remaining = 0
        self.payload = b""
        self.received = []

    def write(self, data):
        super().write(data)
        if self.remaining:
            self.payload += data
            self.remaining -= len(data)
            if self.remaining == 0:
                self.feed(b"\r\nOK\r\n")
            return len(data)
        command = data.decode().strip()
        answer = "OK"
        if command == "AT+CPIN?":
            answer = "+CPIN: READY\r\n\r\nOK"
        elif command == "AT+CEREG?":
            answer = "+CEREG: 0,%d\r\n\r\nOK" % (1 if self.connected else 2)
        elif command == "AT+HTTPINIT":
            self.initialized = True
        elif command == "AT+HTTPTERM":
            self.initialized = False
        elif command.startswith("AT+HTTP") and not (self.connected and self.initialized):
            answer = "ERROR"
        elif command.startswith("AT+HTTPDATA="):
            self.remaining = int(command.split("=")[1].split(",")[0])
            self.payload = b""
            answer = "DOWNLOAD"
        elif command == "AT+HTTPACTION=1":
            self.received.append(json.loads(self.payload))
            answer = "OK\r\n\r\n+HTTPACTION: 1,200,0"
        elif command not in ("AT", "ATE0", "AT+CNMP=38") and not command.startswith(("AT+CGDCONT=", "AT+HTTPPARA=")):
            answer = "ERROR"
        self.feed(("\r\n" + answer + "\r\n").encode())
        return len(data)


def scenario(second):
    window, local = divmod(second, 30)
    if window == 0:
        return "normal", 32, 0.03 * math.sin(second), 0.04 * math.cos(second), 2, True, True, True
    if window == 1:
        sharp = 8 <= local < 9
        return "isolated_maneuver", 32, 0.04, 0.65 if sharp else 0.04, 8, True, True, True
    if window == 2:
        sharp = int(local) % 5 < 2
        return "repeated_aggressive", 42, 0.4 if sharp else 0.04, (0.65 if int(local) % 10 < 5 else -0.65) if sharp else 0.04, 38 if sharp else 3, True, True, True
    if window == 3:
        return "sustained_speeding", 85, 0.03, 0.04, 2, True, True, True
    if window == 4:
        return "network_outage", 32, 0.03, 0.04, 2, True, False, True
    if window == 5:
        return "network_recovery", 32, 0.03, 0.04, 2, True, True, True
    if window == 6:
        return "gps_fix_lost", 32, 0.03, 0.04, 2, False, True, True
    return "sensor_disconnected", 32, 0.03, 0.04, 2, True, True, False


def replay():
    gps_uart, modem_uart, bus = Serial(), ModemSerial(), SensorBus()
    gps, mpu, assessment = GPS(gps_uart), MPU6050(bus), DrivingWindow()
    logs, windows, telemetry = [], [], []
    modem = Modem(modem_uart, emit=logs.append)
    current_phase = None
    sequence = 0
    for now in range(0, 240001, CONFIG["sample_ms"]):
        phase, speed, bus.x, bus.y, bus.yaw, fix_valid, modem_uart.connected, sensor_ok = scenario(max(0, (now - 1) / 1000))
        bus.failed = not sensor_ok
        if phase != current_phase:
            logs.append("SCENARIO " + phase)
            current_phase = phase
        if now % 1000 == 0:
            gps_uart.feed(nmea(speed, fix_valid, now / 1000))
        fix = gps.poll(now)
        try:
            motion = mpu.read()
        except OSError:
            motion = None
        result = assessment.add(now, 0 if now == 0 else CONFIG["sample_ms"], fix, motion)
        if result:
            sequence += 1
            result.update({"sequence": sequence, "uptime_ms": now, "scenario": phase})
            windows.append(result)
            modem.enqueue(result)
            logs.append("ASSESSMENT " + json.dumps(result))
        if now and now % CONFIG["telemetry_ms"] == 0:
            sequence += 1
            item = {"type": "telemetry", "sequence": sequence, "uptime_ms": now,
                    "location": fix, "motion": motion, "gps_valid": fix is not None,
                    "sensor_ok": motion is not None, "scenario": phase}
            telemetry.append(item)
            modem.enqueue(item)
        modem.poll(now)
    for now in range(240050, 250000, 50):
        modem.poll(now)
    return windows, telemetry, modem_uart.received, logs


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=ROOT / "results")
    args = parser.parse_args()
    windows, telemetry, received, logs = replay()
    args.out.mkdir(parents=True, exist_ok=True)
    for name, rows in (("assessments", windows), ("telemetry", telemetry), ("simulated_receiver", received)):
        (args.out / (name + ".jsonl")).write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    (args.out / "replay.log").write_text("\n".join(logs) + "\n", encoding="utf-8")
    for result in windows:
        print("%-24s %-18s alert=%-5s coverage=%.2f events=%d" %
              (result["scenario"], result["status"], result["alert"], result["coverage"], result["events"]))
    print("\n%d messages acknowledged by the simulated receiver; no internet traffic." % len(received))


if __name__ == "__main__":
    main()
