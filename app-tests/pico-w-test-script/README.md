# Pico W Receiver Stub (MicroPython)

This script emulates the receiving end of the EyeCue pipeline on Raspberry Pi Pico W.

## Serial Protocol

Host sends one line:

```text
WIFI_CONFIG {"ssid":"...","password":"...","nonce":"..."}
```

Pico replies:

- `ACK WIFI_CONFIG <nonce>`
- `OK <ipv4>` on success
- `ERR <domain> <reason>` on failure (for example `ERR WIFI ...` or `ERR JPEG ...`)

The script ignores unrelated REPL chatter lines.

## Stream Behavior

- Pico loads `eye.jpg` from its local filesystem at boot.
- `GET /stream` on port `80` serves strict multipart MJPEG with that JPEG repeated.
- Non-`/stream` requests return `404`.

## Convert Your Eye Image

Example deterministic conversion using ImageMagick:

```bash
magick input-eye.png \
  -resize 320x240^ \
  -gravity center \
  -extent 320x240 \
  -colorspace sRGB \
  -interlace none \
  -quality 75 \
  eye.jpg
```

Recommended target:

- baseline JPEG (non-progressive)
- RGB/sRGB
- around `320x240`
- quality `70-85`

## Compress JPG

```bash
magick input-eye2.jpg -resize 320x240^ -gravity center -extent 320x240 -colorspace sRGB -interlace none -quality 75 eye2.jpg
```

## Upload to Pico W

```bash
mpremote cp app-tests/pico-w-test-script/main.py :main.py
mpremote cp eye.jpg :eye.jpg
```

Reset Pico W after upload.

## Run / Validate

1. Start backend + Electron app.
2. Select Pico USB serial port in connect UI.
3. Submit SSID/password once.
4. Expect alert progression:
   - network connected
   - attempting stream
   - stream connected
5. Verify `/runtime/state` shows:
   - `stream_url` set
   - `frames_processed` increasing

## Important Constraint

Do not keep a separate REPL monitor attached while the app owns the serial port. That causes dropped/spotty ACK behavior.
