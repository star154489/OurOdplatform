import cv2
from ultralytics import YOLO

if __name__ == "__main__":
    model = YOLO('./train3-20250704-165500-yolo11n-best.pt')
    cap = cv2.VideoCapture(0)  # 打开摄像头

    while True:
        ret, frame = cap.read()
        if not ret:
            break
        results = model(frame, verbose=False)
        annotated_frame = results[0].plot()
        cv2.imshow('YOLO Inference', annotated_frame)
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q') or key == 27:
            break

    cap.release()
    cv2.destroyAllWindows()