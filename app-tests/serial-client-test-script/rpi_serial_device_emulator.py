#!/usr/bin/env python3
"""Minimal Raspberry Pi serial smoke test for EyeCue flashing flow.

What it does:
- waits for CFGW-framed JSON from the app
- prints and saves the decoded payload
- replies with "OK\n" so app sees an ACK
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

try:
    import serial
except ModuleNotFoundError:
    serial = None

MAGIC = b"CFGW"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Minimal EyeCue serial flashing smoke test")
    parser.add_argument("--port", required=True, help="Serial port on Raspberry Pi (example: /dev/ttyGS0)")
    parser.add_argument("--baud", type=int, default=115200, help="Baud rate")
    parser.add_argument(
        "--out",
        default=str(Path.home() / ".eyecue" / "last_flashing_payload.json"),
        help="Where to store last received payload",
    )
    parser.add_argument("--ack", default="OK", help="ACK line sent back to app")
    return parser.parse_args()


def save_payload(path_str: str, payload: dict) -> None:
    path = Path(path_str).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "received_at_ms": int(time.time() * 1000),
        "payload": payload,
    }
    with path.open("w", encoding="utf-8") as f:
        json.dump(record, f, indent=2, sort_keys=True)


def parse_packets(buffer: bytearray):
    packets = []
    while True:
        start = buffer.find(MAGIC)
        if start < 0:
            if len(buffer) > 3:
                del buffer[:-3]
            break

        if start > 0:
            del buffer[:start]

        if len(buffer) < 6:
            break

        payload_len = int.from_bytes(buffer[4:6], "big", signed=False)
        frame_len = 6 + payload_len
        if len(buffer) < frame_len:
            break

        payload_bytes = bytes(buffer[6:frame_len])
        del buffer[:frame_len]
        packets.append(payload_bytes)

    return packets


def main() -> int:
    args = parse_args()

    if serial is None:
        print("pyserial is required: pip install pyserial")
        return 2

    print(f"Listening on {args.port} @ {args.baud} baud")
    print(f"Writing last payload to: {Path(args.out).expanduser()}")

    rx = bytearray()

    try:
        with serial.Serial(port=args.port, baudrate=args.baud, timeout=0.1, write_timeout=1.0) as ser:
            while True:
                chunk = ser.read(ser.in_waiting or 1)
                if chunk:
                    rx.extend(chunk)

                for payload_bytes in parse_packets(rx):
                    try:
                        text = payload_bytes.decode("utf-8")
                        payload = json.loads(text)
                        print("Received payload:")
                        print(json.dumps(payload, indent=2, sort_keys=True))
                        save_payload(args.out, payload)

                        ser.write((args.ack + "\n").encode("utf-8"))
                        ser.flush()
                        print(f"Sent ACK: {args.ack}")
                    except Exception as exc:
                        print(f"Failed to decode payload: {exc}")
    except KeyboardInterrupt:
        print("Stopped.")
        return 0
    except Exception as exc:
        print(f"Error: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
