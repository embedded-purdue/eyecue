# Minimal Serial Flashing Smoke Test (Raspberry Pi)

This is a trimmed-down serial test script to verify your app sends flashing/network config over serial.

## What it does

- waits for `CFGW + u16 length + JSON` packets
- prints the decoded JSON payload
- saves last payload to `~/.eyecue/last_flashing_payload.json`
- replies `OK` so app receives serial ACK

## Install

```bash
pip install pyserial
```

## Run

```bash
python3 app-tests/serial-client-test-script/rpi_serial_device_emulator.py \
  --port /dev/ttyGS0 \
  --baud 115200
```

Use your actual Pi serial device path if different (`/dev/ttyUSB0`, `/dev/ttyACM0`, etc).

## Expected payload from app

```json
{"type":"wifi_config","ssid":"...","password":"..."}
```

If you see that printed, flashing data send is working.
