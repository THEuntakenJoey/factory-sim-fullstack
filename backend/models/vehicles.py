from __future__ import annotations
import math
import numpy as np
from typing import Optional, List, Dict, Any, Callable
from .kinematics import solve_kinematic_motion, interpolate_motion

class OHTAgent:
    """
    DES-driven Overhead Hoist Transport (OHT) Agent with analytical kinematic interpolation.
    Operates via discrete block reservations, enforces stopping-distance lookaheads,
    and protects curve segments from halting.
    """
    def __init__(self, agent_id: str, map_mgr: Any, traffic_controller: Any):
        self.id = agent_id
        self.map_mgr = map_mgr
        self.traffic_ctrl = traffic_controller

        # Spatial position
        self.current_block: Optional[str] = None
        self.previous_block: Optional[str] = None
        self.current_node: Optional[int] = None
        self.speed = 0.0  # m/s
        self.wait_block_since: Optional[float] = None

        # State machine: "IDLE", "EN_ROUTE_PICKUP", "ACTION_PICKUP", "EN_ROUTE_DROPOFF", "ACTION_DROPOFF", "WAITING_BLOCK"
        self.state = "IDLE"
        self.cargo: Any = None  # Carrier object or None

        # Route & Mission
        self.route: List[str] = []
        self.target_node: Optional[int] = None
        self.current_mission: Optional[Dict[str, Any]] = None

        # Active DES motion profile
        # { start_time, end_time, duration, profile, block_id }
        self.active_motion: Optional[Dict[str, Any]] = None
        self.action_end_time: Optional[float] = 0.0

        # Metrics tracking
        self.idle_since = 0.0
        self.loaded_travel_time = 0.0
        self.empty_travel_time = 0.0
        self.waiting_traffic_time = 0.0
        self.action_time = 0.0
        self.idle_time = 0.0
        self.total_distance = 0.0

        # Cached visual position
        self.pos = np.array([0.0, 0.0, 0.0])
        self.heading = 0.0

    def get_current_node(self) -> int:
        if self.current_block:
            seg = self.map_mgr.segments.get(self.current_block)
            if seg:
                return seg['v']
        if self.current_node is not None:
            return self.current_node
        return 0

    def spawn(self, block_id: str, start_at_beginning: bool = False):
        """Initializes the OHT on a specific block."""
        self.current_block = block_id
        seg = self.map_mgr.segments[block_id]
        self.current_node = seg['v']
        self.speed = 0.0
        self.state = "IDLE"
        self.route = []
        self.active_motion = None
        
        # Lock this initial block
        self.traffic_ctrl.block_owners[block_id] = self.id
        
        # Set initial visual coordinates safely centered inside block
        L = seg['calc_len']
        dist = (L * 0.5) if not start_at_beginning else 0.0
        p, tan = self.map_mgr.get_state(block_id, dist)
        self.pos = p
        self.heading = math.atan2(tan[0], tan[1]) * 180.0 / math.pi


    def nudge_forward(self, sim_engine: Any, visited: Optional[Set[str]] = None) -> bool:
        """
        If idle and blocking another vehicle, advances to the next safe non-critical parking block.
        Cascades forward if candidate blocks are held by other idle vehicles.
        """
        if self.state not in ("IDLE",) or self.current_mission or not self.current_block:
            return False

        if visited is None:
            visited = set()
        if self.id in visited:
            return False
        visited.add(self.id)

        # BFS to find the closest sequence of blocks leading to a safe, non-critical parking block
        queue = [([cand], cand) for cand in self.map_mgr.get_next_segments(self.current_block)]
        while queue:
            route, last_b = queue.pop(0)
            if len(route) > 5:
                continue

            # Verify availability or nudge idle owners along the candidate route
            route_clear = True
            for b in route:
                if not self.traffic_ctrl.is_block_free(b, self.id, self.map_mgr):
                    owner_id = self.traffic_ctrl.block_owners.get(b)
                    if owner_id and owner_id != self.id:
                        agents_map = getattr(getattr(sim_engine, 'state', None), 'agents', {})
                        owner_agent = agents_map.get(owner_id)
                        if owner_agent and owner_agent.state == "IDLE" and not owner_agent.current_mission:
                            owner_agent.nudge_forward(sim_engine, visited)
                    if not self.traffic_ctrl.is_block_free(b, self.id, self.map_mgr):
                        route_clear = False
                        break

            if not route_clear:
                continue

            # If destination block is a safe non-critical parking block (>= 1.0m, not curve/switch)
            if not self.traffic_ctrl.is_critical_block(last_b, self.map_mgr) and self.map_mgr.get_block_length_m(last_b) >= 1.0:
                self.route = list(route)
                self.sim_engine = sim_engine
                self.state = "EN_ROUTE_IDLE"
                self._advance_next_block(sim_engine)
                return True

            for nxt in self.map_mgr.get_next_segments(last_b):
                if nxt not in route:
                    queue.append((route + [nxt], nxt))

        return False


    def assign_mission(
        self,
        mission_type: str,  # "PICKUP" or "DROPOFF"
        target_node: int,
        route: List[str],
        machine: Any,
        port_idx: int,
        carrier: Any = None,
        on_complete: Optional[Callable] = None,
        sim_engine: Any = None
    ):
        """Assigns a new transport task and starts moving."""
        self.sim_engine = sim_engine
        self.current_mission = {
            "type": mission_type,
            "target_node": target_node,
            "machine": machine,
            "port_idx": port_idx,
            "carrier": carrier,
            "on_complete": on_complete
        }
        self.target_node = target_node
        self.route = list(route)
        if self.route and self.route[0] == self.current_block:
            self.route.pop(0)
        self.state = "EN_ROUTE_PICKUP" if mission_type == "PICKUP" else "EN_ROUTE_DROPOFF"

        # Start advancing along the route
        self._advance_next_block(sim_engine)

    def _advance_next_block(self, sim_engine: Any):
        """Attempts to reserve and transition into the next block on the route."""
        if not sim_engine:
            return

        current_time = sim_engine.sim_time

        if not self.route:
            # Arrived at destination!
            self.speed = 0.0
            self._trigger_destination_action(sim_engine)
            return

        next_block = self.route[0]

        # 1. Request block reservation from traffic controller
        granted = self.traffic_ctrl.request_blocks_for_move(self, self.current_block, next_block, self.map_mgr)
        # print(f"[{self.id}] advance to {next_block}: granted={granted}, speed={self.speed}")

        if granted:
            self.wait_block_since = None
            # Advance route
            self.route.pop(0)
            if self.previous_block and self.previous_block != self.current_block:
                self.traffic_ctrl.release_block(self, self.previous_block)
            self.previous_block = self.current_block
            self.current_block = next_block

            # Determine target exit speed
            upcoming_block = self.route[0] if self.route else None
            vf = self.traffic_ctrl.get_exit_speed(self, next_block, upcoming_block, self.map_mgr)
            v_limit = self.map_mgr.get_block_speed_limit(next_block)
            dist_m = self.map_mgr.get_block_length_m(next_block)

            # Solve kinematic profile
            profile = solve_kinematic_motion(
                distance_m=dist_m,
                v0=self.speed,
                vf=vf,
                v_limit=v_limit,
                accel=1.5,
                decel=2.0
            )

            self.active_motion = {
                "start_time": current_time,
                "end_time": current_time + profile["duration"],
                "duration": profile["duration"],
                "profile": profile,
                "block_id": next_block
            }
            self.total_distance += dist_m

            # Schedule arrival event at end of this block
            self._motion_id = getattr(self, '_motion_id', 0) + 1
            m_id = self._motion_id
            sim_engine.schedule_event(
                profile["duration"],
                lambda mid=m_id: self._on_block_arrival(sim_engine, mid)
            )
        else:
            # Block is unreserved/busy; decelerate to stop at end of current block
            self.state = "WAITING_BLOCK"
            if self.wait_block_since is None:
                self.wait_block_since = current_time
            if self.speed > 0.001 and self.current_block:
                # Decel to 0
                dist_rem = self.map_mgr.get_block_length_m(self.current_block) * 0.5
                profile = solve_kinematic_motion(
                    distance_m=max(0.1, dist_rem),
                    v0=self.speed,
                    vf=0.0,
                    v_limit=self.speed,
                    accel=1.5,
                    decel=2.0
                )
                self.active_motion = {
                    "start_time": current_time,
                    "end_time": current_time + profile["duration"],
                    "duration": profile["duration"],
                    "profile": profile,
                    "block_id": self.current_block
                }
                self._motion_id = getattr(self, '_motion_id', 0) + 1
                m_id = self._motion_id
                sim_engine.schedule_event(
                    profile["duration"],
                    lambda mid=m_id: self._on_stopped_waiting(sim_engine, mid)
                )
            else:
                self.speed = 0.0
                self.active_motion = None
                if self.previous_block:
                    self.traffic_ctrl.release_block(self, self.previous_block)
                    self.previous_block = None
                if self.current_block:
                    L = self.map_mgr.get_block_length_m(self.current_block)
                    stop_dist = max(0.0, L - min(0.45, L * 0.5))
                    p, tan = self.map_mgr.get_state(self.current_block, stop_dist)
                    self.pos = p
                    self.heading = math.atan2(tan[0], tan[1]) * 180.0 / math.pi

    def _on_block_arrival(self, sim_engine: Any, motion_id: int):
        """Called by DES engine when vehicle reaches the end of current_block."""
        if motion_id != getattr(self, '_motion_id', 0):
            return  # Ignore stale event

        if self.active_motion:
            self.speed = self.active_motion["profile"]["vf"]

        # If at target destination node, perform action
        if self.current_block:
            seg = self.map_mgr.segments[self.current_block]
            self.current_node = seg['v']

        # Unconditionally release previous block upon arriving at end of current block
        if self.previous_block:
            self.traffic_ctrl.release_block(self, self.previous_block)
            self.previous_block = None

        if not self.route:
            self.speed = 0.0
            if self.current_mission:
                self._trigger_destination_action(sim_engine)
            else:
                self.state = "IDLE"
        else:
            # Keep rolling into next block
            self._advance_next_block(sim_engine)


    def _on_stopped_waiting(self, sim_engine: Any, motion_id: int):
        if motion_id != getattr(self, '_motion_id', 0):
            return  # Ignore stale event
        self.speed = 0.0
        self.active_motion = None
        self.state = "WAITING_BLOCK"
        if self.previous_block:
            self.traffic_ctrl.release_block(self, self.previous_block)
            self.previous_block = None
        if self.current_block:
            L = self.map_mgr.get_block_length_m(self.current_block)
            stop_dist = max(0.0, L - min(0.45, L * 0.5))
            p, tan = self.map_mgr.get_state(self.current_block, stop_dist)
            self.pos = p
            self.heading = math.atan2(tan[0], tan[1]) * 180.0 / math.pi

    def on_block_freed(self, block_id: str, sim_engine: Any = None):
        """Called by traffic controller when a block that this agent is waiting for becomes free."""
        eng = sim_engine or getattr(self, 'sim_engine', None)
        if self.state == "WAITING_BLOCK" and self.route:
            if block_id in self.route[:2]:
                if eng:
                    self._motion_id = getattr(self, '_motion_id', 0) + 1
                    self.state = "EN_ROUTE_PICKUP" if self.cargo is None else "EN_ROUTE_DROPOFF"
                    self._advance_next_block(eng)

    def _trigger_destination_action(self, sim_engine: Any):
        """Handles hoist PICKUP or DROPOFF at the target machine port."""
        if not self.current_mission:
            self.state = "IDLE"
            return

        m_type = self.current_mission["type"]
        machine = self.current_mission["machine"]
        port_idx = self.current_mission["port_idx"]
        on_complete = self.current_mission.get("on_complete")

        hoist_duration = 1.5  # 1.5 seconds for hoist down / lock / hoist up

        if m_type == "PICKUP":
            self.state = "ACTION_PICKUP"
            self.action_end_time = sim_engine.sim_time + hoist_duration

            def finish_pickup():
                self.cargo = machine.retrieve_cargo(port_idx)
                self.state = "IDLE"
                self.current_mission = None
                if on_complete:
                    on_complete(self)

            sim_engine.schedule_event(hoist_duration, finish_pickup)

        elif m_type == "DROPOFF":
            self.state = "ACTION_DROPOFF"
            self.action_end_time = sim_engine.sim_time + hoist_duration

            def finish_dropoff():
                if self.cargo:
                    machine.receive_cargo(port_idx, self.cargo)
                    self.cargo = None
                self.state = "IDLE"
                self.current_mission = None
                if on_complete:
                    on_complete(self)
                # Release lookahead reservations, keeping only current_block
                if hasattr(self.traffic_ctrl, 'release_unneeded_blocks'):
                    self.traffic_ctrl.release_unneeded_blocks(self, {self.current_block})
                # Immediately nudge forward away from dropoff port to prevent clogging
                self.nudge_forward(sim_engine)

            sim_engine.schedule_event(hoist_duration, finish_dropoff)

    def update_metrics(self, dt_sim: float, current_time: float):
        """Accumulates individual OHT state statistics."""
        if self.state == "IDLE":
            self.idle_time += dt_sim
        elif self.state in ("ACTION_PICKUP", "ACTION_DROPOFF"):
            self.action_time += dt_sim
        elif self.state == "WAITING_BLOCK":
            self.waiting_traffic_time += dt_sim
        elif self.state == "EN_ROUTE_PICKUP":
            self.empty_travel_time += dt_sim
        elif self.state == "EN_ROUTE_DROPOFF":
            self.loaded_travel_time += dt_sim

    def get_pos(self, current_time: Optional[float] = None) -> np.ndarray:
        """Returns the smooth interpolated continuous position at current_time."""
        if not self.active_motion or not self.current_block or current_time is None:
            return self.pos

        start_t = self.active_motion["start_time"]
        tau = current_time - start_t
        profile = self.active_motion["profile"]
        dist_m, vel_m_s = interpolate_motion(profile, tau)
        self.speed = vel_m_s

        p, tan = self.map_mgr.get_state(self.current_block, dist_m)
        self.pos = p
        self.heading = math.atan2(tan[0], tan[1]) * 180.0 / math.pi
        return self.pos