import sys
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "prototype"), str(ROOT / "demo")]
from main import CONFIG, GPS, DrivingWindow, Modem, MPU6050
from replay import Serial, ModemSerial, SensorBus, nmea, replay


class PrototypeTests(unittest.TestCase):
    def test_gps_checksum_fragmentation_void_and_stale(self):
        serial = Serial()
        gps = GPS(serial)
        valid = nmea(72)
        serial.feed(valid[:20])
        self.assertIsNone(gps.poll(0))
        serial.feed(valid[20:])
        self.assertAlmostEqual(gps.poll(100)["speed_kmh"], 72, places=1)
        serial.feed(valid.replace(b"GPRMC", b"GNRMC"))  # invalid checksum
        gps.poll(200)
        self.assertEqual(gps.last_valid, 100)
        self.assertIsNone(gps.poll(4000))
        serial.feed(nmea(valid=False))
        self.assertIsNone(gps.poll(4050))

    def test_mpu_scaling_and_negative_acceleration(self):
        bus = SensorBus()
        bus.x, bus.y, bus.yaw = -.5, .75, -90
        reading = MPU6050(bus).read()
        self.assertAlmostEqual(reading["x_g"], -.5)
        self.assertAlmostEqual(reading["y_g"], .75)
        self.assertAlmostEqual(reading["yaw_dps"], -90)

    def test_replay_expected_driving_and_sensor_failures(self):
        windows, _, received, logs = replay()
        self.assertEqual([w["status"] for w in windows], [
            "normal", "normal", "review_driving", "review_driving",
            "normal", "normal", "insufficient_data", "insufficient_data"])
        self.assertTrue(windows[2]["alert"])
        self.assertFalse(windows[3]["alert"])  # cooldown
        self.assertGreater(windows[2]["lateral_rms_g"], .3)
        self.assertTrue(any("MODEM RETRY" in line for line in logs))
        outage = [p for p in received if p.get("scenario") == "network_outage"]
        self.assertGreater(len(outage), 0)
        sequences = [p["sequence"] for p in received]
        self.assertEqual(len(sequences), len(set(sequences)))
        self.assertTrue(all(p["simulation"] for p in received))

    def test_alternating_lateral_forces_do_not_cancel(self):
        assessor = DrivingWindow()
        result = None
        for t in range(0, 30001, 50):
            result = assessor.add(t, 0 if t == 0 else 50, {"speed_kmh": 30},
                                  {"x_g": 0, "y_g": .6 if t % 100 == 0 else -.6, "yaw_dps": 0}) or result
        self.assertEqual(result["status"], "review_driving")
        self.assertAlmostEqual(result["lateral_rms_g"], .6)

    def test_sampling_gap_is_not_counted_as_observed_driving(self):
        assessor = DrivingWindow()
        motion = {"x_g": 0, "y_g": 0, "yaw_dps": 0}
        assessor.add(0, 0, {"speed_kmh": 20}, motion)
        result = assessor.add(30000, 30000, {"speed_kmh": 20}, motion)
        self.assertEqual(result["status"], "insufficient_data")

    def test_alert_retained_when_queue_overflows(self):
        modem = Modem(Serial(), emit=lambda _: None)
        modem.enqueue({"type": "window", "alert": True, "sequence": 1})
        for i in range(50):
            modem.enqueue({"type": "telemetry", "sequence": i+2})
        self.assertEqual(len(modem.queue), CONFIG["queue_limit"])
        self.assertEqual(modem.queue[0]["sequence"], 1)
        self.assertGreater(modem.dropped, 0)

    def test_http_server_error_keeps_payload_for_retry(self):
        class BadServer(ModemSerial):
            def write(self, data):
                result = super().write(data)
                if data == b"AT+HTTPACTION=1\r\n":
                    self.incoming = self.incoming.replace(b",200,", b",503,")
                return result
        uart = BadServer()
        modem = Modem(uart, emit=lambda _: None)
        modem.enqueue({"sequence": 1})
        for t in range(0, 2000, 50):
            modem.poll(t)
        self.assertEqual(len(modem.queue), 1)
        self.assertIsNotNone(modem.retry_at)

    def test_malformed_uart_noise_does_not_crash_transport(self):
        uart = Serial()
        modem = Modem(uart, emit=lambda _: None)
        modem.ready = True
        modem.enqueue({"sequence": 1})
        modem.waiting = "HTTP"
        modem.sent_at = 0
        uart.feed(b"\xff\xfe\r\n+HTTPACTION: malformed\r\n")
        modem.poll(50)
        self.assertIsNone(modem.waiting)
        self.assertIsNotNone(modem.retry_at)
        self.assertEqual(len(modem.queue), 1)


if __name__ == "__main__":
    unittest.main()
