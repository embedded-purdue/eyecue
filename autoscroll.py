# #!/usr/bin/env python3

import cv2
import time
from pupil_detector import detect_pupil_contour

def autoscroll(height, current_y, enter_t, last_scroll, active_zone):
    # scroll percent = 0.15
    top_zone = height * 0.15
    bottom_zone = height * 0.85
    zone = None

    if (current_y <= top_zone):
        zone = 'top'
        # print("Iris in Scroll Up Zone")
    elif (current_y >= bottom_zone):
        zone = 'bottom'
        # print("Iris in Scroll Down Zone")
    
    now = time.time()
    if zone != active_zone:
        active_zone = zone
        enter_t = now

    if active_zone is None:
        return active_zone, last_scroll, enter_t

    hold_time = now - enter_t
    if (hold_time >= 2) and ((now - last_scroll) >= 2):
        if active_zone == 'top':
            print("Scroll Up")
        else:
            print("Scroll Down")
        last_scroll = now
    
    return active_zone, last_scroll, enter_t

# Main Loop --> just for testing
active_zone = None
last_scroll = 0
enter_t = time.time()

cap = cv2.VideoCapture(0)

while True:
    ret, frame = cap.read()
    if not ret:
        break

    # detect pupil center
    (full_cx, full_cy), _ = detect_pupil_contour(frame)
    if full_cx is not None:
        h, w, _ = frame.shape

        # call autoscroll logic
        active_zone, last_scroll, enter_t = autoscroll(
            height=h,
            current_y=full_cy,
            enter_t=enter_t,
            last_scroll=last_scroll,
            active_zone=active_zone
        )

        # visualize
        cv2.circle(frame, (full_cx, full_cy), 5, (0, 0, 255), -1)
        cv2.line(frame, (0, int(h * 0.15)), (w, int(h * 0.15)), (0, 255, 0), 2) # top zone
        cv2.line(frame, (0, int(h * 0.85)), (w, int(h * 0.85)), (255, 0, 0), 2) # bottom zone

    cv2.imshow("Pupil Tracker", frame)
    if cv2.waitKey(1) & 0xFF == 27:
        break

cap.release()
cv2.destroyAllWindows()