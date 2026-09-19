import os
import sys

# Add project root to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.core.state import FactoryState
from backend.core.engine import SimulationEngine

def run_test():
    project_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend", "projects", "factory1")
    print(f"Loading factory from: {project_dir}")

    factory_state = FactoryState(
        project_dir=project_dir,
        map_filename="map.json",
        fleet_size=6,
        strategies={
            "pathfinding": "dijkstra",
            "traffic": "block_reservation",
            "vehicle_assignment": "nearest",
            "machine_allocation": "least_loaded"
        }
    )

    sim = SimulationEngine(factory_state)
    sim.time_scale = 100.0 # Fast-forward in DES

    print(f"Starting simulation run for 150s of sim time (1500 x 0.1s)...")
    for _ in range(1500):
        sim.step(0.1)

    summary = factory_state.analytics.get_summary(sim.sim_time, factory_state.machines, factory_state.agents)

    print("\n" + "="*50)
    print(f"SIMULATION RESULTS AT T = {summary['sim_time']}s")
    print("="*50)
    print(f"Throughput Count:          {summary['throughput']} units")
    print(f"Throughput Rate:           {summary['throughput_rate_hr']} units/hr")
    print(f"Average Cycle/Wait Time:   {summary['avg_wait_time']}s")
    print(f"Fleet Avg Utilization:     {summary['fleet_avg_utilization']}%")

    print("\n--- MACHINE METRICS ---")
    proc1_utils = []
    proc2_utils = []

    for m in summary['machines']:
        role = m['role']
        schema = m['schema_id']
        util = m['utilization_rate']
        idle = round(100.0 - util, 1)
        cnt = m['processed_count']
        state = m['state']
        print(f"[{m['id']}] {m['name']} (Schema {schema}, {role}): Util={util}%, Idle={idle}%, Processed={cnt}, State={state}")

        if schema == "1":
            proc1_utils.append(util)
        elif schema == "2":
            proc2_utils.append(util)

    if proc1_utils and proc2_utils:
        avg_proc1_util = sum(proc1_utils) / len(proc1_utils)
        avg_proc2_util = sum(proc2_utils) / len(proc2_utils)
        avg_proc1_idle = 100.0 - avg_proc1_util
        avg_proc2_idle = 100.0 - avg_proc2_util
        print("\n--- COMPARISON ---")
        print(f"Processor_1 (Schema 1, 15s): Avg Util = {avg_proc1_util:.1f}%, Avg Idle = {avg_proc1_idle:.1f}%")
        print(f"Processor_2 (Schema 2, 10s): Avg Util = {avg_proc2_util:.1f}%, Avg Idle = {avg_proc2_idle:.1f}%")
        print(f"Is Processor_2 idle ratio higher than Processor_1? {'YES' if avg_proc2_idle > avg_proc1_idle else 'NO'}")

    print("\n--- VEHICLE FLEET ---")
    for a in summary['agents']:
        print(f"[{a['id']}]: State={a['state']}, Util={a['utilization_rate']}%, Loaded={a['loaded_time']}s, Empty={a['empty_time']}s, WaitTraffic={a['waiting_traffic_time']}s, Idle={a['idle_time']}s")

    print("\n--- TOP BOTTLENECKS ---")
    for b in summary['top_bottlenecks']:
        print(f"Segment {b['seg_id']}: Jam={b['jam_seconds']}s, Traversals={b['traversals']}")

if __name__ == "__main__":
    run_test()
