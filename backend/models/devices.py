from __future__ import annotations
from typing import TYPE_CHECKING, Optional, List, Tuple

if TYPE_CHECKING:
    from systems import VirtualMES

class Lot:
    """
    Represents the actual product material (Silicon Wafers).
    Future Expansion: This will track Recipe Steps, Wafer Count, and Process History.
    """
    def __init__(self, lot_id: str, product_type: str = "WAFER"):
        self.lot_id = lot_id
        self.product_type = product_type
        # Placeholder for future logic:
        # self.wafer_count = 25
        # self.current_recipe = None
        # self.history = []

class Container:
    """Represents a physical carrier (FOUP, Magazine)."""
    def __init__(self, c_id: str, c_type: str, location_id: int):
        self.id = c_id
        self.type = c_type        # "FOUP", "MAGAZINE", etc.
        self.location = location_id # Node ID
        self.state: str = "STORED"     # STORED, RESERVED, MOVING
       
        # content_id links to the actual product (Lot ID).
        # This allows the machine to say "I processed Lot X" regardless of which FOUP it came in.
        self.content_id: Optional[str] = None   

    def __repr__(self) -> str:
        return f"<{self.type} {self.id} @ {self.location}>"

class MachinePort:
    """A specific slot on a machine or OHB."""
    def __init__(self, index: int):
        self.index = index
        self.container: Optional[Container] = None # Holds Container object
        self.state: str = "EMPTY"  # EMPTY, OCCUPIED, RESERVED

class VirtualMachine:
    """
    Represents a Machine or OHB Rack located at a specific Map Node.
    Defined by the machine_schema.
    """
    def __init__(self, node_id: int, name: str, m_type: str, num_ports: int, mes_ref: VirtualMES):
        self.node_id = node_id   # Access Point on Track
        self.name = name         # e.g., "OHB_01"
        self.type = m_type       # e.g., "OHB", "LITHO"
        self.mes_ref = mes_ref

        # Create capacity based on schema
        self.ports: List[MachinePort] = [MachinePort(i) for i in range(num_ports)]

    def get_empty_port(self) -> Optional[MachinePort]:
        """Returns the first available EMPTY port object, or None."""
        for p in self.ports:
            if p.state == "EMPTY":
                return p
        return None

    def get_port_with_container(self, container_id: str) -> Optional[MachinePort]:
        """Finds the port containing a specific Container ID."""
        for p in self.ports:
            if p.container and p.container.id == container_id:
                return p
        return None

    def reserve_port(self, port_idx: int) -> bool:
        """
        Marks a port as RESERVED for incoming cargo.
        """
        if 0 <= port_idx < len(self.ports):
            p = self.ports[port_idx]
            if p.state == "EMPTY":
                p.state = "RESERVED"
                return True
        return False

    def retrieve_cargo(self, port_idx: Optional[int] = None) -> Optional[Container]:
        """
        Simulates OHT taking cargo FROM this machine.
        Returns the Container object if successful, None otherwise.
        """
        # Safety check for index bounds
        if port_idx is not None and (port_idx < 0 or port_idx >= len(self.ports)):
            return None

        # If port_idx is None, find first port with cargo (Helper behavior)
        target_port = None
        if port_idx is not None:
            target_port = self.ports[port_idx]
        else:
            # Auto-find first occupied port
            for p in self.ports:
                if p.state == "OCCUPIED" and p.container:
                    target_port = p
                    break
       
        if target_port and target_port.container:
            c = target_port.container

            # Physical Update
            target_port.container = None
            target_port.state = "EMPTY"

            # NOTIFY MES
            self.mes_ref.notify_port_change(self.node_id, target_port.index, "EMPTY")

            return c
        return None

    def receive_cargo(self, port_idx: int, container: Container) -> bool:
        """
        Simulates OHT putting cargo ONTO this machine.
        """
        if port_idx < 0 or port_idx >= len(self.ports):
            return False

        target_port = self.ports[port_idx]

        # Validation: Port must be EMPTY or RESERVED (by this job)
        if target_port.state != "EMPTY" and target_port.state != "RESERVED":
            # LOGIC NOTE: (!Empty AND !Reserved) == Occupied.
            # We return False (Failure) if it is Occupied.
            return False

        # Physical Update
        target_port.container = container
        target_port.state = "OCCUPIED"
        container.location = self.node_id

        # NOTIFY MES
        self.mes_ref.notify_port_change(self.node_id, target_port.index, "OCCUPIED", container.id)

        return True

    def get_valid_dual_operations(self) -> List[Tuple[int, int]]:
        """
        Returns list of adjacent (Port_A, Port_B) indices that are
        both OCCUPIED and ready for pickup.
        """
        ready_pairs = []

        # Assuming ports are a list [0, 1, 2, 3...] sorted linearly
        # We iterate through adjacent pairs
        for i in range(len(self.ports) - 1):
            p_a = self.ports[i]
            p_b = self.ports[i+1]

            # Check 1: Are they physically adjacent? (Simple index check usually suffices)
            # Check 2: Are they both OCCUPIED?
            if p_a.state == "OCCUPIED" and p_b.state == "OCCUPIED":
                # Check 3: Do they have Cargo?
                if p_a.container and p_b.container:
                    ready_pairs.append((i, i+1))

        return ready_pairs

    def get_valid_dual_dropoff_slots(self) -> List[Tuple[int, int]]:
        """
        Returns list of adjacent (Port_A, Port_B) indices that are
        both EMPTY.
        """
        empty_pairs = []
        for i in range(len(self.ports) - 1):
            p_a = self.ports[i]
            p_b = self.ports[i+1]
            # We strictly look for EMPTY here to generate *new* reservations.
            if p_a.state == "EMPTY" and p_b.state == "EMPTY":
                empty_pairs.append((i, i+1))
        return empty_pairs
