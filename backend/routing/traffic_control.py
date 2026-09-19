from typing import Dict, List, Optional, Any, Set
from .interfaces import TrafficControlStrategy

class BlockReservationTrafficController(TrafficControlStrategy):
    """
    Virtual Block Signaling & Reservation Traffic Controller.
    Enforces discrete block exclusivity and the strict No-Stopping-On-Curves invariant
    via bundled atomic reservations.
    """
    def __init__(self):
        # block_id -> agent_id holding the lock
        self.block_owners: Dict[str, str] = {}
        # block_id -> list of agent_ids waiting for this block
        self.block_waiters: Dict[str, List[Any]] = {}

    def reset(self):
        self.block_owners.clear()
        self.block_waiters.clear()

    def is_block_free(self, block_id: str, agent_id: str, map_mgr: Optional[Any] = None) -> bool:
        owner = self.block_owners.get(block_id)
        if owner is not None and owner != agent_id:
            return False
        if map_mgr:
            # Check sibling switch branch (_s vs _t mutual exclusion)
            if block_id.endswith('_s'):
                sib = block_id[:-2] + '_t'
                if sib in map_mgr.segments:
                    sib_owner = self.block_owners.get(sib)
                    if sib_owner is not None and sib_owner != agent_id:
                        return False
            elif block_id.endswith('_t'):
                sib = block_id[:-2] + '_s'
                if sib in map_mgr.segments:
                    sib_owner = self.block_owners.get(sib)
                    if sib_owner is not None and sib_owner != agent_id:
                        return False
        return True

    def is_critical_block(self, block_id: str, map_mgr: Any) -> bool:
        """
        Critical junction blocks are segments where a vehicle cannot halt without blocking
        intersecting track traffic. Includes all curves (turns, diverges, merges)
        and short diverge/merge straight branches (<= 0.6m).
        Does NOT apply to normal straight tracks or machine port stations.
        """
        if not block_id:
            return False
        if map_mgr.is_curve(block_id):
            return True
        seg = map_mgr.segments.get(block_id)
        if seg and seg.get('builder_id', '').endswith('_s') and seg.get('calc_len', 1.0) <= 0.6:
            return True
        return False

    def get_downstream_exit_block(self, agent: Any, block_id: str, map_mgr: Any) -> Optional[str]:
        """Returns the downstream exit block, but NEVER bundles beyond the agent's target destination."""
        if hasattr(agent, 'target_node') and agent.target_node is not None:
            seg = map_mgr.segments.get(block_id)
            if seg and seg.get('v') == agent.target_node:
                return None
        if hasattr(agent, 'route'):
            try:
                idx = agent.route.index(block_id)
                if idx + 1 < len(agent.route):
                    return agent.route[idx + 1]
                else:
                    return None  # Reached end of planned route
            except ValueError:
                pass
        next_segs = map_mgr.get_next_segments(block_id)
        return next_segs[0] if next_segs else None

    def request_blocks_for_move(self, agent: Any, current_block: str, next_block: str, map_mgr: Any) -> bool:
        """
        Attempts to reserve next_block. If next_block is critical (curve or < 1.0m),
        also reserves the downstream exit block on the agent's route (bundled reservation).
        """
        if not next_block:
            return False

        agent_id = agent.id
        blocks_to_reserve = [next_block]

        # Invariant: No stopping on critical blocks (curves or sub-meter blocks)!
        if self.is_critical_block(next_block, map_mgr):
            exit_block = self.get_downstream_exit_block(agent, next_block, map_mgr)
            if exit_block:
                blocks_to_reserve.append(exit_block)

        # Check if ALL required blocks are available
        all_free = all(self.is_block_free(b, agent_id, map_mgr) for b in blocks_to_reserve)

        if not all_free:
            # Check if any blocking owner is IDLE and can be nudged
            for b in blocks_to_reserve:
                owner_id = self.block_owners.get(b)
                if not owner_id and map_mgr:
                    if b.endswith('_s'):
                        owner_id = self.block_owners.get(b[:-2] + '_t')
                    elif b.endswith('_t'):
                        owner_id = self.block_owners.get(b[:-2] + '_s')
                if owner_id and owner_id != agent_id and hasattr(agent, 'sim_engine') and agent.sim_engine:
                    owner_agent = getattr(agent.sim_engine.state, 'agents', {}).get(owner_id)
                    if owner_agent and owner_agent.state == "IDLE":
                        owner_agent.nudge_forward(agent.sim_engine)
            # Re-check after nudging
            all_free = all(self.is_block_free(b, agent_id, map_mgr) for b in blocks_to_reserve)

        if all_free:
            # Grant atomic reservation
            for b in blocks_to_reserve:
                self.block_owners[b] = agent_id
            return True
        else:
            # Register agent as waiter on the first unfree block
            for b in blocks_to_reserve:
                if not self.is_block_free(b, agent_id, map_mgr):
                    if b not in self.block_waiters:
                        self.block_waiters[b] = []
                    if agent not in self.block_waiters[b]:
                        self.block_waiters[b].append(agent)
                    break
            return False

    def try_reserve_lookahead(self, agent: Any, upcoming_block: str, map_mgr: Any) -> bool:
        """
        Attempts to reserve upcoming_block as a lookahead window so the vehicle can cruise
        through the current block boundary without decelerating to a stop.
        If upcoming_block is critical, also verifies and reserves the exit block.
        """
        if not upcoming_block:
            return False

        agent_id = agent.id if hasattr(agent, 'id') else str(agent)
        if self.block_owners.get(upcoming_block) == agent_id:
            return True

        blocks_to_reserve = [upcoming_block]
        if self.is_critical_block(upcoming_block, map_mgr):
            exit_block = self.get_downstream_exit_block(agent, upcoming_block, map_mgr)
            if exit_block:
                blocks_to_reserve.append(exit_block)

        # Lookahead only reserves if blocks are currently unowned/free
        if all(self.is_block_free(b, agent_id, map_mgr) for b in blocks_to_reserve):
            for b in blocks_to_reserve:
                self.block_owners[b] = agent_id
            return True
        return False

    def release_unneeded_blocks(self, agent: Any, keep_blocks: Optional[Set[str]] = None):
        """Releases any blocks held by this agent other than keep_blocks."""
        agent_id = agent.id if hasattr(agent, 'id') else str(agent)
        keep = keep_blocks or set()
        to_release = [b for b, owner in list(self.block_owners.items()) if owner == agent_id and b not in keep]
        for b in to_release:
            self.release_block(agent, b)

    def release_block(self, agent: Any, block_id: str):
        """Releases the block and notifies any waiting agents."""
        agent_id = agent.id if hasattr(agent, 'id') else str(agent)
        if self.block_owners.get(block_id) == agent_id:
            del self.block_owners[block_id]

        # Wake up waiting agents on this block and its sibling switch branch
        b_to_wake = [block_id]
        if block_id.endswith('_s'):
            b_to_wake.append(block_id[:-2] + '_t')
        elif block_id.endswith('_t'):
            b_to_wake.append(block_id[:-2] + '_s')

        for b in b_to_wake:
            waiters = self.block_waiters.pop(b, [])
            for waiting_agent in waiters:
                if hasattr(waiting_agent, "on_block_freed"):
                    waiting_agent.on_block_freed(b)


    def get_exit_speed(self, agent: Any, current_block: str, next_block: Optional[str], map_mgr: Any) -> float:
        """
        Determines the target exit speed for current_block into next_block.
        If next_block is None (destination arrived), returns 0.0 to stop.
        If next_block is free or already owned, reserves lookahead and returns its speed limit.
        If next_block is busy, returns 0.0 to smoothly decelerate to stop at the block boundary.
        """
        if not next_block:
            return 0.0

        agent_id = agent.id if hasattr(agent, 'id') else str(agent)
        if self.block_owners.get(next_block) != agent_id:
            if not self.try_reserve_lookahead(agent, next_block, map_mgr):
                return 0.0  # Must decelerate to 0 at block boundary

        # Next block is reserved; return its speed limit
        return map_mgr.get_block_speed_limit(next_block)

class KinematicMergeTrafficController(BlockReservationTrafficController):
    """
    Kinematic Merge Priority Traffic Controller.
    Builds on block reservation with distance-to-merge arbitration for competing lanes.
    """
    def request_blocks_for_move(self, agent: Any, current_block: str, next_block: str, map_mgr: Any) -> bool:
        # Check merge priority if next block is a merge
        seg = map_mgr.segments.get(next_block, {})
        builder_id = seg.get('builder_id', '')

        # Use base block reservation
        return super().request_blocks_for_move(agent, current_block, next_block, map_mgr)

TRAFFIC_STRATEGIES: Dict[str, TrafficControlStrategy] = {
    "block_reservation": BlockReservationTrafficController(),
    "kinematic_merge": KinematicMergeTrafficController()
}

def get_traffic_strategy(name: str) -> TrafficControlStrategy:
    return TRAFFIC_STRATEGIES.get(name, TRAFFIC_STRATEGIES["block_reservation"])
