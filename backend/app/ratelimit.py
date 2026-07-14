"""Per-client token-bucket rate limiting for the API.

In-process on purpose: the app runs as a single process, so shared state
in Redis would be pure overhead here (and the moment there are multiple
replicas, this module is the seam where a shared store slots in).
"""

import math
import threading
import time
from collections.abc import Callable

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from . import metrics

# Buckets idle this long are full again by definition — safe to drop.
PRUNE_IDLE_SECONDS = 120.0
PRUNE_INTERVAL_SECONDS = 60.0


class RateLimiter:
    """Classic token bucket per client: `per_minute` burst capacity,
    refilled continuously at `per_minute`/60 tokens per second.

    The bucket map is pruned periodically so a client cycling source
    addresses can't grow it without bound (the limiter must not be its
    own memory-exhaustion vector).
    """

    def __init__(self, per_minute: int, clock: Callable[[], float] = time.monotonic) -> None:
        self.capacity = float(per_minute)
        self.rate = per_minute / 60.0
        self.clock = clock
        self._buckets: dict[str, tuple[float, float]] = {}  # key -> (tokens, updated)
        self._lock = threading.Lock()
        self._last_prune = clock()

    def allow(self, key: str) -> tuple[bool, float]:
        """Spend one token for `key`. Returns (allowed, retry_after_seconds)."""
        now = self.clock()
        with self._lock:
            if now - self._last_prune >= PRUNE_INTERVAL_SECONDS:
                self._prune(now)
            tokens, updated = self._buckets.get(key, (self.capacity, now))
            tokens = min(self.capacity, tokens + (now - updated) * self.rate)
            if tokens >= 1.0:
                self._buckets[key] = (tokens - 1.0, now)
                return True, 0.0
            self._buckets[key] = (tokens, now)
            return False, (1.0 - tokens) / self.rate

    def _prune(self, now: float) -> None:
        self._last_prune = now
        self._buckets = {
            key: bucket
            for key, bucket in self._buckets.items()
            if now - bucket[1] < PRUNE_IDLE_SECONDS
        }

    def reset(self) -> None:
        with self._lock:
            self._buckets.clear()


def client_key(scope: Scope) -> str:
    """Client identity used for the bucket key.

    Prefers the first X-Forwarded-For hop because in production the app sits
    behind Render's proxy, which sets that header; without a trusted proxy the
    header is spoofable, so direct deployments should rely on the socket
    address fallback (see docs/adr/0004).
    """
    for name, value in scope["headers"]:
        if name == b"x-forwarded-for":
            return value.decode("latin-1").split(",")[0].strip()
    client = scope.get("client")
    return client[0] if client else "unknown"


class RateLimitMiddleware:
    """Rejects /api requests beyond the per-client budget with a 429.

    /api/healthz is exempt so platform health checks can never be throttled
    into a false "service down". Static assets aren't limited either — the
    budget protects the part that does work (database + NOAA), not the CDN-able
    part.
    """

    EXEMPT_PATHS = frozenset({"/api/healthz"})

    def __init__(self, app: ASGIApp, limiter: RateLimiter) -> None:
        self.app = app
        self.limiter = limiter

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] != "http"
            or not scope["path"].startswith("/api")
            or scope["path"] in self.EXEMPT_PATHS
        ):
            await self.app(scope, receive, send)
            return

        allowed, retry_after = self.limiter.allow(client_key(scope))
        if allowed:
            await self.app(scope, receive, send)
            return

        metrics.RATE_LIMITED.inc()
        response = JSONResponse(
            {"detail": "Rate limit exceeded, slow down."},
            status_code=429,
            headers={"Retry-After": str(math.ceil(retry_after))},
        )
        await response(scope, receive, send)
