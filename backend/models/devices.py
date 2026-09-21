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
        self.state_last_change_time = 0.0
        self.state_durations: Dict[str, float] = {
            "IDLE": 0.0,
            "PROCESSING": 0.0,
            "PAUSED_BACKPRESSURE": 0.0
        }
        self._latest_sim_time = 0.0

        # Analytics tracking
        self.processed_count = 0

    def set_state(self, new_state: str, current_time: float):
        """Transitions state event-driven and accumulates duration."""
        self._latest_sim_time = max(self._latest_sim_time, current_time)
        if new_state == self.state:
            return
        dt = max(0.0, current_time - self.state_last_change_time)
        self.state_durations[self.state] = self.state_durations.get(self.state, 0.0) + dt
        self.state = new_state
        self.state_last_change_time = current_time

    def get_state_duration(self, state_name: str, current_time: float) -> float:
        """Returns total seconds spent in state_name up to current_time."""
        self._latest_sim_time = max(self._latest_sim_time, current_time)
        accum = self.state_durations.get(state_name, 0.0)
        if self.state == state_name:
            accum += max(0.0, current_time - self.state_last_change_time)
        return accum

    @property
    def active_processing_time(self) -> float:
        return self.get_state_duration("PROCESSING", self._latest_sim_time)

    @active_processing_time.setter
    def active_processing_time(self, val: float):
        self.state_durations["PROCESSING"] = val

    @property
    def blocked_time(self) -> float:
        return self.get_state_duration("PAUSED_BACKPRESSURE", self._latest_sim_time)

    @blocked_time.setter
    def blocked_time(self, val: float):
        self.state_durations["PAUSED_BACKPRESSURE"] = val

    @property
    def starved_time(self) -> float:
        return self.get_state_duration("IDLE", self._latest_sim_time)

    @starved_time.setter
    def starved_time(self, val: float):
        self.state_durations["IDLE"] = val

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

    def receive_cargo(self, port_idx: int, carrier: Carrier, sim_engine: Optional[Any] = None) -> bool:
        if 0 <= port_idx < len(self.ports):
            port = self.ports[port_idx]
            port.carrier = carrier
            port.state = "OCCUPIED"
            carrier.location = port.node_idx
            carrier.state = "STORED"
            self.pending_deliveries = max(0, self.pending_deliveries - 1)

            # 1. Sink Role: consume carrier immediately and record metrics
            if self.machine_role == "sink":
                port.carrier = None
                port.state = "EMPTY"
                self.processed_count += 1
                curr_t = sim_engine.sim_time if sim_engine else 0.0
                total_time = curr_t - carrier.creation_time
                if sim_engine and hasattr(sim_engine, "state") and getattr(sim_engine.state, "analytics", None):
                    sim_engine.state.analytics.record_job_completion(total_time, carrier.id)
                if sim_engine and hasattr(sim_engine, "state") and hasattr(sim_engine.state, "notify_slot_freed"):
                    sim_engine.state.notify_slot_freed(self, sim_engine)
                return True

            # 2. Normal Processing Machine: move from LOAD port into intake buffer
            port.carrier = None
            port.state = "EMPTY"
            self.intake_buffer.append(carrier)

            # Notify upstream that LOAD port is available again
            if sim_engine and hasattr(sim_engine, "state") and hasattr(sim_engine.state, "notify_slot_freed"):
                sim_engine.state.notify_slot_freed(self, sim_engine)

            # Trigger processing start
            if sim_engine:
                self.try_start_processing(sim_engine)
            return True
        return False

    def try_start_processing(self, sim_engine: Any):
        """Starts processing items from intake buffer up to machine capacity."""
        if not sim_engine:
            return

        while self.intake_buffer and len(self.processing) < self.capacity:
            c = self.intake_buffer.pop(0)
            item_record = {
                "carrier": c,
                "finish_time": sim_engine.sim_time + self.process_time
            }
            self.processing.append(item_record)
            self.set_state("PROCESSING", sim_engine.sim_time)

            # Schedule DES finish event
            sim_engine.schedule_event(
                self.process_time,
                lambda rec=item_record: self._on_item_finished(rec, sim_engine)
            )

    def _on_item_finished(self, item_record: Dict[str, Any], sim_engine: Any):
        """Called by DES engine when an item finishes its processing time."""
        if item_record in self.processing:
            self.processing.remove(item_record)

        carrier = item_record["carrier"]
        carrier.advance_step(self.name, sim_engine.sim_time)
        self.processed_count += 1
        self.output_buffer.append(carrier)

        # Move to UNLOAD port if port is empty
        unload_port = next((p for p in self.ports if p.type in ("UNLOAD", "BIDIRECTIONAL")), None)
        if unload_port and unload_port.state == "EMPTY" and self.output_buffer:
            ready_c = self.output_buffer.pop(0)
            unload_port.carrier = ready_c
            unload_port.state = "OCCUPIED"
            ready_c.location = unload_port.node_idx

            # Reactive check: verify downstream and request transport
            if hasattr(sim_engine, "state") and hasattr(sim_engine.state, "check_downstream_and_request_transport"):
                sim_engine.state.check_downstream_and_request_transport(self, unload_port, ready_c, sim_engine)

        # Check if intake slot was freed
        if hasattr(sim_engine, "state") and hasattr(sim_engine.state, "notify_slot_freed"):
            sim_engine.state.notify_slot_freed(self, sim_engine)

        # Chain next item in intake buffer if available
        self.try_start_processing(sim_engine)

        # Update operational state event-driven
        curr_t = sim_engine.sim_time
        if self.output_buffer or (unload_port and unload_port.state == "OCCUPIED" and len(self.intake_buffer) >= self.capacity):
            self.set_state("PAUSED_BACKPRESSURE", curr_t)
        elif self.processing:
            self.set_state("PROCESSING", curr_t)
        else:
            self.set_state("IDLE", curr_t)

    def retrieve_cargo(self, port_idx: Optional[int] = None, sim_engine: Optional[Any] = None) -> Optional[Carrier]:
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

            # Move next finished item from output buffer into unload port if available
            if self.output_buffer:
                next_c = self.output_buffer.pop(0)
                port.carrier = next_c
                port.state = "OCCUPIED"
                next_c.location = port.node_idx

                if sim_engine and hasattr(sim_engine, "state") and hasattr(sim_engine.state, "check_downstream_and_request_transport"):
                    sim_engine.state.check_downstream_and_request_transport(self, port, next_c, sim_engine)

            # Slot freed! Trigger upstream notification
            eng = sim_engine
            if eng and hasattr(eng, "state") and hasattr(eng.state, "notify_slot_freed"):
                eng.state.notify_slot_freed(self, eng)

            # If source generator was paused due to full unload port, restart generator
            if self.machine_role == "source" and eng:
                self.start_generator(eng)

            # If backpressured, try resuming intake
            if self.state == "PAUSED_BACKPRESSURE" and not self.output_buffer and eng:
                if self.processing:
                    self.set_state("PROCESSING", eng.sim_time)
                else:
                    self.try_start_processing(eng)
                    if not self.processing:
                        self.set_state("IDLE", eng.sim_time)

            return carrier
        return None

    def start_generator(self, sim_engine: Any):
        """Starts or re-arms the periodic lot generator for source machines."""
        if self.machine_role != "source" or not sim_engine:
            return

        def _do_generate():
            unload_port = self.get_ready_unload_port()
            empty_unload = self.get_available_load_port() or next((p for p in self.ports if p.state == "EMPTY"), None)
            curr_t = sim_engine.sim_time

            if empty_unload:
                recipe_id = "1"
                if self.generators:
                    g = self.generators[0]
                    recipe_id = g.get("recipe_id") or "1"

                recipes_dict = getattr(getattr(sim_engine, "state", None), "recipes", {})
                if recipes_dict and recipe_id not in recipes_dict:
                    recipe_id = list(recipes_dict.keys())[0]

                cid = f"LOT_{int(curr_t)}_{random.randint(100, 999)}"
                carrier = Carrier(cid, recipe_id=recipe_id, creation_time=curr_t)
                carrier.location = empty_unload.node_idx
                empty_unload.carrier = carrier
                empty_unload.state = "OCCUPIED"

                self.set_state("PROCESSING", curr_t)

                # Check downstream and request transport
                if hasattr(sim_engine, "state") and hasattr(sim_engine.state, "check_downstream_and_request_transport"):
                    sim_engine.state.check_downstream_and_request_transport(self, empty_unload, carrier, sim_engine)

                # Schedule next generation
                interval = self.generation_interval
                if self.generation_random:
                    interval *= random.uniform(0.7, 1.3)
                sim_engine.schedule_event(max(0.5, interval), _do_generate)
            else:
                # UNLOAD port full -> pause generation (backpressure)
                self.set_state("PAUSED_BACKPRESSURE", curr_t)

        sim_engine.schedule_event(0.1, _do_generate)

    def step(self, dt_sim: float, current_time: float, recipes: Dict[str, Any], analytics_tracker: Any = None):
        """State durations are tracked event-driven on transitions."""
        self._latest_sim_time = current_time

