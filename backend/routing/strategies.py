from typing import List, Optional, Any, Dict
from .interfaces import VehicleAssignmentStrategy, MachineAllocationStrategy

class NearestIdleVehicleAssignment(VehicleAssignmentStrategy):
    """Assigns the idle vehicle with the shortest physical track distance to the pickup node."""
    def select_agent(self, available_agents: List[Any], pickup_node: int, map_mgr: Any) -> Optional[Any]:
        if not available_agents:
            return None

        best_agent = None
        min_dist = float('inf')

        for agent in available_agents:
            agent_node = agent.get_current_node()
            if agent_node == pickup_node:
                return agent
            path = map_mgr.find_path(agent_node, pickup_node)
            if path is not None:
                dist = sum(map_mgr.segments[sid]['calc_len'] for sid in path)
                if dist < min_dist:
                    min_dist = dist
                    best_agent = agent

        return best_agent or available_agents[0]

class FIFOVehicleAssignment(VehicleAssignmentStrategy):
    """Assigns the vehicle that has been idle for the longest duration (First-In, First-Out)."""
    def select_agent(self, available_agents: List[Any], pickup_node: int, map_mgr: Any) -> Optional[Any]:
        if not available_agents:
            return None
        # Sort by idle_since timestamp ascending
        return min(available_agents, key=lambda a: getattr(a, 'idle_since', 0.0))

class LeastLoadedMachineAllocation(MachineAllocationStrategy):
    """Picks the machine with the smallest total workload (intake buffer + in-process + pending incoming)."""
    def select_machine(self, candidate_machines: List[Any], pickup_node: int, map_mgr: Any) -> Optional[Any]:
        if not candidate_machines:
            return None

        # Calculate load for each candidate
        def calc_load(m):
            intake = len(getattr(m, 'intake_buffer', []))
            proc = len(getattr(m, 'processing', []))
            pending = getattr(m, 'pending_deliveries', 0)
            return intake + proc + pending

        min_load = min(calc_load(m) for m in candidate_machines)
        best_candidates = [m for m in candidate_machines if calc_load(m) == min_load]

        if len(best_candidates) == 1:
            return best_candidates[0]

        # Break ties with shortest distance to machine's LOAD port node
        best_m = None
        min_dist = float('inf')
        for m in best_candidates:
            load_node = m.get_load_node()
            if load_node is not None:
                path = map_mgr.find_path(pickup_node, load_node)
                dist = sum(map_mgr.segments[sid]['calc_len'] for sid in path) if path is not None else float('inf')
                if dist < min_dist:
                    min_dist = dist
                    best_m = m

        return best_m or best_candidates[0]

class ClosestMachineAllocation(MachineAllocationStrategy):
    """Picks the machine with the shortest track distance from the upstream pickup point."""
    def select_machine(self, candidate_machines: List[Any], pickup_node: int, map_mgr: Any) -> Optional[Any]:
        if not candidate_machines:
            return None

        best_m = None
        min_dist = float('inf')

        for m in candidate_machines:
            load_node = m.get_load_node()
            if load_node is not None:
                path = map_mgr.find_path(pickup_node, load_node)
                dist = sum(map_mgr.segments[sid]['calc_len'] for sid in path) if path is not None else float('inf')
                if dist < min_dist:
                    min_dist = dist
                    best_m = m

        return best_m or candidate_machines[0]

class RoundRobinMachineAllocation(MachineAllocationStrategy):
    """Cycles through candidate machines in round-robin sequence."""
    def __init__(self):
        self._indices: Dict[str, int] = {}

    def select_machine(self, candidate_machines: List[Any], pickup_node: int, map_mgr: Any) -> Optional[Any]:
        if not candidate_machines:
            return None
        key = candidate_machines[0].type
        idx = self._indices.get(key, 0)
        selected = candidate_machines[idx % len(candidate_machines)]
        self._indices[key] = (idx + 1) % len(candidate_machines)
        return selected

# Registries
VEHICLE_ASSIGNMENT_STRATEGIES: Dict[str, VehicleAssignmentStrategy] = {
    "nearest": NearestIdleVehicleAssignment(),
    "fifo": FIFOVehicleAssignment()
}

MACHINE_ALLOCATION_STRATEGIES: Dict[str, MachineAllocationStrategy] = {
    "least_loaded": LeastLoadedMachineAllocation(),
    "closest": ClosestMachineAllocation(),
    "round_robin": RoundRobinMachineAllocation()
}

def get_vehicle_assignment_strategy(name: str) -> VehicleAssignmentStrategy:
    return VEHICLE_ASSIGNMENT_STRATEGIES.get(name, VEHICLE_ASSIGNMENT_STRATEGIES["nearest"])

def get_machine_allocation_strategy(name: str) -> MachineAllocationStrategy:
    return MACHINE_ALLOCATION_STRATEGIES.get(name, MACHINE_ALLOCATION_STRATEGIES["least_loaded"])
