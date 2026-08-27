// Baseline load test against the gateway. Exercises real, authenticated
// traffic through the actual auth flow (register once, log in, use the
// token) rather than a synthetic bypass -- the gateway now rejects
// anything else (see services/gateway/app/security.py), so a load test
// that skipped this would be testing something that no longer exists.
//
// Run against a real deployment:
//   k6 run -e BASE_URL=https://your-real-gateway-url load-test/k6/baseline.js
//
// STATUS: written, never run. No running deployment was reachable from
// the sandbox this was built in (see the root README's caveats) -- this
// script has been read through carefully for correctness against k6's
// actual API, but "carefully read" is not "executed", and there is no
// load-test result anywhere in this repo to point to. Run it for real
// before citing a number from it.

import http from "k6/http";
import { check, sleep } from "k6";
import { Counter, Trend } from "k6/metrics";

const BASE_URL = __ENV.BASE_URL || "http://localhost:8000";

// Custom metrics, on top of k6's built-in http_req_duration/http_req_failed
// -- these isolate the one endpoint (analytics/overview) this pass added
// caching to (see services/analytics/app/cache.py), so a real run's
// results can actually show whether that cache is doing anything under
// load, not just what the platform's aggregate latency looks like.
const analyticsOverviewDuration = new Trend("analytics_overview_duration", true);
const authFailures = new Counter("auth_failures");

export const options = {
  scenarios: {
    // Ramp from 0 to a moderate concurrent-user count, hold, ramp back
    // down. "Moderate" is deliberate -- this is a baseline/smoke-level
    // load profile meant to catch obvious regressions and confirm the
    // platform behaves reasonably under some real concurrency, not a
    // capacity/breaking-point test. A separate, heavier scenario (see
    // this directory's README) is what you'd actually use to answer
    // "what's the ceiling" -- a materially different exercise this
    // script doesn't attempt.
    baseline: {
      executor: "ramping-vus",
      startVUs: 0,
      stages: [
        { duration: "30s", target: 20 },
        { duration: "2m", target: 20 },
        { duration: "30s", target: 0 },
      ],
    },
  },
  thresholds: {
    // Deliberately generous starting points, not tuned against any real
    // measurement (there isn't one yet -- see this file's STATUS note).
    // Tighten these once a real run establishes what "normal" actually
    // looks like for a real deployment; treat these as "something is
    // badly wrong" trip-wires for a first run, not a performance SLA.
    http_req_failed: ["rate<0.01"],
    http_req_duration: ["p(95)<800"],
    "analytics_overview_duration": ["p(95)<1500"], // higher bar: this endpoint fans out to 3 other services on a cache miss (see services/analytics/README.md-equivalent comments in app/routers/analytics.py)
  },
};

function registerAndLogin() {
  // A fresh, unique user per VU (k6 runs this once per virtual user, not
  // once per request) -- avoids every VU colliding on the same email
  // against auth's real uniqueness constraint.
  const email = `loadtest-${__VU}-${Date.now()}@example.com`;
  const password = "loadtest-password-1";

  const registerRes = http.post(
    `${BASE_URL}/api/v1/auth/register`,
    JSON.stringify({ email, password }),
    { headers: { "Content-Type": "application/json" } }
  );
  check(registerRes, { "register succeeded (201)": (r) => r.status === 201 });

  const loginRes = http.post(
    `${BASE_URL}/api/v1/auth/login`,
    `username=${encodeURIComponent(email)}&password=${encodeURIComponent(password)}`,
    { headers: { "Content-Type": "application/x-www-form-urlencoded" } }
  );
  const ok = check(loginRes, { "login succeeded (200)": (r) => r.status === 200 });
  if (!ok) {
    authFailures.add(1);
    return null;
  }
  return loginRes.json("access_token");
}

export function setup() {
  // Registration/login happens once per VU in the default export below,
  // not in setup() -- k6's setup() runs once total, shared across every
  // VU, which would make every VU fight over the SAME token/user. Nothing
  // to actually do here; kept as an explicit no-op so anyone reading this
  // script doesn't have to wonder whether that sharing was considered.
}

export default function () {
  const token = registerAndLogin();
  if (!token) {
    sleep(1);
    return; // this VU couldn't authenticate -- counted via auth_failures above, no point hammering protected routes with no token
  }
  const authHeaders = { headers: { Authorization: `Bearer ${token}` } };

  // A representative mix of read traffic across several services --
  // deliberately read-heavy (no deployment triggers, no environment
  // provisioning) since this is meant to be safe to point at a real
  // staging environment without it actually rolling out Helm charts or
  // provisioning AWS infrastructure as a side effect of load testing.
  const deployments = http.get(`${BASE_URL}/api/v1/deployments`, authHeaders);
  check(deployments, { "list deployments: 200": (r) => r.status === 200 });

  const incidents = http.get(`${BASE_URL}/api/v1/incidents`, authHeaders);
  check(incidents, { "list incidents: 200": (r) => r.status === 200 });

  const overviewRes = http.get(
    `${BASE_URL}/api/v1/analytics/overview?service_name=gateway`,
    authHeaders
  );
  check(overviewRes, { "analytics overview: 200": (r) => r.status === 200 });
  analyticsOverviewDuration.add(overviewRes.timings.duration);

  const audit = http.get(`${BASE_URL}/api/v1/audit/events`, authHeaders);
  check(audit, { "audit events: 200": (r) => r.status === 200 });

  // Think time -- a real user pauses between actions; a tight loop with
  // no sleep at all tests something closer to "how fast can this server
  // reject requests" than "how does this behave under realistic traffic."
  sleep(Math.random() * 2 + 1);
}
