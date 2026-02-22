#!/usr/bin/env python3


import time


UP_THRESHOLD = 8       # degrees (head up)
DOWN_THRESHOLD = -8    # degrees (head down)

HOLD_DELAY = 0.8       # seconds before scroll starts
SCROLL_INTERVAL = 0.35 # repeat scroll speed 
# we can use calibiration values for these 

SCROLL_STEP = 60       # pixels per scroll event


def autoscroll(angle_v, enter_t, last_scroll, active_zone):

    zone = None

   
    if angle_v > UP_THRESHOLD:
        zone = "up"

    elif angle_v < DOWN_THRESHOLD:
        zone = "down"

    now = time.time()


    if zone != active_zone:
        active_zone = zone
        enter_t = now

    if active_zone is None:
        return active_zone, last_scroll, enter_t

    hold_time = now - enter_t

 
    if hold_time >= HOLD_DELAY and (now - last_scroll) >= SCROLL_INTERVAL:

        if active_zone == "up":
            print("Scroll Up")

        

        elif active_zone == "down":
            print("Scroll Down")


        last_scroll = now

    return active_zone, last_scroll, enter_t