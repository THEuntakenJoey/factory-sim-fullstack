import sys
import os

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.core.state import FactoryState
from backend.core.engine import SimulationEngine

def test_event_analytics():
    proj_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend', 'projects', 'factory1'))
    state = FactoryState(proj_dir, 'map.json', fleet_size=5)
    engine = SimulationEngine(state)

    print("Running headless simulation for 100 seconds (dt=0.1s)...")
    for _ in range(1000):
        engine.step(0.1)

    summary = state.analytics.get_summary(engine.sim_time, state.machines, state.agents)

    print(f"\n--- SIMULATION RESULTS AT T={summary['sim_time']}s ---")
    print(f"Throughput Count: {summary['throughput']}")
    print(f"Throughput Rate: {summary['throughput_rate_hr']} items/hr")
    print(f"Avg Wait Time: {summary['avg_wait_time']}s")
    print(f"Fleet Avg Utility: {summary['fleet_avg_utilization']}%")

    print("\n--- MACHINE METRICS ---")
    for m in summary['machines']:
        print(f"  Machine {m['id']} ({m['role']}): state={m['state']}, util={m['utilization_rate']}%, active={m['active_time']}s, blocked={m['blocked_time']}s, starved={m['starved_time']}s, processed={m['processed_count']}")

    print("\n--- OHT FLEET METRICS ---")
    for a in summary['agents']:
        print(f"  Agent {a['id']}: state={a['state']}, util={a['utilization_rate']}%, loaded={a['loaded_time']}s, empty={a['empty_time']}s, wait={a['waiting_traffic_time']}s, idle={a['idle_time']}s, dist={a['total_distance_m']}m")

    print("\n--- TRACK HEATMAP / TRAVERSALS SAMPLE ---")
    top_trav = sorted(summary['heatmap'].items(), key=lambda x: x[1]['traversals'], reverse=True)[:5]
    for seg_id, data in top_trav:
        print(f"  Segment {seg_id}: traversals={data['traversals']}, jam_sec={data['jam_seconds']}s, heat={data['heat_level']}")

    # Asserts
    assert summary['throughput'] > 0, "Throughput count should be > 0"
    assert summary['throughput_rate_hr'] > 0, "Throughput rate should be > 0"
    assert summary['fleet_avg_utilization'] > 0, "Fleet avg utility should be > 0"
    assert len(top_trav) > 0, "There should be track traversals recorded"
    assert top_trav[0][1]['traversals'] > 0, "Top segment traversals should be > 0"

    print("\n>>> ALL ASSERTIONS PASSED SUCCESSFULLY! Event-driven metrics are working perfectly.")

if __name__ == "__main__":
    test_event_analytics()
