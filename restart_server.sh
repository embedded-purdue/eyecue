#!/bin/bash
# Quick script to restart the Flask server

echo "Restarting Flask server..."

# Kill any existing Flask processes
pkill -f "python.*run_server.py" 2>/dev/null || true
pkill -f "flask run" 2>/dev/null || true

sleep 1

echo "Previous server stopped."
echo "Starting new server..."

# Start the server in the background using venv python
/Users/williamzhang/Documents/GitHub/eyecue/.venv/bin/python run_server.py &

sleep 2

echo "Server restarted!"
echo "Access at: http://127.0.0.1:5001"
