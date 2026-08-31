class GraphWalker:
    def __init__(self, mgr: MapManager, traffic_ctrl: TrafficRegistry):
        self.mgr = mgr
        self.traffic_ctrl = traffic_ctrl

    def get_constraints(self, agent: OHTAgent):
        """
        1. limit_dist: Distance CENTER can move before V=0.
        2. speed_cap: Max velocity allowed by zones.
        """
        specs = OHT_SPECS
        safe = specs['safety']
        limit_dist = agent.total_dist_to_target if agent.total_dist_to_target is not None else float('inf')
        speed_cap = specs['speed_max']

        # 1. SCAN RADII
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

            # --- A. ZONE LOGIC ---
            dist_nose_to_start = (-agent.dist if i == 0 else accum_dist) - specs['offsets']['Preceding']
            if dist_nose_to_start < scan_radius_zone:
                zone_type = seg.get('zone', 'normal')
                target_z_speed = specs['speed_max']
                if zone_type == 'slow': target_z_speed = specs['speed_curve']
                elif zone_type == 'crawl': target_z_speed = specs['speed_crawl']

                if target_z_speed < speed_cap:
                    if dist_nose_to_start <= 0: speed_cap = min(speed_cap, target_z_speed)
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

                    # Fix: Use physical offset instead of -1000
                    if rel_dist < specs['offsets']['Following']: continue

                    gap = rel_dist - specs['offsets']['Preceding'] + specs['offsets']['Following']
                    stop_point = gap - safe['gap_maintained']

                    if 0 < stop_point < scan_radius_obs:
                        if stop_point < limit_dist: limit_dist = stop_point
                    elif stop_point <= 0:
                        limit_dist = 0.0

            # --- C. MERGE LOGIC (Updated) ---
            target_node = seg['v']

            # Check if this node requires negotiation
            # (Assuming map_manager has pre-built caution zones correctly)
            if len(self.mgr.get_competing_segments(target_node)) > 1:

                dist_nose_to_merge = dist_to_seg_end - specs['offsets']['Preceding']

                if 0 <= dist_nose_to_merge < scan_radius_obs:
                    # Pass the distance we just calculated
                    if not self._check_merge_priority(agent, target_node, dist_nose_to_merge):

                        stop_pt = dist_nose_to_merge - safe['gap_yield']
                        if stop_pt < limit_dist: limit_dist = max(0.0, stop_pt)

            if i == 0: accum_dist += (seg_len - agent.dist)
            else: accum_dist += seg_len

        return max(0.0, limit_dist), speed_cap

    def _check_merge_priority(self, agent, merge_node, my_dist_to_merge):
        """
        Arbitrates priority using Pre-Calculated Distances from TrafficRegistry.
        """
        safe = OHT_SPECS['safety']

        # 1. GET COMPETITORS (List of Tuples)
        competitors = self.traffic_ctrl.get_zone_competitors(merge_node)

        for other_agent, other_dist in competitors:
            if other_agent == agent: continue

            # 2. PRIORITY CHECK (Using Snapshotted Distance)

            # Relevance Check
            if other_dist - my_dist_to_merge > safe['merge_relevance_dist']: continue

            delta = other_dist - my_dist_to_merge

            # Tie Breaker
            if abs(delta) < safe['merge_tie_epsilon']:
                if id(agent) < id(other_agent): return False # Yield
                else: continue # Win

            # Distance Check
            if other_dist < my_dist_to_merge:
                return False # Yield

        # 3. OUTGOING CLEARANCE (Anti-Gridlock)
        # This remains a direct check because it's spatial, not intent-based
        if hasattr(self.mgr, 'get_outgoing_segments'):
            outgoing = self.mgr.get_outgoing_segments(merge_node)
            for seg_id in outgoing:
                blockers = self.traffic_ctrl.get_agents_on_segment(seg_id)
                for other in blockers:
                    clearance = abs(OHT_SPECS['offsets']['Following']) + safe['gap_yield']
                    if other.dist < clearance:
                        return False

        return True