from app.service_clients import ServiceClientError


class FakeDeploymentClient:
    def __init__(self, deployments: list[dict] | None = None, raise_error: bool = False):
        self.deployments = deployments or []
        self.raise_error = raise_error
        self.call_count = 0

    def all_deployments(self, service_name: str) -> list[dict]:
        self.call_count += 1
        if self.raise_error:
            raise ServiceClientError("simulated deployment service failure")
        return self.deployments


class FakeIncidentClient:
    def __init__(self, incidents: list[dict] | None = None, raise_error: bool = False):
        self.incidents = incidents or []
        self.raise_error = raise_error
        self.call_count = 0

    def all_incidents(self, service_name: str) -> list[dict]:
        self.call_count += 1
        if self.raise_error:
            raise ServiceClientError("simulated incident service failure")
        return self.incidents


class FakeAlertClient:
    def __init__(
        self,
        rules: list[dict] | None = None,
        alerts: list[dict] | None = None,
        raise_error: bool = False,
    ):
        self.rules = rules or []
        self.alerts = alerts or []
        self.raise_error = raise_error
        self.call_count = 0

    def all_alerts(self, service_name: str) -> tuple[list[dict], list[dict]]:
        self.call_count += 1
        if self.raise_error:
            raise ServiceClientError("simulated alert service failure")
        return self.rules, self.alerts


class FakeCacheClient:
    """In-memory stand-in for RedisCacheClient (app/cache.py) -- no TTL
    expiry simulated (tests that care about TTL check what was PASSED to
    set(), not real elapsed time), and raise_on_get/raise_on_set let tests
    simulate a Redis outage to confirm the routers degrade to "compute
    fresh" rather than breaking.
    """

    def __init__(self, raise_on_get: bool = False, raise_on_set: bool = False):
        self.store: dict[str, str] = {}
        self.raise_on_get = raise_on_get
        self.raise_on_set = raise_on_set
        self.set_calls: list[tuple[str, str, int]] = []

    def get(self, key: str) -> str | None:
        if self.raise_on_get:
            # RedisCacheClient returns None on a Redis error rather than raising -- see app/cache.py
            return None
        return self.store.get(key)

    def set(self, key: str, value: str, ttl_seconds: int) -> None:
        self.set_calls.append((key, value, ttl_seconds))
        if self.raise_on_set:
            return  # same fail-open reasoning -- a set() failure is swallowed, not raised, see app/cache.py
        self.store[key] = value
