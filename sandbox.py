from __future__ import annotations
import argparse
import random
import sys
import tkinter as tk
from tkinter import ttk
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.animation import FuncAnimation
import matplotlib.pyplot as plt

from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from agent import OHTAgent
    from systems import TransportRequest

# Import verified modules
from map_manager import MapManager
from agent import OHTAgent
from traffic import TrafficRegistry
from map_drawer import MapVisualizer
from systems import VirtualMES, VirtualMCS

class DashboardApp:
    def __init__(self, root: tk.Tk, args: argparse.Namespace):
        self.root = root
        self.root.title("OHT Factory Simulation Dashboard")
        self.root.geometry("1400x900")

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        # --- DATA INITIALIZATION ---
        self._init_simulation(args)

        # --- UI LAYOUT ---
        paned = tk.PanedWindow(root, orient=tk.HORIZONTAL, sashwidth=4)
        paned.pack(fill=tk.BOTH, expand=True)

        # 1. Left Frame (Visualization)
        self.frame_left = ttk.Frame(paned, width=900)
        paned.add(self.frame_left)
       
        # Embed Matplotlib
        self.canvas = FigureCanvasTkAgg(self.viz.fig, master=self.frame_left)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        # 2. Right Frame (Data)
        self.frame_right = ttk.Frame(paned, width=500)
        paned.add(self.frame_right)

        self._build_agent_table(self.frame_right)
        self._build_mes_panel(self.frame_right)

        # --- ANIMATION LOOP ---
        # cache_frame_data=False suppresses the warning about unbounded cache
        self.ani = FuncAnimation(self.viz.fig, self.update_loop, interval=30, blit=False, cache_frame_data=False)

    def _init_simulation(self, args):
        print(f"Loading Map: {args.map_json}...")
        try:
            self.mgr = MapManager(args.map_json)
            self.mes = VirtualMES(self.mgr, args.schema)
        except Exception as e:
            print(f"Critical Error: {e}")
            self.root.destroy()
            return

        self.traffic_ctrl = TrafficRegistry()
        self.viz = MapVisualizer(self.mgr)

        # Agents
        self.agents: List[OHTAgent] = []
        spawn_nodes = list(self.mes.machines.keys())
        if not spawn_nodes: raise ValueError("No spawn points found")

        for i in range(args.agents):
            bot = OHTAgent(self.mgr, self.traffic_ctrl)
            bot.spawn(random.choice(spawn_nodes))
            # Random wait timer to desynchronize starts
            bot.wait_timer = random.random() * 2.0
            bot.ui_id = f"OHT_{i+1:02d}"
            self.agents.append(bot)

        self.mcs = VirtualMCS(self.agents, self.mes)
        self.mes.seed_inventory(20)
       
        # Simulation State
        self.sim_ctx = {'dt': 0.05}

    def _build_agent_table(self, parent):
        lbl = ttk.Label(parent, text="Fleet Status", font=("Arial", 12, "bold"))
        lbl.pack(pady=(10, 5), anchor="w")

        cols = ("ID", "State", "Pos", "Cargo", "Target")
        self.tree_agents = ttk.Treeview(parent, columns=cols, show="headings", height=10)
       
        self.tree_agents.heading("ID", text="ID")
        self.tree_agents.column("ID", width=60)
        self.tree_agents.heading("State", text="State")
        self.tree_agents.column("State", width=80)
        self.tree_agents.heading("Pos", text="Pos")
        self.tree_agents.column("Pos", width=60)
        self.tree_agents.heading("Cargo", text="Bay Content")
        self.tree_agents.column("Cargo", width=120)
        self.tree_agents.heading("Target", text="Mission Target")
       
        self.tree_agents.pack(fill=tk.X, padx=5)

    def _build_mes_panel(self, parent):
        # Mission Queue
        lbl_q = ttk.Label(parent, text="MCS Mission Queue", font=("Arial", 12, "bold"))
        lbl_q.pack(pady=(20, 5), anchor="w")

        cols_q = ("CID", "From", "To")
        self.tree_queue = ttk.Treeview(parent, columns=cols_q, show="headings", height=6)
        self.tree_queue.heading("CID", text="Cargo")
        self.tree_queue.column("CID", width=80)
        self.tree_queue.heading("From", text="Source")
        self.tree_queue.column("From", width=60)
        self.tree_queue.heading("To", text="Dest")
        self.tree_queue.column("To", width=60)
        self.tree_queue.pack(fill=tk.X, padx=5)

        # System Logs
        lbl_log = ttk.Label(parent, text="System Logs", font=("Arial", 12, "bold"))
        lbl_log.pack(pady=(20, 5), anchor="w")

        self.list_logs = tk.Listbox(parent, height=10, font=("Consolas", 9))
        self.list_logs.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

    def update_loop(self, frame):
        dt = self.sim_ctx['dt']

        # --- 1. Simulation Steps ---
       
        # Phase 1: Sense (Register State)
        self.traffic_ctrl.clear()
        for bot in self.agents:
            self.traffic_ctrl.register_agent(bot)
           
        # Phase 2: Act (Physics & Logic)
        for bot in self.agents:
            bot.update(dt)

        # Phase 3: Referee (Collision Check)
        self.traffic_ctrl.check_collisions(self.agents)

        # Phase 4: Logistics (MES/MCS Generation)
        if len(self.mcs.job_queue) < 3:
            req = self.mes.generate_transport_request()
            if req:
                self.mcs.add_request(req)
                self.log(f"[MES] New Order: {req['cid']}")

        self.mcs.spin()

        # --- 2. Update Visualizer ---
        artists = self.viz.update(self.agents)

        # --- 3. Update UI Tables (Every 5 frames to save CPU) ---
        if frame % 5 == 0:
            self._update_ui_tables()

        return artists

    def _update_ui_tables(self):
        # Update Agent Table
        for item in self.tree_agents.get_children():
            self.tree_agents.delete(item)
           
        for bot in self.agents:
            # Format Cargo: [FOUP_1, None] -> "FOUP_1, -"
            cargo_str = ", ".join([c.id if c else "-" for c in bot.cargo_bay])
            target_str = str(bot.current_mission.target_id) if bot.current_mission else "-"
           
            # Use 'v' (End Node) as approximate location for dashboard simplicity
            pos_id = self.mgr.segments[bot.current_seg]['v']
           
            self.tree_agents.insert("", "end", values=(
                getattr(bot, 'ui_id', 'OHT_??'),
                bot.state,
                pos_id,
                cargo_str,
                target_str
            ))

        # Update Mission Queue
        for item in self.tree_queue.get_children():
            self.tree_queue.delete(item)
           
        # Show first 6 items
        for i, req in enumerate(list(self.mcs.job_queue)[:6]):
            self.tree_queue.insert("", "end", values=(
                req['cid'],
                req['u'],
                req['v']
            ))

    def log(self, message: str):
        """Adds a message to the log window."""
        self.list_logs.insert(0, message) # Insert at top
        if self.list_logs.size() > 50:
            self.list_logs.delete(50, "end")

    def on_close(self):
        """Kill the simulation and python process."""
        print("Closing Simulation...")
        self.ani.event_source.stop()
        self.root.destroy()
        sys.exit(0)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("map_json", help="Path to map file")
    parser.add_argument("--schema", default="machine_schema.json", help="Schema path")
    parser.add_argument("--agents", type=int, default=5, help="Agent count")
    args = parser.parse_args()

    root = tk.Tk()
    app = DashboardApp(root, args)
    root.mainloop()

if __name__ == "__main__":
    main()
