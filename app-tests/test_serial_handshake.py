import unittest

from app import serial_connect


class _FakeReadSerial:
    def __init__(self, lines):
        self._lines = list(lines)

    def readline(self):
        if not self._lines:
            return b""
        return self._lines.pop(0)


class SerialHandshakeTests(unittest.TestCase):
    def test_build_wifi_config_command(self):
        line = serial_connect.build_wifi_config_command(
            ssid="MyWifi",
            password="Secret123",
            nonce="abc-123",
        )
        self.assertTrue(line.startswith("WIFI_CONFIG "))
        self.assertIn('"ssid":"MyWifi"', line)
        self.assertIn('"password":"Secret123"', line)
        self.assertIn('"nonce":"abc-123"', line)

    def test_parse_handshake_line(self):
        self.assertEqual(serial_connect.parse_handshake_line("ACK WIFI_CONFIG n1"), ("ack", "n1"))
        self.assertEqual(serial_connect.parse_handshake_line("OK 192.168.1.22"), ("ok", "192.168.1.22"))
        self.assertEqual(serial_connect.parse_handshake_line("ERR WIFI bad_password"), ("err", "WIFI bad_password"))
        self.assertEqual(serial_connect.parse_handshake_line("ERR JPEG missing"), ("err", "JPEG missing"))
        self.assertEqual(serial_connect.parse_handshake_line("noise"), ("ignore", "noise"))

    def test_read_handshake_signals_ack_then_ok(self):
        ser = _FakeReadSerial(
            [
                b"READY pico-w line-json receiver\n",
                b"ACK WIFI_CONFIG abc-123\n",
                b"OK 192.168.4.10\n",
            ]
        )
        saw_ack, ip_addr, err, lines = serial_connect.read_handshake_signals(
            ser,
            expected_nonce="abc-123",
            timeout_s=0.1,
        )
        self.assertTrue(saw_ack)
        self.assertEqual(ip_addr, "192.168.4.10")
        self.assertIsNone(err)
        self.assertIn("ACK WIFI_CONFIG abc-123", lines)

    def test_read_handshake_signals_ok_without_ack(self):
        ser = _FakeReadSerial([b"OK 10.0.0.55\n"])
        saw_ack, ip_addr, err, _lines = serial_connect.read_handshake_signals(
            ser,
            expected_nonce="nonce-unused",
            timeout_s=0.1,
        )
        self.assertFalse(saw_ack)
        self.assertEqual(ip_addr, "10.0.0.55")
        self.assertIsNone(err)

    def test_read_handshake_signals_err(self):
        ser = _FakeReadSerial([b"ERR WIFI timeout\n"])
        saw_ack, ip_addr, err, _lines = serial_connect.read_handshake_signals(
            ser,
            expected_nonce="nonce-unused",
            timeout_s=0.1,
        )
        self.assertFalse(saw_ack)
        self.assertIsNone(ip_addr)
        self.assertEqual(err, "WIFI timeout")


if __name__ == "__main__":
    unittest.main()
