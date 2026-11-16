"""
DRAWING ROBOT - UTILITY FUNCTIONS
==================================
This module provides helper utilities for file handling, base64 image encoding,
JSON/CSV serialization of robot paths, and mathematical helper functions.
"""

import os
import json
import csv
import math
import base64
import cv2
import numpy as np
import config

def ensure_directories():
    """Ensure upload and generated path directories exist."""
    os.makedirs(config.UPLOAD_FOLDER, exist_ok=True)
    os.makedirs(config.GENERATED_PATHS_FOLDER, exist_ok=True)

def allowed_file(filename):
    """
    Check if the uploaded file has a valid image extension.
    Example: 'drawing.jpg' -> True, 'script.py' -> False
    """
    if '.' not in filename:
        return False
    ext = filename.rsplit('.', 1)[1].lower()
    return ext in config.ALLOWED_EXTENSIONS

def encode_image_to_base64(image_array, file_format='.png'):
    """
    Convert an OpenCV numpy image array into a Base64 Data URL string
    so it can be displayed directly in the browser's <img> tag.
    """
    if image_array is None:
        return ""
    success, buffer = cv2.imencode(file_format, image_array)
    if not success:
        return ""
    b64_encoded = base64.b64encode(buffer).decode('utf-8')
    mime_type = "image/png" if file_format == '.png' else "image/jpeg"
    return f"data:{mime_type};base64,{b64_encoded}"

def calculate_distance(point1, point2):
    """
    Calculate Euclidean distance between two 2D points (x1, y1) and (x2, y2).
    Formula: sqrt((x2 - x1)^2 + (y2 - y1)^2)
    """
    dx = point2[0] - point1[0]
    dy = point2[1] - point1[1]
    return math.sqrt(dx * dx + dy * dy)

def save_path_to_json(path_data, filepath):
    """Save generated robot path structure to a formatted JSON file."""
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(path_data, f, indent=2)

def load_path_from_json(filepath):
    """Load robot path structure from a JSON file."""
    if not os.path.exists(filepath):
        return None
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)

def export_path_to_csv(path_data, filepath):
    """
    Export generated robot path commands to a clean CSV file.
    Format:
    COMMAND, X_MM, Y_MM, PEN_STATE
    MOVE, 20.50, 30.10, UP
    MOVE, 25.00, 40.00, DOWN
    """
    commands = path_data.get('commands', [])
    with open(filepath, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['COMMAND', 'X_MM', 'Y_MM', 'PEN_STATE'])
        
        current_pen = 'UP'
        for cmd in commands:
            cmd_type = cmd.get('type')
            if cmd_type == 'PEN_UP':
                current_pen = 'UP'
                writer.writerow(['PEN_UP', '', '', 'UP'])
            elif cmd_type == 'PEN_DOWN':
                current_pen = 'DOWN'
                writer.writerow(['PEN_DOWN', '', '', 'DOWN'])
            elif cmd_type == 'MOVE':
                x = round(cmd.get('x', 0.0), 2)
                y = round(cmd.get('y', 0.0), 2)
                writer.writerow(['MOVE', x, y, current_pen])

def load_calibration():
    """Load robot hardware calibration parameters from JSON file or default config."""
    if os.path.exists(config.CALIBRATION_FILE):
        try:
            with open(config.CALIBRATION_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return config.DEFAULT_CALIBRATION.copy()

def save_calibration(calibration_data):
    """Save robot hardware calibration parameters to JSON file."""
    with open(config.CALIBRATION_FILE, 'w', encoding='utf-8') as f:
        json.dump(calibration_data, f, indent=2)
