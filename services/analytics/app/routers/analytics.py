import json

from fastapi import APIRouter, HTTPException, status

from .. import aggregations
from ..cache import get_cache_client
from ..service_clients import ServiceClientError, get_alert_client, get_deployment_client, get_incident_client

router = APIRouter(prefix="/analytics", tags=["analytics"])

# Short enough that "the dashboard looked a few seconds stale" is never a
# real complaint, long enough to meaningfully absorb the traffic
# multiplication a polling dashboard causes -- see app/cache.py.
CACHE_TTL_SECONDS = 30


def _service_unavailable(exc: ServiceClientError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))


def _cached_report(cache_key: str, compute):
    """Cache-aside for the three single-source reports below: compute()
    either returns a plain dict or raises HTTPException (via
    _service_unavailable) -- if it raises, execution never reaches the
    cache.set() call, so a failure is never what gets cached. Only a
    genuinely successful result is.
    """
    cache = get_cache_client()
    hit = cache.get(cache_key)
    if hit is not None:
        return json.loads(hit)

    result = compute()
    cache.set(cache_key, json.dumps(result), CACHE_TTL_SECONDS)
    return result


@router.get("/deployments")
def deployment_report(service_name: str):
    def compute():
        try:
            deployments = get_deployment_client().all_deployments(service_name)
        except ServiceClientError as exc:
            raise _service_unavailable(exc) from exc
        return aggregations.deployment_stats(deployments)

    return _cached_report(f"analytics:deployments:{service_name}", compute)


@router.get("/incidents")
def incident_report(service_name: str):
    def compute():
        try:
            incidents = get_incident_client().all_incidents(service_name)
        except ServiceClientError as exc:
            raise _service_unavailable(exc) from exc
        return aggregations.incident_stats(incidents)

    return _cached_report(f"analytics:incidents:{service_name}", compute)


@router.get("/alerts")
def alert_report(service_name: str):
    def compute():
        try:
            rules, alerts = get_alert_client().all_alerts(service_name)
        except ServiceClientError as exc:
            raise _service_unavailable(exc) from exc
        return aggregations.alert_stats(rules, alerts)

    return _cached_report(f"analytics:alerts:{service_name}", compute)


@router.get("/overview")
def overview_report(service_name: str):
    # Not built on top of _cached_report: overview degrades PER-SECTION
    # instead of raising (one source being down shouldn't blank out the
    # other two -- see the section comment below), so "did this fail"
    # isn't a raised exception here, it's an "error" key inside an
    # otherwise-200 response. Caching that degraded result for
    # CACHE_TTL_SECONDS would extend a temporary upstream blip into a
    # longer visible outage than the blip itself was -- worse than not
    # caching at all -- so this endpoint checks for that shape of failure
    # explicitly before deciding whether to cache.
    cache = get_cache_client()
    cache_key = f"analytics:overview:{service_name}"
    hit = cache.get(cache_key)
    if hit is not None:
        return json.loads(hit)

    # Each source is independent -- one being down shouldn't blank out
    # the other two. Collected into a dict with an "error" key per
    # section instead of failing the whole request, same graceful-
    # degradation instinct as the alert service's webhook/incident calls.
    result: dict = {"service_name": service_name}

    try:
        result["deployments"] = aggregations.deployment_stats(
            get_deployment_client().all_deployments(service_name)
        )
    except ServiceClientError as exc:
        result["deployments"] = {"error": str(exc)}

    try:
        result["incidents"] = aggregations.incident_stats(get_incident_client().all_incidents(service_name))
    except ServiceClientError as exc:
        result["incidents"] = {"error": str(exc)}

    try:
        rules, alerts = get_alert_client().all_alerts(service_name)
        result["alerts"] = aggregations.alert_stats(rules, alerts)
    except ServiceClientError as exc:
        result["alerts"] = {"error": str(exc)}

    any_section_failed = any(
        isinstance(result.get(section), dict) and "error" in result[section]
        for section in ("deployments", "incidents", "alerts")
    )
    if not any_section_failed:
        cache.set(cache_key, json.dumps(result), CACHE_TTL_SECONDS)

    return result
