#!/usr/bin/env python
# -*- coding:utf-8 -*-
# FileName    :03-Opencv叠加信息显示.py
# Time        :2026/7/7 09:45:23
# Author      :雨雪同学
# Project     :ODPlatform
# Function    :显示FPS、推理时间、帧序号和图像尺寸

import cv2
import time
from ultralytics import YOLO

if __name__ == "__main__":
    model = YOLO('./train3-20250704-165500-yolo11n-best.pt')
    cap = cv2.VideoCapture(0)

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
        h, w = frame.shape[:2]

        annotated_frame = results[0].plot()
        cv2.putText(annotated_frame, text=f"FPS: {fps:.2f}", org=(10, 30),
                    fontFace=cv2.FONT_HERSHEY_SIMPLEX, fontScale=1,
                    color=(0, 255, 0), thickness=2)
        cv2.putText(annotated_frame, text=f"Infer: {infer_ms:.2f} ms", org=(10, 60),
                    fontFace=cv2.FONT_HERSHEY_SIMPLEX, fontScale=1,
                    color=(0, 255, 0), thickness=2)
        cv2.putText(annotated_frame, text=f"Frame: {frame_index}", org=(10, 90),
                    fontFace=cv2.FONT_HERSHEY_SIMPLEX, fontScale=1,
                    color=(0, 255, 0), thickness=2)
        cv2.putText(annotated_frame, text=f"Frame Size: {w}x{h}", org=(10, 120),
                    fontFace=cv2.FONT_HERSHEY_SIMPLEX, fontScale=1,
                    color=(0, 255, 0), thickness=2)

        cv2.imshow("YOLO Inference", annotated_frame)

        key = cv2.waitKey(1) & 0xFF
        if key == ord('q') or key == 27:
            break
        frame_index += 1

    cap.release()
    cv2.destroyAllWindows()