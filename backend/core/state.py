import asyncio
import time
from typing import Dict
from .map_manager import MapManager
from ..models.devices import VirtualMachine
from ..models.vehicles import OHTAgent
from ..routing.dispatcher import VirtualMES, VirtualMCS

class FactoryState:
    """
    Global container for all simulation state.
    """
    def __init__(self, map_path: str, schema_path: str = None):
        # 1. Static Layout
        self.map_mgr = MapManager(map_path)
        
        # 2. Dynamic Entities
        self.machines: Dict[int, VirtualMachine] = {}
        self.agents: Dict[str, OHTAgent] = {}
        
        # 3. Control Systems
        self.mes = VirtualMES(self.map_mgr, schema_path)
        self.mcs = VirtualMCS(self.map_mgr, self.mes)
        
        # 4. Metrics
        self.metrics = {
            "throughput": 0,
            "active_vehicles": 0
        }
        
        self.init_machines()

    def init_machines(self):
        # Copy machines that MES created back into the global state for easy access
        self.machines = self.mes.machines

    def to_dict(self):
        """Serialize state for WebSocket transmission"""
        agents_data = []
        for v_id, agent in self.agents.items():
            pos = agent.get_pos()
            agents_data.append({
                "id": v_id,
                "x": pos[0],
                "y": pos[1],
                "state": agent.state,
                "cargo": agent.cargo.lot_id if agent.cargo else None
            })
            
        machines_data = []
        for n_id, machine in self.machines.items():
            machines_data.append({
                "node_id": n_id,
                "name": machine.name,
                "type": machine.type,
                "ports_used": len([p for p in machine.ports if p.state != "EMPTY"]),
                "ports_total": len(machine.ports)
            })

        return {
            "agents": agents_data,
            "machines": machines_data,
            "metrics": self.metrics
        }
