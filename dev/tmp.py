from __future__ import annotations
import math
import numpy as np
from collections import deque
from typing import TYPE_CHECKING, List, Optional, Dict, Any

from config import OHT_SPECS

if TYPE_CHECKING:
    from map_manager import MapManager
    from traffic import TrafficRegistry

# --- CONSTANTS ---
TOLERANCE_NODE = 10.0   # mm: Distance considered "At the node"
TOLERANCE_STOP = 2.0    # mm: Distance considered "Arrived" for physics snap
BLIND_SPOT_BUFFER = -1000.0 # mm: How far past the line we still check priority

class Mission:
    """
    Data container for Transport Orders or Actions.
    """
    def __init__(self, m_type: str, target_id: Optional[int] = None, **kwargs):
        self.type = m_type  # "MOVE" or "ACTION"
        self.target_id = target_id
        self.params = kwargs


class SpeedController:
    """
    Calculates target velocity based on physics and zone constraints.
    """
    def calculate_target_speed(self, limit_dist: float, speed_cap: float) -> float:
        """
        Args:
            limit_dist: Distance to the nearest hard stop (obstacle/target).
            speed_cap: The maximum speed limit (e.g. zone limit).
        """
        # 1. Physics Constraint (Braking Curve)
        # Deadband: Prevent Zeno's Paradox (creeping infinitely to 0)
        if limit_dist <= TOLERANCE_STOP:
            physics_v = 0.0
        else:
            # Safety Factor (0.9): Brakes are treated as 90% effective to create a buffer.
            safe_decel = OHT_SPECS['decel'] * 0.9
            physics_v = math.sqrt(2 * safe_decel * limit_dist)

        # 2. Zone Constraint (The "Ceiling")
        target_v = min(physics_v, speed_cap)

        # 3. Global Hard Clamp
        return max(0.0, min(target_v, OHT_SPECS['speed_max']))

class GraphWalker:
    """
    The 'Eyes' of the agent.
    Scans the path ahead to identify constraints (Obstacles, Curves, Merges).
    """
    def __init__(self, mgr: MapManager, traffic_ctrl: TrafficRegistry):
        self.mgr = mgr
        self.traffic_ctrl = traffic_ctrl

    def get_constraints(self, agent: OHTAgent):
        """
        Returns (limit_dist, speed_cap).
        """
        specs = OHT_SPECS
        safe = specs['safety']

        # Default: Infinite distance (path clear)
        limit_dist = agent.total_dist_to_target if agent.total_dist_to_target is not None else float('inf')
        speed_cap = specs['speed_max']

        # 1. CALCULATE SCAN RADII
        stop_dist_phys = (agent.speed ** 2) / (2 * specs['decel'])

        scan_radius_obs = max(
            stop_dist_phys + safe['buffer_stop_obs'],
            safe['min_lookahead_obs']
        )

        if agent.speed > specs['speed_curve']:
            slow_dist_phys = (agent.speed**2 - specs['speed_curve']**2) / (2 * specs['decel'])
            scan_radius_zone = slow_dist_phys + safe['buffer_stop_zone']
        else:
            scan_radius_zone = safe['min_lookahead_zone']

        max_scan = max(scan_radius_obs, scan_radius_zone)

        # 2. LOOKAHEAD LOOP
        accum_dist = 0.0
        search_path = [agent.current_seg] + agent.seg_queue[:5]

        for i, seg_id in enumerate(search_path):
            if accum_dist > max_scan: break

            seg = self.mgr.segments[seg_id]
            seg_len = seg['calc_len']

            # Distance from Agent Center to the END of this segment
            dist_to_seg_end = (seg_len - agent.dist) if i == 0 else (accum_dist + seg_len)

            # --- A. ZONE LOGIC (Curves) ---
            # Distance from Agent NOSE to start of segment
            dist_nose_to_start = (-agent.dist if i == 0 else accum_dist) - specs['offsets']['Preceding']

            if dist_nose_to_start < scan_radius_zone:
                zone_type = seg.get('zone', 'normal')
                target_z_speed = specs['speed_max']
                if zone_type == 'slow': target_z_speed = specs['speed_curve']
                elif zone_type == 'crawl': target_z_speed = specs['speed_crawl']

                if target_z_speed < speed_cap:
                    if dist_nose_to_start <= 0:
                        speed_cap = min(speed_cap, target_z_speed)
                    else:
                        allowed = math.sqrt(target_z_speed**2 + 2 * specs['decel'] * dist_nose_to_start)
                        speed_cap = min(speed_cap, allowed)

            # --- B. OBSTACLE LOGIC ---
            if accum_dist < scan_radius_obs:
                others = self.traffic_ctrl.get_agents_on_segment(seg_id)
                for other in others:
                    if other == agent: continue

                    if i == 0: rel_dist = other.dist - agent.dist
                    else: rel_dist = accum_dist + other.dist

                    # Anti-Tailing Fix: Ignore cars behind us or overlapping our center.
                    if rel_dist <= 0: continue

                    gap = rel_dist - specs['offsets']['Preceding'] + specs['offsets']['Following']
                    stop_point = gap - safe['gap_maintained']

                    if 0 < stop_point < scan_radius_obs:
                        if stop_point < limit_dist: limit_dist = stop_point
                    elif stop_point <= 0:
                        limit_dist = 0.0 # Crash imminent, force stop

            # --- C. MERGE LOGIC ---
            target_node = seg['v']

            # Only check if it's actually a merge (competitors exist)
            if len(self.mgr.get_competing_segments(target_node)) > 1:

                dist_nose_to_merge = dist_to_seg_end - specs['offsets']['Preceding']

                # Blind Spot Fix: Check even if nose is slightly inside the intersection
                if BLIND_SPOT_BUFFER <= dist_nose_to_merge < scan_radius_obs:

                    # Priority Arbitration (using Center Distance)
                    if not self._check_merge_priority(agent, target_node, dist_to_seg_end):

                        stop_pt = dist_nose_to_merge - safe['gap_yield']

                        # If inside yield gap, force stop (clamp to 0.0)
                        if stop_pt < limit_dist: limit_dist = max(0.0, stop_pt)

            if i == 0: accum_dist += (seg_len - agent.dist)
            else: accum_dist += seg_len

        return max(0.0, limit_dist), speed_cap

    def _check_merge_priority(self, agent, merge_node, my_dist_to_merge):
        """
        Arbitrates priority using Pre-Calculated Distances from TrafficRegistry.
        Returns True (Priority) or False (Yield).
        """
        safe = OHT_SPECS['safety']

        # 1. GET COMPETITORS
        competitors = self.traffic_ctrl.get_zone_competitors(merge_node)

        # Use String ID for deterministic comparison
        my_id = getattr(agent, 'ui_id', str(id(agent)))

        for other_agent, other_dist in competitors:
            if other_agent == agent: continue

            # Relevance Check
            if other_dist - my_dist_to_merge > safe['merge_relevance_dist']:
                # Optimization: Don't yield to someone 10 meters away
                continue

            delta = other_dist - my_dist_to_merge

            # Tie Breaker
            if abs(delta) < safe['merge_tie_epsilon']:
                other_id = getattr(other_agent, 'ui_id', str(id(other_agent)))
                if my_id < other_id: return False # Yield (Lower ID yields)
                else: continue # Win

            # Distance Check
            if other_dist < my_dist_to_merge:
                return False # Yield

        # 2. OUTGOING CLEARANCE (Anti-Gridlock)
        if hasattr(self.mgr, 'get_outgoing_segments'):
            outgoing = self.mgr.get_outgoing_segments(merge_node)
            for seg_id in outgoing:
                blockers = self.traffic_ctrl.get_agents_on_segment(seg_id)
                for other in blockers:
                    # Clearance: Their Rear must be clear of the node
                    clearance = abs(OHT_SPECS['offsets']['Following']) + safe['gap_yield']
                    if other.dist < clearance:
                        return False # Exit Blocked

        return True

    def get_state_at_offset(self, agent: OHTAgent, offset: float):
        """
        Calculates position of a point on the vehicle body (e.g. Rear Bumper),
        handling history if the point wraps around a corner.
        """
        req_dist = agent.dist + offset

        # Case A: Point is on current segment (or future)
        if req_dist >= 0:
            curr_seg = agent.current_seg
            local = req_dist
            q_idx = 0
            while True:
                slen = self.mgr.segments[curr_seg]['calc_len']
                if local <= slen: return self.mgr.get_state(curr_seg, local)
                local -= slen
                if q_idx < len(agent.seg_queue):
                    curr_seg = agent.seg_queue[q_idx]
                    q_idx += 1
                else: return self.mgr.get_state(curr_seg, slen + local)

        # Case B: Point is in history (wrapped around previous turn)
        else:
            curr_seg = agent.current_seg
            local = req_dist
            h_idx = -1
            while True:
                if abs(h_idx) <= len(agent.history):
                    pseg = agent.history[h_idx]
                    plen = self.mgr.segments[pseg]['calc_len']
                    local = plen + local
                    if local >= 0: return self.mgr.get_state(pseg, local)
                    h_idx -= 1
                else:
                    # Run out of history? Clamp to start.
                    anchor = agent.history[0] if agent.history else agent.current_seg
                    return self.mgr.get_state(anchor, local)


class OHTAgent:
    def __init__(self, mgr: MapManager, traffic_ctrl: TrafficRegistry):
        self.mgr = mgr
        self.brain = SpeedController()
        self.walker = GraphWalker(mgr, traffic_ctrl)

        # Navigation State
        self.seg_queue = []
        self.history = []
        self.current_seg = None
        self.dist = 0.0
        self.speed = 0.0
        self.total_dist_to_target = None

        # High-Level State
        self.state = "UNSPAWNED"
        self.wait_timer = 0.0
        self.target_name = ""
        self.ui_id = "OHT_??"

        # Mission System
        self.mission_queue = deque()
        self.current_mission = None

        # Dual Capacity
        self.cargo_bay = [None, None]
        self.capacity = 2

        # Visuals
        self.sensor_visuals = {k: {'pos': np.zeros(3), 'tan': np.zeros(3)} for k in OHT_SPECS['offsets']}

    def spawn(self, node_id: int):
        """Teleports agent to a segment starting at node_id."""
        found = False
        for s in self.mgr.segments.values():
            if s['u'] == node_id:
                self.current_seg = s['id']
                self.dist = 0.0
                self.history = []
                self.seg_queue = []
                self.state = "IDLE"
                found = True
                print(f"[{self.ui_id}] Spawned at Node {node_id} (Seg {s['id']})")
                break

        if not found:
            print(f"[{self.ui_id}] Error: Cannot spawn at Node {node_id}")

    def add_mission(self, m_type: str, target_id=None, **kwargs):
        new_mission = Mission(m_type, target_id, **kwargs)
        self.mission_queue.append(new_mission)
        print(f"[{self.ui_id}] Queued: {m_type} -> {target_id}")

    def update(self, dt: float):
        if self.state == "ERROR": return

        # 1. Mission Lifecycle
        self._update_mission_lifecycle()

        # 2. State Logic
        if self.state == "MOVING":
            self._update_navigation(dt)
        elif self.state == "ACTION":
            self._update_action(dt)

        # 3. Visuals
        if self.current_seg is not None:
            self._update_visuals()

    def _update_mission_lifecycle(self):
        # A. Start work if IDLE
        if self.state == "IDLE" and self.mission_queue:
            self._start_next_mission()

        # B. Check for Completion
        mission_complete = False
        if self.state == "MOVING":
            if self.total_dist_to_target is not None and self.total_dist_to_target <= 0.0:
                print(f"[{self.ui_id}] Arrived at Node {self.current_mission.target_id}")
                mission_complete = True
        elif self.state == "ACTION":
            if self.wait_timer > 3.0: # Hardcoded action duration
                mission_complete = True

        # C. Handle Completion
        if mission_complete:
            # Callback
            if self.current_mission.params.get('on_complete'):
                self.current_mission.params['on_complete']()

            self.current_mission = None
            self.total_dist_to_target = None
            self.speed = 0.0

            if self.mission_queue:
                self._start_next_mission()
            else:
                self.state = "IDLE"

    def _start_next_mission(self):
        mission = self.mission_queue.popleft()
        self.current_mission = mission
        self.wait_timer = 0.0

        if hasattr(self, '_action_performed'):
            del self._action_performed

        if mission.type == "MOVE":
            # Lazy Pathfinding
            logical_loc = self.get_logical_node()
            start_node = logical_loc if logical_loc is not None else self.mgr.segments[self.current_seg]['v']

            path = self.mgr.find_path(start_node, mission.target_id)

            if path is None:
                print(f"[{self.ui_id}] Error: No path to {mission.target_id}")
                self.state = "ERROR"
                return

            # Route Stitching (Swivel Logic)
            if path:
                next_seg_id = path[0]
                if self.current_seg == next_seg_id:
                    self.seg_queue = path[1:]
                else:
                    curr_u = self.mgr.segments[self.current_seg]['u']
                    next_u = self.mgr.segments[next_seg_id]['u']

                    if self.dist < TOLERANCE_NODE and curr_u == next_u:
                        print(f"[{self.ui_id}] Swiveling at Node {curr_u}")
                        self.current_seg = next_seg_id
                        self.seg_queue = path[1:]
                    else:
                        self.seg_queue = path
            else:
                self.seg_queue = []

            self._recalc_path_distance()
            self.state = "MOVING"
            self.target_name = f"Node_{mission.target_id}"

        elif mission.type == "ACTION":
            self.state = "ACTION"
            print(f"[{self.ui_id}] Starting Transfer...")

    def get_logical_node(self):
        """Resolves (seg, dist) to a Node ID if within tolerance."""
        if self.current_seg is None: return None
        seg = self.mgr.segments[self.current_seg]

        if self.dist < TOLERANCE_NODE: return seg['u']
        elif self.dist > (seg['calc_len'] - TOLERANCE_NODE): return seg['v']
        return None

    def _recalc_path_distance(self):
        rem_on_seg = self.mgr.segments[self.current_seg]['calc_len'] - self.dist
        rem_path = sum([self.mgr.segments[sid]['calc_len'] for sid in self.seg_queue])
        self.total_dist_to_target = rem_on_seg + rem_path

    def _update_navigation(self, dt):
        limit_dist, speed_cap = self.walker.get_constraints(self)
        target_v = self.brain.calculate_target_speed(limit_dist, speed_cap)

        # Dynamics
        if self.speed < target_v:
            self.speed = min(target_v, self.speed + OHT_SPECS['accel'] * dt)
        elif self.speed > target_v:
            self.speed = max(target_v, self.speed - OHT_SPECS['decel'] * dt)

        step = self.speed * dt
        self.dist += step
        if self.total_dist_to_target is not None:
            self.total_dist_to_target = max(0.0, self.total_dist_to_target - step)

        # Snap to arrival
        if (self.total_dist_to_target is not None and
            self.total_dist_to_target <= TOLERANCE_STOP and
            self.speed < 10.0):
            self.total_dist_to_target = 0.0
            self.speed = 0.0
            return

        # Segment Transition
        l = self.mgr.segments[self.current_seg]['calc_len']
        if self.dist >= l:
            if self.seg_queue:
                self.history.append(self.current_seg)
                if len(self.history) > 10: self.history.pop(0)
                self.dist -= l
                self.current_seg = self.seg_queue.pop(0)
                self._recalc_path_distance()
            else:
                self.dist = l
                self.total_dist_to_target = 0.0

    def _update_action(self, dt):
        self.wait_timer += dt
        # E84 Delay Simulation (2 seconds)
        if self.wait_timer < 2.0: return

        if not hasattr(self, '_action_performed'):
            self._perform_transfer_logic()
            self._action_performed = True

    def _perform_transfer_logic(self):
        node_id = self.get_logical_node()
        if node_id is None:
            print(f"[{self.ui_id}] Error: Transfer while in transit")
            self.state = "ERROR"
            return

        target_machine = self.mgr.get_machine_at(node_id)
        if not target_machine:
            print(f"[{self.ui_id}] Error: No machine at {node_id}")
            self.state = "ERROR"
            return

        m_params = self.current_mission.params
        m_type = self.current_mission.type
        port_indices = m_params.get('port_indices', [])
        if not isinstance(port_indices, list): port_indices = [port_indices]

        if m_type == "ACTION": # Logic for both PICKUP/DROPOFF encoded in params
            action_sub = m_params.get('type') # PICKUP or DROPOFF

            if action_sub == "PICKUP":
                for port_idx in port_indices:
                    free_slot = self._get_free_bay_slot()
                    if free_slot is None: break

                    cargo = target_machine.retrieve_cargo(port_idx)
                    if cargo:
                        self.cargo_bay[free_slot] = cargo
                        print(f"[{self.ui_id}] Loaded {cargo.id} -> Slot {free_slot}")

            elif action_sub == "DROPOFF":
                target_cids = m_params.get('cargo_ids', m_params.get('cargo_id'))
                if not isinstance(target_cids, list): target_cids = [target_cids]

                # SAFETY CHECK: Mismatched Arrays
                if len(target_cids) != len(port_indices):
                    print(f"[{self.ui_id}] Error: Cargo/Port count mismatch")
                    self.state = "ERROR"
                    return

                for cid, port_idx in zip(target_cids, port_indices):
                    slot, cargo = self._find_cargo_in_bay(cid)
                    if cargo:
                        if target_machine.receive_cargo(port_idx, cargo):
                            self.cargo_bay[slot] = None
                            print(f"[{self.ui_id}] Unloaded {cargo.id} -> Port {port_idx}")
                        else:
                            print(f"[{self.ui_id}] Dropoff Failed: Port {port_idx} busy")
                            self.state = "ERROR"
                            return

    def _get_free_bay_slot(self):
        for i in range(self.capacity):
            if self.cargo_bay[i] is None: return i
        return None

    def _find_cargo_in_bay(self, cid):
        for i, c in enumerate(self.cargo_bay):
            if c and c.id == cid: return i, c
        if cid is None: # Fallback: Return first cargo
             for i, c in enumerate(self.cargo_bay):
                if c: return i, c
        return None, None

    def _update_visuals(self):
        for k, off in OHT_SPECS['offsets'].items():
            pos, tan = self.walker.get_state_at_offset(self, off)
            self.sensor_visuals[k]['pos'] = pos
            self.sensor_visuals[k]['tan'] = tan

    def calc_dist_to_node(self, target_node: int) -> Optional[float]:
        """Calculates dist from NOSE to node. Used by Registry."""
        if self.current_seg is None: return None
        curr_seg = self.mgr.segments[self.current_seg]
        dist_on_curr = curr_seg['calc_len'] - self.dist

        if curr_seg['v'] == target_node: return dist_on_curr

        accum = dist_on_curr
        found = False
        for i, s_id in enumerate(self.seg_queue):
            if i >= 5: break
            s = self.mgr.segments[s_id]
            if s['v'] == target_node:
                accum += s['calc_len']
                found = True
                break
            accum += s['calc_len']
        return accum if found else None