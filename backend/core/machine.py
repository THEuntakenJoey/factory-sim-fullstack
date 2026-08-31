from typing import Callable, List
from .recipe import Content

class MachinePort:
    def __init__(self, index: int, track_id: str, offset: float, node_idx: int):
        self.index = index
        self.track_id = track_id
        self.offset = offset
        self.node_idx = node_idx
        # Normally OHT drops a FOUP Container here, but we simplify to holding Content directly for logic simulation
        self.content = None 

class Machine:
    def __init__(self, machine_id: str, m_type: str, capacity: int, process_mode: str, intake_mode: str, process_time: float, schedule_event_cb: Callable):
        self.id = machine_id
        self.type = m_type
        self.capacity = capacity
        self.process_mode = process_mode  # "batch" or "continuous"
        self.intake_mode = intake_mode    # "batch" or "continuous"
        self.process_time = process_time
        
        self.ports: List[MachinePort] = []
        self.schedule_event = schedule_event_cb
        
        # Internal buffers
        self.intake_buffer: List[Content] = [] # Contents waiting to be processed
        self.processing: List[Content] = []    # Contents currently processing
        self.output_buffer: List[Content] = [] # Contents finished, waiting to be picked up
        
        # State
        self.is_processing = False
        
    def add_port(self, port: MachinePort):
        self.ports.append(port)
        
    def add_to_intake(self, content: Content):
        self.intake_buffer.append(content)
        self._try_start_processing()

    def _try_start_processing(self):
        if self.process_mode == "batch":
            if not self.is_processing and len(self.intake_buffer) >= self.capacity:
                # Start batch processing
                self.is_processing = True
                self.processing = self.intake_buffer[:self.capacity]
                self.intake_buffer = self.intake_buffer[self.capacity:]
                
                # Schedule completion
                self.schedule_event(self.process_time, self._on_batch_complete)
        elif self.process_mode == "continuous":
            # For continuous, each item processes independently
            while self.intake_buffer and len(self.processing) < self.capacity:
                content = self.intake_buffer.pop(0)
                self.processing.append(content)
                self.schedule_event(self.process_time, lambda c=content: self._on_continuous_item_complete(c))

    def _on_batch_complete(self):
        self.is_processing = False
        for c in self.processing:
            c.complete_step()
            self.output_buffer.append(c)
        self.processing = []
        self._try_start_processing()
        
    def _on_continuous_item_complete(self, content: Content):
        self.processing.remove(content)
        content.complete_step()
        self.output_buffer.append(content)
        self._try_start_processing()
