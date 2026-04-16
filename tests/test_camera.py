import cv2
import time

def main():
    print("Starting face tracker test with visual window...")
    
    try:
        import mediapipe as mp
    except ImportError:
        print("[SENSE] ERROR: mediapipe not installed.")
        return

    # Check if we should use the new tasks API or legacy solutions API
    try:
        mp_face = mp.solutions.face_detection
        FaceDetection = mp_face.FaceDetection
    except AttributeError:
        print("Wait! Your mediapipe version is missing 'mp.solutions'.")
        print("Please accept the downgrade command in the chat to fix this.")
        return

    cap = cv2.VideoCapture(0, cv2.CAP_AVFOUNDATION)
    if not cap.isOpened():
        print("ERROR: Cannot open webcam.")
        return

    # To show window on Mac properly, we need to create it in main thread
    cv2.namedWindow("ANIMA Face Tracker Test", cv2.WINDOW_NORMAL)

    with FaceDetection(
        model_selection=0,
        min_detection_confidence=0.6
    ) as detector:

        while True:
            ret, frame = cap.read()
            if not ret:
                time.sleep(0.05)
                continue

            # Flip the frame horizontally for a selfie-view display
            frame = cv2.flip(frame, 1)

            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            rgb_frame.flags.writeable = False
            results = detector.process(rgb_frame)

            if results.detections:
                detection = results.detections[0]
                bboxC = detection.location_data.relative_bounding_box
                ih, iw, _ = frame.shape
                
                # Bounding box coordinates
                x, y, w, h = int(bboxC.xmin * iw), int(bboxC.ymin * ih), int(bboxC.width * iw), int(bboxC.height * ih)
                
                # Clamp center X
                face_center_x = round(bboxC.xmin + bboxC.width / 2, 3)
                face_center_x = max(0.0, min(1.0, face_center_x))
                
                
                # Draw the bounding box
                cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
                
                # Draw text
                cv2.putText(frame, f"Face X: {face_center_x:.2f}", (x, y - 10), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
                
                print(f"Face Present: True | X Position: {face_center_x:.3f}")
            else:
                print("Face Present: False | X Position: -1.000")

            # Show the image
            cv2.imshow("ANIMA Face Tracker Test", frame)

            # Break loop if 'q' button is pressed
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
