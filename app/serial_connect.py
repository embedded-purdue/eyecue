"""
app/serial_connect.py

- Scan ports for added peripheral (ESP32)
- Prompt for WiFi SSID + password (or read from env)
- Connect via serial, send credentials, wait for OK
- Then watch ESP32 logs for connection success.

Protocol (very small + robust):
- PC -> ESP32: b"CFGW" + <u16 payload_len> + <UTF-8 JSON payload>
- ESP32 -> PC: "OK\n" after parsing + starting WiFi.begin()
- ESP32 prints status lines ("Connecting...", "Connected!", "IP address: ...")

Env vars supported:
  EYE_WIFI_SSID
  EYE_WIFI_PASS
  ESP32_PORT (optional fixed port like COM5 or /dev/ttyUSB0)
"""

from __future__ import annotations

import os
import sys
import json
import time
import getpass
from typing import Any, Optional, Tuple, List

try:
    import serial
    from serial.tools import list_ports
except Exception:  # pragma: no cover - dependency availability
    serial = None
    list_ports = None


MAGIC = b"CFGW"
BAUD = 115200


def list_serial_ports():
    if list_ports is None:
        return []
    return list(list_ports.comports())


def score_port(p) -> int:
    """
    Heuristics to pick "most likely ESP32" if multiple ports exist.
    You can tweak these checks for your environment.
    """
    text = f"{p.device} {p.description} {p.manufacturer} {p.hwid}".lower()
    score = 0
    for kw, pts in [
        ("esp32", 50),
        ("silicon labs", 25),   # CP210x
        ("cp210", 25),
        ("wch", 20),            # CH340/CH9102
        ("ch34", 20),
        ("usb serial", 10),
        ("uart", 10),
    ]:
        if kw in text:
            score += pts
    # Prefer "real" ports over bluetooth virtual, etc.
    if "bluetooth" in text:
        score -= 50
    return score


def pick_port(explicit: Optional[str] = None) -> str:
    if explicit:
        return explicit

    ports = list_serial_ports()
    if not ports:
        raise RuntimeError("No serial ports found. Is the ESP32 plugged in and drivers installed?")

    # Sort by heuristic
    ports_sorted = sorted(ports, key=score_port, reverse=True)

    # If best score is low, show options and choose first anyway
    best = ports_sorted[0]
    return best.device


def open_serial(port: str, baud: int = BAUD, timeout: float = 0.5) -> Any:
    if serial is None:
        raise RuntimeError("pyserial is not installed")
    ser = serial.Serial()
    ser.port = port
    ser.baudrate = baud
    ser.timeout = timeout
    ser.write_timeout = 2

    ser.open()

    # Many ESP32 boards reset when the port opens. Give it a moment.
    time.sleep(1.2)

    # Clear any boot noise
    try:
        ser.reset_input_buffer()
    except Exception:
        pass

    return ser


def frame_payload(payload: bytes) -> bytes:
    if len(payload) > 65535:
        raise ValueError("Payload too large for u16 length.")
    length = len(payload).to_bytes(2, byteorder="big", signed=False)
    return MAGIC + length + payload


def send_wifi_credentials(ser: serial.Serial, ssid: str, password: str) -> None:
    msg = {
        "type": "wifi_config",
        "ssid": ssid,
        "password": password,
    }
    payload = json.dumps(msg, separators=(",", ":")).encode("utf-8")
    packet = frame_payload(payload)
    ser.write(packet)
    ser.flush()


def read_lines_for(
    ser: serial.Serial,
    deadline_s: float,
    *,
    want_ok: bool = True,
) -> Tuple[bool, List[str]]:
    """
    Read text lines until deadline. Returns (saw_ok, lines).
    We decode with 'replace' because ESP32 boot logs can have odd bytes.
    """
    end = time.time() + deadline_s
    saw_ok = False
    lines: List[str] = []

    # Use readline() so we can parse "OK", "Connected!", etc.
    while time.time() < end:
        raw = ser.readline()  # reads until '\n' or timeout
        if not raw:
            continue
        line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
        if line:
            lines.append(line)
            print(line)

            if want_ok and line.strip() == "OK":
                saw_ok = True

            # If your firmware prints these, we can stop early
            if "Connected!" in line or "IP address:" in line:
                # Keep collecting a bit more if you want, but we can return quickly.
                pass

    return saw_ok, lines


def get_creds_from_user() -> Tuple[str, str]:
    ssid = os.getenv("EYE_WIFI_SSID") or input("Wi-Fi SSID: ").strip()
    if not ssid:
        raise ValueError("SSID cannot be empty.")

    password = os.getenv("EYE_WIFI_PASS")
    if password is None:
        password = getpass.getpass("Wi-Fi password (hidden): ")
    return ssid, password


def main() -> int:
    explicit_port = os.getenv("ESP32_PORT")  # e.g. COM5 or /dev/ttyUSB0
    try:
        port = pick_port(explicit_port)
        print(f"Using serial port: {port}")

        ssid, password = get_creds_from_user()

        with open_serial(port) as ser:
            print("Sending Wi-Fi credentials to ESP32...")
            send_wifi_credentials(ser, ssid, password)

            print("Waiting for OK from ESP32 (ack)...")
            saw_ok, _ = read_lines_for(ser, deadline_s=6.0, want_ok=True)
            if not saw_ok:
                print("Did not see OK. The ESP32 may not be running the serial-config firmware.")
                print("Tip: confirm Arduino sketch reads the CFGW frame and prints 'OK'.")
                return 2

            print("Ack received. Waiting for Wi-Fi connection logs...")
            # Give it time to connect. Adjust to your environment.
            read_lines_for(ser, deadline_s=20.0, want_ok=False)

        return 0

    except KeyboardInterrupt:
        print("\nCancelled.")
        return 130
    except Exception as e:
        print(f"Error: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
