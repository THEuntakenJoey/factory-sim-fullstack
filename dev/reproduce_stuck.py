import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.core.state import FactoryState
from backend.core.engine import SimulationEngine

def test_long_run():
    project_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend", "projects", "factory1")
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
    sim.time_scale = 100.0

    print("Running simulation up to 1000s...")
    last_tp = 0
    stuck_time = None

    for step_num in range(10000): # 10000 x 0.1s = 1000s
        sim.step(0.1)
        t = sim.sim_time

        # Check every 20s
        if step_num % 200 == 0:
            tp = factory_state.analytics.throughput_count
            # Check if source is full
            source = [m for m in factory_state.machines.values() if m.machine_role == "source"][0]
            src_full = any(p.carrier is not None for p in source.ports)
            moving_agents = [a for a in factory_state.agents.values() if a.state in ("EN_ROUTE_PICKUP", "EN_ROUTE_DROPOFF", "ACTION_PICKUP", "ACTION_DROPOFF") or a.speed > 0]

            print(f"t={t:.1f}s | Throughput={tp} | SrcFull={src_full} | MovingAgents={len(moving_agents)} | SourceState={source.state}")

            if tp == last_tp and src_full and len(moving_agents) == 0 and t > 50:
                if stuck_time is None:
                    stuck_time = t
                elif t - stuck_time > 30:
                    print(f"\n!!! STUCK DETECTED AT t={t:.1f}s !!!")
                    print(f"Source ports: {[(p.index, p.state, p.carrier) for p in source.ports]}")
                    for m in factory_state.machines.values():
                        print(f"Machine {m.id} ({m.machine_role}): State={m.state}, Ports={[(p.index, p.type, p.state, p.carrier, p.reserved_by) for p in m.ports]}")
                    for a in factory_state.agents.values():
                        print(f"Agent {a.id}: State={a.state}, CurrentBlock={a.current_block}, Route={a.route}, Cargo={a.cargo}, Mission={a.current_mission}")
                    return True
            else:
                stuck_time = None
            last_tp = tp

    print("Completed 1000s without full deadlock.")
    return False

if __name__ == "__main__":
    test_long_run()
