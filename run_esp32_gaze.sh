#!/bin/bash
# Quick script to run contour gaze tracker with ESP32 camera
# Usage: ./run_esp32_gaze.sh [ESP32_IP]
# Default IP: 192.168.4.49

ESP32_IP="${1:-192.168.4.49}"
STREAM_URL="http://${ESP32_IP}/stream"

echo "Connecting to ESP32 camera at: $STREAM_URL"
echo "Press 'q' to quit"

python3 /Users/shruthia/eyecue/contour_gaze_tracker.py --camera "$STREAM_URL"


