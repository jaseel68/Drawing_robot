"""
DRAWING ROBOT - COORDINATE CONVERTER MODULE
===========================================
This module converts pixel coordinates from OpenCV image space into physical
millimetre coordinates for the robot drawing surface.

Coordinate Systems:
-------------------
1. OpenCV Image Coordinates:
   - Origin (0,0) is at TOP-LEFT of image.
   - +X axis points RIGHT.
   - +Y axis points DOWNWARDS.

2. Robot Paper Coordinates (Millimetres):
   - Paper boundary: Width (e.g. 210mm for A4), Height (e.g. 297mm for A4).
   - Origin choices: 'bottom_left' (recommended), 'top_left', 'center'.
   - In Cartesian Robot Space (+Y UPWARDS), OpenCV Y must be INVERTED.

Transformation Steps:
---------------------
Pixel Coordinate (x_px, y_px)
  ↓
Normalized Coordinate [0.0 to 1.0]:
  norm_x = x_px / image_width
  norm_y = y_px / image_height
  ↓
Scaled Drawing Size (mm) fitted inside paper margins
  ↓
Physical Robot Coordinates (x_mm, y_mm) with Y Inversion & Origin Offset
"""

import config

def compute_drawing_dimensions(img_width, img_height, paper_config, scale_mode='fit_paper', 
                              custom_w_mm=None, custom_h_mm=None, maintain_aspect=True):
    """
    Compute the physical width and height (in mm) that the image will occupy on paper,
    accounting for paper size, margins, scaling mode, and aspect ratio.
    """
    paper_w = paper_config.get('width_mm', 210.0)
    paper_h = paper_config.get('height_mm', 297.0)
    
    margins = paper_config.get('margins', config.DEFAULT_MARGINS)
    left_m = margins.get('left_mm', 15.0)
    right_m = margins.get('right_mm', 15.0)
    top_m = margins.get('top_mm', 15.0)
    bottom_m = margins.get('bottom_mm', 15.0)
    
    # Maximum usable drawing area inside margins
    avail_w = max(1.0, paper_w - left_m - right_m)
    avail_h = max(1.0, paper_h - top_m - bottom_m)
    
    img_aspect = img_width / float(img_height) if img_height > 0 else 1.0
    
    if scale_mode == 'fit_paper':
        # Scale to largest dimensions that fit inside available area
        avail_aspect = avail_w / avail_h
        if img_aspect > avail_aspect:
            draw_w = avail_w
            draw_h = draw_w / img_aspect
        else:
            draw_h = avail_h
            draw_w = draw_h * img_aspect
            
    elif scale_mode == 'fit_width':
        draw_w = avail_w
        draw_h = draw_w / img_aspect if maintain_aspect else avail_h
        
    elif scale_mode == 'fit_height':
        draw_h = avail_h
        draw_w = draw_h * img_aspect if maintain_aspect else avail_w
        
    elif scale_mode == 'custom' and custom_w_mm and custom_h_mm:
        draw_w = min(float(custom_w_mm), avail_w)
        draw_h = min(float(custom_h_mm), avail_h)
        if maintain_aspect:
            if draw_w / draw_h > img_aspect:
                draw_w = draw_h * img_aspect
            else:
                draw_h = draw_w / img_aspect
    else:
        # Fallback to fit_paper
        draw_w = avail_w
        draw_h = draw_w / img_aspect
        
    return {
        'paper_width_mm': paper_w,
        'paper_height_mm': paper_h,
        'available_width_mm': avail_w,
        'available_height_mm': avail_h,
        'drawing_width_mm': draw_w,
        'drawing_height_mm': draw_h,
        'margins': margins
    }

def convert_pixels_to_mm(contours, img_width, img_height, paper_config, 
                          origin='bottom_left', scale_mode='fit_paper',
                          custom_w_mm=None, custom_h_mm=None, maintain_aspect=True):
    """
    Transforms pixel contours into physical robot millimetre coordinates.
    
    Parameters:
    - contours: list of list of [x_pixel, y_pixel]
    - img_width, img_height: original pixel dimensions of processed image
    - paper_config: dict with width_mm, height_mm, margins
    - origin: 'bottom_left', 'top_left', 'center', 'top_center'
    """
    dims = compute_drawing_dimensions(
        img_width, img_height, paper_config, scale_mode=scale_mode,
        custom_w_mm=custom_w_mm, custom_h_mm=custom_h_mm, maintain_aspect=maintain_aspect
    )
    
    draw_w = dims['drawing_width_mm']
    draw_h = dims['drawing_height_mm']
    margins = dims['margins']
    left_m = margins['left_mm']
    bottom_m = margins['bottom_mm']
    paper_w = dims['paper_width_mm']
    paper_h = dims['paper_height_mm']
    
    # Calculate offset positioning on paper
    # Center the drawing inside the available margin area
    offset_x = left_m + (dims['available_width_mm'] - draw_w) / 2.0
    offset_y = bottom_m + (dims['available_height_mm'] - draw_h) / 2.0
    
    transformed_contours_mm = []
    
    for cnt in contours:
        cnt_mm = []
        for point in cnt:
            px_x, px_y = point[0], point[1]
            
            # Step 1: Normalize pixel position [0.0 to 1.0]
            norm_x = px_x / float(img_width)
            norm_y = px_y / float(img_height)
            
            # Step 2: Transform to paper mm coordinates based on origin
            if origin == 'bottom_left':
                # +X points Right, +Y points UPWARDS (OpenCV Y inverted)
                x_mm = offset_x + norm_x * draw_w
                y_mm = offset_y + (1.0 - norm_y) * draw_h
                
            elif origin == 'top_left':
                # +X points Right, +Y points DOWNWARDS (standard screen origin)
                x_mm = offset_x + norm_x * draw_w
                y_mm = (paper_h - offset_y - draw_h) + norm_y * draw_h
                
            elif origin == 'center':
                # (0,0) is at center of drawing surface
                x_mm = (norm_x - 0.5) * draw_w
                y_mm = (0.5 - norm_y) * draw_h
                
            else:
                # Default fallback to bottom_left
                x_mm = offset_x + norm_x * draw_w
                y_mm = offset_y + (1.0 - norm_y) * draw_h
                
            # Round to 2 decimal places for clean motor precision (0.01 mm)
            x_mm = round(max(0.0, min(paper_w, x_mm)), 2)
            y_mm = round(max(0.0, min(paper_h, y_mm)), 2)
            
            cnt_mm.append([x_mm, y_mm])
            
        if len(cnt_mm) >= 2:
            transformed_contours_mm.append(cnt_mm)
            
    return {
        'contours_mm': transformed_contours_mm,
        'dimensions': dims,
        'origin': origin
    }
