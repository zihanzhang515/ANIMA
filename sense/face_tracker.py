"""
sense/face_tracker.py
---------------------
S1: Is face present? (True/False)
S2: Where is face horizontally? (0.0 to 1.0)

Uses MediaPipe FaceDetection via laptop webcam.
Runs in its own thread, updates shared_state continuously.
"""

import cv2
import time
import threading
from sense.sensor_state import shared_state


def run_face_tracker(stop_event: threading.Event):
    """
    Main loop for face tracking.
    Call this in a daemon thread from main.py.
    
    stop_event: threading.Event - set this to stop the thread cleanly
    """
    try:
        import mediapipe as mp
        mp_face = mp.solutions.face_detection
    except ImportError:
        print("[SENSE] ERROR: mediapipe not installed. Run: pip install mediapipe")
        return

    cap = cv2.VideoCapture(0, cv2.CAP_AVFOUNDATION)
    if not cap.isOpened():
        print("[SENSE] ERROR: Cannot open webcam.")
        return

    print("[SENSE] Face tracker started.")

    with mp_face.FaceDetection(
        model_selection=0,          # 0 = short range (< 2m), good for desk
        min_detection_confidence=0.6
    ) as detector:

        while not stop_event.is_set():
            ret, frame = cap.read()
            if not ret:
                time.sleep(0.05)
                continue

            # Convert BGR to RGB for MediaPipe
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            rgb_frame.flags.writeable = False
            results = detector.process(rgb_frame)

            if results.detections:
                # Face detected - get first face's center X position
                detection = results.detections[0]
                bbox = detection.location_data.relative_bounding_box

                # Calculate face center X (0.0 = left edge, 1.0 = right edge)
                face_center_x = round(bbox.xmin + bbox.width / 2, 3)
                # Clamp to valid range
                face_center_x = max(0.0, min(1.0, face_center_x))

                shared_state.update("face_present", True)
                shared_state.update("face_x", face_center_x)
            else:
                # No face detected
                shared_state.update("face_present", False)
                shared_state.update("face_x", 0.5)  # Reset to center

            time.sleep(0.05)  # ~20fps, fast enough for real-time tracking

    cap.release()
    print("[SENSE] Face tracker stopped.")
