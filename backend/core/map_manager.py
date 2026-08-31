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
        p_start = np.array([x, y, 0])
        
        if tt == 'STRAIGHT':
            l = t.get('length', 1.0)
            
            # Apply Port Splitting
            if tid in self.port_locations:
                ports = self.port_locations[tid]
                curr_start = p_start
                curr_offset = 0
                
                for pinfo in ports:
                    split_offset = pinfo['offset']
                    seg_len = split_offset - curr_offset
                    if seg_len > 0:
                        p_end = curr_start + vec * seg_len
                        self._raw_segments.append({
                            'builder_id': f"{tid}_part_{curr_offset}",
                            'type': 'line', 'start': curr_start, 'end': p_end, 'calc_len': seg_len
                        })
                        curr_start = p_end
                        curr_offset = split_offset
                    
                    # Register this coordinate as the port node
                    self.port_node_indices[(pinfo['machine_id'], pinfo['port_idx'])] = curr_start

                # Final piece
                rem_len = l - curr_offset
                if rem_len > 0:
                    p_end = curr_start + vec * rem_len
                    self._raw_segments.append({
                        'builder_id': f"{tid}_part_{curr_offset}",
                        'type': 'line', 'start': curr_start, 'end': p_end, 'calc_len': rem_len
                    })
            else:
                p_end = p_start + vec * l
                self._raw_segments.append({
                    'builder_id': tid, 'type': 'line',
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
            
            self._raw_segments.append({
                'builder_id': tid, 'type': 'curve',
                'start': p_start, 'end': p_end, 'calc_len': r * abs(ang_t),
                'center': center, 'radius': r, 'angleStart': ang_s, 'angleTotal': ang_t
            })
            
        elif tt.startswith('DIVERGE'):
            turn_dir = 'R' if '_R' in tt else 'L'
            l = 0.5
            r = 0.5
            
            p_end_s = p_start + vec * l
            self._raw_segments.append({
                'builder_id': tid + '_s', 'type': 'line',
                'start': p_start, 'end': p_end_s, 'calc_len': l
            })
            
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
            
            self._raw_segments.append({
                'builder_id': tid + '_t', 'type': 'curve',
                'start': p_end_s, 'end': p_end_t, 'calc_len': r * abs(ang_t),
                'center': center, 'radius': r, 'angleStart': ang_s, 'angleTotal': ang_t
            })
            
        elif tt.startswith('MERGE'):
            turn_dir = 'R' if '_R' in tt else 'L'
            l = 1.0
            r = 0.5
            
            p_end_s = p_start + vec * l
            self._raw_segments.append({
                'builder_id': tid + '_s', 'type': 'line',
                'start': p_start, 'end': p_end_s, 'calc_len': l
            })
            
            if turn_dir == 'R':
                cx = p_end_s[0] - r * math.cos(rad)
                cy = p_end_s[1] + r * math.sin(rad)
                center = np.array([cx, cy, 0])
                ang_e = -rad
                ang_s = ang_e - math.pi / 2
                ang_t = math.pi / 2
            else:
                cx = p_end_s[0] + r * math.cos(rad)
                cy = p_end_s[1] - r * math.sin(rad)
                center = np.array([cx, cy, 0])
                ang_e = -rad + math.pi
                ang_s = ang_e + math.pi / 2
                ang_t = -math.pi / 2
                
            p_start_t = center + np.array([r * math.cos(ang_s), r * math.sin(ang_s), 0])
            
            self._raw_segments.append({
                'builder_id': tid + '_t', 'type': 'curve',
                'start': p_start_t, 'end': p_end_s, 'calc_len': r * abs(ang_t),
                'center': center, 'radius': r, 'angleStart': ang_s, 'angleTotal': ang_t
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
   
    def _build_caution_zones(self):
        self.segment_to_zones = {}
        # Simple implementation for now to prevent crashes
        pass

    def get_zones_for_segment(self, seg_id):
        return self.segment_to_zones.get(seg_id, [])
