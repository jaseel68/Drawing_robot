"""
DRAWING ROBOT - PATH PROCESSOR MODULE
=====================================
This module takes millimetre contours, optimizes the drawing order to reduce
pen-up travel distance, generates structured Pen UP / MOVE / Pen DOWN command
sequences, and calculates path statistics (draw distance, travel distance, estimated time).

Path Command Structure:
-----------------------
[
  { "type": "PEN_UP" },
  { "type": "MOVE", "x": 15.0, "y": 20.0 },
  { "type": "PEN_DOWN" },
  { "type": "MOVE", "x": 18.2, "y": 24.5 },
  ...
  { "type": "PEN_UP" }
]
"""

import math
import utils

def optimize_contour_order(contours_mm, start_pos=(0.0, 0.0)):
    """
    Greedy Nearest-Neighbor Path Optimization.
    Reorders contours and flips contour direction if necessary so that the robot
    moves to the nearest next contour start point, minimizing pen-up travel distance.
    """
    if not contours_mm:
        return []
        
    remaining = [list(c) for c in contours_mm]
    ordered_contours = []
    current_pos = list(start_pos)
    
    while remaining:
        best_idx = 0
        best_dist = float('inf')
        should_flip = False
        
        for idx, cnt in enumerate(remaining):
            start_p = cnt[0]
            end_p = cnt[-1]
            
            d_start = utils.calculate_distance(current_pos, start_p)
            d_end = utils.calculate_distance(current_pos, end_p)
            
            if d_start < best_dist:
                best_dist = d_start
                best_idx = idx
                should_flip = False
                
            if d_end < best_dist:
                best_dist = d_end
                best_idx = idx
                should_flip = True
                
        chosen_cnt = remaining.pop(best_idx)
        if should_flip:
            chosen_cnt.reverse()
            
        ordered_contours.append(chosen_cnt)
        current_pos = list(chosen_cnt[-1])
        
    return ordered_contours

def generate_robot_commands(contours_mm, optimize=True, home_pos=(0.0, 0.0)):
    """
    Generates structured JSON commands for the robot from millimetre contours.
    
    Returns:
    - commands: list of dicts [{'type': 'MOVE', 'x': 10.0, 'y': 20.0}, {'type': 'PEN_DOWN'}, ...]
    - stats: summary metrics (distances, bounds, time estimates)
    """
    if optimize:
        contours = optimize_contour_order(contours_mm, start_pos=home_pos)
    else:
        contours = contours_mm
        
    commands = []
    pen_down_dist = 0.0
    pen_up_dist = 0.0
    
    min_x, max_x = float('inf'), float('-inf')
    min_y, max_y = float('inf'), float('-inf')
    
    current_pos = list(home_pos)
    current_pen_state = 'UP'
    
    # Initial command: Lift pen
    commands.append({'type': 'PEN_UP'})
    
    for cnt in contours:
        if not cnt:
            continue
            
        start_p = cnt[0]
        
        # 1. Pen-up travel move to start of contour
        travel_d = utils.calculate_distance(current_pos, start_p)
        pen_up_dist += travel_d
        
        commands.append({'type': 'MOVE', 'x': round(start_p[0], 2), 'y': round(start_p[1], 2)})
        current_pos = list(start_p)
        
        # 2. Lower pen onto paper
        commands.append({'type': 'PEN_DOWN'})
        current_pen_state = 'DOWN'
        
        # 3. Draw contour points
        for i in range(1, len(cnt)):
            pt = cnt[i]
            draw_d = utils.calculate_distance(current_pos, pt)
            pen_down_dist += draw_d
            
            commands.append({'type': 'MOVE', 'x': round(pt[0], 2), 'y': round(pt[1], 2)})
            current_pos = list(pt)
            
            # Update coordinate bounds
            min_x = min(min_x, pt[0])
            max_x = max(max_x, pt[0])
            min_y = min(min_y, pt[1])
            max_y = max(max_y, pt[1])
            
        # 4. Lift pen after contour complete
        commands.append({'type': 'PEN_UP'})
        current_pen_state = 'UP'
        
    # Return home position command
    if contours:
        return_d = utils.calculate_distance(current_pos, home_pos)
        pen_up_dist += return_d
        commands.append({'type': 'MOVE', 'x': round(home_pos[0], 2), 'y': round(home_pos[1], 2)})
        
    # Handle empty contour edge case
    if min_x == float('inf'):
        min_x = max_x = min_y = max_y = 0.0
        
    total_dist = pen_down_dist + pen_up_dist
    
    # Estimated time calculation (assuming 50 mm/s draw speed, 80 mm/s travel speed, 0.4s per pen lift)
    draw_speed = 50.0  # mm/s
    travel_speed = 80.0 # mm/s
    pen_lift_time = 0.4 # seconds per pen change
    
    pen_changes = len(contours) * 2
    est_seconds = (pen_down_dist / draw_speed) + (pen_up_dist / travel_speed) + (pen_changes * pen_lift_time)
    
    minutes = int(est_seconds // 60)
    seconds = int(est_seconds % 60)
    time_str = f"{minutes}m {seconds}s" if minutes > 0 else f"{seconds}s"
    
    total_points = sum(len(c) for c in contours)
    
    stats = {
        'total_contours': len(contours),
        'total_points': total_points,
        'pen_down_distance_mm': round(pen_down_dist, 2),
        'pen_up_distance_mm': round(pen_up_dist, 2),
        'total_distance_mm': round(total_dist, 2),
        'estimated_time_seconds': round(est_seconds, 1),
        'estimated_time_formatted': time_str,
        'drawing_width_mm': round(max_x - min_x, 2) if contours else 0.0,
        'drawing_height_mm': round(max_y - min_y, 2) if contours else 0.0,
        'bounds': {
            'min_x': round(min_x, 2),
            'max_x': round(max_x, 2),
            'min_y': round(min_y, 2),
            'max_y': round(max_y, 2)
        }
    }
    
    return commands, stats
