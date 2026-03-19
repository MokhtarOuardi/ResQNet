from flask import Flask, request
import os
import zipfile

app = Flask(__name__)

# Directory to save received files
UPLOAD_FOLDER = 'received_drone_data'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

import cv2
import glob
import re

def get_frame_num(filename):
    match = re.search(r'frame_(\d+)\.jpg', filename)
    return int(match.group(1)) if match else -1

def stitch_videos(extract_path):
    print(f"Checking for frames in: {extract_path}")
    # Each subfolder is a drone ID
    for drone_id in os.listdir(extract_path):
        drone_folder = os.path.join(extract_path, drone_id)
        if not os.path.isdir(drone_folder):
            continue

        # Find all jpg frames
        frame_pattern = os.path.join(drone_folder, "frame_*.jpg")
        frames = glob.glob(frame_pattern)
        if not frames:
            continue

        # Sort frames numerically: frame_0.jpg, frame_1.jpg, ...
        frames.sort(key=get_frame_num)
        
        print(f"Stitching {len(frames)} frames for drone {drone_id}...")
        
        # Determine properties from first frame
        first_frame = cv2.imread(frames[0])
        if first_frame is None:
            print(f"Failed to read first frame for {drone_id}")
            continue
            
        height, width, layers = first_frame.shape
        video_path = os.path.join(drone_folder, "drone_video.mp4")
        
        # Define codec and VideoWriter (using mp4v for generic mp4)
        fourcc = cv2.VideoWriter_fourcc(*'mp4v') 
        out = cv2.VideoWriter(video_path, fourcc, 10, (width, height))

        for frame_file in frames:
            img = cv2.imread(frame_file)
            if img is not None:
                out.write(img)
        
        out.release()
        print(f"Video saved: {video_path}")

@app.route('/upload', methods=['POST'])
@app.route('/upload/<phase>', methods=['POST'])
def upload_file(phase=None):
    if 'file' not in request.files:
        return 'No file part', 400
    
    file = request.files['file']
    if file.filename == '':
        return 'No selected file', 400

    if file:
        # If phase is provided, save into a subfolder for that phase
        target_folder = UPLOAD_FOLDER
        if phase:
            target_folder = os.path.join(UPLOAD_FOLDER, phase.lower())
            if not os.path.exists(target_folder):
                os.makedirs(target_folder)
        
        file_path = os.path.join(target_folder, file.filename)
        file.save(file_path)
        print(f"Received file for phase {phase or 'default'}: {file.filename}")

        # Automatically unzip the file
        try:
            with zipfile.ZipFile(file_path, 'r') as zip_ref:
                extract_path = os.path.join(target_folder, file.filename.replace('.zip', ''))
                zip_ref.extractall(extract_path)
                print(f"Extracted to: {extract_path}")
                
                # STITCH VIDEOS ON SERVER
                stitch_videos(extract_path)
        except Exception as e:
            print(f"Failed to process: {e}")

        return f'File successfully uploaded to {phase or "default"} and processed', 200

if __name__ == '__main__':
    # Listen on all interfaces (0.0.0.0) so other PCs can connect
    app.run(host='0.0.0.0', port=8080)
