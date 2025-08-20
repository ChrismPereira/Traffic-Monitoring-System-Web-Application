import cv2
import os
import time
import subprocess
import json
import csv
from ultralytics import YOLO
from tracker import Tracker

cancel_flag = False

def cancel_processing():
    global cancel_flag
    cancel_flag = True

def process_video(input_path, output_path, update, is_active):
    global cancel_flag
    cancel_flag = False

    model = YOLO("yolov8n.pt")
    cap = cv2.VideoCapture(input_path)
    assert cap.isOpened(), f"Cannot open video {input_path}"

    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    output_path = os.path.join("static", "processed", "output.mp4")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

    tracker = Tracker()
    line_position = height // 2
    frame_count = 0
    start_time = time.time()
    tracked_speeds = {}
    violation_speed_threshold = 40

    log_data = {
        'vehicle_count': 0,
        'vehicles': [],
        'violations': []
    }
    seen_ids = set()

    while True:
        if not is_active():
            cancel_flag = True
            break

        ret, frame = cap.read()
        if not ret:
            break

        frame_count += 1
        results = model(frame, verbose=False)[0]
        detections = []

        for result in results.boxes.data.tolist():
            x1, y1, x2, y2, score, class_id = result
            if score < 0.4:
                continue
            w, h = int(x2 - x1), int(y2 - y1)
            detections.append([int(x1), int(y1), w, h])

        tracked_objects = tracker.update(detections)

        for obj in tracked_objects:
            x, y, w, h, obj_id = obj
            cx = x + w // 2
            cy = y + h // 2

            if obj_id not in tracked_speeds:
                tracked_speeds[obj_id] = {'positions': [(frame_count, cx, cy)], 'logged': False}
            else:
                tracked_speeds[obj_id]['positions'].append((frame_count, cx, cy))

            if obj_id not in seen_ids:
                seen_ids.add(obj_id)
                log_data['vehicle_count'] += 1
                log_data['vehicles'].append({
                    'id': obj_id,
                    'type': 'Vehicle',  # Placeholder
                    'initial_frame': frame_count
                })

            cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
            cv2.putText(frame, f'ID: {obj_id}', (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)

            positions = tracked_speeds[obj_id]['positions']
            if len(positions) >= 2:
                (f1, x1, y1), (f2, x2, y2) = positions[-2], positions[-1]
                distance_px = ((x2 - x1)**2 + (y2 - y1)**2)**0.5
                time_sec = (f2 - f1) / fps
                speed_kmph = (distance_px / time_sec) * 0.06 if time_sec > 0 else 0
                cv2.putText(frame, f"{speed_kmph:.1f} km/h", (x, y + h + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)

                if speed_kmph > violation_speed_threshold and not tracked_speeds[obj_id]['logged']:
                    tracked_speeds[obj_id]['logged'] = True
                    log_data['violations'].append({
                        'id': obj_id,
                        'speed': round(speed_kmph, 1),
                        'frame': frame_count,
                        'time': round(frame_count / fps, 2)
                    })
                    cv2.putText(frame, "Violation!", (x, y + h + 40), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)

        out.write(frame)

        progress = int((frame_count / total_frames) * 100)
        update(progress)

    cap.release()
    out.release()

    if not cancel_flag:
        temp_path = output_path.replace(".mp4", "_temp.mp4")
        subprocess.run([
            'ffmpeg', '-y', '-i', output_path,
            '-c:v', 'libx264', '-preset', 'fast', '-crf', '23',
            '-c:a', 'aac', '-b:a', '128k',
            '-movflags', '+faststart',
            temp_path
        ])
        os.replace(temp_path, output_path)

        with open("static/processed/log.json", "w") as f:
            json.dump(log_data, f, indent=4)
            
        csv_path = "static/processed/log.csv"
        with open(csv_path, mode='w', newline='') as csv_file:
            writer = csv.writer(csv_file)
            writer.writerow(['Vehicle ID', 'Speed (km/h)', 'Frame', 'Time (s)'])
            for violation in log_data['violations']:
                writer.writerow([violation['id'], violation['speed'], violation['frame'], violation['time']])

        print(f"Processing finished in {time.time() - start_time:.2f} seconds")
