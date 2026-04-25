"""
sense/face_tracker.py — v2
新增：追踪脸部大小（bbox.width），用于 Shy 触发检测
face_size 是脸部宽度占画面宽度的比例（0.0-1.0）
正常坐在电脑前大约 0.1-0.2，靠近时会增大
"""

import cv2
import time
import threading
from sense.sensor_state import shared_state


def run_face_tracker(stop_event: threading.Event):
    try:
        import mediapipe as mp
        mp_face = mp.solutions.face_detection
    except ImportError:
        print("[SENSE] ERROR: mediapipe not installed")
        return

    cap = cv2.VideoCapture(0, cv2.CAP_AVFOUNDATION)
    if not cap.isOpened():
        print("[SENSE] ERROR: Cannot open webcam.")
        return

    print("[SENSE] Face tracker started (with size tracking).")

    with mp_face.FaceDetection(
        model_selection=0,
        min_detection_confidence=0.6
    ) as detector:

        while not stop_event.is_set():
            ret, frame = cap.read()
            if not ret:
                time.sleep(0.05)
                continue

            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            rgb_frame.flags.writeable = False
            results = detector.process(rgb_frame)

            if results.detections:
                detection = results.detections[0]
                bbox = detection.location_data.relative_bounding_box

                face_center_x = round(bbox.xmin + bbox.width / 2, 3)
                face_center_x = max(0.0, min(1.0, face_center_x))

                # 脸部大小 = bounding box 宽度（相对画面宽度）
                # 正常距离约 0.10-0.20，靠近时增大
                face_size = round(min(1.0, max(0.0, bbox.width)), 3)

                shared_state.update("face_present", True)
                shared_state.update("face_x", face_center_x)
                shared_state.update("face_size", face_size)
            else:
                shared_state.update("face_present", False)
                shared_state.update("face_x", 0.5)
                shared_state.update("face_size", 0.0)

            time.sleep(0.05)

    cap.release()
    print("[SENSE] Face tracker stopped.")
