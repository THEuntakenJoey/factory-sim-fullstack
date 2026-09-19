import heapq
from typing import List, Optional, Dict, Any
from .interfaces import PathfindingStrategy

class DijkstraPathfinder(PathfindingStrategy):
    """Computes shortest physical distance paths on the track graph."""
    def find_path(self, map_mgr: Any, start_node: int, end_node: int, traffic_data: Optional[Dict[str, Any]] = None) -> Optional[List[str]]:
        if start_node == end_node:
            return []
        
        q = [(0.0, start_node, [])]
        visited = set()

        while q:
            cost, curr, path = heapq.heappop(q)
            if curr in visited:
                continue
            visited.add(curr)

            if curr == end_node:
                return path

            for neighbor, seg_id, weight in map_mgr.graph.get(curr, []):
                if neighbor not in visited:
                    heapq.heappush(q, (cost + weight, neighbor, path + [seg_id]))
        return None

class CongestionAwarePathfinder(PathfindingStrategy):
    """
    Computes dynamic shortest paths, penalizing segments with active traffic,
    slow-moving vehicles, or recent traffic jam history.
    """
    def find_path(self, map_mgr: Any, start_node: int, end_node: int, traffic_data: Optional[Dict[str, Any]] = None) -> Optional[List[str]]:
        if start_node == end_node:
            return []

        # traffic_data format:
        # {
        #    "occupancy": { seg_id: count },
        #    "jam_time": { seg_id: seconds }
        # }
        occupancy = (traffic_data or {}).get("occupancy", {})
        jam_time = (traffic_data or {}).get("jam_time", {})

        q = [(0.0, start_node, [])]
        visited = set()

        while q:
            cost, curr, path = heapq.heappop(q)
            if curr in visited:
                continue
            visited.add(curr)

            if curr == end_node:
                return path

            for neighbor, seg_id, weight in map_mgr.graph.get(curr, []):
                if neighbor not in visited:
                    # Dynamic cost formula:
                    # Base distance + 4.0m penalty per active vehicle + 0.2m penalty per accumulated jam second
                    occ_penalty = occupancy.get(seg_id, 0) * 4.0
                    jam_penalty = min(20.0, jam_time.get(seg_id, 0.0) * 0.2)
                    edge_cost = weight + occ_penalty + jam_penalty

                    heapq.heappush(q, (cost + edge_cost, neighbor, path + [seg_id]))
        return None

# Global Strategy Registry
PATHFINDING_STRATEGIES: Dict[str, PathfindingStrategy] = {
    "dijkstra": DijkstraPathfinder(),
    "congestion_aware": CongestionAwarePathfinder()
}

def get_pathfinding_strategy(name: str) -> PathfindingStrategy:
    return PATHFINDING_STRATEGIES.get(name, PATHFINDING_STRATEGIES["dijkstra"])