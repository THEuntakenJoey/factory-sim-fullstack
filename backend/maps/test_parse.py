import json
import math
import numpy as np

def normAng(a):
    return a % 360

def parse_map(json_path):
    with open(json_path, 'r') as f:
        data = json.load(f)

    raw_tracks = data.get('tracks', [])
    segments = []
    
    for t in raw_tracks:
        tid = t['id']
        tt = t['type']
        x, y, h = t['x'], t['y'], t['heading']
        
        rad = h * math.pi / 180.0
        vec = np.array([math.sin(rad), math.cos(rad), 0])
        p_start = np.array([x, y, 0])
        
        if tt == 'STRAIGHT':
            l = t.get('length', 1.0)
            p_end = p_start + vec * l
            segments.append({
                'id': tid, 'builder_id': tid, 'type': 'line',
                'start': p_start, 'end': p_end, 'calc_len': l
            })
            
        elif tt.startswith('TURN'):
            turn_dir = 'R' if '_R' in tt else 'L'
            r = t.get('radius', 0.5)
            
            if turn_dir == 'R':
                cx = x + r * math.cos(rad)
                cy = y - r * math.sin(rad)
                ang_s = -rad + math.pi
                ang_t = -math.pi / 2
            else:
                cx = x - r * math.cos(rad)
                cy = y + r * math.sin(rad)
                ang_s = -rad
                ang_t = math.pi / 2
                
            center = np.array([cx, cy, 0])
            p_end = center + np.array([r * math.cos(ang_s + ang_t), r * math.sin(ang_s + ang_t), 0])
            
            segments.append({
                'id': tid, 'builder_id': tid, 'type': 'curve',
                'start': p_start, 'end': p_end, 'calc_len': r * abs(ang_t),
                'center': center, 'radius': r, 'angleStart': ang_s, 'angleTotal': ang_t
            })
            
        elif tt.startswith('DIVERGE'):
            turn_dir = 'R' if '_R' in tt else 'L'
            l = 0.5
            r = 0.5
            
            # Straight part
            p_end_s = p_start + vec * l
            segments.append({
                'id': tid + '_s', 'builder_id': tid, 'type': 'line',
                'start': p_start, 'end': p_end_s, 'calc_len': l
            })
            
            # Turn part starts from p_end_s
            h2 = h
            rad2 = rad
            if turn_dir == 'R':
                cx = p_end_s[0] + r * math.cos(rad2)
                cy = p_end_s[1] - r * math.sin(rad2)
                ang_s = -rad2 + math.pi
                ang_t = -math.pi / 2
            else:
                cx = p_end_s[0] - r * math.cos(rad2)
                cy = p_end_s[1] + r * math.sin(rad2)
                ang_s = -rad2
                ang_t = math.pi / 2
                
            center = np.array([cx, cy, 0])
            p_end_t = center + np.array([r * math.cos(ang_s + ang_t), r * math.sin(ang_s + ang_t), 0])
            
            segments.append({
                'id': tid + '_t', 'builder_id': tid, 'type': 'curve',
                'start': p_end_s, 'end': p_end_t, 'calc_len': r * abs(ang_t),
                'center': center, 'radius': r, 'angleStart': ang_s, 'angleTotal': ang_t
            })
            
        elif tt.startswith('MERGE'):
            turn_dir = 'R' if '_R' in tt else 'L'
            l = 1.0
            r = 0.5
            
            # Straight part
            p_end_s = p_start + vec * l
            segments.append({
                'id': tid + '_s', 'builder_id': tid, 'type': 'line',
                'start': p_start, 'end': p_end_s, 'calc_len': l
            })
            
            # Turn part: ends at p_end_s.
            # If MERGE_R, it's a right turn coming into the straight line at offset l/2.
            # Wait, the user said:
            # "One starting node at (0, 0) heading 0." (this is p_start)
            # "One starting node at (0.5, 0) heading 270." (this is the turn start)
            # "One ending node at (0, 0.5) heading 0." (this is p_end_s, wait, length is 0.5!)
            # Ah, MERGE_R length is 0.5 in the user's description?
            # Let's check test_parse.py output for track_66632 (MERGE_R, length=1)
            # In builder.js MERGE_R length is 1.0.
            # The merge turn connects to the straight line at length 0.5? No, the user said:
            # "One straight connecting (0, 0) to (0, 0.5)" -> wait, length is 0.5 in the user's comment, but track length is 1.0.
            # Actually, `builder.js` does whatever it wants based on `length=1.0`.
            # If MERGE_R length=1.0, and radius=0.5.
            # Then straight goes from (0,0) to (0, 1.0).
            # Where does the turn join? At the end (0, 1.0)?
            # If radius is 0.5, and it joins at (0, 1.0) heading 0, the turn must start at (0.5, 0.5) heading 270.
            # Let's assume the turn ends at the END of the straight line (`p_end_s`).
            # If so, the turn center must be such that at `p_end_s`, the tangent is `h`.
            # If it's a MERGE_R, it's coming from the right, so it's a RIGHT turn if we trace backwards,
            # which means going forward it's a RIGHT turn?
            # No, if we trace backwards from (0, 1.0) heading 0 (South), turning right means we go West to (0.5, 0.5).
            # So going forward it's a LEFT turn from heading 270 to heading 0.
            # Let's assume it's a LEFT turn.
            # End point is `p_end_s`. End tangent is `h`.
            # For a LEFT turn, center is 90 deg counter-clockwise from travel dir.
            # So center is `p_end_s + [r*cos(rad), -r*sin(rad)]` ?
            # Let's trace it. Turn ends at `p_end_s`.
            if turn_dir == 'R': # Merge Right means track is on the right. It joins the straight line.
                # It is a LEFT turn from the perspective of the incoming vehicle.
                # End math angle = pi/2 - rad.
                # Center is 90 deg CCW from end tangent:
                cx = p_end_s[0] - r * math.cos(rad)
                cy = p_end_s[1] + r * math.sin(rad)
                center = np.array([cx, cy, 0])
                ang_e = -rad # angle of p_end_s from center
                ang_s = ang_e - math.pi / 2
                ang_t = math.pi / 2
            else: # Merge Left
                # It is a RIGHT turn from the perspective of the incoming vehicle.
                cx = p_end_s[0] + r * math.cos(rad)
                cy = p_end_s[1] - r * math.sin(rad)
                center = np.array([cx, cy, 0])
                ang_e = -rad + math.pi
                ang_s = ang_e + math.pi / 2
                ang_t = -math.pi / 2
                
            p_start_t = center + np.array([r * math.cos(ang_s), r * math.sin(ang_s), 0])
            
            segments.append({
                'id': tid + '_t', 'builder_id': tid, 'type': 'curve',
                'start': p_start_t, 'end': p_end_s, 'calc_len': r * abs(ang_t),
                'center': center, 'radius': r, 'angleStart': ang_s, 'angleTotal': ang_t
            })

    print(f"Generated {len(segments)} flat segments.")
    for s in segments:
        print(f"{s['id']}: start={s['start']} end={s['end']}")

if __name__ == '__main__':
    parse_map('backend/maps/map.json')
