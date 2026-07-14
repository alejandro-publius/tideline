"""In-process metrics, exposed at /api/metrics in Prometheus text format.

Hand-rolled on purpose: this app needs a handful of counters, and a dict
behind a lock is the whole implementation — no client library, no metrics
process. If histograms or multi-process aggregation ever matter, swap in
prometheus-client; the exposition format is already compatible.
"""

import threading

from starlette.types import ASGIApp, Message, Receive, Scope, Send


class Counter:
    """A monotonically increasing counter, optionally split by labels."""

    def __init__(self, name: str, help_text: str, label_names: tuple[str, ...] = ()) -> None:
        self.name = name
        self.help_text = help_text
        self.label_names = label_names
        self._values: dict[tuple[str, ...], int] = {}
        self._lock = threading.Lock()

    def inc(self, **labels: str | int) -> None:
        key = tuple(str(labels[name]) for name in self.label_names)
        with self._lock:
            self._values[key] = self._values.get(key, 0) + 1

    def samples(self) -> dict[tuple[str, ...], int]:
        with self._lock:
            return dict(self._values)

    def reset(self) -> None:
        with self._lock:
            self._values.clear()


REGISTRY: list[Counter] = []


def _counter(name: str, help_text: str, label_names: tuple[str, ...] = ()) -> Counter:
    counter = Counter(name, help_text, label_names)
    REGISTRY.append(counter)
    return counter


HTTP_REQUESTS = _counter(
    "tideline_http_requests_total",
    "API requests handled, by route template and status code.",
    ("method", "path", "status"),
)
NOAA_REQUESTS = _counter(
    "tideline_noaa_requests_total",
    "Upstream NOAA fetches, by final outcome.",
    ("outcome",),  # ok | error
)
NOAA_RETRIES = _counter(
    "tideline_noaa_retries_total",
    "NOAA fetch attempts retried after a transient failure.",
)
CACHE_LOOKUPS = _counter(
    "tideline_cache_lookups_total",
    "Series cache lookups, by where the data came from.",
    ("result",),  # noaa (miss) | cache (hit) | stale (miss, NOAA down)
)
RATE_LIMITED = _counter(
    "tideline_rate_limited_total",
    "Requests rejected with 429 by the rate limiter.",
)


def render() -> str:
    """All counters in Prometheus exposition format."""
    lines: list[str] = []
    for counter in REGISTRY:
        lines.append(f"# HELP {counter.name} {counter.help_text}")
        lines.append(f"# TYPE {counter.name} counter")
        samples = counter.samples()
        if not counter.label_names:
            lines.append(f"{counter.name} {samples.get((), 0)}")
            continue
        for key, value in sorted(samples.items()):
            labels = ",".join(
                f'{name}="{v}"' for name, v in zip(counter.label_names, key, strict=True)
            )
            lines.append(f"{counter.name}{{{labels}}} {value}")
    return "\n".join(lines) + "\n"


def reset() -> None:
    """Zero every counter (test isolation)."""
    for counter in REGISTRY:
        counter.reset()


class MetricsMiddleware:
    """Counts every /api request by method, route template, and status.

    The label is the matched route's template (e.g. /api/stations/{station_id}/
    readings), not the raw URL — otherwise every station id and query string
    would mint a new label and the series count would grow without bound.
    Unmatched paths (scanners probing /api/anything) collapse into one label
    for the same reason.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope["path"].startswith("/api"):
            await self.app(scope, receive, send)
            return

        status = {"code": 500}  # if the app crashes before responding, count it as a 500

        async def record_status(message: Message) -> None:
            if message["type"] == "http.response.start":
                status["code"] = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, record_status)
        finally:
            route = scope.get("route")  # set by FastAPI once routing matches
            path = route.path if route is not None else "(unmatched)"
            HTTP_REQUESTS.inc(method=scope["method"], path=path, status=status["code"])
