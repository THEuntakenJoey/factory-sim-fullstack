class AnalyticsTracker:
    def __init__(self):
        self.throughput_count = 0
        self.wait_times = []
        self.utilization = {} # Machine ID -> float
        self.start_time = 0.0

    def record_job_completion(self, wait_time: float):
        self.throughput_count += 1
        self.wait_times.append(wait_time)

    def get_metrics(self, current_time: float):
        avg_wait = sum(self.wait_times) / len(self.wait_times) if self.wait_times else 0.0
        return {
            "throughput": self.throughput_count,
            "average_wait_time": avg_wait,
            "utilization": self.utilization
        }
