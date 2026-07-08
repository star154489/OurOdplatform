import cv2
import time
from ultralytics import YOLO

# 输入控制
CAMERA_WIDTH = 1280
CAMERA_HEIGHT = 720
CAMERA_FPS = 90

# 输出控制（设为None则保持原始尺寸）
DISPLAY_WIDTH = 1280
DISPLAY_HEIGHT = 720

model = YOLO('./train3-20258704-165508-yolo11n-best.pt')
cap = cv2.VideoCapture(0)

# 设置摄像头参数
cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAMERA_WIDTH)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_HEIGHT)
cap.set(cv2.CAP_PROP_FPS, CAMERA_FPS)

# 获取实际参数
actual_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
actual_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
actual_fps = int(cap.get(cv2.CAP_PROP_FPS))
total_frame = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

if total_frame > 0:
    print(f"摄像头参数:{actual_width}x{actual_height} {actual_fps}，总帧数:{total_frame}")
else:
    print(f"摄像头参数:{actual_width}x{actual_height} {actual_fps}(没有总帧数)")

frame_index = 0
fps = 0.0
last_time = time.time()

while True:
    ret, frame = cap.read()
    if not ret:
        break

    t_start = time.time()
    results = model(frame, verbose=False)
    t_end = time.time()
    infer_ms = (t_end - t_start) * 1000

    now = time.time()
    fps = 1.0 / (now - last_time)
    last_time = now

    annotated_frame = results[0].plot()
    cv2.putText(annotated_frame, text=f"Fps: {fps:.2f}", org=(10, 30),
                fontFace=cv2.FONT_HERSHEY_SIMPLEX, fontScale=1,
                color=(0, 255, 0), thickness=2)
    cv2.putText(annotated_frame, text=f"Infer: {infer_ms:.2f} ms", org=(10, 60),
                fontFace=cv2.FONT_HERSHEY_SIMPLEX, fontScale=1,
                color=(0, 255, 0), thickness=2)
    cv2.putText(annotated_frame, text=f"Frame: {frame_index}", org=(10, 90),
                fontFace=cv2.FONT_HERSHEY_SIMPLEX, fontScale=1,
                color=(0, 255, 0), thickness=2)
    cv2.putText(annotated_frame, text=f"size: {actual_width} * {actual_height}", org=(10, 120),
                fontFace=cv2.FONT_HERSHEY_SIMPLEX, fontScale=1,
                color=(0, 255, 0), thickness=2)

    # 根据设置决定是否缩放显示
    if DISPLAY_WIDTH is not None and DISPLAY_HEIGHT is not None:
        display_frame = cv2.resize(annotated_frame, dsize=(DISPLAY_WIDTH, DISPLAY_HEIGHT),
                                   interpolation=cv2.INTER_AREA)
    else:
        display_frame = annotated_frame

    cv2.imshow('frame', display_frame)

    key = cv2.waitKey(1) & 0xFF
    if key == ord('q') or key == 27:
        break
    frame_index += 1

cap.release()
cv2.destroyAllWindows()