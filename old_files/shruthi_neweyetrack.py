#!/usr/bin/env python3
"""
basic pupil tracker
- focus on eye roi, not whole face
- find pupil as darkest blob
- print pupil (x,y) coords
"""

import cv2

# start cam
cap = cv2.VideoCapture(0)

while True:
    ret, frame = cap.read()
    if not ret:
        break

    # gray img
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    # crop roi ~ eye area (adj ratios if needed)
    h, w = gray.shape
    roi = gray[int(h*0.3):int(h*0.8), int(w*0.2):int(w*0.8)]
    roi_color = frame[int(h*0.3):int(h*0.8), int(w*0.2):int(w*0.8)]

    # binarize -> pupil dark spot
    thresh = cv2.adaptiveThreshold(
        roi, 255,
        cv2.ADAPTIVE_THRESH_MEAN_C,
        cv2.THRESH_BINARY_INV,
        21, 10
    )

    # find cnts (blobs)
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    if contours:
        # assume biggest blob = pupil
        pupil = max(contours, key=cv2.contourArea)
        x, y, w_box, h_box = cv2.boundingRect(pupil)

        # draw box
        cv2.rectangle(roi_color, (x, y), (x+w_box, y+h_box), (0, 255, 0), 2)

        # calc center coords
        cx = x + w_box // 2
        cy = y + h_box // 2

        # print coords (rel to roi)
        print(f"pupil: ({cx}, {cy})")

    # show live + bin view
    cv2.imshow("roi", roi_color)
    cv2.imshow("thresh", thresh)

    # quit on q
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()

