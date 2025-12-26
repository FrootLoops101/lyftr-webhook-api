"""Prometheus metrics collection and exposition."""

from typing import Dict


class MetricsCollector:
    """Collect and expose Prometheus metrics."""

    def __init__(self):
        # Counters: {(method, path, status): count}
        self.http_requests_total: Dict[tuple, int] = {}
        # Counters: {result: count}
        self.webhook_requests_total: Dict[str, int] = {}

    def increment_http_request(self, method: str, path: str, status: int) -> None:
        """Increment HTTP request counter."""
        key = (method, path, status)
        self.http_requests_total[key] = self.http_requests_total.get(key, 0) + 1

    def increment_webhook_request(self, result: str) -> None:
        """Increment webhook request counter by result."""
        self.webhook_requests_total[result] = (
            self.webhook_requests_total.get(result, 0) + 1
        )

    def render_prometheus(self) -> str:
        """Render metrics in Prometheus text exposition format."""
        lines = [
            "# HELP http_requests_total Total HTTP requests by method, path, and status",
            "# TYPE http_requests_total counter",
        ]

        for (method, path, status), count in sorted(
            self.http_requests_total.items()
        ):
            lines.append(
                f'http_requests_total{{method="{method}",path="{path}",status="{status}"}} {count}'
            )

        lines.append(
            "# HELP webhook_requests_total Total webhook requests by result"
        )
        lines.append("# TYPE webhook_requests_total counter")

        for result, count in sorted(self.webhook_requests_total.items()):
            lines.append(f'webhook_requests_total{{result="{result}"}} {count}')

        return "\n".join(lines) + "\n"


metrics = MetricsCollector()
