from typing import Any, Optional, Set
from .interfaces import IdleVehicleStrategy

class StayAndNudgeStrategy(IdleVehicleStrategy):
    """
    Idle OHTs park in place at their last dropoff station.
    If an approaching moving vehicle requests the block, the idle vehicle
    nudges forward to the nearest safe, non-critical parking block (>= 1.2m).
    """
    def on_idle(self, agent: Any, sim_engine: Any) -> bool:
        agent.state = "IDLE"
        agent.route = []
        agent.active_motion = None
        return True

    def on_nudge_requested(self, agent: Any, requesting_agent: Any, sim_engine: Any, visited: Optional[Set[str]] = None) -> bool:
        if agent.state not in ("IDLE", "EN_ROUTE_IDLE") or agent.current_mission or not agent.current_block:
            return False

        if visited is None:
            visited = set()
        if agent.id in visited:
            return False
        visited.add(agent.id)

        map_mgr = agent.map_mgr
        traffic_ctrl = agent.traffic_ctrl

        # BFS to find the closest safe non-critical parking block
        queue = [([cand], cand) for cand in map_mgr.get_next_segments(agent.current_block)]
        min_park_len = getattr(map_mgr, 'min_section_len', 1.2)

        while queue:
            route, last_b = queue.pop(0)
            if len(route) > 6:
                continue

            route_clear = True
            for b in route:
                if not traffic_ctrl.is_block_free(b, agent.id, map_mgr):
                    owner_id = traffic_ctrl.block_owners.get(b)
                    if owner_id and owner_id != agent.id:
                        agents_map = getattr(getattr(sim_engine, 'state', None), 'agents', {})
                        owner_agent = agents_map.get(owner_id)
                        if owner_agent and owner_agent.state in ("IDLE", "EN_ROUTE_IDLE") and not owner_agent.current_mission:
                            if hasattr(traffic_ctrl, 'idle_strategy'):
                                traffic_ctrl.idle_strategy.on_nudge_requested(owner_agent, agent, sim_engine, visited)
                    if not traffic_ctrl.is_block_free(b, agent.id, map_mgr):
                        route_clear = False
                        break

            if not route_clear:
                continue

            # Safe destination check
            if not traffic_ctrl.is_critical_block(last_b, map_mgr) and map_mgr.get_block_length_m(last_b) >= min_park_len:
                agent.route = list(route)
                agent.sim_engine = sim_engine
                agent.state = "EN_ROUTE_IDLE"
                agent._advance_next_block(sim_engine)
                return True

            for nxt in map_mgr.get_next_segments(last_b):
                if nxt not in route:
                    queue.append((route + [nxt], nxt))

        return False


class CruisingStrategy(IdleVehicleStrategy):
    """
    Idle OHTs do not park on the tracks.
    They continuously cruise along available loops/main tracks to maintain
    fluid traffic circulation and reduce pickup dispatch latency.
    """
    def on_idle(self, agent: Any, sim_engine: Any) -> bool:
        if agent.current_mission or agent.cargo is not None:
            return False

        map_mgr = agent.map_mgr
        curr_b = agent.current_block
        if not curr_b:
            return False

        nxts = map_mgr.get_next_segments(curr_b)
        if not nxts:
            return False

        # Plan a forward cruising sequence (up to 3 segments ahead)
        cruise_route = [nxts[0]]
        for _ in range(2):
            last_seg = cruise_route[-1]
            more = map_mgr.get_next_segments(last_seg)
            if more:
                cruise_route.append(more[0])
            else:
                break

        agent.route = cruise_route
        agent.sim_engine = sim_engine
        agent.state = "EN_ROUTE_IDLE"
        agent._advance_next_block(sim_engine)
        return True

    def on_nudge_requested(self, agent: Any, requesting_agent: Any, sim_engine: Any, visited: Optional[Set[str]] = None) -> bool:
        return self.on_idle(agent, sim_engine)
