from urllib.parse import quote

import httpx
from fastapi import Depends, Request, Response
from fastapi.responses import JSONResponse
from fastapi.routing import APIRouter

from ..config import settings
from ..core.http_client import get_http_client
from ..security import enforce_authentication

# dependencies=[...] here applies to every route this router registers
# below -- both the real proxy routes and the NOT_YET_IMPLEMENTED stubs --
# so enforce_authentication (app/security.py) runs before ANY of them,
# without having to remember to add it route-by-route. It internally
# allowlists the three genuinely public auth paths; everything else needs
# a valid access token or the request never reaches a downstream service
# at all.
router = APIRouter(prefix="/api/v1", dependencies=[Depends(enforce_authentication)])

# Headers that are specific to a single hop and must not be blindly
# forwarded between the client<->gateway and gateway<->upstream legs.
HOP_BY_HOP_HEADERS = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailers", "transfer-encoding", "upgrade", "content-length", "host",
}

# Services from the original design that are documented in the API surface
# but don't exist yet. Each returns an honest 501 with the phase it's
# planned for instead of either a 404 (which would hide that it's planned)
# or fabricated data (which would misrepresent what the platform can do).
# "deployments", "alerts", "incidents", "ai", "analytics", "notifications",
# "audit", and now "infrastructure" aren't listed here anymore -- see the
# real proxy routes below. "monitoring" is the one entry left: its
# Prometheus-querying responsibility is partly covered by the alert
# service now, but "service health views" and "health summaries" aren't
# built as their own thing.
NOT_YET_IMPLEMENTED = {
    "monitoring": "Phase 3 -- Observability (partially covered by alert service)",
}


def _unsafe_path(path: str) -> bool:
    """True if a (already URL-decoded) path tail could climb out of the
    service prefix or smuggle URL structure into the upstream request.
    `..%2fmetrics` decodes to `../metrics`; httpx then normalises the dot
    segment and the request lands on the upstream's /metrics instead of
    anything under /deployments/. Also rejects backslashes and control
    characters, which some servers treat as separators.
    """
    if "\\" in path or any(ord(c) < 0x20 or ord(c) == 0x7F for c in path):
        return True
    return any(segment in {".", ".."} for segment in path.split("/"))


def _make_proxy(
    service_name: str,
    upstream_base_url,
    upstream_path_prefix: str | None = None,
    timeout_seconds=lambda: settings.UPSTREAM_TIMEOUT_SECONDS,
):
    """Build a handler that forwards /api/v1/<service_name>[/<path>] to
    <upstream_base_url()>/<upstream_path_prefix>[/<path>]. By default the
    upstream prefix is the gateway service name. `infrastructure` is the
    one exception: its service exposes `/environments` directly, while the
    public gateway namespace remains `/infrastructure/environments`.
    upstream_base_url is a zero-arg callable (not a plain string) so it
    re-reads `settings` on every call instead of freezing the URL at import
    time -- matters for tests that patch settings, and costs nothing in
    production since Settings is effectively static there.
    """

    async def _proxy(request: Request, path: str = "") -> Response:
        if _unsafe_path(path):
            return JSONResponse(status_code=400, content={"detail": "Invalid request path"})

        client = get_http_client()
        upstream_prefix = service_name if upstream_path_prefix is None else upstream_path_prefix
        url_parts = [upstream_base_url().rstrip("/")]
        if upstream_prefix:
            url_parts.append(upstream_prefix)
        if path:
            # Re-encode: `path` arrives decoded, so a literal `?` or `#`
            # (from %3f / %23) would otherwise start a query string or
            # fragment in the upstream URL instead of staying path data.
            url_parts.append(quote(path, safe="/"))
        url = "/".join(url_parts)
        # Drop any client-supplied identity headers up front. Identity is
        # set below from the VERIFIED token, and only there -- on public
        # paths (login/register) there is no verified identity, so nothing
        # may be forwarded; a caller who could set X-ICOP-Role themselves
        # would be forging the very header downstream services are meant to
        # trust.
        headers = {
            k: v
            for k, v in request.headers.items()
            if k.lower() not in HOP_BY_HOP_HEADERS and not k.lower().startswith("x-icop-")
        }

        # Fast path: reject before reading anything if the client honestly
        # declared an oversized body. Not sufficient on its own --
        # Content-Length can be absent (chunked transfer encoding) or
        # simply wrong, which is what the check after body-reading below
        # (the real backstop) is for.
        content_length = request.headers.get("content-length")
        if (
            content_length is not None
            and content_length.isdigit()
            and int(content_length) > settings.MAX_REQUEST_BODY_BYTES
        ):
            return JSONResponse(status_code=413, content={"detail": "Request body too large"})

        # request.state.jwt_claims is set by enforce_authentication
        # (app/security.py) for every route except the three public auth
        # paths, which never reach this point with an unverified token in
        # the first place -- see that module for why. Absent entirely for
        # the public paths themselves (register/login/refresh have no
        # identity yet to forward). No downstream service reads these
        # headers today (see the root README) -- forwarding them anyway
        # costs nothing and means adopting them later is additive, not
        # another round of gateway changes.
        claims = getattr(request.state, "jwt_claims", None)
        if claims:
            headers["X-ICOP-User"] = str(claims.get("sub", ""))
            headers["X-ICOP-Role"] = str(claims.get("role", ""))

        body = await request.body()
        # Backstop: catches an absent or understated Content-Length --
        # Starlette has already fully buffered `body` by this point (this
        # framework doesn't support streaming an unbounded body through
        # to httpx without buffering it first), so this doesn't prevent
        # THIS one request from being read into memory, but it does stop
        # it from being forwarded any further, and bounds the damage to
        # one such body rather than an unbounded flood of them.
        if len(body) > settings.MAX_REQUEST_BODY_BYTES:
            return JSONResponse(status_code=413, content={"detail": "Request body too large"})

        try:
            upstream = await client.request(
                request.method,
                url,
                params=request.query_params,
                headers=headers,
                content=body,
                timeout=timeout_seconds(),
            )
        except httpx.HTTPError:
            return JSONResponse(
                status_code=503, content={"detail": f"{service_name} service is unavailable"}
            )

        response_headers = {
            k: v for k, v in upstream.headers.items() if k.lower() not in HOP_BY_HOP_HEADERS
        }
        return Response(
            content=upstream.content,
            status_code=upstream.status_code,
            headers=response_headers,
            media_type=upstream.headers.get("content-type"),
        )

    return _proxy


_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE"]


def _register_proxy(
    service_name: str,
    upstream_base_url,
    upstream_path_prefix: str | None = None,
    timeout_seconds=lambda: settings.UPSTREAM_TIMEOUT_SECONDS,
) -> None:
    handler = _make_proxy(service_name, upstream_base_url, upstream_path_prefix, timeout_seconds)
    router.add_api_route(f"/{service_name}", handler, methods=_METHODS)
    router.add_api_route(f"/{service_name}/{{path:path}}", handler, methods=_METHODS)


_register_proxy("auth", lambda: settings.AUTH_SERVICE_URL)
_register_proxy("deployments", lambda: settings.DEPLOYMENT_SERVICE_URL)
_register_proxy("alerts", lambda: settings.ALERT_SERVICE_URL)
_register_proxy("incidents", lambda: settings.INCIDENT_SERVICE_URL)
# /ai/explain runs a multi-round LLM tool loop (up to MAX_AGENT_ITERATIONS
# calls of up to 60s each), so it needs far longer than the 10s every other
# route gets -- at 10s it could never finish a real answer.
_register_proxy(
    "ai",
    lambda: settings.AIOPS_SERVICE_URL,
    timeout_seconds=lambda: settings.AI_UPSTREAM_TIMEOUT_SECONDS,
)
_register_proxy("analytics", lambda: settings.ANALYTICS_SERVICE_URL)
_register_proxy("notifications", lambda: settings.NOTIFICATION_SERVICE_URL)
_register_proxy("audit", lambda: settings.AUDIT_SERVICE_URL)
_register_proxy("infrastructure", lambda: settings.INFRASTRUCTURE_SERVICE_URL, upstream_path_prefix="")


def _make_stub(service: str, phase: str):
    # Factory function so each stub closes over its OWN service/phase
    # values. Without this, a closure referencing the loop variables
    # directly would have every stub resolve to the last (service, phase)
    # pair in the dict once the loop finishes -- a classic late-binding bug.
    async def _stub(path: str = ""):
        return JSONResponse(
            status_code=501,
            content={
                "detail": f"'{service}' service is not implemented yet.",
                "planned_for": phase,
                "see": "ROADMAP.md",
            },
        )

    return _stub


for _service, _phase in NOT_YET_IMPLEMENTED.items():
    _handler = _make_stub(_service, _phase)
    router.add_api_route(f"/{_service}", _handler, methods=_METHODS)
    router.add_api_route(f"/{_service}/{{path:path}}", _handler, methods=_METHODS)
