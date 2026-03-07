"""Pico W MicroPython test harness for EyeCue serial + MJPEG pipeline.

Behavior:
- Reads CFGW-framed JSON over USB serial.
- Expects payload: {"type":"wifi_config","ssid":"...","password":"..."}.
- Connects to Wi-Fi and replies: "OK <ip>".
- Serves /stream as an MJPEG endpoint with a repeated placeholder JPEG frame.
"""

import json
import socket
import sys
import time

import network

try:
    import uselect as select
except ImportError:
    import select


MAGIC = b"CFGW"
SERIAL_BAUD_HINT = 115200
WIFI_CONNECT_TIMEOUT_MS = 20_000
FRAME_INTERVAL_MS = 150  # ~6.6 FPS placeholder stream
BOUNDARY = b"frame"

# Valid 1x1 JPEG generated once and embedded as static bytes.
JPEG_PLACEHOLDER = (
    b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    b"\xff\xdb\x00C\x00\x06\x04\x05\x06\x05\x04\x06\x06\x05\x06\x07\x07\x06"
    b"\x08\n\x10\n\n\t\t\n\x14\x0e\x0f\x0c\x10\x17\x14\x18\x18\x17\x14\x16\x16"
    b"\x1a\x1d%\x1f\x1a\x1b#\x1c\x16\x16 , #&')*)\x19\x1f-0-(0%()(\xff\xdb\x00C"
    b"\x01\x07\x07\x07\n\x08\n\x13\n\n\x13(((((((((((((((((((((((((((((((((((("
    b"((((((((((((((\xff\xc0\x00\x11\x08\x00\x01\x00\x01\x03\x01\"\x00\x02\x11"
    b"\x01\x03\x11\x01\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01"
    b"\x00\x00\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b"
    b"\xff\xc4\x00\xb5\x10\x00\x02\x01\x03\x03\x02\x04\x03\x05\x05\x04\x04\x00"
    b"\x00\x01}\x01\x02\x03\x00\x04\x11\x05\x12!1A\x06\x13Qa\x07\"q\x142\x81\x91"
    b"\xa1\x08#B\xb1\xc1\x15R\xd1\xf0$3br\x82\t\n\x16\x17\x18\x19\x1a%&'()*456789:"
    b"CDEFGHIJSTUVWXYZcdefghijstuvwxyz\x83\x84\x85\x86\x87\x88\x89\x8a\x92\x93\x94"
    b"\x95\x96\x97\x98\x99\x9a\xa2\xa3\xa4\xa5\xa6\xa7\xa8\xa9\xaa\xb2\xb3\xb4\xb5"
    b"\xb6\xb7\xb8\xb9\xba\xc2\xc3\xc4\xc5\xc6\xc7\xc8\xc9\xca\xd2\xd3\xd4\xd5\xd6"
    b"\xd7\xd8\xd9\xda\xe1\xe2\xe3\xe4\xe5\xe6\xe7\xe8\xe9\xea\xf1\xf2\xf3\xf4\xf5"
    b"\xf6\xf7\xf8\xf9\xfa\xff\xc4\x00\x1f\x01\x00\x03\x01\x01\x01\x01\x01\x01\x01"
    b"\x01\x01\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\xff"
    b"\xc4\x00\xb5\x11\x00\x02\x01\x02\x04\x04\x03\x04\x07\x05\x04\x04\x00\x01\x02"
    b"w\x00\x01\x02\x03\x11\x04\x05!1\x06\x12AQ\x07aq\x13\"2\x81\x08\x14B\x91\xa1"
    b"\xb1\xc1\t#3R\xf0\x15br\xd1\n\x16$4\xe1%\xf1\x17\x18\x19\x1a&'()*56789:CDEFG"
    b"HIJSTUVWXYZcdefghijstuvwxyz\x82\x83\x84\x85\x86\x87\x88\x89\x8a\x92\x93\x94"
    b"\x95\x96\x97\x98\x99\x9a\xa2\xa3\xa4\xa5\xa6\xa7\xa8\xa9\xaa\xb2\xb3\xb4\xb5"
    b"\xb6\xb7\xb8\xb9\xba\xc2\xc3\xc4\xc5\xc6\xc7\xc8\xc9\xca\xd2\xd3\xd4\xd5\xd6"
    b"\xd7\xd8\xd9\xda\xe2\xe3\xe4\xe5\xe6\xe7\xe8\xe9\xea\xf2\xf3\xf4\xf5\xf6\xf7"
    b"\xf8\xf9\xfa\xff\xda\x00\x0c\x03\x01\x00\x02\x11\x03\x11\x00?\x00\xf9R\x8a"
    b"(\xa0\x0f\xff\xd9"
)

STREAM_HEADERS = (
    b"HTTP/1.1 200 OK\r\n"
    b"Connection: close\r\n"
    b"Cache-Control: no-cache\r\n"
    b"Pragma: no-cache\r\n"
    b"Content-Type: multipart/x-mixed-replace; boundary=frame\r\n"
    b"\r\n"
)
STREAM_PART_PREFIX = (
    b"--" + BOUNDARY + b"\r\n"
    b"Content-Type: image/jpeg\r\n"
    b"Content-Length: " + str(len(JPEG_PLACEHOLDER)).encode("ascii") + b"\r\n"
    b"\r\n"
)


def _serial_streams():
    stdin = getattr(sys.stdin, "buffer", sys.stdin)
    stdout = getattr(sys.stdout, "buffer", sys.stdout)
    return stdin, stdout


def _as_bytes(raw):
    if raw is None:
        return b""
    if isinstance(raw, bytes):
        return raw
    if isinstance(raw, str):
        return raw.encode("utf-8")
    return bytes(raw)


def serial_write_line(text):
    _stdin, stdout = _serial_streams()
    payload = _as_bytes(text)
    if not payload.endswith(b"\n"):
        payload += b"\n"
    try:
        stdout.write(payload)
    except TypeError:
        # Some MicroPython builds expect str on sys.stdout (non-buffer variant).
        sys.stdout.write(payload.decode("utf-8", "replace"))
    try:
        stdout.flush()
    except Exception:
        try:
            sys.stdout.flush()
        except Exception:
            pass


def parse_cfgw_packets(rx_buffer):
    """Parse zero or more CFGW packets.

    Returns:
      (packets, remainder_buffer)
    """
    packets = []
    data = bytes(rx_buffer)
    total = len(data)
    cursor = 0

    while True:
        start = data.find(MAGIC, cursor)
        if start < 0:
            # Keep only a tiny tail so partial "CFGW" can be completed by next chunk.
            tail_start = total - 3 if total > 3 else 0
            if tail_start < cursor:
                tail_start = cursor
            return packets, bytearray(data[tail_start:])

        if (total - start) < 6:
            # Not enough bytes for magic + length header yet.
            return packets, bytearray(data[start:])

        payload_len = (data[start + 4] << 8) | data[start + 5]
        frame_end = start + 6 + payload_len
        if total < frame_end:
            # Partial frame, keep from magic onward.
            return packets, bytearray(data[start:])

        packets.append(data[start + 6:frame_end])
        cursor = frame_end


def wait_for_wifi_payload():
    stdin, _stdout = _serial_streams()
    poller = select.poll()
    poller.register(sys.stdin, select.POLLIN)
    rx_buffer = bytearray()

    serial_write_line("READY pico-w cfgw receiver")
    serial_write_line("INFO waiting for CFGW payload over USB serial")
    serial_write_line("INFO host should use baud {}".format(SERIAL_BAUD_HINT))

    while True:
        events = poller.poll(200)
        if not events:
            continue

        try:
            chunk = stdin.read(128)
        except Exception:
            chunk = None
        chunk = _as_bytes(chunk)
        if not chunk:
            continue

        rx_buffer.extend(chunk)

        packets, rx_buffer = parse_cfgw_packets(rx_buffer)
        for payload_bytes in packets:
            try:
                payload = json.loads(payload_bytes.decode("utf-8"))
            except Exception as exc:
                serial_write_line("ERR invalid_json {}".format(exc))
                continue

            if not isinstance(payload, dict):
                serial_write_line("ERR payload_not_object")
                continue

            if payload.get("type") != "wifi_config":
                serial_write_line("ERR invalid_type")
                continue

            ssid = payload.get("ssid")
            password = payload.get("password")
            if not isinstance(ssid, str) or not isinstance(password, str):
                serial_write_line("ERR missing_ssid_or_password")
                continue

            serial_write_line("INFO received wifi_config for ssid={}".format(ssid))
            return payload


def connect_wifi(ssid, password):
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if wlan.isconnected():
        try:
            wlan.disconnect()
            time.sleep_ms(250)
        except Exception:
            pass

    serial_write_line("INFO connecting_wifi")
    wlan.connect(ssid, password)

    deadline = time.ticks_add(time.ticks_ms(), WIFI_CONNECT_TIMEOUT_MS)
    while not wlan.isconnected():
        if time.ticks_diff(deadline, time.ticks_ms()) <= 0:
            raise RuntimeError("wifi_connect_timeout")
        time.sleep_ms(200)

    ip_addr = wlan.ifconfig()[0]
    return wlan, ip_addr


def send_404(conn):
    conn.send(
        b"HTTP/1.1 404 Not Found\r\n"
        b"Connection: close\r\n"
        b"Content-Type: text/plain\r\n"
        b"Content-Length: 9\r\n"
        b"\r\n"
        b"not found"
    )


def handle_client(conn):
    conn.settimeout(2)
    request = b""
    while b"\r\n\r\n" not in request and len(request) < 1024:
        chunk = conn.recv(256)
        if not chunk:
            break
        request += chunk

    request_line = request.split(b"\r\n", 1)[0] if request else b""
    try:
        request_text = request_line.decode("utf-8")
    except Exception:
        request_text = ""

    path = ""
    if request_text.startswith("GET "):
        parts = request_text.split(" ")
        if len(parts) >= 2:
            path = parts[1]

    if path != "/stream":
        send_404(conn)
        return

    conn.send(STREAM_HEADERS)

    while True:
        conn.send(STREAM_PART_PREFIX)
        conn.send(JPEG_PLACEHOLDER)
        conn.send(b"\r\n")
        time.sleep_ms(FRAME_INTERVAL_MS)


def serve_mjpeg():
    addr = socket.getaddrinfo("0.0.0.0", 80)[0][-1]
    sock = socket.socket()
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    except Exception:
        pass
    sock.bind(addr)
    sock.listen(2)
    sock.settimeout(1)

    serial_write_line("INFO mjpeg_server_listening port=80 path=/stream")

    while True:
        try:
            conn, remote = sock.accept()
        except OSError:
            continue

        try:
            serial_write_line("INFO client_connected {}".format(remote))
            handle_client(conn)
        except Exception:
            # Client disconnected or parse error; continue serving others.
            pass
        finally:
            try:
                conn.close()
            except Exception:
                pass


def main():
    payload = wait_for_wifi_payload()
    ssid = payload.get("ssid", "")
    password = payload.get("password", "")

    try:
        _wlan, ip_addr = connect_wifi(ssid, password)
    except Exception as exc:
        serial_write_line("ERR wifi_connect_failed {}".format(exc))
        return

    # The host backend watches for line starting with OK and an IPv4 token.
    serial_write_line("OK {}".format(ip_addr))
    serial_write_line("INFO wifi_connected ip={}".format(ip_addr))

    serve_mjpeg()


main()
