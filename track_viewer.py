import json
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
import numpy as np
import math
import argparse

parser = argparse.ArgumentParser()
parser.add_argument("input_json")
args = parser.parse_args()

# --- Load Data ---
with open(args.input_json, 'r') as f:
    data = json.load(f)

# --- MOCK DATA FOR TESTING (Uncomment above to use real file) ---
# This mock data ensures you can run it immediately to see the effect
# data = {
#     "nodes": [
#         [0, 0, 0], [10, 0, 0], [20, 0, 0], [20, 10, 0]
#     ],
#     "segments": [
#         {"id": 1, "type": "line", "u": 0, "v": 1, "zone": "normal"},
#         {"id": 2, "type": "line", "u": 1, "v": 2, "zone": "slow"},
#         # A curve that goes from 2 -> 3
#         {"id": 3, "type": "curve", "u": 2, "v": 3, "center": [20,0,0], "radius": 10, "angleStart": 0, "angleTotal": 1.57, "zone": "normal"}
#     ]
# }
# ----------------------------------------------------------------

nodes = np.array(data['nodes'])
segments = data['segments']

def plot_gradient(ax, x, y, cmap_name='Blues'):
    """
    Plots a line with a gradient color from Start (Dark) to End (Light).
    """
    # Create a set of line segments so each can have a unique color
    points = np.array([x, y]).T.reshape(-1, 1, 2)
    segments = np.concatenate([points[:-1], points[1:]], axis=1)

    # Create the LineCollection
    norm = plt.Normalize(0, 1)
    lc = LineCollection(segments, cmap=cmap_name, norm=norm)
   
    # Generate color values:
    # 1.0 (Dark/High) -> 0.3 (Light/Low)
    # We stop at 0.3 so the line doesn't become invisible white
    color_values = np.linspace(1.0, 0.3, len(segments))
   
    lc.set_array(color_values)
    lc.set_linewidth(3)
    ax.add_collection(lc)

def get_curve_points(u_idx, v_idx, center, r, ang_start, ang_tot):
    """
    Generates points for a curve, ensuring they flow from u -> v.
    """
    # 1. Calculate Geometric Start and End points of the arc
    geo_start_x = center[0] + r * math.cos(ang_start)
    geo_start_y = center[1] + r * math.sin(ang_start)
   
    geo_end_x = center[0] + r * math.cos(ang_start + ang_tot)
    geo_end_y = center[1] + r * math.sin(ang_start + ang_tot)
   
    u_coords = nodes[u_idx]
   
    # 2. Calculate distances from Node U to both Geometric Start and Geometric End
    dist_to_start = math.hypot(u_coords[0] - geo_start_x, u_coords[1] - geo_start_y)
    dist_to_end   = math.hypot(u_coords[0] - geo_end_x,   u_coords[1] - geo_end_y)
   
    # 3. Determine direction based on which end is closer
    # If U is closer to the Start, we move Forward (Start -> End)
    # If U is closer to the End, we move Backward (End -> Start)
    if dist_to_start < dist_to_end:
        # Forward direction (CCW relative to angle definition)
        thetas = np.linspace(ang_start, ang_start + ang_tot, 50)
    else:
        # Reverse direction (CW relative to angle definition)
        thetas = np.linspace(ang_start + ang_tot, ang_start, 50)
       
    xs = center[0] + r * np.cos(thetas)
    ys = center[1] + r * np.sin(thetas)
    return xs, ys


# --- Visualization ---
fig, ax = plt.subplots(figsize=(10, 10))
ax.set_aspect('equal')
ax.grid(True, linestyle='--', alpha=0.6)
ax.set_facecolor('#f8f8f8')

print("--- Plotting Gradients ---")
print("Dark Color = Start (u)")
print("Light Color = End (v)")

for seg in segments:
    # 1. Determine Color Map based on Type/Zone
    if seg.get('zone') == 'slow':
        # Magenta/Purple for slow zones
        cmap = 'PuRd'
    elif seg['type'] == 'curve':
        # Green for curves
        cmap = 'Greens'
    else:
        # Blue for standard lines
        cmap = 'Blues'

    # 2. Generate Points (xs, ys) ordered from u -> v
    if seg['type'] == 'line':
        p1 = nodes[seg['u']]
        p2 = nodes[seg['v']]
        xs = np.linspace(p1[0], p2[0], 20) # 20 segments for smooth gradient
        ys = np.linspace(p1[1], p2[1], 20)
       
    elif seg['type'] == 'curve':
        xs, ys = get_curve_points(
            seg['u'], seg['v'],
            seg['center'], seg['radius'],
            seg['angleStart'], seg['angleTotal']
        )

    # 3. Plot with Gradient
    plot_gradient(ax, xs, ys, cmap)

# Draw Nodes on top
ax.scatter(nodes[:,0], nodes[:,1], c='black', zorder=10, s=20)
for i, n in enumerate(nodes):
    ax.text(n[0], n[1]+0.2, str(i), fontsize=9, color='black', fontweight='bold', ha='center')

# Legend hack
from matplotlib.lines import Line2D
custom_lines = [Line2D([0], [0], color='blue', lw=2),
                Line2D([0], [0], color='green', lw=2),
                Line2D([0], [0], color='magenta', lw=2)]
ax.legend(custom_lines, ['Line (Normal)', 'Curve', 'Slow Zone'], loc='upper right')

plt.title("Track Direction Verification\n(Dark End = Start Node, Light End = Destination Node)")
plt.show()

