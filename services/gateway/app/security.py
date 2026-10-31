"""Gateway-level JWT verification.

Closes a real gap that was documented but not fixed: the gateway forwarded
every request to whatever downstream service the path named, Authorization
header included verbatim if present, without ever checking whether that
header held a valid token. And no downstream service (deployment, incident,
alert, aiops, analytics, notification, audit, infrastructure) checks
authentication itself either -- only the auth service's own routes did,
via services/auth/app/deps.py's get_current_user. In practice, that meant
anyone who could reach any endpoint -- through the gateway or, in a real
deployment, directly to a service's ClusterIP -- could call it with zero
authentication. Not a theoretical gap: `POST /api/v1/deployments` and
`POST /api/v1/infrastructure/environments` (trigger a real Helm rollout;
provision real AWS infrastructure) were both reachable by anyone.

The fix: every route this gateway proxies now requires a valid, unexpired
access token before the gateway forwards anything, except the three paths
where requiring one would be circular (you can't have a token before you
register or log in). Verification is a local HS256 decode against the
same SECRET_KEY the auth service signs with (services/auth/app/security.py)
-- not a network call to auth on every request. That matters under load:
a local decode is a microseconds-scale CPU operation; a round trip to
another service, on the hot path of every single gateway request, would
turn the busiest service in the platform into a second bottleneck the
moment traffic grew.

What this deliberately does NOT do: enforce per-role permissions (can
THIS operator touch THIS cluster). That's authorization, not
authentication, and stays each downstream service's own concern -- see
ROADMAP.md's Phase 1 for why, and for the one place that already does
this correctly (services/auth/app/deps.py's require_role, on auth's own
/auth/users route). This gateway fix makes "who is this, verified" true
platform-wide; it does not make "and are they allowed to do this
specific thing" true anywhere it wasn't already.
"""

import jwt
from fastapi import HTTPException, Request, status

from .config import settings

# Role ladder: a higher number can do everything a lower one can.
ROLE_RANK = {"viewer": 0, "developer": 1, "operator": 2, "admin": 3}
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

# service -> (minimum role for read-only methods, minimum role for anything
# that changes state). `None` means "nobody, through the gateway" -- used for
# analytics (computed, never written) and audit (events are written by the
# services themselves over the internal network, never by an API caller:
# letting any logged-in user POST /audit/events would make the "immutable
# audit trail" forgeable). A service missing from this table is admin-only,
# i.e. a newly proxied service fails closed until someone decides its policy.
#
# The auth service is deliberately permissive here -- it enforces its own,
# finer-grained rules (/auth/users and the role-change endpoint are
# admin-only inside auth itself).
POLICY: dict[str, tuple[str, str | None]] = {
    "auth": ("viewer", "viewer"),
    "deployments": ("viewer", "operator"),
    "alerts": ("viewer", "operator"),
    "incidents": ("viewer", "operator"),
    "ai": ("viewer", "developer"),
    "analytics": ("viewer", None),
    "notifications": ("viewer", "operator"),
    "audit": ("operator", None),
    "infrastructure": ("operator", "admin"),
    "monitoring": ("viewer", "viewer"),  # 501 stub today
}

# Requesting a token requires not having one yet -- these three are the
# only routes under /api/v1/* that skip verification. Exact-match on the
# resolved path, not a prefix rule: /api/v1/auth/me and /api/v1/auth/users
# are proxied through the same generic "auth" route as these three (see
# routers/proxy.py's _register_proxy) but are NOT public, so a prefix rule
# would wrongly wave them through too.
PUBLIC_PATHS = frozenset({
    "/api/v1/auth/register",
    "/api/v1/auth/login",
    "/api/v1/auth/refresh",
})


async def enforce_authentication(request: Request) -> None:
    if request.url.path in PUBLIC_PATHS:
        return

    auth_header = request.headers.get("authorization", "")
    scheme, _, token = auth_header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        # `require` closes a real hole: PyJWT only validates `exp` IF it is
        # present, so a token signed with the right key but carrying no `exp`
        # at all was accepted forever.
        claims = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=["HS256"],
            options={"require": ["exp", "sub", "type"]},
        )
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None

    if claims.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh tokens cannot be used to authenticate requests",
        )

    # Stashed on request.state, not returned -- FastAPI dependencies used
    # via APIRouter(dependencies=[...]) (see routers/proxy.py) run before
    # the route handler but their return value isn't injected into it;
    # request.state is the one object both this dependency and the proxy
    # handler both see. routers/proxy.py's _make_proxy reads this to
    # forward identity downstream as trusted headers -- no service
    # consumes them yet (see the root README), but establishing "who is
    # this, verified" belongs at the platform's one real trust boundary
    # regardless of whether every downstream service reads it today.
    _authorize(request, claims)
    request.state.jwt_claims = claims


def _authorize(request: Request, claims: dict) -> None:
    """Role-based access check, run after the token itself is verified.

    Role comes from the token, so a role change takes effect when the user's
    current access token expires (<= ACCESS_TOKEN_EXPIRE_MINUTES), not
    instantly -- there is no revocation list yet (see ROADMAP.md).
    """
    parts = request.url.path.split("/")  # ["", "api", "v1", <service>, ...]
    service = parts[3] if len(parts) > 3 else ""
    read_role, write_role = POLICY.get(service, ("admin", "admin"))
    required = read_role if request.method in SAFE_METHODS else write_role

    if required is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"{request.method} is not permitted on '{service}' through the gateway",
        )

    caller_rank = ROLE_RANK.get(str(claims.get("role", "")))
    if caller_rank is None or caller_rank < ROLE_RANK[required]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"role '{claims.get('role')}' cannot {request.method} '{service}' (requires '{required}')",
        )
