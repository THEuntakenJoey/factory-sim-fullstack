import io
import csv
from typing import Dict, List, Any, Optional

class AnalyticsTracker:
    """
    Collects detailed operational metrics:
    - Factory throughput & rate
    - Carrier wait & cycle times
    - Machine utilization, starvation, blocking
    - OHT fleet utilization breakdown
    - Track segment usage frequency & traffic jam hot spots
    """
    def __init__(self):
        self.start_time = 0.0
        self.throughput_count = 0
        self.completed_wait_times: List[float] = []
        self.segment_traversals: Dict[str, int] = {}
        self.segment_jam_time: Dict[str, float] = {}
        # Event tracking for blocks
        self.segment_occupied_time: Dict[str, float] = {}
        self.segment_occupied_since: Dict[str, float] = {}
        self.segment_waiting_since: Dict[str, Dict[str, float]] = {}

    def reset(self):
        self.start_time = 0.0
        self.throughput_count = 0
        self.completed_wait_times.clear()
        self.segment_traversals.clear()
        self.segment_jam_time.clear()
        self.segment_occupied_time.clear()
        self.segment_occupied_since.clear()
        self.segment_waiting_since.clear()

    def record_job_completion(self, wait_time: float, carrier_id: str = ""):
        self.throughput_count += 1
        self.completed_wait_times.append(max(0.0, wait_time))

    def record_segment_entry(self, seg_id: str, current_time: float = 0.0, agent_id: str = ""):
        if not seg_id:
            return
        self.segment_traversals[seg_id] = self.segment_traversals.get(seg_id, 0) + 1
        self.segment_occupied_since[seg_id] = current_time

    def record_segment_exit(self, seg_id: str, current_time: float = 0.0, agent_id: str = ""):
        if not seg_id:
            return
        if seg_id in self.segment_occupied_since:
            start_t = self.segment_occupied_since.pop(seg_id)
            self.segment_occupied_time[seg_id] = self.segment_occupied_time.get(seg_id, 0.0) + max(0.0, current_time - start_t)

    def record_segment_wait_start(self, seg_id: str, current_time: float = 0.0, agent_id: str = ""):
        if not seg_id or not agent_id:
            return
        if seg_id not in self.segment_waiting_since:
            self.segment_waiting_since[seg_id] = {}
        self.segment_waiting_since[seg_id][agent_id] = current_time

    def record_segment_wait_end(self, seg_id: str, current_time: float = 0.0, agent_id: str = ""):
        if not seg_id or not agent_id:
            return
        if seg_id in self.segment_waiting_since and agent_id in self.segment_waiting_since[seg_id]:
            w_start = self.segment_waiting_since[seg_id].pop(agent_id)
            dt = max(0.0, current_time - w_start)
            self.segment_jam_time[seg_id] = self.segment_jam_time.get(seg_id, 0.0) + dt

    def record_segment_jam(self, seg_id: str, dt: float):
        """Fallback integration hook."""
        self.segment_jam_time[seg_id] = self.segment_jam_time.get(seg_id, 0.0) + dt

    def get_summary(self, sim_time: float, machines: Dict[str, Any], agents: Dict[str, Any]) -> Dict[str, Any]:
        total_time = max(0.1, sim_time)
        avg_wait = sum(self.completed_wait_times) / len(self.completed_wait_times) if self.completed_wait_times else 0.0
        throughput_rate_hr = (self.throughput_count / total_time) * 3600.0

        # Machine statistics (Event-driven duration queries)
        machine_stats = []
        for m in machines.values():
            active_t = m.get_state_duration("PROCESSING", sim_time) if hasattr(m, "get_state_duration") else getattr(m, "active_processing_time", 0.0)
            blocked_t = m.get_state_duration("PAUSED_BACKPRESSURE", sim_time) if hasattr(m, "get_state_duration") else getattr(m, "blocked_time", 0.0)
            starved_t = m.get_state_duration("IDLE", sim_time) if hasattr(m, "get_state_duration") else getattr(m, "starved_time", 0.0)
            util_rate = min(1.0, active_t / total_time) if total_time > 0 else 0.0
            machine_stats.append({
                "id": m.id,
                "name": m.name,
                "schema_id": m.schema_id,
                "role": m.machine_role,
                "state": m.state,
                "processed_count": m.processed_count,
                "utilization_rate": round(util_rate * 100.0, 1),
                "active_time": round(active_t, 1),
                "blocked_time": round(blocked_t, 1),
                "starved_time": round(starved_t, 1),
                "intake_buffer_len": len(m.intake_buffer),
                "processing_len": len(m.processing)
            })

        # OHT Fleet statistics (Event-driven duration queries)
        oht_stats = []
        fleet_util_sum = 0.0
        for a in agents.values():
            loaded_t = a.get_state_duration("EN_ROUTE_DROPOFF", sim_time) if hasattr(a, "get_state_duration") else getattr(a, "loaded_travel_time", 0.0)
            action_t = (a.get_state_duration("ACTION_PICKUP", sim_time) + a.get_state_duration("ACTION_DROPOFF", sim_time)) if hasattr(a, "get_state_duration") else getattr(a, "action_time", 0.0)
            empty_t = (a.get_state_duration("EN_ROUTE_PICKUP", sim_time) + a.get_state_duration("EN_ROUTE_IDLE", sim_time)) if hasattr(a, "get_state_duration") else getattr(a, "empty_travel_time", 0.0)
            waiting_t = a.get_state_duration("WAITING_BLOCK", sim_time) if hasattr(a, "get_state_duration") else getattr(a, "waiting_traffic_time", 0.0)
            idle_t = a.get_state_duration("IDLE", sim_time) if hasattr(a, "get_state_duration") else getattr(a, "idle_time", 0.0)

            working_time = loaded_t + action_t
            agent_util = min(1.0, working_time / total_time) if total_time > 0 else 0.0
            fleet_util_sum += agent_util
            oht_stats.append({
                "id": a.id,
                "state": a.state,
                "speed": round(a.speed, 2),
                "has_cargo": a.cargo is not None,
                "cargo_id": a.cargo.id if a.cargo else None,
                "total_distance_m": round(a.total_distance, 1),
                "utilization_rate": round(agent_util * 100.0, 1),
                "loaded_time": round(loaded_t, 1),
                "empty_time": round(empty_t, 1),
                "waiting_traffic_time": round(waiting_t, 1),
                "idle_time": round(idle_t, 1)
            })

        fleet_avg_util = (fleet_util_sum / len(agents)) if agents else 0.0

        # Incorporate active queue jam durations
        active_jam_times: Dict[str, float] = dict(self.segment_jam_time)
        for sid, waiters in self.segment_waiting_since.items():
            for aid, w_start in waiters.items():
                active_jam_times[sid] = active_jam_times.get(sid, 0.0) + max(0.0, sim_time - w_start)

        max_traversals = max(self.segment_traversals.values()) if self.segment_traversals else 1
        max_jam = max(active_jam_times.values()) if active_jam_times else 1.0

        heatmap_data = {}
        all_segments = set(self.segment_traversals.keys()).union(active_jam_times.keys())
        for sid in all_segments:
            trav = self.segment_traversals.get(sid, 0)
            jam = active_jam_times.get(sid, 0.0)
            heat_level = round(min(1.0, (trav / max_traversals) * 0.5 + (jam / max_jam) * 0.5), 2)
            heatmap_data[sid] = {
                "traversals": trav,
                "jam_seconds": round(jam, 1),
                "heat_level": heat_level
            }

        # Aggregate to parent builder track IDs so map renderer lights up the tracks
        for sid in list(all_segments):
            base_id = sid.split('_blk')[0].split('_p_')[0]
            if base_id.endswith('_s') or base_id.endswith('_t'):
                base_id = base_id[:-2]
            if base_id != sid:
                if base_id not in heatmap_data:
                    heatmap_data[base_id] = {
                        "traversals": 0,
                        "jam_seconds": 0.0,
                        "heat_level": 0.0
                    }
                heatmap_data[base_id]["traversals"] += self.segment_traversals.get(sid, 0)
                heatmap_data[base_id]["jam_seconds"] = round(heatmap_data[base_id]["jam_seconds"] + active_jam_times.get(sid, 0.0), 1)
                b_trav = heatmap_data[base_id]["traversals"]
                b_jam = heatmap_data[base_id]["jam_seconds"]
                heatmap_data[base_id]["heat_level"] = round(min(1.0, (b_trav / max_traversals) * 0.5 + (b_jam / max_jam) * 0.5), 2)

        # Top bottlenecks (sorted by jam time)
        top_bottlenecks = sorted(
            [{"seg_id": sid, "jam_seconds": round(jam, 1), "traversals": self.segment_traversals.get(sid, 0)}
             for sid, jam in active_jam_times.items() if jam > 0.05],
            key=lambda x: x["jam_seconds"],
            reverse=True
        )[:5]

        return {
            "sim_time": round(sim_time, 1),
            "throughput": self.throughput_count,
            "throughput_rate_hr": round(throughput_rate_hr, 1),
            "avg_wait_time": round(avg_wait, 1),
            "fleet_avg_utilization": round(fleet_avg_util * 100.0, 1),
            "machines": machine_stats,
            "agents": oht_stats,
            "heatmap": heatmap_data,
            "top_bottlenecks": top_bottlenecks
        }

    def export_csv(self, summary: Dict[str, Any]) -> str:
        """Exports key metrics as a CSV text."""
        output = io.StringIO()
        writer = csv.writer(output)

        writer.writerow(["=== FACTORY SIMULATION METRICS SUMMARY ==="])
        writer.writerow(["Sim Time (s)", summary.get("sim_time", 0)])
        writer.writerow(["Throughput (items)", summary.get("throughput", 0)])
        writer.writerow(["Throughput Rate (items/hr)", summary.get("throughput_rate_hr", 0)])
        writer.writerow(["Average Cycle / Wait Time (s)", summary.get("avg_wait_time", 0)])
        writer.writerow(["Fleet Avg Utilization (%)", summary.get("fleet_avg_utilization", 0)])
        writer.writerow([])

        writer.writerow(["=== MACHINE UTILIZATION & COUNTS ==="])
        writer.writerow(["ID", "Name", "Schema", "Role", "State", "Processed Count", "Utility %", "Active Time (s)", "Blocked Time (s)", "Starved Time (s)"])
        for m in summary.get("machines", []):
            writer.writerow([m["id"], m["name"], m["schema_id"], m["role"], m["state"], m["processed_count"], m["utilization_rate"], m["active_time"], m["blocked_time"], m["starved_time"]])
        writer.writerow([])

        writer.writerow(["=== OHT FLEET PERFORMANCE ==="])
        writer.writerow(["Agent ID", "State", "Utility %", "Total Distance (m)", "Loaded Time (s)", "Empty Time (s)", "Waiting Traffic Time (s)", "Idle Time (s)"])
        for a in summary.get("agents", []):
            writer.writerow([a["id"], a["state"], a["utilization_rate"], a["total_distance_m"], a["loaded_time"], a["empty_time"], a["waiting_traffic_time"], a["idle_time"]])
        writer.writerow([])

        writer.writerow(["=== TOP BOTTLENECK SEGMENTS ==="])
        writer.writerow(["Segment ID", "Jam Duration (s)", "Traversal Count"])
        for b in summary.get("top_bottlenecks", []):
            writer.writerow([b["seg_id"], b["jam_seconds"], b["traversals"]])

        return output.getvalue()
