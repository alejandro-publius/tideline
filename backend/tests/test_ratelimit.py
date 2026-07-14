from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.ratelimit import RateLimiter, RateLimitMiddleware, client_key


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def test_bucket_allows_burst_then_refuses():
    clock = FakeClock()
    limiter = RateLimiter(per_minute=3, clock=clock)

    assert all(limiter.allow("1.2.3.4")[0] for _ in range(3))
    allowed, retry_after = limiter.allow("1.2.3.4")
    assert not allowed
    assert retry_after > 0


def test_bucket_refills_over_time():
    clock = FakeClock()
    limiter = RateLimiter(per_minute=60, clock=clock)  # 1 token/second

    for _ in range(60):
        limiter.allow("1.2.3.4")
    assert not limiter.allow("1.2.3.4")[0]

    clock.advance(2.0)
    assert limiter.allow("1.2.3.4")[0]  # refilled ~2 tokens
    assert limiter.allow("1.2.3.4")[0]
    assert not limiter.allow("1.2.3.4")[0]


def test_clients_have_independent_buckets():
    clock = FakeClock()
    limiter = RateLimiter(per_minute=1, clock=clock)

    assert limiter.allow("1.1.1.1")[0]
    assert not limiter.allow("1.1.1.1")[0]
    assert limiter.allow("2.2.2.2")[0]  # a noisy neighbor must not starve others


def test_idle_buckets_are_pruned():
    clock = FakeClock()
    limiter = RateLimiter(per_minute=10, clock=clock)

    limiter.allow("1.1.1.1")
    clock.advance(300)
    limiter.allow("2.2.2.2")  # triggers the periodic prune

    assert "1.1.1.1" not in limiter._buckets  # idle bucket dropped, map stays bounded
    assert "2.2.2.2" in limiter._buckets


def test_client_key_prefers_forwarded_for_then_socket():
    scope = {
        "headers": [(b"x-forwarded-for", b"203.0.113.9, 10.0.0.1")],
        "client": ("127.0.0.1", 1),
    }
    assert client_key(scope) == "203.0.113.9"
    assert client_key({"headers": [], "client": ("127.0.0.1", 1)}) == "127.0.0.1"
    assert client_key({"headers": [], "client": None}) == "unknown"


def _throttled_app(per_minute: int, clock: FakeClock) -> TestClient:
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware, limiter=RateLimiter(per_minute, clock=clock))

    @app.get("/api/ping")
    def ping() -> dict[str, bool]:
        return {"ok": True}

    @app.get("/api/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return TestClient(app)


def test_middleware_returns_429_with_retry_after():
    client = _throttled_app(per_minute=2, clock=FakeClock())

    assert client.get("/api/ping").status_code == 200
    assert client.get("/api/ping").status_code == 200
    resp = client.get("/api/ping")
    assert resp.status_code == 429
    assert int(resp.headers["Retry-After"]) >= 1
    assert "detail" in resp.json()


def test_healthz_is_exempt_even_when_budget_is_exhausted():
    """A throttled client must never make the platform think the app is down."""
    client = _throttled_app(per_minute=1, clock=FakeClock())

    client.get("/api/ping")
    assert client.get("/api/ping").status_code == 429
    assert client.get("/api/healthz").status_code == 200


def test_main_app_serves_within_default_budget(client):
    """The real app wires the limiter in; normal traffic passes untouched."""
    for _ in range(5):
        assert client.get("/api/stations").status_code == 200
