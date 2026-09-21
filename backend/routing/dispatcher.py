from __future__ import annotations
from typing import Dict, List, Optional, Any
from .interfaces import PathfindingStrategy, VehicleAssignmentStrategy, MachineAllocationStrategy
from .pathfinding import get_pathfinding_strategy
from .strategies import get_vehicle_assignment_strategy, get_machine_allocation_strategy

class Dispatcher:
    """
    Central Logistics Coordinator implementing the Closed-Loop Recipe Dispatcher
    with Downstream Reservation & Backpressure Flow Control.
    """
    def __init__(
        self,
        map_mgr: Any,
        traffic_controller: Any,
        pathfinding_strategy_name: str = "dijkstra",
        vehicle_assignment_strategy_name: str = "nearest",
        machine_allocation_strategy_name: str = "least_loaded"
    ):
        self.map_mgr = map_mgr
        self.traffic_ctrl = traffic_controller

        # Modular Strategies
        self.pathfinder: PathfindingStrategy = get_pathfinding_strategy(pathfinding_strategy_name)
        self.vehicle_selector: VehicleAssignmentStrategy = get_vehicle_assignment_strategy(vehicle_assignment_strategy_name)
        self.machine_selector: MachineAllocationStrategy = get_machine_allocation_strategy(machine_allocation_strategy_name)

        self.strategy_names = {
            "pathfinding": pathfinding_strategy_name,
            "vehicle_assignment": vehicle_assignment_strategy_name,
            "machine_allocation": machine_allocation_strategy_name
        }

        # Event-driven pending transport requests queue: list of dicts
        self.pending_requests: List[Dict[str, Any]] = []

    def set_strategies(
        self,
        pathfinding: Optional[str] = None,
        vehicle_assignment: Optional[str] = None,
        machine_allocation: Optional[str] = None
    ):
        if pathfinding:
            self.pathfinder = get_pathfinding_strategy(pathfinding)
            self.strategy_names["pathfinding"] = pathfinding
        if vehicle_assignment:
            self.vehicle_selector = get_vehicle_assignment_strategy(vehicle_assignment)
            self.strategy_names["vehicle_assignment"] = vehicle_assignment
        if machine_allocation:
            self.machine_selector = get_machine_allocation_strategy(machine_allocation)
            self.strategy_names["machine_allocation"] = machine_allocation

    def request_transport(self, src_machine: Any, port: Any, carrier: Any, sim_engine: Any):
        """Called by a machine when it finishes an item and requests transportation."""
        # Avoid duplicate requests for the same carrier
        for req in self.pending_requests:
            if req.get("carrier") == carrier:
                return

        req = {
            "source_machine": src_machine,
            "port": port,
            "carrier": carrier,
            "request_time": sim_engine.sim_time if sim_engine else 0.0
        }
        self.pending_requests.append(req)
        self.try_dispatch(sim_engine)

    def on_agent_idle(self, agent: Any, sim_engine: Any):
        """Called when an OHT enters IDLE state with no route or cargo."""
        self.try_dispatch(sim_engine)

    def on_machine_slot_freed(self, machine: Any, sim_engine: Any):
        """Called when a machine slot becomes free."""
        self.try_dispatch(sim_engine)


    def try_dispatch(self, sim_engine: Any):
        """Processes pending transport requests in FIFO order and matches with best idle OHT."""
        if not sim_engine or not hasattr(sim_engine, "state"):
            return

        state = sim_engine.state
        agents = state.agents
        machines = state.machines
        recipes = getattr(state, "recipes", {})
        analytics_tracker = getattr(state, "analytics", None)

        idle_agents = [a for a in agents.values() if a.state == "IDLE" and not a.route and not a.current_mission]
        if not idle_agents:
            return

        traffic_data = {
            "occupancy": {},
            "jam_time": getattr(analytics_tracker, "segment_jam_time", {}) if analytics_tracker else {}
        }
        for a in agents.values():
            if a.current_block:
                traffic_data["occupancy"][a.current_block] = traffic_data["occupancy"].get(a.current_block, 0) + 1

        i = 0
        while i < len(self.pending_requests) and idle_agents:
            req = self.pending_requests[i]
            src_m = req["source_machine"]
            carrier = req["carrier"]
            unload_port = req["port"]

            # Check if request is still valid
            if unload_port.carrier != carrier or carrier.state == "IN_TRANSIT":
                self.pending_requests.pop(i)
                continue

            if carrier.state == "RESERVED_FOR_PICKUP":
                i += 1
                continue

            # 1. Determine destination machine candidates
            next_schema_id = carrier.get_current_step_schema(recipes)
            dest_candidates = []

            if carrier.is_finished(recipes) or next_schema_id is None:
                dest_candidates = [m for m in machines.values() if m.machine_role == "sink" and m.get_available_load_port()]
            else:
                dest_candidates = [
                    m for m in machines.values()
                    if m.schema_id == next_schema_id and m.get_available_load_port()
                ]

            # 2. BACKPRESSURE CHECK: If no downstream machine has space, request remains queued & upstream machine stays halted
            if not dest_candidates:
                src_m.state = "PAUSED_BACKPRESSURE"
                i += 1
                continue

            # 3. Select target machine via MachineAllocationStrategy
            src_node = unload_port.node_idx
            target_machine = self.machine_selector.select_machine(dest_candidates, src_node, self.map_mgr)
            if not target_machine:
                i += 1
                continue

            # 4. Select best idle OHT via VehicleAssignmentStrategy
            agent = self.vehicle_selector.select_agent(idle_agents, src_node, self.map_mgr)
            if not agent:
                break

            # 5. LAZY RESERVATION: Atomically lock downstream port at dispatch time
            target_port = target_machine.reserve_load_port(agent.id)
            if not target_port:
                i += 1
                continue

            carrier.state = "RESERVED_FOR_PICKUP"
            dest_node = target_port.node_idx

            # 6. Compute Paths
            agent_node = agent.get_current_node()
            path_to_pickup = self.pathfinder.find_path(self.map_mgr, agent_node, src_node, traffic_data)
            path_to_dropoff = self.pathfinder.find_path(self.map_mgr, src_node, dest_node, traffic_data)

            if path_to_pickup is None or path_to_dropoff is None:
                # Route unavailable; release reservation and leave request queued
                target_port.state = "EMPTY"
                target_port.reserved_by = None
                target_machine.pending_deliveries = max(0, target_machine.pending_deliveries - 1)
                carrier.state = "STORED"
                i += 1
                continue

            # Successfully planned transfer! Remove request and agent
            self.pending_requests.pop(i)
            idle_agents.remove(agent)

            # 7. Handshake Mission Chain (Factory function prevents late-binding closure bug)
            def make_pickup_complete(d_node, d_mach, d_port_idx, c_obj, s_eng):
                def on_pickup_complete(ag):
                    curr_node = ag.get_current_node()
                    fresh_route = self.pathfinder.find_path(self.map_mgr, curr_node, d_node, traffic_data)
                    if not fresh_route:
                        fresh_route = self.pathfinder.find_path(self.map_mgr, curr_node, d_node)
                    ag.assign_mission(
                        mission_type="DROPOFF",
                        target_node=d_node,
                        route=fresh_route or [],
                        machine=d_mach,
                        port_idx=d_port_idx,
                        carrier=ag.cargo or c_obj,
                        on_complete=None,
                        sim_engine=s_eng
                    )
                return on_pickup_complete

            agent.assign_mission(
                mission_type="PICKUP",
                target_node=src_node,
                route=path_to_pickup,
                machine=src_m,
                port_idx=unload_port.index,
                carrier=carrier,
                on_complete=make_pickup_complete(dest_node, target_machine, target_port.index, carrier, sim_engine),
                sim_engine=sim_engine
            )

    def spin(
        self,
        agents: Dict[str, Any],
        machines: Dict[str, Any],
        recipes: Dict[str, Any],
        sim_engine: Any,
        analytics_tracker: Any = None
    ):
        """Watchdog / fallback periodic sweep to resolve deadlocks and sync requests."""
        current_time = sim_engine.sim_time

        # 0. Watchdog: recover from deadlocked pickup missions
        for a in agents.values():
            if a.state == "WAITING_BLOCK" and a.current_mission and a.current_mission.get("type") == "PICKUP":
                wait_since = getattr(a, 'wait_block_since', None)
                if wait_since is not None and (current_time - wait_since) > 15.0:
                    mission = a.current_mission
                    carrier = mission.get("carrier")
                    if carrier:
                        carrier.state = "STORED"
                    a.current_mission = None
                    a.route = []
                    a.state = "IDLE"
                    a.wait_block_since = None
                    if hasattr(self.traffic_ctrl, 'release_unneeded_blocks'):
                        self.traffic_ctrl.release_unneeded_blocks(a, {a.current_block})
                    for m in machines.values():
                        for p in m.ports:
                            if p.reserved_by == a.id:
                                p.reserved_by = None
                                if p.state == "RESERVED":
                                    p.state = "EMPTY"
                                    m.pending_deliveries = max(0, m.pending_deliveries - 1)

        # Fallback sync: enqueue any unreserved unloads
        for src_m in machines.values():
            unload_port = src_m.get_ready_unload_port()
            if unload_port and unload_port.carrier and unload_port.carrier.state not in ("RESERVED_FOR_PICKUP", "IN_TRANSIT"):
                carrier = unload_port.carrier
                if not any(req.get("carrier") == carrier for req in self.pending_requests):
                    self.pending_requests.append({
                        "source_machine": src_m,
                        "port": unload_port,
                        "carrier": carrier,
                        "request_time": current_time
                    })

        self.try_dispatch(sim_engine)


