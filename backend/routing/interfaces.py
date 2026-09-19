from abc import ABC, abstractmethod
from typing import List, Optional, Any, Dict

class PathfindingStrategy(ABC):
    """Abstract base class for pathfinding algorithms (Dijkstra, Congestion-Aware, etc.)."""
    @abstractmethod
    def find_path(self, map_mgr: Any, start_node: int, end_node: int, traffic_data: Optional[Dict[str, Any]] = None) -> Optional[List[str]]:
        """Returns a list of segment/block IDs from start_node to end_node, or None if unreachable."""
        pass

class TrafficControlStrategy(ABC):
    """Abstract base class for traffic coordination and reservation management."""
    @abstractmethod
    def request_blocks_for_move(self, agent: Any, current_block: str, next_block: str, map_mgr: Any) -> bool:
        """
        Attempts to reserve the required block(s) ahead.
        For curves, this enforces the bundled reservation of (CurveBlock + NextStraightBlock).
        Returns True if reservation is granted, False otherwise.
        """
        pass

    @abstractmethod
    def release_block(self, agent: Any, block_id: str):
        """Releases reservation on a block when vehicle clears it, waking up any waiting agents."""
        pass

    @abstractmethod
    def get_exit_speed(self, agent: Any, current_block: str, next_block: Optional[str], map_mgr: Any) -> float:
        """Determines the target exit speed (m/s) for the current block (0.0 if next is unreserved/stop)."""
        pass

    @abstractmethod
    def reset(self):
        """Clears all locks and reservations."""
        pass

class VehicleAssignmentStrategy(ABC):
    """Abstract base class for dispatching an idle OHT to a transport request."""
    @abstractmethod
    def select_agent(self, available_agents: List[Any], pickup_node: int, map_mgr: Any) -> Optional[Any]:
        """Selects the best idle OHT for a pickup mission."""
        pass

class MachineAllocationStrategy(ABC):
    """Abstract base class for selecting which machine should process the next recipe step."""
    @abstractmethod
    def select_machine(self, candidate_machines: List[Any], pickup_node: int, map_mgr: Any) -> Optional[Any]:
        """Selects the target machine among matching candidates with available capacity/ports."""
        pass
