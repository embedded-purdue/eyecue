from flask import Blueprint
from flask import request, jsonify

serial_bp = Blueprint('serial', __name__, url_prefix='/serial')

@serial_bp.route('/connect', methods=["POST"])
def connect():

    if request.method == 'POST':
        ssid = request.form.get('ssid')
        password = request.form.get('password')

    # resp, err = serial_connect(ssid, password)
    resp, err = (None, None)
    if resp != 200:
        return jsonify({"message": err})
    
        
    return jsonify({"message": "ok"}), 200


@serial_bp.route('/status', methods=["GET"])
def status():


    # resp, err = serial_read()
    resp, err = (None, None)
    if resp != 200:
        return jsonify({"message": err})
    
        
    return jsonify({"message": "ok"}), 200