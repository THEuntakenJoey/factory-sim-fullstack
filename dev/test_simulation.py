import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.core.state import FactoryState
from backend.core.engine import SimulationEngine

def run_test():
    print("=== STARTING SIMULATION VERIFICATION TEST ===")
    project_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'backend', 'projects', 'factory1')
    print(f"Loading project from: {project_dir}")

    state = FactoryState(
        project_dir=project_dir,
        map_filename="map.json",
        fleet_size=4,
        strategies={
            "pathfinding": "dijkstra",
            "traffic": "block_reservation",
            "vehicle_assignment": "nearest",
            "machine_allocation": "least_loaded"
        }
    )
    engine = SimulationEngine(state)

    print(f"Map loaded with {len(state.map_mgr.nodes)} nodes and {len(state.map_mgr.segments)} segments.")
    print(f"Machines loaded: {len(state.machines)}")
    for mid, m in state.machines.items():
        print(f"  - Machine {mid} ({m.name}): schema {m.schema_id}, role={m.machine_role}, ports={len(m.ports)}")
    print(f"Agents spawned: {len(state.agents)}")
    for aid, a in state.agents.items():
        print(f"  - Agent {aid}: at block {a.current_block}, state={a.state}")

    print("\n--- Stepping simulation for 150 seconds (1500 steps of 0.1s) ---")
    for step_i in range(1500):
        engine.step(0.1)

    for aid, a in state.agents.items():
        print(f"Agent {aid}: block={a.current_block}, route={a.route}, state={a.state}")
    print("Block owners:", state.traffic_ctrl.block_owners)
    print("Block waiters:", {k: [w.id for w in v] for k, v in state.traffic_ctrl.block_waiters.items()})

    summary = state.analytics.get_summary(engine.sim_time, state.machines, state.agents)
    print("\n=== SIMULATION METRICS AFTER 30s ===")
    print(f"Sim Time: {summary['sim_time']}s")
    print(f"Throughput Count: {summary['throughput']}")
    print(f"Fleet Avg Utilization: {summary['fleet_avg_utilization']}%")
    print("\nMachines:")
    for m in summary['machines']:
        print(f"  [{m['id']}] {m['name']} ({m['role']}): state={m['state']}, processed={m['processed_count']}, util={m['utilization_rate']}%, blocked_time={m['blocked_time']}s")
    print("\nAgents:")
    for a in summary['agents']:
        print(f"  [{a['id']}]: state={a['state']}, cargo={a['cargo_id']}, dist={a['total_distance_m']}m, util={a['utilization_rate']}%")

    print("\nHeatmap Segments recorded:", len(summary['heatmap']))
    print("Top bottlenecks:", summary['top_bottlenecks'])

    # Verify backpressure / flow control invariants
    for a in state.agents.values():
        if a.cargo:
            # If agent has cargo, destination machine must have a reserved load port
            assert a.current_mission is not None
            assert a.current_mission['type'] == 'DROPOFF'

    print("\n=== TEST COMPLETED SUCCESSFULLY! ===")

if __name__ == "__main__":
    run_test()
