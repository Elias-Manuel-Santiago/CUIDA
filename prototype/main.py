"""CUIDA v0.1 -- ESP32 MicroPython firmware.

Simulation defaults, NOT a trained or safety-validated driving classifier.
Mounting convention: X forward, Y left, Z up; rigid, level mounting required.
No app, accident detection, battery, or actual cloud endpoint in this milestone.
"""
import time
import math
try:
    import ujson as json
except ImportError:
    import json

CONFIG = {
    "sample_ms": 50,
    "window_ms": 30000,
    "telemetry_ms": 5000,
    "gps_stale_ms": 3000,
    "min_coverage": 0.90,
    "speed_kmh": 60.0,
    "lateral_g": 0.30,
    "longitudinal_g": 0.30,
    "yaw_dps": 30.0,
    "exceedance_fraction": 0.20,
    "min_event_ms": 250,
    "min_events": 3,
    "cooldown_ms": 60000,
    "queue_limit": 24,
    "apn": "SIMULATION_ONLY",
    "url": "http://prototype.invalid/telemetry",
    "simulation": True,
}


def elapsed(now, then):
    return time.ticks_diff(now, then) if hasattr(time, "ticks_diff") else now - then


class GPS:
    """Bounded, checksum-validated RMC decoder. Voids and stale fixes stay invalid."""
    def __init__(self, uart):
        self.uart = uart
        self.buffer = b""
        self.fix = None
        self.last_valid = None

    @staticmethod
    def coordinate(value, hemisphere):
        split = 2 if hemisphere in ("N", "S") else 3
        result = int(value[:split]) + float(value[split:]) / 60
        return -result if hemisphere in ("S", "W") else result

    def sentence(self, raw, now):
        try:
            text = raw.decode().strip()
            body, checksum = text[1:].split("*")
            check = 0
            for char in body:
                check ^= ord(char)
            if not text.startswith("$") or len(checksum) != 2 or check != int(checksum, 16):
                return
            fields = body.split(",")
            if fields[0] not in ("GPRMC", "GNRMC"):
                return
            if fields[2] != "A":
                self.fix = None
                return
            if fields[4] not in ("N", "S") or fields[6] not in ("E", "W"):
                return
            latitude = self.coordinate(fields[3], fields[4])
            longitude = self.coordinate(fields[5], fields[6])
            speed = float(fields[7]) * 1.852
            if not (-90 <= latitude <= 90 and -180 <= longitude <= 180 and 0 <= speed <= 300):
                return
            self.fix = {"lat": latitude, "lon": longitude, "speed_kmh": speed,
                        "utc": fields[1], "date": fields[9]}
            self.last_valid = now
        except (ValueError, IndexError, UnicodeError):
            return

    def poll(self, now):
        chunk = self.uart.read(512)
        if chunk:
            self.buffer += chunk
            while b"\n" in self.buffer:
                raw, self.buffer = self.buffer.split(b"\n", 1)
                self.sentence(raw, now)
            if len(self.buffer) > 160:
                self.buffer = b""
        if self.last_valid is None or elapsed(now, self.last_valid) > CONFIG["gps_stale_ms"]:
            return None
        return self.fix


class MPU6050:
    """Direct I2C driver: +/-4 g, +/-500 deg/s, 20 Hz DLPF configuration."""
    def __init__(self, i2c, address=0x68):
        self.i2c, self.address = i2c, address
        if i2c.readfrom_mem(address, 0x75, 1)[0] & 0x7E != 0x68:
            raise OSError("MPU6050 WHO_AM_I mismatch")
        for register, value in ((0x6B, 0x01), (0x1A, 0x04), (0x1B, 0x08), (0x1C, 0x08)):
            i2c.writeto_mem(address, register, bytes([value]))

    def read(self):
        data = self.i2c.readfrom_mem(self.address, 0x3B, 14)
        def signed(i):
            value = data[i] * 256 + data[i + 1]
            return value - 65536 if value & 32768 else value
        return {"x_g": signed(0) / 8192, "y_g": signed(2) / 8192,
                "z_g": signed(4) / 8192, "yaw_dps": signed(12) / 65.5}


class DrivingWindow:
    """Magnitude and time-based assessment; baseline stays fixed during a trip."""
    def __init__(self, config=None):
        self.config = dict(CONFIG if config is None else config)
        self.start = None
        self.last_alert = None
        self.reset()

    def reset(self):
        self.covered_ms = self.exceeded_ms = self.events = 0
        self.speed_sum = self.lat_squared = self.long_squared = self.yaw_squared = 0.0
        self.episode_ms = 0
        self.episode_counted = False
        self.peak_lateral = 0.0

    def add(self, now, dt_ms, fix, motion):
        if self.start is None:
            self.start = now
        c = self.config
        # A late loop must not fabricate the missing samples or their duration.
        dt = min(max(dt_ms, 0), c["sample_ms"] * 2)
        valid = fix is not None and motion is not None
        if valid:
            self.covered_ms += dt
            speed = fix["speed_kmh"]
            lateral, longitudinal, yaw = abs(motion["y_g"]), abs(motion["x_g"]), abs(motion["yaw_dps"])
            self.speed_sum += speed * dt
            self.lat_squared += lateral * lateral * dt
            self.long_squared += longitudinal * longitudinal * dt
            self.yaw_squared += yaw * yaw * dt
            self.peak_lateral = max(self.peak_lateral, lateral)
            excessive = (speed > c["speed_kmh"] or lateral > c["lateral_g"]
                         or longitudinal > c["longitudinal_g"] or yaw > c["yaw_dps"])
        else:
            excessive = False
        if valid and excessive:
            self.exceeded_ms += dt
            self.episode_ms += dt
            if self.episode_ms >= c["min_event_ms"] and not self.episode_counted:
                self.events += 1
                self.episode_counted = True
        else:
            self.episode_ms = 0
            self.episode_counted = False
        duration = elapsed(now, self.start)
        if duration < c["window_ms"]:
            return None
        coverage = min(1.0, self.covered_ms / max(duration, 1))
        fraction = self.exceeded_ms / max(self.covered_ms, 1)
        # Sustained exceedance or repeated separated events can trigger review.
        concern = fraction >= c["exceedance_fraction"] or self.events >= c["min_events"]
        status = "insufficient_data" if coverage < c["min_coverage"] else ("review_driving" if concern else "normal")
        alert = (status == "review_driving" and
                 (self.last_alert is None or elapsed(now, self.last_alert) >= c["cooldown_ms"]))
        if alert:
            self.last_alert = now
        denominator = max(self.covered_ms, 1)
        result = {"type": "window", "status": status, "alert": alert,
                  "duration_ms": duration, "coverage": round(coverage, 3),
                  "exceedance_fraction": round(fraction, 3), "events": self.events,
                  "mean_speed_kmh": round(self.speed_sum / denominator, 2),
                  "lateral_rms_g": round(math.sqrt(self.lat_squared / denominator), 3),
                  "longitudinal_rms_g": round(math.sqrt(self.long_squared / denominator), 3),
                  "yaw_rms_dps": round(math.sqrt(self.yaw_squared / denominator), 2),
                  "peak_lateral_g": round(self.peak_lateral, 3), "baseline": "provisional_untrained"}
        self.start = now
        self.reset()
        return result


class Modem:
    """Nonblocking AT/HTTP transport. Simulation acknowledgement is not delivery.

    A bounded RAM queue preserves alerts ahead of routine telemetry. No persistence
    across power loss, TLS provisioning, or production endpoint in this version.
    """
    def __init__(self, uart, emit=print):
        self.uart, self.emit = uart, emit
        self.buffer = b""
        self.queue = []
        self.dropped = 0
        self.steps = []
        self.waiting = None
        self.seen = []
        self.sent_at = 0
        self.retry_at = None
        self.ready = False
        self.current = None

    def enqueue(self, payload):
        payload = dict(payload)
        payload["simulation"] = CONFIG["simulation"]
        if len(self.queue) >= CONFIG["queue_limit"]:
            routine = next((i for i, p in enumerate(self.queue) if not p.get("alert")), None)
            if routine is None:
                self.dropped += 1
                self.emit("QUEUE FULL: newest message dropped; existing alerts retained")
                return
            self.queue.pop(routine)
            self.dropped += 1
        self.queue.append(payload)

    def init_steps(self):
        return [("AT", "OK"), ("ATE0", "OK"), ("AT+CPIN?", "+CPIN: READY"),
                ("AT+CNMP=38", "OK"), ("AT+CEREG?", "REGISTERED"),
                ('AT+CGDCONT=1,"IP","%s"' % CONFIG["apn"], "OK"),
                ("AT+HTTPTERM", "OPTIONAL"), ("AT+HTTPINIT", "OK")]

    def retry(self, now, reason):
        self.emit("MODEM RETRY: " + reason)
        self.ready = False
        self.current = None  # message stays queued until HTTP success
        self.steps = []
        self.waiting = None
        self.retry_at = now
        self.buffer = b""

    def poll(self, now):
        chunk = self.uart.read(2048)
        if chunk:
            self.buffer += chunk
        while b"\n" in self.buffer:
            raw, self.buffer = self.buffer.split(b"\n", 1)
            try:
                line = raw.decode().strip()
            except UnicodeError:
                continue
            if line:
                self.seen.append(line)
        if len(self.buffer) > 4096:
            self.retry(now, "response overflow")
        if self.waiting:
            expected = self.waiting
            errors = any("ERROR" in line for line in self.seen)
            if expected == "REGISTERED":
                matched = any(line.startswith("+CEREG:") and line.split(",")[-1].strip() in ("1", "5") for line in self.seen)
            elif expected == "HTTP":
                actions = [line for line in self.seen if line.startswith("+HTTPACTION:")]
                try:
                    matched = bool(actions) and 200 <= int(actions[-1].split(",")[1]) < 300
                except (ValueError, IndexError):
                    matched = False
                if actions and not matched:
                    errors = True
            elif expected == "OPTIONAL":
                matched = "OK" in self.seen or errors
                errors = False
            else:
                matched = expected in self.seen
            # CPIN and CEREG require their terminating OK too, so stale OK cannot
            # acknowledge the next command. HTTPACTION uses its later URC.
            if expected in ("REGISTERED", "+CPIN: READY"):
                matched = matched and "OK" in self.seen
            if matched:
                self.waiting = None
                self.seen = []
                if expected == "HTTP":
                    item = self.current
                    if self.queue and self.queue[0] is item:
                        self.queue.pop(0)
                    self.emit(("SIMULATED ACK " if CONFIG["simulation"] else "HTTP ACK ") + json.dumps(item))
                    self.current = None
            elif errors or elapsed(now, self.sent_at) > 15000:
                self.retry(now, "error or timeout; retaining queued message")
            else:
                return
        if self.retry_at is not None:
            if elapsed(now, self.retry_at) < 5000:
                return
            self.retry_at = None
        if not self.steps:
            if not self.ready:
                self.steps = self.init_steps()
                self.ready = True
            elif self.queue:
                self.current = self.queue[0]
                body = json.dumps(self.current).encode()
                self.steps = [('AT+HTTPPARA="URL","%s"' % CONFIG["url"], "OK"),
                              ('AT+HTTPPARA="CONTENT","application/json"', "OK"),
                              ("AT+HTTPDATA=%d,10" % len(body), "DOWNLOAD"),
                              (body, "OK"), ("AT+HTTPACTION=1", "HTTP")]
            else:
                return
        command, self.waiting = self.steps.pop(0)
        self.seen = []
        self.uart.write(command if isinstance(command, bytes) else (command + "\r\n").encode())
        self.sent_at = now


def run():
    from machine import Pin, I2C, UART
    if not CONFIG["simulation"] and ("invalid" in CONFIG["url"] or CONFIG["apn"] == "SIMULATION_ONLY"):
        raise ValueError("Configure a real endpoint/APN and validate hardware before live mode")
    print("CUIDA v0.1 | VIRTUAL PROTOTYPE | provisional untrained baseline")
    gps = GPS(UART(1, baudrate=9600, tx=Pin(26), rx=Pin(27), rxbuf=2048))
    modem = Modem(UART(2, baudrate=115200, tx=Pin(17), rx=Pin(16), rxbuf=4096))
    i2c = I2C(0, scl=Pin(22), sda=Pin(21), freq=400000)
    sensor = None
    assessor = DrivingWindow()
    previous = last_telemetry = last_sensor_retry = time.ticks_ms()
    sequence = 0
    while True:
        now = time.ticks_ms()
        fix = gps.poll(now)
        modem.poll(now)
        if elapsed(now, previous) >= CONFIG["sample_ms"]:
            dt = elapsed(now, previous)
            previous = now
            motion = None
            try:
                if sensor is None and elapsed(now, last_sensor_retry) >= 1000:
                    last_sensor_retry = now
                    sensor = MPU6050(i2c)
                if sensor is not None:
                    motion = sensor.read()
            except OSError:
                sensor = None
            result = assessor.add(now, dt, fix, motion)
            if result:
                sequence += 1
                result.update({"sequence": sequence, "uptime_ms": now,
                               "location": fix, "sensor_ok": motion is not None})
                print("ASSESSMENT " + json.dumps(result))
                modem.enqueue(result)
            if elapsed(now, last_telemetry) >= CONFIG["telemetry_ms"]:
                sequence += 1
                modem.enqueue({"type": "telemetry", "sequence": sequence,
                               "uptime_ms": now, "location": fix, "motion": motion,
                               "gps_valid": fix is not None, "sensor_ok": motion is not None,
                               "dropped_messages": modem.dropped})
                last_telemetry = now
        time.sleep_ms(5)


if __name__ == "__main__":
    run()
