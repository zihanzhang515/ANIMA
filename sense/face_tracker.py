"""
sense/face_tracker.py
---------------------
S1: Is face present? (True/False)
S2: Where is face horizontally? (0.0 to 1.0)

Uses MediaPipe FaceDetection via laptop webcam.
Runs in its own thread, updates shared_state continuously.
"""

import sys
import os

# 为了让你可以直接在 IDE 点击“运行”按钮或者运行文件的绝对路径，我们把项目根目录加入到 Python 的搜索路径中
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2
import time
import threading
from sense.sensor_state import shared_state


def run_face_tracker(stop_event: threading.Event, show_video: bool = False):
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

    try:
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
                # 反转 X 坐标，修正摄像头镜像导致的左右相反问题
                face_center_x = 1.0 - (bbox.xmin + bbox.width / 2)
                face_center_x = round(face_center_x, 3)
                # Clamp to valid range
                face_center_x = max(0.0, min(1.0, face_center_x))

                # face_size: bbox.width 是人脸宽度占画面比例（大约 0.1（远）到 0.6）（近））
                face_size = round(min(1.0, max(0.0, bbox.width)), 3)

                shared_state.update("face_present", True)
                shared_state.update("face_x", face_center_x)
                shared_state.update("face_size", face_size)
            else:
                # No face detected
                shared_state.update("face_present", False)
                shared_state.update("face_x", 0.5)  # Reset to center
                shared_state.update("face_size", 0.0)

            if show_video:
                display_frame = frame.copy()
                if results.detections:
                    for detection in results.detections:
                        mp.solutions.drawing_utils.draw_detection(display_frame, detection)
                
                # 水平翻转图像，使其像照镜子一样自然
                cv2.imshow("Anima Face Tracker (Press 'q' to exit)", cv2.flip(display_frame, 1))
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    stop_event.set()
                    break

            time.sleep(0.05)  # ~20fps, fast enough for real-time tracking

    finally:
        cap.release()
        if show_video:
            cv2.destroyAllWindows()
        print("[SENSE] Face tracker stopped.")

if __name__ == "__main__":
    import threading
    stop_event = threading.Event()

    # 启动一个专门用来只读和打印状态的小线程（用来给你演示如何查看）
    def print_state():
        while not stop_event.is_set():
            print(f"\n当前汇总的最终数据: {shared_state.get()}")
            time.sleep(1)  # 每 1 秒打印一次
            
    printer_thread = threading.Thread(target=print_state)
    printer_thread.start()

    try:
        run_face_tracker(stop_event, show_video=True)
    except KeyboardInterrupt:
        stop_event.set()
    
    printer_thread.join()
    print("停止测试")
