import asyncio
import time
import heapq
from typing import Callable, Any, List

class SimulationEngine:
    """
    Discrete-Event Simulation (DES) Engine.
    Coordinates event scheduling, continuous kinematic interpolation,
    machine processing, backpressure propagation, and metric collection.
    """
    def __init__(self, state: Any):
        self.state = state
        self.running = False
        self.sim_time = 0.0
        self.time_scale = 1.0   # 1.0 = real time, 2.0 = 2x, 0.0 = paused
        self.tick_rate = 30     # 30 FPS broadcast/coordination rate
        
        # Priority queue for DES events: (scheduled_time, event_id, callback)
        self.event_queue: List[Any] = []
        self._event_id_counter = 0

        # Link engine reference to all agents for traffic nudging
        if hasattr(self.state, "agents"):
            for a in self.state.agents.values():
                a.sim_engine = self

    def reset(self):
        self.sim_time = 0.0
        self.event_queue.clear()
        self._event_id_counter = 0
        if hasattr(self.state, "agents"):
            for a in self.state.agents.values():
                a.sim_engine = self
        if hasattr(self.state, "analytics"):
            self.state.analytics.reset()


    def schedule_event(self, delay: float, callback: Callable):
        """Schedules a callback to fire at (current_sim_time + delay)."""
        scheduled_time = self.sim_time + max(0.0, delay)
        heapq.heappush(self.event_queue, (scheduled_time, self._event_id_counter, callback))
        self._event_id_counter += 1

    def _process_events(self):
        """Executes all DES events that are due at or before the current sim_time."""
        while self.event_queue and self.event_queue[0][0] <= self.sim_time:
            _, _, callback = heapq.heappop(self.event_queue)
            try:
                callback()
            except Exception as e:
                print(f"Error executing DES event: {e}")

    def step(self, dt: float = 0.1):
        """Advances simulation by a fixed time step when paused."""
        self.sim_time += dt
        self._process_events()

        # Step machines
        for m in self.state.machines.values():
            m.step(dt, self.sim_time, self.state.recipes, self.state.analytics)

        # Step agents & record track analytics
        for a in self.state.agents.values():
            a.update_metrics(dt, self.sim_time)
            # If agent is in traffic jam (waiting for block or creeping < 0.3 m/s)
            if a.state == "WAITING_BLOCK" or (a.state in ("EN_ROUTE_PICKUP", "EN_ROUTE_DROPOFF") and a.speed < 0.3):
                if a.current_block and hasattr(self.state, "analytics"):
                    self.state.analytics.record_segment_jam(a.current_block, dt)

        # Dispatcher scan
        self.state.dispatcher.spin(
            self.state.agents,
            self.state.machines,
            self.state.recipes,
            self,
            self.state.analytics
        )

    async def run(self):
        self.running = True
        dt_real = 1.0 / self.tick_rate

        while self.running:
            start_time = time.time()

            if self.time_scale > 0.0:
                dt_sim = dt_real * self.time_scale
                self.sim_time += dt_sim

                # 1. Process DES Events (Arrivals, Releases, Hoist Actions)
                self._process_events()

                # 2. Step Machines (Processing, Backpressure Pausing, Sinks)
                for m in self.state.machines.values():
                    m.step(dt_sim, self.sim_time, self.state.recipes, self.state.analytics)

                # 3. Step Agents & Record Jam Metrics
                for a in self.state.agents.values():
                    a.update_metrics(dt_sim, self.sim_time)
                    if a.state == "WAITING_BLOCK" or (a.state in ("EN_ROUTE_PICKUP", "EN_ROUTE_DROPOFF") and a.speed < 0.3):
                        if a.current_block and hasattr(self.state, "analytics"):
                            self.state.analytics.record_segment_jam(a.current_block, dt_sim)

                # 4. Dispatcher Periodic Spin (Closed-Loop Reservations)
                self.state.dispatcher.spin(
                    self.state.agents,
                    self.state.machines,
                    self.state.recipes,
                    self,
                    self.state.analytics
                )

            # Sleep to maintain tick rate
            elapsed = time.time() - start_time
            sleep_time = max(0.001, dt_real - elapsed)
            await asyncio.sleep(sleep_time)

    def stop(self):
        self.running = False
