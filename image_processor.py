"""
DRAWING ROBOT - IMAGE PROCESSOR MODULE
========================================
This module handles OpenCV computer vision algorithms to convert raster 
images (PNG, JPG, BMP, WEBP) into ordered, simplified 2D single-line contours.

Key Capabilities:
-----------------
1. Single Line / Centerline Vectorization (Zhang-Suen morphological thinning):
   Extracts true single-stroke centerlines from line art, drawings, sketches,
   and thick stroke shapes—eliminating unwanted double/concentric outlines!
2. Standard Edge & Boundary Contours (Canny, Otsu, Adaptive):
   Retained for users who specifically desire perimeter silhouettes.
3. Douglas-Peucker Simplification (cv2.approxPolyDP):
   Reduces dense pixel trails to minimal vertex polylines for fast robot motion.
4. Transparent PNG support:
   Blends alpha channel seamlessly onto pure white canvas.
5. Base64 Preview Generation:
   Multi-stage preview inspection (Original, Grayscale, Processed/Skeleton, Contours).
"""

import cv2
import numpy as np
import utils

def load_and_resize_image(image_path, max_dim=2000):
    """
    Step 1: Load image from disk, blend transparency if RGBA, and resize if it exceeds max_dim.
    Preserves original aspect ratio.
    """
    raw = cv2.imread(image_path, cv2.IMREAD_UNCHANGED)
    if raw is None:
        raise ValueError(f"Could not load image from path: {image_path}")
    
    # Handle alpha channel: blend transparent pixels onto a pure white canvas
    if len(raw.shape) == 3 and raw.shape[2] == 4:
        alpha = raw[:, :, 3] / 255.0
        bgr = raw[:, :, :3]
        white_bg = np.ones_like(bgr, dtype=np.uint8) * 255
        image = (bgr * alpha[:, :, np.newaxis] + white_bg * (1.0 - alpha[:, :, np.newaxis])).astype(np.uint8)
    elif len(raw.shape) == 3:
        image = raw
    else:
        image = cv2.cvtColor(raw, cv2.COLOR_GRAY2BGR)
    
    h, w = image.shape[:2]
    
    # If image exceeds max dimension, scale down proportionally
    if max(h, w) > max_dim:
        scale = max_dim / float(max(h, w))
        new_w = int(w * scale)
        new_h = int(h * scale)
        image = cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_AREA)
        
    return image

def convert_to_grayscale(image):
    """
    Step 2: Convert RGB/BGR image to 1-channel Grayscale.
    Pixels range from 0 (Black) to 255 (White).
    """
    if len(image.shape) == 3:
        return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return image.copy()

def apply_noise_reduction(gray_image, blur_type='gaussian', kernel_size=5):
    """
    Step 3: Apply noise reduction blur to smooth pixel artifacts and camera noise.
    Kernel size must be an odd positive integer (3, 5, 7...).
    """
    if kernel_size % 2 == 0:
        kernel_size += 1  # Ensure odd kernel size
        
    if blur_type == 'gaussian':
        return cv2.GaussianBlur(gray_image, (kernel_size, kernel_size), 0)
    elif blur_type == 'median':
        return cv2.medianBlur(gray_image, kernel_size)
    else:
        return gray_image.copy()

def zhang_suen_thinning(binary_mask):
    """
    Fast Vectorized Zhang-Suen Morphological Thinning Algorithm.
    Reduces any thick stroke or line shape to a 1-pixel wide topological skeleton (centerline).
    Uses a 256-entry lookup table (LUT) and 2D convolution for millisecond execution.
    """
    skeleton = (binary_mask > 0).astype(np.uint8)
    
    # Neighborhood kernel with powers of 2 for 8 neighbors:
    # P9(128)  P2(1)   P3(2)
    # P8(64)   P1(0)   P4(4)
    # P7(32)   P6(16)  P5(8)
    kernel = np.array([[128, 1, 2],
                       [ 64, 0, 4],
                       [ 32,16, 8]], dtype=np.uint8)
                       
    lut1 = np.zeros(256, dtype=bool)
    lut2 = np.zeros(256, dtype=bool)
    
    for i in range(256):
        p2 = (i >> 0) & 1
        p3 = (i >> 1) & 1
        p4 = (i >> 2) & 1
        p5 = (i >> 3) & 1
        p6 = (i >> 4) & 1
        p7 = (i >> 5) & 1
        p8 = (i >> 6) & 1
        p9 = (i >> 7) & 1
        
        nbrs = [p2, p3, p4, p5, p6, p7, p8, p9]
        b = sum(nbrs)
        seq = nbrs + [p2]
        a = sum(seq[j] == 0 and seq[j+1] == 1 for j in range(8))
        
        if 2 <= b <= 6 and a == 1:
            if (p2 * p4 * p6 == 0) and (p4 * p6 * p8 == 0):
                lut1[i] = True
            if (p2 * p4 * p8 == 0) and (p2 * p6 * p8 == 0):
                lut2[i] = True

    while True:
        code1 = cv2.filter2D(skeleton, cv2.CV_8U, kernel, borderType=cv2.BORDER_CONSTANT)
        to_del1 = (skeleton == 1) & lut1[code1]
        if not np.any(to_del1):
            break
        skeleton[to_del1] = 0
        
        code2 = cv2.filter2D(skeleton, cv2.CV_8U, kernel, borderType=cv2.BORDER_CONSTANT)
        to_del2 = (skeleton == 1) & lut2[code2]
        if not np.any(to_del2):
            break
        skeleton[to_del2] = 0
        
    return skeleton

def extract_single_line_contours(skeleton, tolerance=1.5, min_length=5.0):
    """
    Traces a 1-pixel-wide binary skeleton image into clean continuous polylines.
    
    Handles:
    - Open strokes starting from degree-1 endpoints.
    - Closed loops without endpoints (e.g. circles, hexagons, closed polygons).
    - Junction direction continuity to avoid jagged zigzags.
    - Douglas-Peucker geometric simplification.
    """
    deltas = [(-1, -1), (-1, 0), (-1, 1),
              ( 0, -1),          ( 0, 1),
              ( 1, -1), ( 1, 0), ( 1, 1)]
              
    skel_pts = set(zip(*np.where(skeleton > 0)))
    if not skel_pts:
        return []
        
    def get_neighbors(pt, pt_set):
        r, c = pt
        return [(r + dr, c + dc) for dr, dc in deltas if (r + dr, c + dc) in pt_set]

    # Clean redundant 2x2 blocks if any (removes diagonal shortcut in 2x2 clusters)
    cleaned_skel = set(skel_pts)
    for r, c in skel_pts:
        if (r+1, c) in cleaned_skel and (r, c+1) in cleaned_skel and (r+1, c+1) in cleaned_skel:
            cleaned_skel.discard((r+1, c+1))

    remaining = set(cleaned_skel)
    paths = []
    
    while remaining:
        # Priority 1: Start at endpoints (degree == 1)
        endpoints = [p for p in remaining if len(get_neighbors(p, remaining)) == 1]
        # Priority 2: Start at branches / junctions (degree >= 3)
        junctions = [p for p in remaining if len(get_neighbors(p, remaining)) >= 3]
        
        if endpoints:
            start = endpoints[0]
        elif junctions:
            start = junctions[0]
        else:
            # Closed loop without endpoints or junctions: pick any pixel with minimal degree
            start = min(remaining, key=lambda p: len(get_neighbors(p, remaining)))
            
        current = start
        path = [current]
        remaining.remove(current)
        
        while True:
            nbrs = get_neighbors(current, remaining)
            if not nbrs:
                # If path has at least 3 points and end touches start, close loop!
                if len(path) >= 3 and start in get_neighbors(current, cleaned_skel):
                    path.append(start)
                break
                
            if len(nbrs) == 1:
                next_pt = nbrs[0]
            else:
                # Direction continuity: choose neighbor that minimizes turn angle
                if len(path) >= 2:
                    dr_curr = current[0] - path[-2][0]
                    dc_curr = current[1] - path[-2][1]
                    norm_curr = np.hypot(dr_curr, dc_curr) + 1e-6
                    best_score = -999.0
                    best_nbr = nbrs[0]
                    for nb in nbrs:
                        dr_nb = nb[0] - current[0]
                        dc_nb = nb[1] - current[1]
                        norm_nb = np.hypot(dr_nb, dc_nb) + 1e-6
                        score = (dr_curr * dr_nb + dc_curr * dc_nb) / (norm_curr * norm_nb)
                        if score > best_score:
                            best_score = score
                            best_nbr = nb
                    next_pt = best_nbr
                else:
                    next_pt = nbrs[0]
                    
            path.append(next_pt)
            remaining.remove(next_pt)
            current = next_pt
            
        if len(path) >= int(min_length):
            # Convert (row, col) to (x, y) coordinates
            pts_xy = [[int(c), int(r)] for r, c in path]
            pts_arr = np.array(pts_xy, dtype=np.int32).reshape((-1, 1, 2))
            
            # Arc length for simplification epsilon
            length = cv2.arcLength(pts_arr, False)
            if length >= min_length:
                # Douglas-Peucker epsilon tolerance
                eps = max(1.0, (tolerance / 100.0) * length)
                approx = cv2.approxPolyDP(pts_arr, eps, False)
                simplified = [[int(pt[0][0]), int(pt[0][1])] for pt in approx]
                
                if len(simplified) >= 2:
                    # If original path was a closed loop, ensure simplified polygon is closed
                    if path[0] == path[-1] or np.hypot(path[0][0]-path[-1][0], path[0][1]-path[-1][1]) <= 3:
                        if simplified[0] != simplified[-1]:
                            simplified.append(simplified[0])
                    paths.append(simplified)
                    
    return paths

def apply_threshold_or_edges(gray_image, mode='single_line', threshold_val=128, canny_low=50, canny_high=150, invert=False):
    """
    Step 4: Convert grayscale image to binary (Black/White) line mask.
    
    Modes:
    - 'single_line': High-contrast binarization optimized for centerline skeletonization.
    - 'edge' / Canny: Finds outer boundary gradient intensity edges.
    - 'outline' / Otsu: Global automatic thresholding.
    - 'threshold': Fixed manual thresholding.
    - 'contour' / Adaptive: Local thresholding for non-uniform lighting.
    """
    # Detect background lightness by inspecting outer border pixels
    border_pixels = np.concatenate([
        gray_image[0, :], gray_image[-1, :],
        gray_image[:, 0], gray_image[:, -1]
    ])
    bg_is_light = np.median(border_pixels) > 127
    should_invert = bg_is_light if not invert else (not bg_is_light)
    thresh_flag = cv2.THRESH_BINARY_INV if should_invert else cv2.THRESH_BINARY

    if mode == 'single_line':
        # Otsu thresholding with auto-contrast for clean skeletonization
        _, binary = cv2.threshold(gray_image, 0, 255, thresh_flag + cv2.THRESH_OTSU)
    elif mode == 'edge':
        # Canny edge detector
        binary = cv2.Canny(gray_image, canny_low, canny_high)
    elif mode == 'threshold':
        # Global thresholding
        _, binary = cv2.threshold(gray_image, threshold_val, 255, thresh_flag)
    elif mode == 'outline':
        # Otsu automatic thresholding
        _, binary = cv2.threshold(gray_image, 0, 255, thresh_flag + cv2.THRESH_OTSU)
    elif mode == 'contour':
        # Adaptive Gaussian Thresholding
        binary = cv2.adaptiveThreshold(
            gray_image, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
            thresh_flag, 11, 2
        )
    else:
        # Default fallback to single_line
        _, binary = cv2.threshold(gray_image, 0, 255, thresh_flag + cv2.THRESH_OTSU)
        
    return binary

def extract_raw_contours(binary_image, retrieval_mode='tree'):
    """
    Find vector contours (lines/curves) from binary edge mask.
    """
    if retrieval_mode == 'external':
        mode_flag = cv2.RETR_EXTERNAL
    elif retrieval_mode == 'all':
        mode_flag = cv2.RETR_LIST
    else:
        mode_flag = cv2.RETR_TREE
        
    contours, _ = cv2.findContours(binary_image, mode_flag, cv2.CHAIN_APPROX_NONE)
    return contours

def filter_and_simplify_contours(contours, min_area=10.0, min_length=5.0, tolerance=1.5):
    """
    Filter out noise specks and simplify contour point counts using Douglas-Peucker.
    """
    simplified_contours = []
    
    for cnt in contours:
        length = cv2.arcLength(cnt, False)
        area = cv2.contourArea(cnt)
        
        # Discard tiny noise specks
        if length < min_length or (area > 0 and area < min_area):
            continue
            
        epsilon = (tolerance / 100.0) * length
        approx = cv2.approxPolyDP(cnt, epsilon, False)
        
        points = []
        for p in approx:
            x, y = int(p[0][0]), int(p[0][1])
            points.append([x, y])
            
        if len(points) >= 2:
            simplified_contours.append(points)
            
    return simplified_contours

def generate_contour_visualization(width, height, simplified_contours):
    """
    Generate a clean visual RGB preview image of the extracted vector contours
    drawn on a white canvas with distinct colors and start/end markers.
    """
    canvas = np.ones((height, width, 3), dtype=np.uint8) * 255  # White canvas
    
    colors = [
        (40, 40, 180),   # Crimson
        (180, 40, 40),   # Royal Blue
        (40, 180, 40),   # Emerald Green
        (140, 40, 140),  # Purple
        (0, 140, 220)    # Amber Orange
    ]
    
    for idx, contour in enumerate(simplified_contours):
        color = colors[idx % len(colors)]
        pts = np.array(contour, dtype=np.int32).reshape((-1, 1, 2))
        cv2.polylines(canvas, [pts], isClosed=False, color=color, thickness=2)
        
        # Draw start point marker (Green dot) and end point marker (Red dot)
        if len(contour) > 0:
            cv2.circle(canvas, tuple(contour[0]), 3, (0, 200, 0), -1)
            cv2.circle(canvas, tuple(contour[-1]), 3, (0, 0, 220), -1)
            
    return canvas

def process_image(image_path, settings=None):
    """
    Master pipeline controller.
    Runs the image through processing stages and returns structured single-line contours,
    point statistics, and base64 preview images for front-end rendering.
    """
    if settings is None:
        settings = {}
        
    mode = settings.get('mode', 'single_line')
    threshold_val = int(settings.get('threshold', 128))
    canny_low = int(settings.get('canny_low', 50))
    canny_high = int(settings.get('canny_high', 150))
    blur_type = settings.get('blur_type', 'gaussian')
    blur_kernel = int(settings.get('blur_kernel', 5))
    retrieval_mode = settings.get('contour_retrieval', 'tree')
    tolerance = float(settings.get('simplification_tolerance', 1.5))
    min_area = float(settings.get('min_contour_area', 10.0))
    min_length = float(settings.get('min_contour_length', 5.0))
    invert = bool(settings.get('invert_image', False))
    
    # 1. Load image & resize
    orig_bgr = load_and_resize_image(image_path, max_dim=2000)
    height, width = orig_bgr.shape[:2]
    
    # 2. Grayscale & Noise reduction
    gray = convert_to_grayscale(orig_bgr)
    blurred = apply_noise_reduction(gray, blur_type=blur_type, kernel_size=blur_kernel)
    
    # 3. Process based on selected mode
    if mode == 'single_line':
        # SINGLE LINE CENTERLINE VECTORIZATION PIPELINE
        binary = apply_threshold_or_edges(blurred, mode='single_line', threshold_val=threshold_val, invert=invert)
        skeleton = zhang_suen_thinning(binary)
        simplified_contours = extract_single_line_contours(skeleton, tolerance=tolerance, min_length=min_length)
        
        # For UI processed preview: show skeleton slightly dilated for clear visual inspection
        preview_mask = cv2.dilate(skeleton * 255, np.ones((2, 2), np.uint8), iterations=1)
    else:
        # Traditional edge / boundary contour pipeline
        binary = apply_threshold_or_edges(blurred, mode=mode, threshold_val=threshold_val,
                                         canny_low=canny_low, canny_high=canny_high, invert=invert)
        raw_contours = extract_raw_contours(binary, retrieval_mode=retrieval_mode)
        simplified_contours = filter_and_simplify_contours(raw_contours, min_area=min_area, 
                                                            min_length=min_length, tolerance=tolerance)
        preview_mask = binary

    # 4. Generate clean vector visualization
    contour_vis_img = generate_contour_visualization(width, height, simplified_contours)
    
    # 5. Point and contour statistics
    total_points = sum(len(c) for c in simplified_contours)
    total_contours = len(simplified_contours)
    
    # 6. Base64 Previews for UI debugging tabs
    previews = {
        'original': utils.encode_image_to_base64(orig_bgr),
        'grayscale': utils.encode_image_to_base64(gray),
        'processed': utils.encode_image_to_base64(preview_mask),
        'contours_preview': utils.encode_image_to_base64(contour_vis_img)
    }
    
    warning = None
    if total_points > 25000:
        warning = f"High point count ({total_points:,} points). Consider increasing Simplification Tolerance to reduce drawing time."
    elif total_contours == 0:
        warning = "No lines detected! Try checking the Invert Image option or adjusting parameters."
        
    return {
        'success': True,
        'image_width': width,
        'image_height': height,
        'contours': simplified_contours,
        'total_contours': total_contours,
        'total_points': total_points,
        'previews': previews,
        'warning': warning
    }
