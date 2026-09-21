import os
import json
from typing import Dict, List, Any, Optional

from .map_manager import MapManager
from ..models.devices import VirtualMachine
from ..models.vehicles import OHTAgent
from ..routing.dispatcher import Dispatcher
from ..routing.traffic_control import get_traffic_strategy
from ..routing.strategies import get_idle_vehicle_strategy
from ..metrics.analytics import AnalyticsTracker

class FactoryState:
    """
    Unified state container for the factory simulation.
    Manages the map graph, machines, OHT fleet, modular dispatch, and analytics.
    """
    def __init__(
        self,
        project_dir: str,
        map_filename: str = "map.json",
        fleet_size: int = 5,
        strategies: Optional[Dict[str, str]] = None,
        recipes: Optional[Dict[str, Any]] = None
    ):
        self.project_dir = project_dir
        self.map_filename = map_filename
        self.fleet_size = fleet_size
        self.strategies = strategies or {
            "pathfinding": "dijkstra",
            "traffic": "block_reservation",
            "vehicle_assignment": "nearest",
            "machine_allocation": "least_loaded",
            "idle_strategy": "stay_and_nudge"
        }

        # FIFO list of upstream machines halted waiting for downstream capacity
        # [{"machine": vm, "schema_id": str, "time": float, "carrier": carrier, "port": port}]
        self.halted_upstream_machines: List[Dict[str, Any]] = []

        # 1. File Paths
        map_path = os.path.join(project_dir, 'maps', map_filename)
        schema_path = os.path.join(project_dir, 'schema', 'machineAndSchema.json')
        recipes_path = os.path.join(project_dir, 'schema', 'recipes.json')


        # 2. Load Static Layout
        self.map_mgr = MapManager(map_path)

        # 3. Load Schemas and Recipes
        self.schemas: Dict[str, Any] = {}
        if os.path.exists(schema_path):
            try:
                with open(schema_path, 'r') as f:
                    self.schemas = json.load(f)
            except Exception as e:
                print(f"Error loading schemas: {e}")

        self.recipes: Dict[str, Any] = {}
        if recipes is not None:
            self.recipes = recipes
            try:
                with open(recipes_path, 'w') as f:
                    json.dump(self.recipes, f, indent=2)
            except Exception as e:
                print(f"Error persisting recipes: {e}")
        elif os.path.exists(recipes_path):
            try:
                with open(recipes_path, 'r') as f:
                    self.recipes = json.load(f)
            except Exception as e:
                print(f"Error loading recipes: {e}")

        # 4. Control Systems & Analytics
        self.traffic_ctrl = get_traffic_strategy(self.strategies.get("traffic", "block_reservation"))
        self.traffic_ctrl.reset()
        self.traffic_ctrl.idle_strategy = get_idle_vehicle_strategy(self.strategies.get("idle_strategy", "stay_and_nudge"))

        self.dispatcher = Dispatcher(
            map_mgr=self.map_mgr,
            traffic_controller=self.traffic_ctrl,
            pathfinding_strategy_name=self.strategies.get("pathfinding", "dijkstra"),
            vehicle_assignment_strategy_name=self.strategies.get("vehicle_assignment", "nearest"),
            machine_allocation_strategy_name=self.strategies.get("machine_allocation", "least_loaded")
        )

        self.analytics = AnalyticsTracker()

        # 5. Build Dynamic Entities
        self.machines: Dict[str, VirtualMachine] = {}
        self.agents: Dict[str, OHTAgent] = {}

        self._build_machines()
        self._spawn_fleet(self.fleet_size)

    def init_simulation(self, sim_engine: Any):
        """Called upon simulation engine startup or reset."""
        for a in self.agents.values():
            a.sim_engine = sim_engine
        for m in self.machines.values():
            if m.machine_role == "source":
                m.start_generator(sim_engine)

    def check_downstream_and_request_transport(self, src_machine: VirtualMachine, port: Any, carrier: Any, sim_engine: Any):
        """
        Reactive downstream availability check.
        If downstream has an available LOAD port, notifies dispatcher.
        If not, puts machine in PAUSED_BACKPRESSURE and enqueues to FIFO halted list.
        """
        if not carrier:
            return

        # Fallback recipe id if carrier's recipe_id is missing from active recipes
        if carrier.recipe_id not in self.recipes and self.recipes:
            carrier.recipe_id = list(self.recipes.keys())[0]

        next_schema_id = carrier.get_current_step_schema(self.recipes)
        dest_candidates = []

        if carrier.is_finished(self.recipes) or next_schema_id is None:
            dest_candidates = [m for m in self.machines.values() if m.machine_role == "sink" and m.get_available_load_port()]
        else:
            dest_candidates = [
                m for m in self.machines.values()
                if m.schema_id == next_schema_id and m.get_available_load_port()
            ]

        if dest_candidates:
            # Downstream available -> request transport
            self.dispatcher.request_transport(src_machine, port, carrier, sim_engine)
        else:
            # Downstream unavailable -> halt machine (backpressure) and register in FIFO queue
            src_machine.state = "PAUSED_BACKPRESSURE"
            if not any(entry["carrier"] == carrier for entry in self.halted_upstream_machines):
                self.halted_upstream_machines.append({
                    "machine": src_machine,
                    "schema_id": next_schema_id or "sink",
                    "time": sim_engine.sim_time if sim_engine else 0.0,
                    "carrier": carrier,
                    "port": port
                })

    def notify_slot_freed(self, freed_machine: VirtualMachine, sim_engine: Any):
        """
        Called when a machine slot is freed.
        Performs a FIFO check on halted upstream machines to awaken the oldest waiting machine.
        """
        freed_schema = freed_machine.schema_id if freed_machine.machine_role != "sink" else "sink"

        # Search for oldest halted upstream machine needing this schema
        for idx, entry in enumerate(list(self.halted_upstream_machines)):
            if entry["schema_id"] == freed_schema:
                up_m = entry["machine"]
                port = entry["port"]
                carrier = entry["carrier"]

                # Check if carrier still ready
                if port.carrier == carrier:
                    self.halted_upstream_machines.pop(idx)
                    up_m.state = "PROCESSING" if up_m.processing else "IDLE"
                    self.dispatcher.request_transport(up_m, port, carrier, sim_engine)
                    break

        # Notify dispatcher
        self.dispatcher.on_machine_slot_freed(freed_machine, sim_engine)


    def _build_machines(self):
        """Constructs VirtualMachines from map machine placements and schemas."""
        self.machines.clear()
        for m_data in self.map_mgr.machines:
            m_id = m_data.get("id")
            schema_id = str(m_data.get("schema_id", ""))
            schema_cfg = self.schemas.get(schema_id, {})
            m_name = m_data.get("name") or f"M_{m_id[-5:]}"

            # Map ports to track nodes
            port_node_map = {}
            for idx, p in enumerate(m_data.get("ports", [])):
                node_idx = self.map_mgr.port_node_indices.get((m_id, idx))
                if node_idx is not None:
                    port_node_map[idx] = node_idx

            vm = VirtualMachine(
                machine_id=m_id,
                name=m_name,
                schema_id=schema_id,
                config=schema_cfg,
                port_node_map=port_node_map
            )
            self.machines[m_id] = vm

    def _spawn_fleet(self, count: int):
        """Spawns OHTs safely distributed across straight track blocks."""
        self.agents.clear()
        self.traffic_ctrl.reset()

        # Find straight blocks suitable for parking (at least 1.1m, no switch branches)
        straight_blocks = [
            sid for sid, s in self.map_mgr.segments.items()
            if s.get("type") == "line" and s.get("calc_len", 0) >= 1.1 and not s.get("builder_id", "").endswith("_s")
        ]

        if not straight_blocks:
            straight_blocks = [
                sid for sid, s in self.map_mgr.segments.items()
                if s.get("type") == "line" and s.get("calc_len", 0) >= 0.85
            ] or list(self.map_mgr.segments.keys())

        # Distribute vehicles evenly
        step = max(1, len(straight_blocks) // max(1, count))
        for i in range(count):
            ag_id = f"OHT_{i+1:02d}"
            agent = OHTAgent(ag_id, self.map_mgr, self.traffic_ctrl)
            block_idx = (i * step) % len(straight_blocks)
            block_id = straight_blocks[block_idx]

            agent.spawn(block_id)
            self.agents[ag_id] = agent


    def update_strategies(self, strategies: Dict[str, str]):
        self.strategies.update(strategies)
        if "traffic" in strategies:
            self.traffic_ctrl = get_traffic_strategy(strategies["traffic"])
            self.dispatcher.traffic_ctrl = self.traffic_ctrl
            for agent in self.agents.values():
                agent.traffic_ctrl = self.traffic_ctrl

        if "idle_strategy" in strategies:
            self.traffic_ctrl.idle_strategy = get_idle_vehicle_strategy(strategies["idle_strategy"])

        self.dispatcher.set_strategies(
            pathfinding=strategies.get("pathfinding"),
            vehicle_assignment=strategies.get("vehicle_assignment"),
            machine_allocation=strategies.get("machine_allocation")
        )


    def set_fleet_size(self, count: int):
        self.fleet_size = max(1, min(20, count))
        self._spawn_fleet(self.fleet_size)

    def to_dict(self, current_time: float = 0.0) -> Dict[str, Any]:
        """Serializes the complete factory state for WebSocket transmission at 30 FPS."""
        agents_data = []
        for v_id, agent in self.agents.items():
            pos = agent.get_pos(current_time)
            agents_data.append({
                "id": v_id,
                "x": round(float(pos[0]), 3),
                "y": round(float(pos[1]), 3),
                "heading": round(float(agent.heading), 1),
                "speed": round(float(agent.speed), 2),
                "state": agent.state,
                "cargo": agent.cargo.id if agent.cargo else None,
                "recipe_step": agent.cargo.step_idx if agent.cargo else None,
                "current_block": agent.current_block,
                "target_node": agent.target_node
            })

        machines_data = []
        for m_id, vm in self.machines.items():
            ports_info = []
            for p in vm.ports:
                ports_info.append({
                    "index": p.index,
                    "type": p.type,
                    "state": p.state,
                    "node_idx": p.node_idx,
                    "cargo": p.carrier.id if p.carrier else None
                })

            machines_data.append({
                "id": m_id,
                "name": vm.name,
                "schema_id": vm.schema_id,
                "role": vm.machine_role,
                "state": vm.state,
                "processed_count": vm.processed_count,
                "intake_count": len(vm.intake_buffer),
                "processing_count": len(vm.processing),
                "ports": ports_info
            })

        metrics_data = self.analytics.get_summary(current_time, self.machines, self.agents)
        from .config import get_oht_specs

        strat_dict = dict(self.dispatcher.strategy_names)
        strat_dict["traffic"] = self.strategies.get("traffic", "block_reservation")
        strat_dict["idle_strategy"] = self.strategies.get("idle_strategy", "stay_and_nudge")

        return {
            "sim_time": round(current_time, 2),
            "agents": agents_data,
            "machines": machines_data,
            "metrics": metrics_data,
            "strategies": strat_dict,
            "oht_specs": get_oht_specs()
        }

