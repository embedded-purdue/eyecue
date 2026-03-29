"""Pico W MicroPython receiver for EyeCue serial + MJPEG pipeline.

Protocol:
- Host -> device:
    WIFI_CONFIG {"ssid":"...","password":"...","nonce":"..."}\n
- Device -> host:
    ACK WIFI_CONFIG <nonce>
    OK <ip>
    ERR <domain> <reason>

Stream:
- GET /stream serves multipart MJPEG using eye.jpg from Pico filesystem.
"""

import json
import socket
import sys
import time

import network  # type: ignore

try:
    import uselect as select  # type: ignore
except ImportError:
    import select


WIFI_CONFIG_PREFIX = "WIFI_CONFIG "
WIFI_CONNECT_TIMEOUT_MS = 30_000
FRAME_INTERVAL_MS = 150  # ~6.6 FPS
BOUNDARY = b"frame"
EYE_JPEG_PATH = "eye.jpg"


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
        sys.stdout.write(payload.decode("utf-8", "replace"))

    try:
        stdout.flush()
    except Exception:
        try:
            sys.stdout.flush()
        except Exception:
            pass


def _split_lines(buffer):
    if not buffer:
        return [], b""

    lines = []
    start = 0
    while True:
        idx = buffer.find(b"\n", start)
        if idx < 0:
            break
        line = buffer[start:idx].rstrip(b"\r")
        lines.append(line)
        start = idx + 1
    return lines, buffer[start:]


def _parse_wifi_config_line(line):
    text = (line or "").strip()
    if not text.startswith(WIFI_CONFIG_PREFIX):
        return None, None

    payload_text = text[len(WIFI_CONFIG_PREFIX):].strip()
    try:
        payload = json.loads(payload_text)
    except Exception as exc:
        return None, "invalid_json {}".format(exc)

    if not isinstance(payload, dict):
        return None, "payload_not_object"

    ssid = payload.get("ssid")
    password = payload.get("password")
    nonce = payload.get("nonce")
    if not isinstance(ssid, str) or not isinstance(password, str) or not isinstance(nonce, str):
        return None, "missing_ssid_password_or_nonce"

    return payload, None


def wait_for_wifi_payload():
    stdin, _stdout = _serial_streams()
    poller = select.poll()
    poller.register(sys.stdin, select.POLLIN)
    rx_buffer = b""

    serial_write_line("READY pico-w line-json receiver")
    serial_write_line("INFO waiting for WIFI_CONFIG line over USB serial")

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

        rx_buffer += chunk
        lines, rx_buffer = _split_lines(rx_buffer)
        for raw_line in lines:
            try:
                line = raw_line.decode("utf-8", "replace").strip()
            except Exception:
                continue
            if not line:
                continue

            # Explicit debug visibility for host-side transcript logs.
            serial_write_line("INFO serial_rx {}".format(line))

            payload, error = _parse_wifi_config_line(line)
            if error:
                serial_write_line("ERR WIFI_CONFIG {}".format(error))
                continue
            if payload is None:
                continue

            nonce = payload.get("nonce", "")
            ssid = payload.get("ssid", "")
            serial_write_line("ACK WIFI_CONFIG {}".format(nonce))
            serial_write_line("INFO received_wifi_config ssid={} nonce={}".format(ssid, nonce))
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

    return wlan.ifconfig()[0]


def load_eye_jpeg(path):
    try:
        with open(path, "rb") as f:
            jpeg = f.read()
    except Exception as exc:
        raise RuntimeError("jpeg_missing {}".format(exc))

    if not jpeg:
        raise RuntimeError("jpeg_empty")
    if len(jpeg) < 4:
        raise RuntimeError("jpeg_too_small")
    if not jpeg.startswith(b"\xff\xd8") or not jpeg.endswith(b"\xff\xd9"):
        raise RuntimeError("jpeg_invalid_markers")
    return jpeg


def _send_all(conn, payload):
    view = payload
    while view:
        sent = conn.send(view)
        if sent is None or sent <= 0:
            raise OSError("socket_send_failed")
        view = view[sent:]


def send_404(conn):
    _send_all(
        conn,
        b"HTTP/1.1 404 Not Found\r\n"
        b"Connection: close\r\n"
        b"Content-Type: text/plain\r\n"
        b"Content-Length: 9\r\n"
        b"\r\n"
        b"not found",
    )


def handle_client(conn, jpeg_bytes):
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
            path = parts[1].split("?", 1)[0]

    if path != "/stream":
        send_404(conn)
        return

    stream_headers = (
        b"HTTP/1.1 200 OK\r\n"
        b"Connection: close\r\n"
        b"Cache-Control: no-cache\r\n"
        b"Pragma: no-cache\r\n"
        b"Content-Type: multipart/x-mixed-replace; boundary=frame\r\n"
        b"\r\n"
    )
    part_prefix = (
        b"--" + BOUNDARY + b"\r\n"
        b"Content-Type: image/jpeg\r\n"
        b"Content-Length: " + str(len(jpeg_bytes)).encode("ascii") + b"\r\n"
        b"\r\n"
    )

    _send_all(conn, stream_headers)
    while True:
        _send_all(conn, part_prefix)
        _send_all(conn, jpeg_bytes)
        _send_all(conn, b"\r\n")
        time.sleep_ms(FRAME_INTERVAL_MS)


def serve_mjpeg(jpeg_bytes):
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
            handle_client(conn, jpeg_bytes)
        except Exception:
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
        ip_addr = connect_wifi(ssid, password)
    except Exception as exc:
        serial_write_line("ERR WIFI {}".format(exc))
        return

    try:
        jpeg_bytes = load_eye_jpeg(EYE_JPEG_PATH)
    except Exception as exc:
        serial_write_line("ERR JPEG {}".format(exc))
        return

    serial_write_line("OK {}".format(ip_addr))
    serial_write_line("INFO wifi_connected ip={}".format(ip_addr))
    serial_write_line("INFO jpeg_loaded path={} bytes={}".format(EYE_JPEG_PATH, len(jpeg_bytes)))

    serve_mjpeg(jpeg_bytes)


main()
