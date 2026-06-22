import threading
import time


class MetricsCollector:
    def __init__(self):
        self.lock = threading.Lock()
        self.total_requests = 0
        self.error_count = 0
        self.status_codes = {}
        self.total_latency_ms = 0
        self.start_time = time.time()

    def record_request(self, status_code, latency_ms):
        with self.lock:
            self.total_requests += 1
            self.total_latency_ms += latency_ms

            if status_code >= 400:
                self.error_count += 1

            if status_code not in self.status_codes:
                self.status_codes[status_code] = 0
            self.status_codes[status_code] += 1

    def get_metrics(self):
        with self.lock:
            uptime = time.time() - self.start_time
            return {
                "total_requests": self.total_requests,
                "error_count": self.error_count,
                "status_codes": self.status_codes.copy(),
                "total_latency_ms": self.total_latency_ms,
                "uptime_seconds": uptime,
                "avg_latency_ms": self.total_latency_ms / self.total_requests if self.total_requests > 0 else 0
            }
