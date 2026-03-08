"""
app/serial_connect.py

- Scan ports for added peripheral (ESP32)
- Prompt for Wi-Fi SSID + password (or read from env)
- Connect via serial and send line-based config command
- Read line-based handshake responses (ACK / OK / ERR)

Protocol:
- Host -> device:
    WIFI_CONFIG {"ssid":"...","password":"...","nonce":"..."}\n
- Device -> host:
    ACK WIFI_CONFIG <nonce>
    OK <ip>
    ERR <domain> <reason>

Env vars supported:
  EYE_WIFI_SSID
  EYE_WIFI_PASS
  ESP32_PORT (optional fixed port like COM5 or /dev/ttyUSB0)
"""

from __future__ import annotations

import os
import json
import random
import re
import time
import getpass
from typing import Any, Callable, Optional, Tuple, List

try:
    import serial
    from serial import Serial
    from serial.tools import list_ports
except Exception:  # pragma: no cover - dependency availability
    serial = None
    list_ports = None


BAUD = 115200
WIFI_CONFIG_PREFIX = "WIFI_CONFIG "
DEFAULT_HANDSHAKE_ATTEMPTS = 3
DEFAULT_HANDSHAKE_TIMEOUT_S = 6.0
_IPV4_RE = re.compile(r"\b(\d{1,3}(?:\.\d{1,3}){3})\b")


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


def make_nonce() -> str:
    return f"{int(time.time() * 1000)}-{random.randrange(1000, 9999)}"


def build_wifi_config_command(ssid: str, password: str, nonce: str) -> str:
    payload = {
        "ssid": str(ssid),
        "password": str(password),
        "nonce": str(nonce),
    }
    return WIFI_CONFIG_PREFIX + json.dumps(payload, separators=(",", ":"))


def send_wifi_config_command(ser: Serial, ssid: str, password: str, nonce: str) -> str:
    line = build_wifi_config_command(ssid=ssid, password=password, nonce=nonce)
    ser.write((line + "\n").encode("utf-8"))
    ser.flush()
    return line


def extract_ipv4(text: str) -> Optional[str]:
    match = _IPV4_RE.search(text or "")
    if not match:
        return None
    candidate = match.group(1)
    parts = candidate.split(".")
    if all(0 <= int(part) <= 255 for part in parts):
        return candidate
    return None


def parse_handshake_line(line: str) -> Tuple[str, Optional[str]]:
    """Parse a serial line into one of: ack, ok, err, ignore."""
    text = (line or "").strip()
    if not text:
        return "ignore", None

    if text.startswith("ACK WIFI_CONFIG"):
        parts = text.split()
        nonce = parts[2] if len(parts) >= 3 else None
        return "ack", nonce

    if text.startswith("OK"):
        ip_addr = extract_ipv4(text)
        return "ok", ip_addr

    if text.startswith("ERR "):
        parts = text.split(" ", 2)
        domain = parts[1] if len(parts) >= 2 else "UNKNOWN"
        reason = parts[2] if len(parts) >= 3 else "unknown"
        return "err", f"{domain} {reason}".strip()

    return "ignore", text


def read_handshake_signals(
    ser: Serial,
    *,
    expected_nonce: Optional[str],
    timeout_s: float,
    line_logger: Optional[Callable[[str], None]] = None,
) -> Tuple[bool, Optional[str], Optional[str], List[str]]:
    """Read serial lines until timeout and parse ACK/OK/ERR signals."""
    end = time.monotonic() + max(0.1, float(timeout_s))
    saw_ack = False
    ok_ip: Optional[str] = None
    wifi_error: Optional[str] = None
    lines: List[str] = []

    while time.monotonic() < end:
        raw = ser.readline()
        if not raw:
            continue

        line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
        if not line:
            continue
        lines.append(line)
        if line_logger:
            try:
                line_logger(line)
            except Exception:
                pass

        kind, value = parse_handshake_line(line)
        if kind == "ack":
            if expected_nonce is None or value == expected_nonce:
                saw_ack = True
        if kind == "ok":
            if value:
                ok_ip = value
                return saw_ack, ok_ip, None, lines
        elif kind == "err":
            wifi_error = value or "unknown"
            return saw_ack, None, wifi_error, lines

    return saw_ack, ok_ip, wifi_error, lines


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
            for attempt in range(1, DEFAULT_HANDSHAKE_ATTEMPTS + 1):
                nonce = make_nonce()
                print(f"Sending WIFI_CONFIG attempt={attempt}/{DEFAULT_HANDSHAKE_ATTEMPTS} nonce={nonce}")
                send_wifi_config_command(ser, ssid, password, nonce)
                saw_ack, ip_addr, wifi_error, lines = read_handshake_signals(
                    ser,
                    expected_nonce=nonce,
                    timeout_s=DEFAULT_HANDSHAKE_TIMEOUT_S,
                )
                for line in lines:
                    print(line)

                if wifi_error:
                    print(f"Device reported error: {wifi_error}")
                    return 2
                if ip_addr:
                    print(f"Handshake complete. ACK seen={saw_ack} ip={ip_addr}")
                    return 0

                print("No ACK/OK response in time; retrying...")

            print("Failed to provision device after retries.")
            return 2

        return 0

    except KeyboardInterrupt:
        print("\nCancelled.")
        return 130
    except Exception as e:
        print(f"Error: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
