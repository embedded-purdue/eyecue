# eyecue

Repository for the EyeCue project

Weekly Goals for the project

Week 1 (Sep 7): Onboarding & research Introduce team roles & tools (Raspberry Pi, OpenCV, HID basics). Research existing eye-tracking methods + accessibility devices. Set up GitHub repo, task tracker (Notion).

Week 2: Environment setup & first tests Verify webcam/camera capture on laptops + Pi. Run OpenCV face/eye detection demo. Record sample eye videos or pull from existing database for algorithm testing. Week 3:

Basic eyetracking and pupil detection Implement grayscale + thresholding pupil detection. Track pupil center in real-time on screen (debug overlay). Deliverable: live video with overlaid pupil marker.

Week 4: Prototype cursor control Map gaze to mouse cursor movement (PC prototype). Add dwell-time click simulation. UX subteam refines sensitivity, calibration ideas.

Week 5: Embedded integration start Port code to Raspberry Pi. Optimize CV loop for low latency. Begin Pi acting as USB HID mouse.

Week 6: Map gaze commands → forward/turn movements. Demo: eye-controlled cursor with basic functionalities like click and scroll.

Week 7: Calibration & UX improvements Add calibration step (user looks at corners of screen). Improve dwell-time click, cursor smoothing. Collect first round of user feedback.

Week 8: Testing & refinement Measure accuracy, latency, false detections. Adjust algorithms (maybe Mediapipe for stability).

Week 9: Accessibility mode finalization Finalize PC accessibility version (cursor). Package software for easy installation. Document how it works for demo.

Week 10: Test gaze-to-cursor control in different environments. Safety checks: cursor movement stops when face not detected. Record demo video.

Week 11: Integration & user testing Bring all features together (PC cursor). Run demos with multiple testers. Document results for SPARK prep.

Week 12: Polish & presentation prep Final debugging + polish. Prepare slides, poster, and demo script. Run mock demos.

Week 13 (stop for SPARK): Wrap-up Freeze codebase Final rehearsal for SPARK demo. Write summary doc for future work.

Stretch Goal (if time allows) Glasses Hardware Expansion Mount Pi Camera/ESP32-CAM onto glasses frame.

