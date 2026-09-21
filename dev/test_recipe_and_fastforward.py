import sys
import os
import json
import asyncio

# Ensure project root is on PYTHONPATH
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.core.state import FactoryState
from backend.core.engine import SimulationEngine
from backend.models.devices import Carrier

def test_recipe_sync_and_fallback():
    print("\n--- TEST: Recipe Sync & Generator Fallback ---")
    proj_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend', 'projects', 'factory1'))
    
    # 1. Custom recipe with modified sequence: machine schema "2" then "1"
    custom_recipes = {
        "Custom_Wafer_21": {
            "id": "Custom_Wafer_21",
            "steps": ["2", "1"]
        }
    }
    
    # Create factory state with custom recipes
    state = FactoryState(
        project_dir=proj_dir,
        map_filename="map.json",
        fleet_size=3,
        recipes=custom_recipes
    )
    
    # Verify recipes loaded into state
    assert "Custom_Wafer_21" in state.recipes, "Custom recipe should be in state.recipes"
    print("[OK] Custom recipe successfully initialized in FactoryState")

    # Verify carrier fallback when generator creates with default recipe_id not in custom recipes
    engine = SimulationEngine(state)
    source_machine = next((m for m in state.machines.values() if m.machine_role == "source"), None)
    assert source_machine is not None, "Source machine should exist"
    
    # Simulate lot generation
    carrier = Carrier("TEST_LOT_1", recipe_id="non_existent", creation_time=0.0)
    # Check downstream request
    state.check_downstream_and_request_transport(source_machine, source_machine.ports[0], carrier, engine)
    
    # Carrier should have fallen back to Custom_Wafer_21
    assert carrier.recipe_id == "Custom_Wafer_21", f"Carrier should fallback to Custom_Wafer_21, got {carrier.recipe_id}"
    next_step = carrier.get_current_step_schema(state.recipes)
    assert next_step == "2", f"First recipe step should be '2', got {next_step}"
    print(f"[OK] Carrier dynamically fell back to active recipe '{carrier.recipe_id}', first step: Schema '{next_step}'")

def test_fast_forward_duration():
    print("\n--- TEST: Fast-Forward Duration Benchmark ---")
    proj_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend', 'projects', 'factory1'))
    
    state = FactoryState(
        project_dir=proj_dir,
        map_filename="map.json",
        fleet_size=4
    )
    engine = SimulationEngine(state)
    
    # Step engine to 120s simulated time in turbo mode (dt = 0.05)
    target_duration = 120.0
    dt = 0.05
    steps = 0
    import time
    start_cpu = time.time()
    
    while engine.sim_time < target_duration:
        step_dt = min(dt, target_duration - engine.sim_time)
        if step_dt <= 0.0001:
            break
        engine.step(step_dt)
        steps += 1
        
    cpu_elapsed = time.time() - start_cpu
    print(f"[OK] Stepped {steps} ticks ({engine.sim_time:.1f}s simulated) in {cpu_elapsed:.2f}s CPU time (Speed: {engine.sim_time / cpu_elapsed:.1f}x real-time)")
    
    # Get metrics summary
    summary = state.analytics.get_summary(engine.sim_time, state.machines, state.agents)
    
    print(f"  - Throughput: {summary['throughput']} units")
    print(f"  - Throughput Rate: {summary['throughput_rate_hr']:.1f} units/hr")
    print(f"  - Avg Wait Time: {summary['avg_wait_time']:.1f}s")
    print(f"  - Fleet Avg Utility: {summary['fleet_avg_utilization']}%")
    
    assert engine.sim_time >= target_duration - 1e-4, f"Engine should have reached {target_duration}s, got {engine.sim_time}"
    assert len(summary['machines']) > 0, "Machines summary should not be empty"
    
    # Check machine state durations
    total_active = sum(m['active_time'] for m in summary['machines'])
    total_blocked = sum(m['blocked_time'] for m in summary['machines'])
    total_starved = sum(m['starved_time'] for m in summary['machines'])
    print(f"  - Machine Time Distribution: Active={total_active:.1f}s, Blocked={total_blocked:.1f}s, Starved={total_starved:.1f}s")
    
    assert (total_active + total_blocked + total_starved) > 0, "Machine state durations should be accumulated"
    print("[OK] Machine state time distribution verified")

if __name__ == "__main__":
    test_recipe_sync_and_fallback()
    test_fast_forward_duration()
    print("\nAll automated verification tests passed successfully!")
