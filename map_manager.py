import json
import numpy as np
import math
import heapq
import os

class MapManager:
    def __init__(self, json_path):
        if not os.path.exists(json_path):
            raise FileNotFoundError(f"Map not found: {json_path}")

        with open(json_path, 'r') as f:
            data = json.load(f)

        self.nodes = np.array(data['nodes'])
        self.segments = {int(s['id']): s for s in data['segments']}

        # --- WAYPOINTS & MACHINES ---
        # Data format: "101": {"id": "WP_A", "type": "OHB", "rotate": 0}
        self.waypoints = {}       # Node_ID (int) -> Data (dict)
        self.waypoint_lookup = {} # Name (str) -> Node_ID (int)
        self.machines = {}        # Node_ID (int) -> VirtualMachine Object

        if 'waypoints' in data:
            for node_str, wp_data in data['waypoints'].items():
                nid = int(node_str)
                # Store full object: {'id': 'Name', 'type': 'Type'}
                self.waypoints[nid] = wp_data
                self.waypoint_lookup[wp_data['id']] = nid

        self.graph = {i: [] for i in range(len(self.nodes))}
       
        # Build Order Matters!
        self._build_graph()          # 1. Geometry
        self.build_node_lookup()     # 2. Connectivity (Incoming/Outgoing)
        self._build_caution_zones()  # 3. Intelligence (Merge Zones)

    def _build_graph(self):
        for s in self.segments.values():
            u, v = int(s['u']), int(s['v'])

            # Geometry & Reversal Logic
            if s['type'] == 'line':
                l = np.linalg.norm(self.nodes[v] - self.nodes[u])
            elif s['type'] == 'curve':
                l = s['radius'] * abs(s['angleTotal'])
                c = np.array(s['center'])
                r = s['radius']
                ang_s = s['angleStart']
                ang_e = s['angleStart'] + s['angleTotal']

                p_geo_start = c + np.array([r*math.cos(ang_s), r*math.sin(ang_s), 0])
                p_geo_end   = c + np.array([r*math.cos(ang_e), r*math.sin(ang_e), 0])

                d_start = np.linalg.norm(self.nodes[u] - p_geo_start)
                d_end   = np.linalg.norm(self.nodes[u] - p_geo_end)
                s['is_geo_reversed'] = d_end < d_start

            s['calc_len'] = l
            self.graph[u].append((v, s['id'], l))

    def find_path(self, start, end):
        if start == end: return []
        q = [(0, start, [])]
        visited = set()
        while q:
            cost, curr, path = heapq.heappop(q)
            if curr in visited: continue
            visited.add(curr)
            if curr == end: return path
            for neighbor, seg_id, weight in self.graph[curr]:
                if neighbor not in visited:
                    heapq.heappush(q, (cost + weight, neighbor, path + [seg_id]))
        return None

    def get_state(self, seg_id, dist):
        s = self.segments[seg_id]
        l = s['calc_len']
        d = max(0.0, min(dist, l))
        excess = dist - d if dist > l else (dist if dist < 0 else 0)

        t = d/l if l>0 else 0
        if s['type'] == 'line':
            p1, p2 = self.nodes[s['u']], self.nodes[s['v']]
            vec = p2 - p1
            norm = np.linalg.norm(vec)
            tan = vec/norm if norm > 0 else np.array([1.0, 0.0, 0.0])
            pos = p1 + (tan * d)
        elif s['type'] == 'curve':
            c, r = np.array(s['center']), s['radius']
            ang_s, ang_t = s['angleStart'], s['angleTotal']

            if s.get('is_geo_reversed', False):
                curr = ang_s + (ang_t * (1.0 - t))
                tm = -1.0 if ang_t > 0 else 1.0
            else:
                curr = ang_s + (ang_t * t)
                tm = 1.0 if ang_t > 0 else -1.0

            pos = c + np.array([r*math.cos(curr), r*math.sin(curr), 0])
            tan = np.array([-math.sin(curr), math.cos(curr), 0]) * tm

        if abs(excess) > 0.001:
            pos = pos + (tan * excess)
        return pos, tan

    def get_competing_segments(self, target_node_id):
        return self.incoming_map.get(target_node_id, [])

    def register_machine(self, node_id, machine_obj):
        self.machines[node_id] = machine_obj

    def get_machine_at(self, node_id):
        return getattr(self, 'machines', {}).get(node_id)

    def build_node_lookup(self):
        # key: node_id, value: list of segment_ids
        self.incoming_map = {}
        self.outgoing_map = {}

        for seg_id, seg_data in self.segments.items():
            # Incoming (End Node)
            v = seg_data['v']
            if v not in self.incoming_map: self.incoming_map[v] = []
            self.incoming_map[v].append(seg_id)
           
            # Outgoing (Start Node)
            u = seg_data['u']
            if u not in self.outgoing_map: self.outgoing_map[u] = []
            self.outgoing_map[u].append(seg_id)

    def get_outgoing_segments(self, node_id):
        return self.outgoing_map.get(node_id, [])
   
    def _build_caution_zones(self):
        """
        Identifies Merge Nodes and creates upstream Caution Zones.
        Populates self.segment_to_zones = { seg_id: [merge_node_id, ...] }
        """
        from config import OHT_SPECS
       
        # 1. Identify Merge Nodes (>1 incoming segment)
        merge_nodes = []
        for node_id, incoming_segs in self.incoming_map.items():
            if len(incoming_segs) > 1:
                merge_nodes.append(node_id)

        # 2. Flood Fill Upstream
        # We need to cover 'merge_relevance_dist'
        safety_dist = OHT_SPECS['safety']['merge_relevance_dist']
       
        self.segment_to_zones = {} # Key: SegID, Value: List of MergeNodeIDs

        for m_node in merge_nodes:
            # BFS backwards
            # Queue: (segment_id, accumulated_distance_from_merge)
            queue = []
           
            # Init with immediate incoming segments
            for seg_id in self.incoming_map[m_node]:
                queue.append((seg_id, 0.0))

            visited_segs = set()

            while queue:
                curr_seg_id, dist_so_far = queue.pop(0)
                if curr_seg_id in visited_segs: continue
                visited_segs.add(curr_seg_id)

                # Register mapping
                if curr_seg_id not in self.segment_to_zones:
                    self.segment_to_zones[curr_seg_id] = []
                # Avoid duplicates
                if m_node not in self.segment_to_zones[curr_seg_id]:
                    self.segment_to_zones[curr_seg_id].append(m_node)

                # Check if we need to go further back
                seg_len = self.segments[curr_seg_id]['calc_len']
                new_dist = dist_so_far + seg_len
               
                if new_dist < safety_dist:
                    # Still within caution range, grab parents
                    start_node = self.segments[curr_seg_id]['u']
                    parent_segs = self.incoming_map.get(start_node, [])
                    for p_seg in parent_segs:
                        queue.append((p_seg, new_dist))

    def get_zones_for_segment(self, seg_id):
        return self.segment_to_zones.get(seg_id, [])
