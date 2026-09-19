import json
import numpy as np
import math
import heapq
import os

def normAng(a):
    return a % 360

class MapManager:
    def __init__(self, json_path):
        if not os.path.exists(json_path):
            raise FileNotFoundError(f"Map not found: {json_path}")

        with open(json_path, 'r') as f:
            data = json.load(f)

        raw_tracks = data.get('tracks', [])
        self.machines = data.get('machines', [])
        self.waypoints = {} # For backwards compatibility with older dispatcher

        # 1. Collect Port Offsets
        # Map of trackId -> list of { offset, machine_id, port_idx }
        self.port_locations = {}
        for m in self.machines:
            for idx, p in enumerate(m.get('ports', [])):
                if not p: continue
                tid = p.get('trackId')
                if tid not in self.port_locations:
                    self.port_locations[tid] = []
                self.port_locations[tid].append({
                    'offset': p.get('offset', 0),
                    'machine_id': m.get('id'),
                    'port_idx': idx
                })

        # Sort offsets so we can split tracks sequentially
        for tid in self.port_locations:
            self.port_locations[tid].sort(key=lambda x: x['offset'])

        self.port_node_indices = {} # (machine_id, port_idx) -> integer node index

        # 2. Decompose Builder Tracks into Math Segments & Split at Ports
        self._raw_segments = []
        for t in raw_tracks:
            self._flatten_and_split_track(t)

        # 3. Build Unique Physical Nodes
        # OHTAgent requires self.nodes to be an array of points, and segments reference indices.
        self.nodes = [] # List of np.array([x, y, 0])
        node_lookup = {} # "x,y" -> index

        def get_or_create_node(pt):
            # Quantize to 1mm to avoid floating point issues
            k = f"{round(pt[0]*1000)},{round(pt[1]*1000)}"
            if k not in node_lookup:
                node_lookup[k] = len(self.nodes)
                self.nodes.append(pt)
            return node_lookup[k]

        self.segments = {}
        for s in self._raw_segments:
            u_idx = get_or_create_node(s['start'])
            v_idx = get_or_create_node(s['end'])
            s['u'] = u_idx
            s['v'] = v_idx
            
            # Reversal logic (legacy support for OHTAgent `is_geo_reversed`)
            if s['type'] == 'curve':
                s['is_geo_reversed'] = False

            s['id'] = s['builder_id']
            self.segments[s['id']] = s

        self.nodes = np.array(self.nodes)

        # Convert port_node_indices coordinates to integer node indices
        for k, pt in self.port_node_indices.items():
            self.port_node_indices[k] = get_or_create_node(pt)

        self.graph = {i: [] for i in range(len(self.nodes))}
        
        # Build Order Matters!
        self._build_graph()          # 1. Geometry
        self.build_node_lookup()     # 2. Connectivity (Incoming/Outgoing)
        self._build_caution_zones()  # 3. Intelligence (Merge Zones)

    def _flatten_and_split_track(self, t):
        tid = t['id']
        tt = t['type']
        x, y, h = t['x'], t['y'], t['heading']
        
        rad = h * math.pi / 180.0
        vec = np.array([math.sin(rad), math.cos(rad), 0])
        d_right = np.array([math.cos(rad), -math.sin(rad), 0])
        d_left = np.array([-math.cos(rad), math.sin(rad), 0])
        p_start = np.array([x, y, 0])
        
        MIN_BLOCK_LEN = 1.1

        def add_subdivided_blocks(start_pt, end_pt, seg_len, base_id):
            if seg_len <= 0.001:
                return
            num_blocks = max(1, int(seg_len // MIN_BLOCK_LEN))
            block_len = seg_len / num_blocks
            p_curr = start_pt
            for b in range(num_blocks):
                p_next = start_pt + vec * ((b + 1) * block_len) if b < num_blocks - 1 else end_pt
                blk_id = f"{base_id}_b{b}" if num_blocks > 1 else base_id
                self._raw_segments.append({
                    'builder_id': blk_id,
                    'type': 'line',
                    'start': p_curr,
                    'end': p_next,
                    'calc_len': block_len,
                    'zone': 'normal'
                })
                p_curr = p_next

        if tt == 'STRAIGHT':
            l = t.get('length', 1.0)
            
            # Apply Port Splitting and Block Discretization
            if tid in self.port_locations:
                ports = self.port_locations[tid]
                curr_start = p_start
                curr_offset = 0
                
                for pinfo in ports:
                    split_offset = pinfo['offset']
                    seg_len = split_offset - curr_offset
                    if seg_len > 0:
                        p_end = curr_start + vec * seg_len
                        add_subdivided_blocks(curr_start, p_end, seg_len, f"{tid}_p_{round(curr_offset*1000)}")
                        curr_start = p_end
                        curr_offset = split_offset
                    
                    # Register this coordinate as the port node
                    self.port_node_indices[(pinfo['machine_id'], pinfo['port_idx'])] = curr_start

                # Final piece after last port
                rem_len = l - curr_offset
                if rem_len > 0:
                    p_end = curr_start + vec * rem_len
                    add_subdivided_blocks(curr_start, p_end, rem_len, f"{tid}_p_{round(curr_offset*1000)}")
            else:
                p_end = p_start + vec * l
                add_subdivided_blocks(p_start, p_end, l, tid)
            
        elif tt.startswith('TURN'):
            is_right = '_R' in tt
            r = t.get('radius', 0.5)
            
            d_turn = np.array([math.cos(rad), -math.sin(rad), 0]) if is_right else np.array([-math.cos(rad), math.sin(rad), 0])
            center = p_start + d_turn * r
            ang_s = math.atan2(-d_turn[1], -d_turn[0])
            ang_t = -math.pi / 2 if is_right else math.pi / 2
            
            p_end = center + np.array([r * math.cos(ang_s + ang_t), r * math.sin(ang_s + ang_t), 0])
            
            self._raw_segments.append({
                'builder_id': tid, 'type': 'curve',
                'start': p_start, 'end': p_end, 'calc_len': r * abs(ang_t),
                'center': center, 'radius': r, 'angleStart': ang_s, 'angleTotal': ang_t,
                'zone': 'slow'
            })
            
        elif tt.startswith('DIVERGE'):
            is_right = '_R' in tt
            l = 0.5
            r = 0.5
            
            # 1. Straight branch
            p_end_s = p_start + vec * l
            self._raw_segments.append({
                'builder_id': tid + '_s', 'type': 'line',
                'start': p_start, 'end': p_end_s, 'calc_len': l,
                'zone': 'normal'
            })
            
            # 2. Turn branch (starts at p_start, branches out)
            d_turn = np.array([math.cos(rad), -math.sin(rad), 0]) if is_right else np.array([-math.cos(rad), math.sin(rad), 0])
            center = p_start + d_turn * r
            ang_s = math.atan2(-d_turn[1], -d_turn[0])
            ang_t = -math.pi / 2 if is_right else math.pi / 2
            p_end_t = center + np.array([r * math.cos(ang_s + ang_t), r * math.sin(ang_s + ang_t), 0])
            
            self._raw_segments.append({
                'builder_id': tid + '_t', 'type': 'curve',
                'start': p_start, 'end': p_end_t, 'calc_len': r * abs(ang_t),
                'center': center, 'radius': r, 'angleStart': ang_s, 'angleTotal': ang_t,
                'zone': 'slow'
            })
            
        elif tt.startswith('MERGE'):
            is_right = '_R' in tt
            l = 0.5
            r = 0.5
            
            # 1. Straight branch (from p_start to p_end_s)
            p_end_s = p_start + vec * l
            self._raw_segments.append({
                'builder_id': tid + '_s', 'type': 'line',
                'start': p_start, 'end': p_end_s, 'calc_len': l,
                'zone': 'normal'
            })
            
            # 2. Turn branch (starts at side input in2, merges tangentially into p_end_s)
            d_side = d_right if is_right else d_left
            p_start_t = p_start + d_side * r
            center = p_start + d_side * r + vec * r
            ang_s = math.atan2(-vec[1], -vec[0])
            ang_t = -math.pi / 2 if is_right else math.pi / 2
            p_end_t = p_end_s
            
            self._raw_segments.append({
                'builder_id': tid + '_t', 'type': 'curve',
                'start': p_start_t, 'end': p_end_t, 'calc_len': r * abs(ang_t),
                'center': center, 'radius': r, 'angleStart': ang_s, 'angleTotal': ang_t,
                'zone': 'slow'
            })


    def _build_graph(self):
        for s in self.segments.values():
            u, v = s['u'], s['v']
            self.graph[u].append((v, s['id'], s['calc_len']))

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
            c, r = s['center'], s['radius']
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
        # We now manage machines inside FactoryState, but keep this for backwards compatibility
        pass

    def get_machine_at(self, node_id):
        return None

    def build_node_lookup(self):
        self.incoming_map = {}
        self.outgoing_map = {}

        for seg_id, seg_data in self.segments.items():
            v = seg_data['v']
            if v not in self.incoming_map: self.incoming_map[v] = []
            self.incoming_map[v].append(seg_id)
           
            u = seg_data['u']
            if u not in self.outgoing_map: self.outgoing_map[u] = []
            self.outgoing_map[u].append(seg_id)

    def get_outgoing_segments(self, node_id):
        return self.outgoing_map.get(node_id, [])
   
    def is_curve(self, seg_id) -> bool:
        seg = self.segments.get(seg_id)
        return bool(seg and seg.get('type') == 'curve')

    def get_block_length_m(self, seg_id) -> float:
        seg = self.segments.get(seg_id)
        return seg['calc_len'] if seg else 1.0

    def get_block_speed_limit(self, seg_id) -> float:
        seg = self.segments.get(seg_id)
        if not seg: return 2.0
        zone = seg.get('zone', 'normal')
        if seg.get('type') == 'curve' or zone == 'slow':
            return 0.8  # 800 mm/s = 0.8 m/s
        elif zone == 'crawl':
            return 0.3  # 300 mm/s = 0.3 m/s
        return 2.0      # 2000 mm/s = 2.0 m/s

    def get_next_segments(self, seg_id):
        seg = self.segments.get(seg_id)
        if not seg: return []
        v = seg['v']
        return self.get_outgoing_segments(v)

    def get_curve_exit_blocks(self, seg_id):
        """For a curve segment, returns all downstream straight blocks."""
        if not self.is_curve(seg_id):
            return []
        return self.get_next_segments(seg_id)

    def _build_caution_zones(self):
        self.segment_to_zones = {}

    def get_zones_for_segment(self, seg_id):
        return self.segment_to_zones.get(seg_id, [])
