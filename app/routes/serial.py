from __future__ import annotations

from flask import Blueprint, jsonify

from app import serial_connect


serial_bp = Blueprint("serial", __name__, url_prefix="/serial")


@serial_bp.route("/ports", methods=["GET"])
def ports() -> tuple:
    ports = serial_connect.list_serial_ports()
    payload = [
        {
            "device": getattr(port, "device", ""),
            "description": getattr(port, "description", ""),
            "hwid": getattr(port, "hwid", ""),
        }
        for port in ports
    ]
    return jsonify({"ok": True, "data": payload}), 200
