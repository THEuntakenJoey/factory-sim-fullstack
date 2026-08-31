import heapq

from backend.core.machine import Machine, MachinePort
from backend.core.recipe import Recipe, Content

class MockEngine:
    def __init__(self):
        self.sim_time = 0.0
        self.event_queue = []
        self._event_id_counter = 0
        
    def schedule_event(self, delay, callback):
        scheduled_time = self.sim_time + delay
        heapq.heappush(self.event_queue, (scheduled_time, self._event_id_counter, callback))
        self._event_id_counter += 1
        print(f"[Time: {self.sim_time:.1f}] Scheduled event for {scheduled_time:.1f}")
        
    def run_until(self, target_time):
        print(f"\n--- Running until {target_time:.1f} ---")
        while self.event_queue and self.event_queue[0][0] <= target_time:
            time, _, callback = heapq.heappop(self.event_queue)
            self.sim_time = time
            print(f"[Time: {self.sim_time:.1f}] Executing Event...")
            callback()
        self.sim_time = target_time
        print(f"--- Reached {target_time:.1f} ---\n")

def test_batch_machine():
    engine = MockEngine()
    
    # 1. Create a Batch machine (capacity 2, process_time 5.0)
    m = Machine("M1", "PROCESS", capacity=2, process_mode="batch", intake_mode="continuous", process_time=5.0, schedule_event_cb=engine.schedule_event)
    
    recipe = Recipe(["PROCESS", "INSPECT"])
    c1 = Content("C1", recipe)
    c2 = Content("C2", recipe)
    c3 = Content("C3", recipe)
    
    print("Adding C1 to machine intake")
    m.add_to_intake(c1)
    
    engine.run_until(2.0)
    
    print("Adding C2 to machine intake (should trigger batch start)")
    m.add_to_intake(c2)
    
    print("Adding C3 to machine intake (should wait in queue)")
    m.add_to_intake(c3)
    
    assert m.is_processing == True
    assert len(m.processing) == 2
    assert len(m.intake_buffer) == 1
    
    engine.run_until(10.0)
    
    assert m.is_processing == False
    assert len(m.processing) == 0
    assert len(m.output_buffer) == 2
    assert c1 in m.output_buffer
    assert c2 in m.output_buffer
    print("Batch test passed!")

def test_continuous_machine():
    engine = MockEngine()
    
    m = Machine("M2", "PROCESS", capacity=2, process_mode="continuous", intake_mode="continuous", process_time=5.0, schedule_event_cb=engine.schedule_event)
    
    recipe = Recipe(["PROCESS", "INSPECT"])
    c1 = Content("C1", recipe)
    c2 = Content("C2", recipe)
    c3 = Content("C3", recipe)
    
    print("Adding C1 and C2 (should start processing independently)")
    m.add_to_intake(c1)
    m.add_to_intake(c2)
    
    assert len(m.processing) == 2
    
    print("Adding C3 (should wait since capacity is 2)")
    m.add_to_intake(c3)
    assert len(m.intake_buffer) == 1
    
    engine.run_until(4.0)
    assert len(m.output_buffer) == 0
    
    engine.run_until(6.0) # Process time is 5.0, so at 5.0 they finish, and C3 starts.
    assert len(m.output_buffer) == 2
    assert len(m.processing) == 1
    assert c3 in m.processing
    
    engine.run_until(11.0)
    assert len(m.output_buffer) == 3
    print("Continuous test passed!")

if __name__ == "__main__":
    test_batch_machine()
    test_continuous_machine()
