from __future__ import annotations
from typing import TYPE_CHECKING, List, Dict, Tuple, Optional

import numpy as np

if TYPE_CHECKING:
    from agent import OHTAgent

class TrafficRegistry:
    """
    A lightweight spatial hash map to allow O(1) lookups of who is on a track.
    Refreshed every frame to ensure up-to-date collision detection.
    """
    def __init__(self):
        # Spatial Hash: Segment -> [Agents]
        self.registry: Dict[int, List['OHTAgent']] = {}
       
        # Intent Hash: MergeNode -> [(Agent, Snapshot_Distance), ...]
        self.zone_registry: Dict[int, List[Tuple['OHTAgent', float]]] = {}

    def clear(self):
        """Call this at the start of every simulation frame."""
        self.registry = {}
        self.zone_registry = {}

    def register_agent(self, agent: OHTAgent):
        """
        Registers an agent for both Spatial Awareness (Obstacles)
        and Intent Awareness (Merges).
        Should be called by the Simulation Loop, not the Agent itself.
        """
        if agent.current_seg is None: return

        # 1. Spatial Registration (Existing)
        if agent.current_seg not in self.registry:
            self.registry[agent.current_seg] = []
        self.registry[agent.current_seg].append(agent)
       
        # 2. Intent Registration
        # Identify which Merge Zones this agent is currently influencing
        zones = agent.mgr.get_zones_for_segment(agent.current_seg)
       
        for merge_node in zones:
            # CALCULATE DISTANCE ONCE HERE
            # This captures the agent's exact state at the start of the frame.
            dist_to_node = agent.calc_dist_to_node(merge_node)
           
            # If the agent actually has a path to this node:
            if dist_to_node is not None:
                if merge_node not in self.zone_registry:
                    self.zone_registry[merge_node] = []
               
                # Store tuple: (Agent, Snapshot_Distance)
                self.zone_registry[merge_node].append((agent, dist_to_node))

    def get_agents_on_segment(self, seg_id: int) -> List['OHTAgent']:
        """
        Returns list of agents currently occupying the given segment.
        Returns empty list if segment is clear.
        """
        return self.registry.get(seg_id, [])
   
    def get_zone_competitors(self, merge_node_id: int) -> List[Tuple['OHTAgent', float]]:
        """
        Returns list of (Agent, Distance) tuples for a specific merge node.
        Used for O(1) priority arbitration.
        """
        return self.zone_registry.get(merge_node_id, [])

    def check_collisions(self, agents: List['OHTAgent']) -> List[Tuple['OHTAgent', 'OHTAgent']]:
        """
        Brute-force O(N^2) check for physical overlaps.
        Returns list of colliding pairs.
        """
        collisions = []
       
        # Threshold Logic:
        # Car Length ~1200mm. Center-to-Center contact is ~1200mm.
        # We set threshold to 1000mm to catch any significant overlap.
        crash_threshold = 500.0
       
        for i in range(len(agents)):
            for j in range(i + 1, len(agents)):
                a = agents[i]
                b = agents[j]
               
                # Simple Dist Check (Visual Center)
                p1 = a.sensor_visuals['Center']['pos']
                p2 = b.sensor_visuals['Center']['pos']
                dist = np.linalg.norm(p1 - p2)
               
                if dist < crash_threshold:
                    collisions.append((a, b))
                    print(f"(!) CRASH DETECTED: {getattr(a, 'ui_id', 'A')} <-> {getattr(b, 'ui_id', 'B')} (Dist: {dist:.1f})")
                   
                    # Force Stop (Simulation Referee)
                    a.state = "ERROR"; a.speed = 0
                    b.state = "ERROR"; b.speed = 0
                   
        return collisions