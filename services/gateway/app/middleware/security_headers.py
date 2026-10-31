from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

# A fixed set, not configurable per-environment -- unlike CORS (which
# genuinely differs between local dev and production), there's no
# legitimate reason any deployment of this gateway would want a weaker
# version of these. All of them are meaningful for a pure JSON API, not
# just an HTML-serving one: X-Content-Type-Options and
# X-Frame-Options/CSP still matter because error responses and Swagger's
# /docs (served by every downstream FastAPI service directly, not by the
# gateway, but reachable the same way) render in a browser even though
# the gateway's own proxied responses are JSON.
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    # A pure JSON API has no legitimate use for any active content --
    # this is the strictest CSP that exists, appropriate here specifically
    # because this gateway never returns HTML/JS of its own.
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
    # Explicitly "0", not "1; mode=block" -- current OWASP guidance is
    # that the old X-XSS-Protection browser feature this header controls
    # is deprecated and, in some older browsers, an actual attack vector
    # in its own right (it could be used to selectively suppress
    # legitimate page content). Explicitly disabling it is the current
    # recommendation, not just omitting the header.
    "X-XSS-Protection": "0",
    # Only meaningful once real TLS termination exists in front of this
    # gateway (see gitops/README.md -- not built yet, ArgoCD itself is
    # bootstrapped with `--insecure` today). Set now anyway: harmless over
    # plain HTTP (browsers ignore HSTS on a non-HTTPS response), and one
    # less thing to remember to add later when TLS does exist.
    "Strict-Transport-Security": "max-age=63072000; includeSubDomains",
}


# Swagger UI (/docs) and ReDoc (/redoc) are the only HTML this gateway
# serves. FastAPI's generated pages load their bundle from cdn.jsdelivr.net
# and boot it from an inline <script>, so the blanket `default-src 'none'`
# above renders them as a blank page. This relaxed policy applies to those
# two paths only, allows exactly the hosts they need, and still forbids
# framing, plugins, base-tag and form hijacking. Every other path --
# including every /api/v1/* response -- keeps the strict policy.
DOCS_PATHS = ("/docs", "/redoc")
DOCS_CONTENT_SECURITY_POLICY = (
    "default-src 'none'; "
    "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com; "
    "img-src 'self' data: https://fastapi.tiangolo.com https://cdn.redoc.ly; "
    "font-src https://fonts.gstatic.com; "
    "connect-src 'self'; "
    "worker-src blob:; "
    "object-src 'none'; base-uri 'none'; form-action 'self'; "
    "frame-ancestors 'none'"
)


def _is_docs_path(path: str) -> bool:
    return any(path == p or path.startswith(p + "/") for p in DOCS_PATHS)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Adds a fixed set of defensive headers to every response, including
    error responses (429s, 401s, 500s) -- added as the outermost layer in
    app/main.py for exactly that reason, same ordering logic already
    documented there for CorrelationIdMiddleware.
    """

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        for header, value in SECURITY_HEADERS.items():
            response.headers[header] = value
        if _is_docs_path(request.url.path):
            response.headers["Content-Security-Policy"] = DOCS_CONTENT_SECURITY_POLICY
        return response
