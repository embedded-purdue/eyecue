import cv2
from flask import Flask, Response

app = Flask(__name__)

cap = cv2.VideoCapture(0)

def generate():
    while True:
        success, frame = cap.read()
        if not success:
            break

        ret, buffer = cv2.imencode('.jpg', frame)
        frame_bytes = buffer.tobytes()

        yield (
            b'--frame\r\n'
            b'Content-Type: image/jpeg\r\n\r\n' +
            frame_bytes +
            b'\r\n'
        )

@app.route('/stream')
def stream():
    return Response(
        generate(),
        mimetype='multipart/x-mixed-replace; boundary=frame'
    )

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5052, threaded=True)