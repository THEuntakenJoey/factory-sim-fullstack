import asyncio
import time
import heapq
from typing import Callable, Any, Tuple
from .state import FactoryState

class SimulationEngine:
    def __init__(self, state: FactoryState):
        self.state = state
        self.running = False
        self.sim_time = 0.0
        self.time_scale = 1.0  # e.g., 2.0 = 2x real time
        self.tick_rate = 30  # FPS for OHT kinematics
        
        # DES Event Queue: (scheduled_time, event_id, callback)
        self.event_queue = []
        self._event_id_counter = 0

    def schedule_event(self, delay: float, callback: Callable):
        """Schedule an event to occur 'delay' seconds from current sim_time."""
        scheduled_time = self.sim_time + delay
        heapq.heappush(self.event_queue, (scheduled_time, self._event_id_counter, callback))
        self._event_id_counter += 1

    def _process_events(self):
        """Execute all events that are due at the current sim_time."""
        while self.event_queue and self.event_queue[0][0] <= self.sim_time:
            _, _, callback = heapq.heappop(self.event_queue)
            callback()

    async def run(self):
        self.running = True
        dt_real = 1.0 / self.tick_rate
        
        while self.running:
            start_time = time.time()
            
            # 1. Update Sim Time
            dt_sim = dt_real * self.time_scale
            self.sim_time += dt_sim
            
            # 2. Process DES Events (Machines, Logistics)
            self._process_events()
            
            # 3. Continuous Tick for OHT Kinematics
            for agent in self.state.agents.values():
                agent.update(dt_sim)
                
            # 4. Optional: Dispatcher Logic
            # In a full simulation, the MCS might poll for idle agents here
            self.state.mcs.spin()
                
            # 5. Sleep to maintain tick rate
            elapsed = time.time() - start_time
            sleep_time = max(0, dt_real - elapsed)
            await asyncio.sleep(sleep_time)

    def stop(self):
        self.running = False
