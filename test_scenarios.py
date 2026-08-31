from __future__ import annotations
import argparse
import json
import random
import tkinter as tk
from typing import TYPE_CHECKING, Any

from sandbox import DashboardApp
from agent import OHTAgent
from virtual_objects import Container
from config import OHT_SPECS

if TYPE_CHECKING:
    from systems import VirtualMachine
    

class AdvancedScenarioRunner(DashboardApp):
    def __init__(self, root: tk.Tk, args: argparse.Namespace, scenario_data: dict[str, Any]):
        self.data = scenario_data
        self.scenario_type = scenario_data.get('type')
        super().__init__(root, args)

        # Custom State for Tests
        self.chaos_timer = 0.0
        self.lead_agent = None

    def _init_simulation(self, args):
        super()._init_simulation(args)
       
        # Reset Environment
        self.agents = []
        self.mcs.job_queue.clear()
       
        # Dispatch Setup
        if self.scenario_type == "TAILING":
            self._setup_tailing()
        elif self.scenario_type == "MERGE":
            self._setup_merge()
        elif self.scenario_type == "DUAL_LOGIC":
            self._setup_dual_logic()
        elif self.scenario_type == "ERROR_HANDLING":
            self._setup_error_handling()
           
        self.mcs.agents = self.agents

    # --- SCENARIO SETUPS ---

    def _setup_tailing(self):
        start = self.data['start_node']
        target = self.data['target_node']
        count = self.data.get('agent_count', 4)
        spacing = self.data.get('spawn_spacing_m', 2.0)

        # Identify Segment
        start_seg = next((s for s in self.mgr.segments.values() if s['u'] == start), None)
        if not start_seg: return

        for i in range(count):
            bot = OHTAgent(self.mgr, self.traffic_ctrl)
            bot.current_seg = start_seg['id']
            bot.dist = spacing * 1000.0 * i
            bot.state = "IDLE"
            bot.ui_id = f"Car_{i+1}"
            if i == count - 1: bot.ui_id += " (LEAD)" # Front car is last in list visually
           
            bot.add_mission("MOVE", target)
            self.agents.append(bot)
       
        # The agent furthest ahead (largest dist) is the leader
        self.lead_agent = self.agents[-1]

    def _setup_merge(self):

        gap = OHT_SPECS['safety']['gap_maintained'] + 200.0 # Safety buffer

        # Spawn Platoon A
        for i in range(self.data.get('cars_per_lane', 3)):
            bot = OHTAgent(self.mgr, self.traffic_ctrl)
            bot.spawn(self.data['lane_a_start'])
            # Hack: Manually offset position so they don't stack
            bot.dist = -gap * (i + 1) # Negative dist means "waiting behind start" conceptually
                                   # In reality, GraphWalker handles this, or spawn on previous segs
            bot.ui_id = f"B_{i}"
            bot.add_mission("MOVE", self.data['exit_node'])
            self.agents.append(bot)

        # Spawn Platoon B
        for i in range(self.data.get('cars_per_lane', 3)):
            bot = OHTAgent(self.mgr, self.traffic_ctrl)
            bot.spawn(self.data['lane_b_start'])
            bot.dist = -gap * i
            bot.ui_id = f"A_{i}"
            bot.add_mission("MOVE", self.data['exit_node'])
            self.agents.append(bot)



    def _setup_dual_logic(self):
        """
        Populate inventory and let MCS/MES logic decide the mission structure.
        """
        src_id = self.data['src_machine']
        ports = self.data['ports'] # List of indices, e.g. [0, 1] or [0, 2]
       
        src_vm = self.mes.machines[src_id]
       
        # Populate Ports
        for i, p_idx in enumerate(ports):
            c_id = f"TEST_{i}"
            c = Container(c_id, "FOUP", src_id)
            src_vm.ports[p_idx].container = c
            src_vm.ports[p_idx].state = "OCCUPIED"
            # Register in MES inventory manually for this test
            self.mes.containers[c_id] = c

        # Spawn Observer Agent
        bot = OHTAgent(self.mgr, self.traffic_ctrl)
        bot.spawn(src_id)
        bot.ui_id = "Observer"
        self.agents.append(bot)
       
        print(f">>> TEST CONDITION: Cargo at Ports {ports}")
        print(">>> Watch 'Mission Queue' to see if 1 Dual or 2 Singles are generated.")

    def _setup_error_handling(self):
        mid = self.data['machine_node']
        mode = self.data['mode']
       
        bot = OHTAgent(self.mgr, self.traffic_ctrl)
        bot.spawn(mid)
        bot.ui_id = "Err_Bot"
        self.agents.append(bot)
       
        if mode == "GHOST_PICKUP":
            print(">>> INJECTING: Pickup from Empty Port 0")
            # Port 0 is empty by default
            bot.add_mission("ACTION", type="PICKUP", port_indices=[0])
           
        elif mode == "JAMMED_DROPOFF":
            print(">>> INJECTING: Dropoff into Full Port 0")
            # Fill Port 0
            vm = self.mes.machines[mid]
            vm.ports[0].state = "OCCUPIED"
            vm.ports[0].container = Container("BLOCKER", "FOUP", mid)
           
            # Give Bot Cargo
            c = Container("PAYLOAD", "FOUP", mid)
            bot.cargo_bay[0] = c
           
            bot.add_mission("ACTION", type="DROPOFF", cargo_ids=["PAYLOAD"], port_indices=[0])

    # --- DYNAMIC UPDATES ---

    def update_loop(self, frame):
        # 1. Chaos Generator (Tailing Test)
        if self.scenario_type == "TAILING" and self.lead_agent:
            prob = self.data.get('chaos_prob', 0.01)
           
            if self.lead_agent.state == "MOVING":
                # Random Brake Check
                if random.random() < prob:
                    print(f"(!) CHAOS: Lead car Emergency Stop @ Frame {frame}")
                    self.lead_agent.speed = 0.0
                    # Force a visual indication
                    self.lead_agent.state = "ERROR"
                    self.chaos_timer = 2.0 # Stop for 2 seconds (simulated time)
           
            # Recovery Logic
            if self.chaos_timer > 0:
                self.chaos_timer -= 0.05 # decrement by dt
                if self.chaos_timer <= 0:
                    print("(!) CHAOS: Lead car Resuming")
                    self.lead_agent.state = "MOVING"

        # 2. Dual Logic Trigger
        if self.scenario_type == "DUAL_LOGIC":
            # Force MCS to scan for batch moves every frame
            # (Assuming you implemented generate_smart_batch_moves in systems.py)
            self.mcs.generate_smart_batch_moves()

        # 3. Standard Loop
        return super().update_loop(frame)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("map_json")
    parser.add_argument("scenarios_json")
    parser.add_argument("test_name")
    parser.add_argument("--schema", default="machine_schema.json")
    # Agents arg ignored
    parser.add_argument("--agents", type=int, default=0)
    args = parser.parse_args()

    with open(args.scenarios_json, 'r') as f:
        config = json.load(f)

    root = tk.Tk()
    app = AdvancedScenarioRunner(root, args, config[args.test_name])
    root.mainloop()

if __name__ == "__main__":
    main()