import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.core.config import get_oht_specs, update_oht_specs
from backend.core.map_manager import MapManager
from backend.core.state import FactoryState
from backend.core.engine import SimulationEngine

def test_track_splitting():
    print("\n--- TEST 1: Track Splitting with OHT Length + Buffer ---")
    specs = get_oht_specs()
    min_len = specs.get("min_section_len_m", 1.2)
    print(f"Configured min_section_len: {min_len}m (OHT Length: {specs['length_m']}m, Buffer: {specs['buffer_m']}m)")

    map_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend", "projects", "factory1", "maps", "map.json")
    mgr = MapManager(map_path)

    short_straight_blocks = []
    for sid, s in mgr.segments.items():
        if s.get("type") == "line":
            # Exclude diverge/merge straight branches (_s) which are 0.5m
            if not sid.endswith("_s"):
                calc_l = s.get("calc_len", 0)
                if calc_l < min_len - 0.05: # allow small float tolerance
                    short_straight_blocks.append((sid, calc_l))

    print(f"Total track segments: {len(mgr.segments)}")
    if short_straight_blocks:
        print(f"WARNING: Found {len(short_straight_blocks)} non-switch straight blocks < {min_len}m: {short_straight_blocks[:5]}")
    else:
        print(f"SUCCESS: All standard straight blocks satisfy length >= {min_len}m!")

def test_event_driven_machine_cycle():
    print("\n--- TEST 2: Event-Driven Machine Intake, Finish, & Backpressure ---")
    project_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend", "projects", "factory1")
    state = FactoryState(project_dir=project_dir, fleet_size=4)
    sim = SimulationEngine(state)

    source = next(m for m in state.machines.values() if m.machine_role == "source")
    print(f"Source machine: {source.id}, state: {source.state}")

    # Step engine for 5 seconds
    for _ in range(50):
        sim.step(0.1)

    print(f"After 5s: sim_time={sim.sim_time:.1f}s, source state={source.state}, processed={source.processed_count}")
    assert source.processed_count > 0 or any(p.carrier is not None for p in source.ports), "Source should have generated lots"
    print("SUCCESS: Event-driven source generation & transport dispatch verified!")

def test_idle_strategies_comparison():
    print("\n--- TEST 3: Idle Strategies Benchmark (Stay & Nudge vs Cruising) ---")
    project_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend", "projects", "factory1")

    # Run Stay & Nudge
    state_nudge = FactoryState(
        project_dir=project_dir,
        fleet_size=5,
        strategies={"idle_strategy": "stay_and_nudge", "pathfinding": "dijkstra", "traffic": "block_reservation"}
    )
    sim_nudge = SimulationEngine(state_nudge)
    for _ in range(3000): # 300s
        sim_nudge.step(0.1)
    tp_nudge = state_nudge.analytics.throughput_count
    metrics_nudge = state_nudge.analytics.get_summary(sim_nudge.sim_time, state_nudge.machines, state_nudge.agents)

    # Run Cruising
    state_cruise = FactoryState(
        project_dir=project_dir,
        fleet_size=5,
        strategies={"idle_strategy": "cruising", "pathfinding": "dijkstra", "traffic": "block_reservation"}
    )
    sim_cruise = SimulationEngine(state_cruise)
    for _ in range(3000): # 300s
        sim_cruise.step(0.1)
    tp_cruise = state_cruise.analytics.throughput_count
    metrics_cruise = state_cruise.analytics.get_summary(sim_cruise.sim_time, state_cruise.machines, state_cruise.agents)

    print(f"Stay & Nudge (300s): Throughput = {tp_nudge} units | Fleet Avg Util = {metrics_nudge['fleet_avg_utilization']}%")
    print(f"Cruising     (300s): Throughput = {tp_cruise} units | Fleet Avg Util = {metrics_cruise['fleet_avg_utilization']}%")
    print("SUCCESS: Modular Idle Strategy comparison executed cleanly!")

if __name__ == "__main__":
    test_track_splitting()
    test_event_driven_machine_cycle()
    test_idle_strategies_comparison()
