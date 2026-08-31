from __future__ import annotations
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import numpy as np
from config import OHT_SPECS

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from map_manager import MapManager
    from agent import OHTAgent


class MapVisualizer:
    def __init__(self, mgr: MapManager):
        self.mgr = mgr

        # Setup Plot
        # Height ratio 4:1 for Map vs Speed Graph
        self.fig, (self.ax_map, self.ax_speed) = plt.subplots(2, 1, figsize=(10, 12), gridspec_kw={'height_ratios': [4, 1]})
       
        # --- 1. Map Styling ---
        self.ax_map.set_aspect('equal')
        self.ax_map.set_facecolor('#1a1a1a') # Dark Grey Background
        self.ax_map.set_title("OHT Simulation Sandbox")
       
        # Draw Tracks & Machines
        self._draw_static_map()
        self._draw_machines()

        # --- 2. Dynamic Actor Cache ---
        # Dictionary to store graphical artists for each agent
        # { agent_instance: { 'body': Line2D, 'cargo': Line2D, 'text': Text } }
        self.agent_artists = {}
        self.agent_patches = {}

        # --- 3. Speed Graph (Agent 0 Only) ---
        self.speed_data = []
        self.ax_speed.set_title("Speed Profile (Agent 0) [mm/s]")
        self.ax_speed.set_ylim(0, OHT_SPECS['speed_max'] * 1.1)
        self.ax_speed.set_xlim(0, 200)
        self.ax_speed.grid(True, linestyle='--', alpha=0.3)
        self.ln_speed, = self.ax_speed.plot([], [], 'c-', lw=1.5)

    def _draw_static_map(self):
        """Draws the track network."""
        for s in self.mgr.segments.values():
            # Color logic: Slow zones are Orange, Normal are Blue
            c = '#d35400' if s.get('zone') in ['slow', 'crawl'] else '#2980b9'
           
            if s['type'] == 'line':
                p1, p2 = self.mgr.nodes[s['u']], self.mgr.nodes[s['v']]
                self.ax_map.plot([p1[0], p2[0]], [p1[1], p2[1]], color=c, lw=1.5, zorder=1)
               
            elif s['type'] == 'curve':
                ctr, r = s['center'], s['radius']
                # Draw arc
                th = np.linspace(s['angleStart'], s['angleStart'] + s['angleTotal'], 20)
                self.ax_map.plot(ctr[0] + r*np.cos(th), ctr[1] + r*np.sin(th), color=c, lw=1.5, zorder=1)
    
    def _draw_machines(self):
        """Draws static markers for OHBs and Machines."""
        for nid, wp_data in self.mgr.waypoints.items():
            pos = self.mgr.nodes[nid]
            w_type = wp_data.get('type', 'UNKNOWN')
           
            # Style based on type
            if 'OHB' in w_type:
                marker = 's' # Square
                color = '#27ae60' # Green
            else:
                marker = '^' # Triangle
                color = '#8e44ad' # Purple
           
            self.ax_map.plot(pos[0], pos[1], marker=marker, color=color, ms=8, zorder=2)
            # Optional: Add small text ID
            # self.ax_map.text(pos[0], pos[1], str(nid), color='white', fontsize=6, alpha=0.5)

    def update(self, agents):
        artists = []
       
        # 1. Update/Create Agent Bodies (Rectangles)
        for bot in agents:
            if bot not in self.agent_patches:
                # Create Rectangle (Width x Length)
                # Length = Front - Rear
                length = OHT_SPECS['offsets']['Front'] - OHT_SPECS['offsets']['Rear']
                width = OHT_SPECS['width']
               
                # Anchor point is bottom-left of the rectangle relative to center
                rect = patches.Rectangle((0,0), length, width, angle=0.0, zorder=10)
                self.ax_map.add_patch(rect)
                self.agent_patches[bot] = rect
           
            # Update Position & Rotation
            rect = self.agent_patches[bot]
           
            # Get Center Pos and Tangent
            pos = bot.sensor_visuals['Center']['pos']
            tan = bot.sensor_visuals['Center']['tan']
           
            # Calculate Angle in Degrees
            angle = np.degrees(np.arctan2(tan[1], tan[0]))
           
            # Calculate Bottom-Left Corner for the Rectangle anchor
            # We need to shift back by Rear offset, and left by Width/2
            # (Requires simple rotation math)
            l_offset = OHT_SPECS['offsets']['Rear'] # e.g. -600
            w_offset = -OHT_SPECS['width'] / 2.0
           
            # Rotation Matrix
            c, s = np.cos(np.radians(angle)), np.sin(np.radians(angle))
           
            # Apply rotation to offsets
            dx = l_offset * c - w_offset * s
            dy = l_offset * s + w_offset * c
           
            rect.set_xy((pos[0] + dx, pos[1] + dy))
            rect.set_angle(angle)
           
            # Color Logic
            if bot.state == "ERROR": color = '#c0392b' # Red
            elif bot.state == "ACTION": color = '#f1c40f' # Yellow
            elif any(bot.cargo_bay): color = '#00d2d3' # Cyan
            else: color = '#ecf0f1' # White
           
            rect.set_facecolor(color)
            artists.append(rect)

        # 2. Update Speed Graph
        if agents:
            self.speed_data.append(agents[0].speed)
            if len(self.speed_data) > 200: self.speed_data.pop(0)
            self.ln_speed.set_data(range(len(self.speed_data)), self.speed_data)
            artists.append(self.ln_speed)

        return artists


