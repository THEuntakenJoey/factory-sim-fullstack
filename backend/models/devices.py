from __future__ import annotations
import random
from typing import Optional, List, Dict, Any, Callable

class Carrier:
    """Represents a physical cargo carrier (e.g. FOUP) containing a product lot."""
    def __init__(self, carrier_id: str, recipe_id: str = "1", carrier_type: str = "FOUP", creation_time: float = 0.0):
        self.id = carrier_id
        self.recipe_id = recipe_id
        self.type = carrier_type
        self.step_idx = 0
        self.creation_time = creation_time
        self.location: Optional[int] = None  # Current node_id or None if carried by OHT
        self.state = "STORED"  # "STORED", "RESERVED_FOR_PICKUP", "IN_TRANSIT"
        self.history: List[Dict[str, Any]] = []

    def get_current_step_schema(self, recipes_dict: Dict[str, Any]) -> Optional[str]:
        recipe = recipes_dict.get(self.recipe_id)
        if not recipe:
            return None
        steps = recipe.get("steps", [])
        if self.step_idx < len(steps):
            return str(steps[self.step_idx])
        return None

    def advance_step(self, machine_name: str, current_time: float):
        self.history.append({
            "step": self.step_idx,
            "machine": machine_name,
            "completed_at": current_time
        })
        self.step_idx += 1

    def is_finished(self, recipes_dict: Dict[str, Any]) -> bool:
        recipe = recipes_dict.get(self.recipe_id)
        if not recipe:
            return True
        steps = recipe.get("steps", [])
        return self.step_idx >= len(steps)

    def __repr__(self) -> str:
        return f"<Carrier {self.id} (Recipe {self.recipe_id}, Step {self.step_idx})>"

class MachinePort:
    """A port connecting a machine to a specific track node."""
    def __init__(self, index: int, port_id: str, port_type: str, node_idx: int):
        self.index = index
        self.port_id = port_id
        self.type = port_type  # "LOAD", "UNLOAD", or "BIDIRECTIONAL"
        self.node_idx = node_idx
        self.carrier: Optional[Carrier] = None
        self.state = "EMPTY"  # "EMPTY", "RESERVED", "OCCUPIED"
        self.reserved_by: Optional[str] = None

    def is_available_for_dropoff(self) -> bool:
        return self.state == "EMPTY" and self.carrier is None

    def is_ready_for_pickup(self) -> bool:
        return self.state == "OCCUPIED" and self.carrier is not None

class VirtualMachine:
    """
    Simulates a factory machine, source generator, or sink.
    Implements DES processing, capacity limits, and downstream backpressure pausing.
    """
    def __init__(
        self,
        machine_id: str,
        name: str,
        schema_id: str,
        config: Dict[str, Any],
        port_node_map: Dict[int, int]
    ):
        self.id = machine_id
        self.name = name
        self.schema_id = str(schema_id)
        self.type = self.schema_id
        self.config = config or {}

        # Machine configuration
        self.machine_role = self.config.get("machine_role", "process")
        self.capacity = max(1, int(self.config.get("capacity", 1)))
        self.process_mode = self.config.get("process_mode", "batch")
        self.intake_mode = self.config.get("intake_mode", "continuous")
        self.process_time = max(0.1, float(self.config.get("process_time", 5.0)))
        self.intake_time = float(self.config.get("intake_time", 1.0))

        # Generator settings (for source)
        self.generation_interval = float(self.config.get("generation_interval", 5.0))
        self.generation_random = bool(self.config.get("generation_random", False))
        self.generators = self.config.get("generators", [])
        self.next_generation_time = 0.0

        # Build ports from schema config and port_node_map
        self.ports: List[MachinePort] = []
        schema_ports = self.config.get("ports", [])
        for idx, sp in enumerate(schema_ports):
            ptype = sp.get("type", "LOAD" if idx == 0 else "UNLOAD")
            if self.machine_role == "source":
                ptype = "UNLOAD"
            elif self.machine_role == "sink":
                ptype = "LOAD"
            node_idx = port_node_map.get(idx, 0)
            self.ports.append(MachinePort(idx, sp.get("id", f"p_{idx}"), ptype, node_idx))

        # Internal buffers
        self.intake_buffer: List[Carrier] = []
        self.processing: List[Dict[str, Any]] = []  # [{"carrier": c, "finish_time": t}]
        self.output_buffer: List[Carrier] = []
        self.pending_deliveries = 0

        # Operational state: "IDLE", "PROCESSING", "BLOCKED", "PAUSED_BACKPRESSURE"
        self.state = "IDLE"

        # Analytics tracking
        self.processed_count = 0
        self.active_processing_time = 0.0
        self.blocked_time = 0.0
        self.starved_time = 0.0

    def get_load_node(self) -> Optional[int]:
        if self.machine_role == "sink":
            return self.ports[0].node_idx if self.ports else None
        for p in self.ports:
            if p.type in ("LOAD", "BIDIRECTIONAL"):
                return p.node_idx
        return self.ports[0].node_idx if self.ports else None

    def get_unload_node(self) -> Optional[int]:
        if self.machine_role == "source":
            return self.ports[0].node_idx if self.ports else None
        for p in self.ports:
            if p.type in ("UNLOAD", "BIDIRECTIONAL"):
                return p.node_idx
        return self.ports[-1].node_idx if self.ports else None

    def get_available_load_port(self) -> Optional[MachinePort]:
        if self.machine_role == "sink":
            for p in self.ports:
                if p.is_available_for_dropoff():
                    return p
            return None
        for p in self.ports:
            if p.type in ("LOAD", "BIDIRECTIONAL") and p.is_available_for_dropoff():
                return p
        return None

    def get_ready_unload_port(self) -> Optional[MachinePort]:
        if self.machine_role == "source":
            for p in self.ports:
                if p.is_ready_for_pickup():
                    return p
            return None
        for p in self.ports:
            if p.type in ("UNLOAD", "BIDIRECTIONAL") and p.is_ready_for_pickup():
                return p
        return None

    def reserve_load_port(self, agent_id: str) -> Optional[MachinePort]:
        port = self.get_available_load_port()
        if port:
            port.state = "RESERVED"
            port.reserved_by = agent_id
            self.pending_deliveries += 1
            return port
        return None

    def receive_cargo(self, port_idx: int, carrier: Carrier) -> bool:
        if 0 <= port_idx < len(self.ports):
            port = self.ports[port_idx]
            port.carrier = carrier
            port.state = "OCCUPIED"
            carrier.location = port.node_idx
            carrier.state = "STORED"
            self.pending_deliveries = max(0, self.pending_deliveries - 1)

            # In normal processing, cargo is moved from LOAD port into intake buffer
            if self.machine_role != "sink":
                # Clear port immediately or after intake time
                port.carrier = None
                port.state = "EMPTY"
                self.intake_buffer.append(carrier)
            return True
        return False

    def retrieve_cargo(self, port_idx: Optional[int] = None) -> Optional[Carrier]:
        port = None
        if port_idx is not None and 0 <= port_idx < len(self.ports):
            port = self.ports[port_idx]
        else:
            port = self.get_ready_unload_port()

        if port and port.carrier:
            carrier = port.carrier
            port.carrier = None
            port.state = "EMPTY"
            port.reserved_by = None
            carrier.state = "IN_TRANSIT"
            carrier.location = None
            return carrier
        return None

    def step(self, dt_sim: float, current_time: float, recipes: Dict[str, Any], analytics_tracker: Any = None):
        """Advances machine logic, processing, backpressure checks, and metrics."""
        # 1. Sink Role: destroy completed carriers and record throughput
        if self.machine_role == "sink":
            for port in self.ports:
                if port.carrier:
                    c = port.carrier
                    port.carrier = None
                    port.state = "EMPTY"
                    self.processed_count += 1
                    total_time = current_time - c.creation_time
                    if analytics_tracker:
                        analytics_tracker.record_job_completion(total_time, c.id)
            self.state = "IDLE"
            self.starved_time += dt_sim
            return

        # 2. Source Role: generate carriers into UNLOAD port if space exists
        if self.machine_role == "source":
            unload_port = self.get_ready_unload_port()
            empty_unload = self.get_available_load_port() or next((p for p in self.ports if p.state == "EMPTY"), None)

            if current_time >= self.next_generation_time:
                if empty_unload:
                    # Pick recipe from generator config
                    recipe_id = "1"
                    if self.generators:
                        g = self.generators[0]
                        recipe_id = g.get("recipe_id") or "1"

                    cid = f"LOT_{int(current_time)}_{random.randint(100, 999)}"
                    carrier = Carrier(cid, recipe_id=recipe_id, creation_time=current_time)
                    carrier.location = empty_unload.node_idx
                    empty_unload.carrier = carrier
                    empty_unload.state = "OCCUPIED"

                    # Schedule next generation
                    interval = self.generation_interval
                    if self.generation_random:
                        interval *= random.uniform(0.7, 1.3)
                    self.next_generation_time = current_time + max(0.5, interval)
                    self.state = "PROCESSING"
                    self.active_processing_time += dt_sim
                else:
                    # BACKPRESSURE PAUSE: Ports full, pause generation!
                    self.state = "PAUSED_BACKPRESSURE"
                    self.blocked_time += dt_sim
            else:
                self.state = "IDLE"
                self.starved_time += dt_sim
            return

        # 3. Standard Processing Machine:
        # Check completed processing items
        finished = [p for p in self.processing if p["finish_time"] <= current_time]
        for item in finished:
            carrier = item["carrier"]
            self.processing.remove(item)
            carrier.advance_step(self.name, current_time)
            self.processed_count += 1
            self.output_buffer.append(carrier)

        # Move from output buffer into UNLOAD port
        unload_port = next((p for p in self.ports if p.type in ("UNLOAD", "BIDIRECTIONAL")), None)
        if unload_port and unload_port.state == "EMPTY" and self.output_buffer:
            ready_c = self.output_buffer.pop(0)
            unload_port.carrier = ready_c
            unload_port.state = "OCCUPIED"
            ready_c.location = unload_port.node_idx

        # Start new processing if capacity available
        while self.intake_buffer and len(self.processing) < self.capacity:
            c = self.intake_buffer.pop(0)
            self.processing.append({
                "carrier": c,
                "finish_time": current_time + self.process_time
            })

        # Update State & Metrics
        if self.output_buffer or (unload_port and unload_port.state == "OCCUPIED" and len(self.intake_buffer) >= self.capacity):
            # Machine is blocked or pausing because output is full and cannot take more
            self.state = "PAUSED_BACKPRESSURE"
            self.blocked_time += dt_sim
        elif self.processing:
            self.state = "PROCESSING"
            self.active_processing_time += dt_sim
        else:
            self.state = "IDLE"
            self.starved_time += dt_sim
