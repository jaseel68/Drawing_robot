"""
DRAWING ROBOT - CONFIGURATION SETTINGS
======================================
This file stores default configuration parameters for image processing,
paper sizes, coordinate transformations, robot hardware calibration,
and ESP32 Wi-Fi communication settings.
"""

import os

# Base Directory of the Project
BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# Folder Paths
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
GENERATED_PATHS_FOLDER = os.path.join(BASE_DIR, 'generated_paths')
CALIBRATION_FILE = os.path.join(BASE_DIR, 'calibration.json')

# Allowed Image File Extensions
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'bmp', 'webp'}
MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB max upload size

# Max image dimension before downscaling (to ensure fast processing)
MAX_IMAGE_DIMENSION = 2000

# ----------------------------------------------------
# PAPER DIMENSIONS (in Millimetres)
# ----------------------------------------------------
PAPER_SIZES = {
    'A1': {'width_mm': 594.0, 'height_mm': 841.0},
    'A2': {'width_mm': 420.0, 'height_mm': 594.0},
    'A3': {'width_mm': 297.0, 'height_mm': 420.0},
    'A4': {'width_mm': 210.0, 'height_mm': 297.0},
    'A5': {'width_mm': 148.0, 'height_mm': 210.0},
    'Custom': {'width_mm': 200.0, 'height_mm': 200.0}
}

DEFAULT_PAPER_SIZE = 'A4'

DEFAULT_MARGINS = {
    'left_mm': 15.0,
    'right_mm': 15.0,
    'top_mm': 15.0,
    'bottom_mm': 15.0
}

# ----------------------------------------------------
# IMAGE PROCESSING DEFAULTS
# ----------------------------------------------------
DEFAULT_PROCESSING_SETTINGS = {
    # Mode: 'single_line', 'edge', 'outline', 'threshold', 'contour'
    'mode': 'single_line',
    
    # Global / Adaptive Thresholding
    'threshold': 128,  # 0 - 255
    
    # Canny Edge Detector Thresholds
    'canny_low': 50,
    'canny_high': 150,
    
    # Blur Mode: 'none', 'gaussian', 'median'
    'blur_type': 'gaussian',
    'blur_kernel': 5,
    
    # Contour Retrieval Mode: 'external', 'all', 'tree'
    'contour_retrieval': 'tree',
    
    # Douglas-Peucker Simplification Tolerance (higher = fewer points)
    'simplification_tolerance': 1.5,
    
    # Filter out tiny noise contours
    'min_contour_area': 10.0,
    'min_contour_length': 5.0,
    
    # Max points warning threshold
    'max_points_warning': 15000,
    
    # Image Inversion (Invert black & white if background is dark)
    'invert_image': False
}

# ----------------------------------------------------
# ROBOT ORIGIN & COORDINATE DEFAULTS
# ----------------------------------------------------
ROBOT_ORIGIN = 'bottom_left'  # 'bottom_left', 'top_left', 'center', 'top_center'

# Scale Modes: 'fit_paper', 'fit_width', 'fit_height', 'custom'
DEFAULT_SCALE_MODE = 'fit_paper'

# ----------------------------------------------------
# ESP32 & SIMULATION DEFAULTS
# ----------------------------------------------------
ESP32_DEFAULT_IP = '192.168.1.100'
ESP32_TIMEOUT_SECONDS = 3.0

# Simulation Mode (ON by default so app is fully testable without hardware)
SIMULATION_MODE_DEFAULT = False
    
# ----------------------------------------------------
# ROBOT HARDWARE CALIBRATION DEFAULTS
# ----------------------------------------------------
DEFAULT_CALIBRATION = {
    'wheel_diameter_mm': 60.0,       # Diameter of drive wheels (verified physical measurement)
    'wheel_base_mm': 260.0,          # Distance between the two drive wheel centers (wheelbase)
    'pen_offset_mm': 160.0,          # Pen offset from drive-wheel axle midpoint
    'encoder_resolution': 200,       # Motor full steps per revolution (200 steps/rev)
    'motor_max_speed_mm_s': 80.0,    # Max drawing speed in mm/s
    'pen_up_angle': 90,              # Servo angle for Pen UP (verified standalone test)
    'pen_down_angle': 40,            # Servo angle for Pen DOWN (verified standalone test)
    'x_calibration_factor': 1.0,     # Scale factor for X axis motor tuning
    'y_calibration_factor': 1.0      # Scale factor for Y axis motor tuning
}
