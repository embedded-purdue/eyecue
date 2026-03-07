# Pico W Receiver Stub (MicroPython)

This script emulates the receiving end of the current EyeCue pipeline on a Raspberry Pi Pico W.

It does the following:

- waits for `CFGW + u16 + JSON` over USB serial
- expects payload:
  - `{"type":"wifi_config","ssid":"...","password":"..."}`
- connects to Wi-Fi with `network.WLAN(network.STA_IF)`
- sends `OK <ipv4>` over serial once connected
- serves `GET /stream` on port `80` as MJPEG
- streams a repeated tiny placeholder JPEG frame (no camera yet)

## Files

- `main.py`: MicroPython firmware script to copy to Pico W.

## Flash / Run

1. Install MicroPython on Pico W.
2. Copy `main.py` to the Pico W filesystem so it runs at boot.
3. Plug Pico W into the machine running EyeCue.
4. In EyeCue connect UI, pick the Pico W serial device and submit SSID/password.

## Protocol Notes

- Host app sends `CFGW` framed binary payload.
- Pico script replies with:
  - `OK <ip>`
- Backend then requests:
  - `http://<ip>/stream`

Important:

- Stream is served on port `80` (default HTTP).
- The current backend expects a bare IPv4 in the ACK line.

## Quick Validation

1. Start backend + Electron app.
2. Connect using Pico W serial port.
3. Confirm status alerts progress to:
   - `Network connected. Safe to unplug device.`
   - `Attempting to open camera stream…`
   - `Camera stream connected.`
4. Call `/runtime/state` and confirm:
   - `stream_url` is set
   - `frames_processed` increases over time

## Troubleshooting

- If no serial ACK appears:
  - verify the selected serial port is the Pico W USB serial device
  - reset Pico W and retry
- If Wi-Fi fails:
  - confirm SSID/password and 2.4 GHz support for your network
- If stream is not reached:
  - confirm Pico and host are on same LAN and port `80` is reachable
