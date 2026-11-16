"""
DRAWING ROBOT - MAIN FLASK APPLICATION SERVER
=============================================
This is the entry point for the Web Application.
It serves the HTML/CSS/JavaScript dashboard and exposes REST API endpoints for:
- Image uploading & inspection
- OpenCV image processing & contour generation
- Pixel-to-mm coordinate conversion & path generation
- Path JSON/CSV export & saving
- Virtual Simulation & ESP32 Wi-Fi Robot control
"""

import os
import json
import traceback
from flask import Flask, render_template, request, jsonify, send_from_directory, Response
from werkzeug.utils import secure_filename

import config
import utils
import image_processor
import coordinate_converter
import path_processor
import robot_communication

# Initialize Flask App
app = Flask(__name__, template_folder='templates', static_folder='static')
app.config['UPLOAD_FOLDER'] = config.UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = config.MAX_CONTENT_LENGTH

# Ensure essential storage directories exist on server startup
utils.ensure_directories()

# Global state to hold currently uploaded image path and generated path
current_state = {
    'uploaded_image_path': None,
    'processed_contours': [],
    'image_width': 0,
    'image_height': 0,
    'current_path_data': None,
    'simulation_mode': config.SIMULATION_MODE_DEFAULT,
    'esp32_ip': config.ESP32_DEFAULT_IP,
    'emergency_stopped': False
}

# ----------------------------------------------------
# PAGE ROUTES
# ----------------------------------------------------
@app.route('/')
def index():
    """Render main Drawing Robot control dashboard."""
    return render_template('index.html')

# ----------------------------------------------------
# IMAGE UPLOAD & PROCESSING API ENDPOINTS
# ----------------------------------------------------
@app.route('/api/upload', methods=['POST'])
def upload_image():
    """
    Endpoint: POST /api/upload
    Accepts image file via multipart form-data (drag-and-drop or file picker).
    Saves file to uploads directory and returns metadata + base64 preview.
    """
    try:
        if 'image' not in request.files:
            return jsonify({'success': False, 'message': 'No image file uploaded'}), 400
            
        file = request.files['image']
        if file.filename == '':
            return jsonify({'success': False, 'message': 'No selected file'}), 400
            
        if file and utils.allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(config.UPLOAD_FOLDER, filename)
            file.save(filepath)
            
            current_state['uploaded_image_path'] = filepath
            
            # Read image to obtain metadata dimensions
            import cv2
            img = cv2.imread(filepath)
            if img is None:
                return jsonify({'success': False, 'message': 'Invalid image format or corrupt file'}), 400
                
            h, w = img.shape[:2]
            current_state['image_width'] = w
            current_state['image_height'] = h
            
            file_size_bytes = os.path.getsize(filepath)
            file_size_kb = round(file_size_bytes / 1024.0, 1)
            
            preview_b64 = utils.encode_image_to_base64(img)
            
            return jsonify({
                'success': True,
                'filename': filename,
                'width': w,
                'height': h,
                'file_size_kb': file_size_kb,
                'preview_url': preview_b64,
                'message': 'Image uploaded successfully.'
            })
        else:
            return jsonify({'success': False, 'message': 'File extension not allowed. Use PNG, JPG, JPEG, BMP, or WEBP'}), 400
            
    except Exception as e:
        app.logger.error(f"Error uploading image: {traceback.format_exc()}")
        return jsonify({'success': False, 'message': f"Server error: {str(e)}"}), 500


@app.route('/api/process', methods=['POST'])
def process_image_route():
    """
    Endpoint: POST /api/process
    Runs the uploaded image through the OpenCV computer vision pipeline.
    Accepts processing settings JSON and returns contours & base64 previews.
    """
    try:
        if not current_state['uploaded_image_path'] or not os.path.exists(current_state['uploaded_image_path']):
            return jsonify({'success': False, 'message': 'Please upload an image first.'}), 400
            
        settings = request.json or {}
        
        # Process image using OpenCV module
        result = image_processor.process_image(current_state['uploaded_image_path'], settings)
        
        current_state['processed_contours'] = result['contours']
        current_state['image_width'] = result['image_width']
        current_state['image_height'] = result['image_height']
        
        return jsonify(result)
        
    except Exception as e:
        app.logger.error(f"Error processing image: {traceback.format_exc()}")
        return jsonify({'success': False, 'message': f"Image processing error: {str(e)}"}), 500


# ----------------------------------------------------
# PATH GENERATION & COORDINATE CONVERSION ENDPOINTS
# ----------------------------------------------------
@app.route('/api/generate-path', methods=['POST'])
def generate_path_route():
    """
    Endpoint: POST /api/generate-path
    Converts image contours to physical paper millimetre coordinates and generates
    robot PEN_UP / PEN_DOWN / MOVE command sequence.
    """
    try:
        contours = current_state.get('processed_contours', [])
        img_w = current_state.get('image_width', 800)
        img_h = current_state.get('image_height', 600)
        
        if not contours:
            return jsonify({'success': False, 'message': 'No contours available. Process an image first.'}), 400
            
        payload = request.json or {}
        
        paper_size_key = payload.get('paper_size', 'A4')
        custom_paper_w = payload.get('paper_width_mm')
        custom_paper_h = payload.get('paper_height_mm')
        
        if paper_size_key in config.PAPER_SIZES:
            paper_w = config.PAPER_SIZES[paper_size_key]['width_mm']
            paper_h = config.PAPER_SIZES[paper_size_key]['height_mm']
        else:
            paper_w = float(custom_paper_w or 210.0)
            paper_h = float(custom_paper_h or 297.0)
            
        margins = {
            'left_mm': float(payload.get('margin_left', 15.0)),
            'right_mm': float(payload.get('margin_right', 15.0)),
            'top_mm': float(payload.get('margin_top', 15.0)),
            'bottom_mm': float(payload.get('margin_bottom', 15.0))
        }
        
        paper_config = {
            'width_mm': paper_w,
            'height_mm': paper_h,
            'margins': margins
        }
        
        scale_mode = payload.get('scale_mode', 'fit_paper')
        origin = payload.get('origin', 'bottom_left')
        custom_w = payload.get('custom_width_mm')
        custom_h = payload.get('custom_height_mm')
        maintain_aspect = payload.get('maintain_aspect', True)
        
        # 1. Transform pixels to physical mm coordinates
        conversion_result = coordinate_converter.convert_pixels_to_mm(
            contours, img_w, img_h, paper_config, origin=origin, scale_mode=scale_mode,
            custom_w_mm=custom_w, custom_h_mm=custom_h, maintain_aspect=maintain_aspect
        )
        
        contours_mm = conversion_result['contours_mm']
        
        # 2. Generate optimized Pen UP / Pen DOWN commands and statistics
        commands, stats = path_processor.generate_robot_commands(contours_mm, optimize=True)
        
        path_data = {
            'paper': paper_config,
            'drawing_dimensions': conversion_result['dimensions'],
            'origin': origin,
            'stats': stats,
            'contours_mm': contours_mm,
            'commands': commands
        }
        
        current_state['current_path_data'] = path_data
        
        # Save to auto-cache JSON
        cache_path = os.path.join(config.GENERATED_PATHS_FOLDER, 'current_path.json')
        utils.save_path_to_json(path_data, cache_path)
        
        return jsonify({'success': True, 'path_data': path_data})
        
    except Exception as e:
        app.logger.error(f"Error generating path: {traceback.format_exc()}")
        return jsonify({'success': False, 'message': f"Path generation error: {str(e)}"}), 500


@app.route('/api/path/export/<fmt>', methods=['GET'])
def export_path(fmt):
    """
    Endpoint: GET /api/path/export/json or /api/path/export/csv
    Exports the current generated path as downloadable file.
    """
    try:
        path_data = current_state.get('current_path_data')
        if not path_data:
            cache_path = os.path.join(config.GENERATED_PATHS_FOLDER, 'current_path.json')
            path_data = utils.load_path_from_json(cache_path)
            
        if not path_data:
            return jsonify({'success': False, 'message': 'No generated path to export.'}), 400
            
        if fmt.lower() == 'json':
            content = json.dumps(path_data, indent=2)
            return Response(
                content,
                mimetype='application/json',
                headers={'Content-Disposition': 'attachment;filename=robot_path.json'}
            )
        elif fmt.lower() == 'csv':
            csv_path = os.path.join(config.GENERATED_PATHS_FOLDER, 'export.csv')
            utils.export_path_to_csv(path_data, csv_path)
            with open(csv_path, 'r', encoding='utf-8') as f:
                content = f.read()
            return Response(
                content,
                mimetype='text/csv',
                headers={'Content-Disposition': 'attachment;filename=robot_path.csv'}
            )
        else:
            return jsonify({'success': False, 'message': 'Invalid format. Use json or csv'}), 400
            
    except Exception as e:
        return jsonify({'success': False, 'message': f"Export error: {str(e)}"}), 500


@app.route('/api/path/save', methods=['POST'])
def save_path_route():
    """Save current path JSON to server storage."""
    path_data = current_state.get('current_path_data')
    if not path_data:
        return jsonify({'success': False, 'message': 'No path data to save.'}), 400
        
    filename = request.json.get('filename', 'saved_path.json') if request.json else 'saved_path.json'
    if not filename.endswith('.json'):
        filename += '.json'
    filepath = os.path.join(config.GENERATED_PATHS_FOLDER, secure_filename(filename))
    utils.save_path_to_json(path_data, filepath)
    return jsonify({'success': True, 'message': f'Path saved successfully to {filename}'})


@app.route('/api/path/load', methods=['POST'])
def load_path_route():
    """Load path JSON from server storage."""
    filename = request.json.get('filename', 'current_path.json') if request.json else 'current_path.json'
    filepath = os.path.join(config.GENERATED_PATHS_FOLDER, secure_filename(filename))
    data = utils.load_path_from_json(filepath)
    if data:
        current_state['current_path_data'] = data
        return jsonify({'success': True, 'path_data': data})
    return jsonify({'success': False, 'message': f'File {filename} not found.'}), 404


# ----------------------------------------------------
# ESP32 & SIMULATION CONTROL ENDPOINTS
# ----------------------------------------------------
@app.route('/api/robot/config', methods=['GET', 'POST'])
def robot_config_route():
    """Get or update ESP32 IP address and Simulation Mode toggle."""
    if request.method == 'POST':
        payload = request.json or {}
        if 'simulation_mode' in payload:
            current_state['simulation_mode'] = bool(payload['simulation_mode'])
        if 'esp32_ip' in payload:
            current_state['esp32_ip'] = str(payload['esp32_ip'])
            
    return jsonify({
        'simulation_mode': current_state['simulation_mode'],
        'esp32_ip': current_state['esp32_ip']
    })


@app.route('/api/robot/connect', methods=['POST'])
def connect_robot():
    """Test connection to physical ESP32 or initialize Virtual Robot Simulator."""
    payload = request.json or {}
    ip = payload.get('esp32_ip', current_state['esp32_ip'])
    sim_mode = payload.get('simulation_mode', current_state['simulation_mode'])
    
    current_state['esp32_ip'] = ip
    current_state['simulation_mode'] = sim_mode
    
    if sim_mode:
        return jsonify({
            'success': True,
            'connected': True,
            'simulation_mode': True,
            'message': 'Connected to Virtual Robot Simulator.'
        })
    else:
        client = robot_communication.ESP32RobotClient(ip)
        res = client.test_connection()
        return jsonify(res)


@app.route('/api/robot/status', methods=['GET'])
def get_status_route():
    """Get live telemetry status from ESP32 or Virtual Simulator."""
    ip = current_state['esp32_ip']
    sim_mode = current_state['simulation_mode']
    emergency_stopped = current_state.get('emergency_stopped', False)
    status = robot_communication.get_robot_status(ip, simulation_mode=sim_mode, emergency_stopped=emergency_stopped)
    return jsonify(status)


@app.route('/api/robot/upload-path', methods=['POST'])
def upload_path_to_robot():
    """Send generated path command list to ESP32 / Simulator."""
    path_data = current_state.get('current_path_data')
    if not path_data or 'commands' not in path_data:
        return jsonify({'success': False, 'message': 'No path generated yet.'}), 400
        
    commands = path_data['commands']
    ip = current_state['esp32_ip']
    sim_mode = current_state['simulation_mode']
    
    current_state['emergency_stopped'] = False
    res = robot_communication.send_robot_action(ip, 'upload_path', payload={'commands': commands}, simulation_mode=sim_mode)
    return jsonify(res)


@app.route('/api/robot/control/<action>', methods=['POST'])
def control_robot(action):
    """
    Trigger motion action: 'start', 'pause', 'resume', 'stop', 'estop', 'home', 'pen_up', 'pen_down'
    """
    ip = current_state['esp32_ip']
    sim_mode = current_state['simulation_mode']
    payload = request.json or {}
    
    if action in ['stop', 'estop']:
        current_state['emergency_stopped'] = True
    elif action in ['start', 'upload_path']:
        current_state['emergency_stopped'] = False
        
    res = robot_communication.send_robot_action(ip, action, payload=payload, simulation_mode=sim_mode)
    return jsonify(res)


@app.route('/api/calibration', methods=['GET', 'POST'])
def calibration_route():
    """Get or save robot hardware calibration settings (wheelbase, wheel diameter, servo angles)."""
    if request.method == 'POST':
        cal_data = request.json or {}
        utils.save_calibration(cal_data)
        return jsonify({'success': True, 'message': 'Calibration saved.', 'calibration': cal_data})
    else:
        cal_data = utils.load_calibration()
        return jsonify(cal_data)

# ----------------------------------------------------
# START FLASK SERVER
# ----------------------------------------------------
if __name__ == '__main__':
    print("\n" + "="*60)
    print(" [ROBOT] 2-WHEEL DRAWING ROBOT WEB APPLICATION SERVER ")
    print("="*60)
    print(" * Server running on: http://127.0.0.1:5000/")
    print(f" * Simulation Mode: {'ENABLED' if config.SIMULATION_MODE_DEFAULT else 'DISABLED'}")
    print("="*60 + "\n")
    app.run(host='127.0.0.1', port=5000, debug=True)
