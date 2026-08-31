import csv
import os

class LayoutDatabase:
    def __init__(self, machine_csv, types_csv):
        self.machines = {}      # ID -> Data
        self.nodes_to_machines = {} # NodeID -> MachineID
        self.types = {}         # TypeID -> Data

        self._load_types(types_csv)
        self._load_machines(machine_csv)

    def _load_types(self, path):
        # CSV Format: type_id, row_offsets, slot_offsets, z_height, valid_pairs
        with open(path, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                tid = row['type_id']
                self.types[tid] = {
                    "row_offsets": [float(x) for x in row['row_offsets'].split(';')],
                    "slot_offsets": [float(x) for x in row['slot_offsets'].split(';')],
                    "z_height": float(row['z_height']),
                    "valid_pairs": row['valid_pairs'] # Keep as string or parse if needed
                }

    def _load_machines(self, path):
        # CSV Format: machine_id, node_id, type_id, side_offset, orientation
        with open(path, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                mid = row['machine_id']
                nid = int(row['node_id'])
                self.machines[mid] = {
                    "node_id": nid,
                    "type": row['type_id'],
                    "side_offset": float(row['side_offset']),
                    "orientation": int(row['orientation'])
                }
                self.nodes_to_machines[nid] = mid

    def get_machine_node(self, machine_id):
        return self.machines[machine_id]['node_id']

    def calculate_detail(self, machine_id, row_idx, slot_indices):
        """
        The Detailer Function.
        Returns: { stop_offset, claw_center, side }
        """
        m = self.machines[machine_id]
        t = self.types[m['type']]

        # 1. Orientation Logic
        orient = m['orientation']

        # 2. Stop Offset (Traverse)
        # Note: row_idx is 0-based index from WMS (0=Row1, 1=Row2)
        raw_row_offset = t['row_offsets'][row_idx]
        stop_offset = raw_row_offset * orient

        # 3. Claw Logic (Side Shift)
        # Calculate global slot positions relative to machine center
        slot_positions = []
        for s_idx in slot_indices:
            # Slot offset defined in type
            s_off = t['slot_offsets'][s_idx]
            # Apply orientation (If flipped, left becomes right)
            s_off_oriented = s_off * orient
            # Add machine side offset (Global offset from track center)
            total_offset = m['side_offset'] + s_off_oriented
            slot_positions.append(total_offset)

        # Target is the average of required slot positions
        claw_center_target = sum(slot_positions) / len(slot_positions)

        return {
            "stop_offset": stop_offset,
            "claw_reach": claw_center_target,
            # If reach is positive, it's RIGHT side (relative to track forward)
            "side": "RIGHT" if claw_center_target > 0 else "LEFT"
        }