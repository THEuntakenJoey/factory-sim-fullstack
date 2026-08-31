from __future__ import annotations
import json
import random
import os
from collections import deque
from typing import TYPE_CHECKING, List, Dict, TypedDict, Optional, Tuple

if TYPE_CHECKING:
    from map_manager import MapManager
    from agent import OHTAgent
from virtual_objects import Container, VirtualMachine

# --- TYPE DEFINITION ---
class TransportRequest(TypedDict):
    cid: str
    u: int          # Start Node
    u_port_idx: int # Start Port
    v: int          # End Node
    v_port_idx: int # End Port

class VirtualMES:
    """
    The 'Boss'. Knows inventory and generates high-level Transport Requests.
    For this test, it implements the 'Mindless Shuffle' logic.
    """
    def __init__(self, map_mgr: MapManager, schema_path: str):
        self.map_mgr = map_mgr

        # 1. Load Schema
        if not os.path.exists(schema_path):
            raise FileNotFoundError(f"Schema not found: {schema_path}")
        with open(schema_path, 'r') as f:
            self.schema = json.load(f)

        # 2. Build Virtual Factory
        # Key: Node_ID (int), Value: VirtualMachine Object
        self.machines: Dict[int, VirtualMachine] = {}
        self._build_factory()

        # 3. Inventory
        self.containers: Dict[str, Container] = {}

    def _build_factory(self):
        """Iterates map waypoints and creates VirtualMachines based on schema."""
        for nid, wp_data in self.map_mgr.waypoints.items():
            w_type = wp_data.get('type')
            w_name = wp_data.get('id')

            # Look up config in schema
            if w_type in self.schema:
                config = self.schema[w_type]
                num_ports = config.get('ports', 1)

                vm = VirtualMachine(nid, w_name, w_type, num_ports, self)
                self.machines[nid] = vm
                # print(f"[MES] Built {w_name} ({w_type}) at Node {nid} with {num_ports} ports.")
                self.map_mgr.register_machine(nid, vm)

    def seed_inventory(self, amount: int, mix_ratio=0.5):
        """
        Populates empty ports with Containers.
        mix_ratio: Percentage of FOUPs vs Magazines.
        """
        # Find all empty ports across all machines
        available_spots = []
        for vm in self.machines.values():
            for port in vm.ports:
                if port.state == "EMPTY":
                    available_spots.append((vm, port))

        # Create Cargo
        count = min(amount, len(available_spots))
        if count == 0: return
       
        selected = random.sample(available_spots, count)

        for i, (vm, port) in enumerate(selected):
            # Determine Type
            c_type = "FOUP" if random.random() < mix_ratio else "MAGAZINE"
            c_id = f"{c_type}_{i:03d}"

            # Create Container
            c = Container(c_id, c_type, vm.node_id)

            # Place in Port
            port.container = c
            port.state = "OCCUPIED"

            self.containers[c_id] = c
            print(f"[MES] Seeded {c_id} at {vm.name} (Port {port.index})")

    def generate_transport_request(self) -> Optional[TransportRequest]:
        # 1. Source
        valid_sources = [c for c in self.containers.values() if c.state == "STORED"]
        if not valid_sources: return None

        target_c = random.choice(valid_sources)

        src_vm = self.machines.get(target_c.location)
        if not src_vm: return None
       
        src_port = src_vm.get_port_with_container(target_c.id)
        if not src_port: return None # Should not happen if state is synced

        # 2. Dest: Find an EMPTY Port (not at current loc)
        valid_dests = []
        for vm in self.machines.values():
            # Don't move to same machine
            if vm.node_id == target_c.location: continue

            p = vm.get_empty_port()
            if p: valid_dests.append((vm, p))

        if not valid_dests: return None

        dest_vm, dest_port = random.choice(valid_dests)

        # 3. Reserve
        target_c.state = "RESERVED"
        dest_port.state = "RESERVED"

        # We return the Port Index so MCS can tell the Agent exactly where to put it
        return {
            'cid': target_c.id,
            'u': target_c.location,
            'u_port_idx': src_port.index,
            'v': dest_vm.node_id,
            'v_port_idx': dest_port.index
        }

    def complete_transfer(self, cid, final_node, port_idx):
        """Called by MCS when Agent drops off cargo."""
        c = self.containers.get(cid)
        vm = self.machines.get(final_node)

        if c and vm:
            port = vm.ports[port_idx]

            # Update Container
            c.location = final_node
            c.state = "STORED"

            # Update Port
            port.container = c
            port.state = "OCCUPIED"

            # Clear old port?
            # (In reality, source port became empty when Pickup happened.
            #  We should have a pickup_callback too, but skipping for brevity.)
            print(f"[MES] Transfer Finalized: {cid} -> {vm.name} Port {port_idx}")

    def notify_pickup(self, cid):
        """Clean up source port."""
        c = self.containers.get(cid)
        # Note: Physical machine port is already cleared by VirtualMachine.retrieve_cargo
        # We just update the Container state here.
        if c:
            c.state = "MOVING"

    def notify_port_change(self, node_id, port_idx, new_state, cid=None):
        """
        Callback from VirtualMachine when physical state changes.
        Used to keep MES state in sync if hardware changes autonomously.
        """
        # For this simulation, complete_transfer handles the logic,
        # but this is required for the VirtualMachine class to not crash.
        pass

class VirtualMCS:
    """
    The 'Dispatcher'. Receives Requests from MES and assigns them to OHTs.
    """
    def __init__(self, agents: List[OHTAgent], mes: VirtualMES):
        self.agents = agents # List of OHTAgent objects
        self.mes = mes       # Reference back to MES for updates
        self.job_queue: deque[TransportRequest] = deque()

    def add_request(self, request: TransportRequest):
        """Request format: (cid, start_node, end_node)"""
        self.job_queue.append(request)
        print(f"[MCS] Job Queued: {request['cid']} ({request['u']} -> {request['v']})")

    def spin(self):
        """Main dispatch loop. Call this every frame."""
        if not self.job_queue: return

        # Try to assign the next job
        request = self.job_queue[0] # Peek

        # 1. Find Best Agent
        # Find Agent
        agent = self._find_agent(request['u'])
        if agent:
            self.job_queue.popleft()
            self._dispatch(agent, request)
        else:
            # No agents available, wait for next tick
            pass

    def _find_agent(self, target_node):
        candidates = [a for a in self.agents if a.state == "IDLE" and not a.mission_queue]

        if not candidates: return None

        # In a real system, we'd calculate path distance.
        # For now, just pick the first one or random.
        return candidates[0]

    def _dispatch(self, agent: OHTAgent, req: TransportRequest):
        cid = req['cid']
        print(f"[MCS] Dispatching {cid} to Agent")

        # 1. Move to Source
        agent.add_mission("MOVE", req['u'])

        # 2. Pickup
        def on_pickup():
            self.mes.notify_pickup(cid)

        agent.add_mission("ACTION", type="PICKUP",
                          port_indices=[req['u_port_idx']],
                          on_complete=on_pickup)

        # 3. Move to Dest
        agent.add_mission("MOVE", req['v'])

        # 4. Dropoff
        def on_dropoff():
            self.mes.complete_transfer(cid, req['v'], req['v_port_idx'])

        agent.add_mission("ACTION", type="DROPOFF",
                          port_indices=[req['v_port_idx']],
                          cargo_ids=[cid], # DROPOFF needs cargo ID
                          on_complete=on_dropoff)

    def generate_smart_batch_moves(self):
        """
        Scans machines for Dual-Move opportunities.
        """
        for vm in self.mes.machines.values():
            # 1. Check for Dual Pickup
            pairs = vm.get_valid_dual_operations()
            for (idx_a, idx_b) in pairs:
                cid_a = vm.ports[idx_a].container.id
                cid_b = vm.ports[idx_b].container.id

                # Create a "Batch Mission"
                # (Logic to find a destination that ALSO has 2 empty slots...)
                dest_vm, dest_pair = self._find_dual_capacity_machine()

                if dest_vm:
                    self._dispatch_dual_transfer(vm, (idx_a, idx_b), (cid_a, cid_b), dest_vm, dest_pair)
                    return # Dispatched one, break to next tick

    def _find_dual_capacity_machine(self) -> Tuple[Optional[VirtualMachine], Optional[Tuple[int, int]]]:
        """
        Scans all machines to find one with adjacent empty ports (e.g. 0 and 1).
        Returns: (VirtualMachine, (port_idx_a, port_idx_b)) or (None, None)
        """
        for vm in self.mes.machines.values():
            pairs = vm.get_valid_dual_dropoff_slots() # Uses the helper we wrote in virtual_objects
            if pairs:
                # Found a machine with space!
                return vm, pairs[0]
        return None, None

    def _dispatch_dual_transfer(self,
                              src_vm: VirtualMachine,
                              src_ports: Tuple[int, int],
                              cids: Tuple[str, str],
                              dest_vm: VirtualMachine,
                              dest_ports: Tuple[int, int]):
       
        # 1. Find Agent
        agent = self._find_agent(src_vm.node_id)
        if not agent:
            return # Retry next frame

        print(f"[MCS] Dispatching DUAL BATCH {cids} to Agent")

        # 2. Reserve Resources IMMEDIATELY (Prevent Double Dispatch)
        # Source
        src_vm.ports[src_ports[0]].container.state = "RESERVED"
        src_vm.ports[src_ports[1]].container.state = "RESERVED"
       
        # Dest
        dest_vm.ports[dest_ports[0]].state = "RESERVED"
        dest_vm.ports[dest_ports[1]].state = "RESERVED"

        # 3. Build Missions
        # A. Move to Source
        agent.add_mission("MOVE", src_vm.node_id)
       
        # B. Pickup Pair
        def on_pickup_dual():
            self.mes.notify_pickup(cids[0])
            self.mes.notify_pickup(cids[1])
           
        agent.add_mission("ACTION", type="PICKUP",
                          port_indices=list(src_ports),
                          on_complete=on_pickup_dual)
       
        # C. Move to Dest
        agent.add_mission("MOVE", dest_vm.node_id)
       
        # D. Dropoff Pair
        def on_dropoff_dual():
            self.mes.complete_transfer(cids[0], dest_vm.node_id, dest_ports[0])
            self.mes.complete_transfer(cids[1], dest_vm.node_id, dest_ports[1])
           
        agent.add_mission("ACTION", type="DROPOFF",
                          port_indices=list(dest_ports),
                          cargo_ids=list(cids),
                          on_complete=on_dropoff_dual)
