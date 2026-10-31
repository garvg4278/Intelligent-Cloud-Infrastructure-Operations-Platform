import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { NAV_ITEMS } from "../navigation";
import { ROUTES } from "../routes";
import { App } from "../App";
import { emptyApi, fakeToken, json, mockFetch, on, renderApp, seedSession } from "../../test/helpers";

describe("route table", () => {
  it("has a page for every navigation item, with the same minimum role", () => {
    for (const item of NAV_ITEMS) expect(ROUTES.find((r) => r.path === item.to)?.minRole).toBe(item.minRole);
  });
});

describe("signed out", () => {
  it("shows the sign-in form, and signs in with the API's form-encoded login", async () => {
    const { fetch, calls } = mockFetch(
      on("POST", "/api/v1/auth/login", () => json({ access_token: fakeToken("viewer"), refresh_token: "r" })),
      ...emptyApi,
    );
    const user = userEvent.setup();
    renderApp(<App />, { fetch });
    expect(screen.getByRole("heading", { name: "Sign in" })).toBeInTheDocument();
    await user.type(screen.getByLabelText("Email"), "me@example.com");
    await user.type(screen.getByLabelText("Password"), "supersecret1");
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("heading", { name: "Overview", level: 1 })).toBeInTheDocument();
    expect(String(calls[0].init.body)).toContain("username=me%40example.com");
  });

  it("shows the server's error message and moves focus to it when sign-in fails", async () => {
    const { fetch } = mockFetch(on("POST", "/api/v1/auth/login", () => json({ detail: "Incorrect email or password" }, 401)));
    const user = userEvent.setup();
    renderApp(<App />, { fetch });
    await user.type(screen.getByLabelText("Email"), "me@example.com");
    await user.type(screen.getByLabelText("Password"), "wrongpassword");
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Incorrect email or password");
    expect(alert).toHaveFocus();
  });

  it("validates a too-short password on registration before calling the API", async () => {
    const { fetch, calls } = mockFetch();
    const user = userEvent.setup();
    renderApp(<App />, { fetch });
    await user.click(screen.getByRole("button", { name: /Need an account/ }));
    await user.type(screen.getByLabelText("Email"), "new@example.com");
    await user.type(screen.getByLabelText(/^Password/), "short");
    await user.click(screen.getByRole("button", { name: "Create account" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("at least 8 characters");
    expect(calls).toHaveLength(0);
  });
});

describe("role-aware navigation", () => {
  it("hides operator/admin pages from a viewer and shows the no-access page on a direct visit", async () => {
    seedSession("viewer");
    window.history.replaceState(null, "", "/environments");
    const { fetch, calls } = mockFetch(...emptyApi);
    renderApp(<App />, { fetch });
    expect(await screen.findByRole("heading", { name: "You don't have access" })).toBeInTheDocument();
    const nav = screen.getByRole("navigation", { name: "Main" });
    expect(within(nav).queryByRole("link", { name: "Environments" })).not.toBeInTheDocument();
    expect(within(nav).queryByRole("link", { name: "Users & roles" })).not.toBeInTheDocument();
    expect(calls.some((c) => c.url.pathname.includes("/infrastructure"))).toBe(false); // no pointless request
  });

  it("shows admin pages to an admin", async () => {
    seedSession("admin");
    renderApp(<App />, { fetch: mockFetch(...emptyApi).fetch });
    const nav = await screen.findByRole("navigation", { name: "Main" });
    for (const name of ["Overview", "Incidents", "Alerts", "Environments", "Audit log", "Users & roles"]) {
      expect(within(nav).getByRole("link", { name })).toBeInTheDocument();
    }
  });
});

describe("custom 404", () => {
  it("shows a helpful page for unknown routes, inside the app chrome", async () => {
    seedSession("viewer");
    window.history.replaceState(null, "", "/no/such/page");
    renderApp(<App />, { fetch: mockFetch(...emptyApi).fetch });
    expect(await screen.findByRole("heading", { name: "Page not found" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to the overview" })).toHaveAttribute("href", "/");
    expect(document.title).toContain("Page not found");
  });
});

describe("session expiry", () => {
  it("returns to sign-in with an explanation when the token and refresh both fail", async () => {
    seedSession("viewer");
    const { fetch } = mockFetch(
      on("POST", "/api/v1/auth/refresh", () => json({ detail: "Invalid refresh token" }, 401)),
      (url) => (url.pathname.startsWith("/api/v1/") ? json({ detail: "Invalid or expired token" }, 401) : undefined),
    );
    renderApp(<App />, { fetch });
    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("session expired");
  });
});

describe("mobile menu, theme, search, chrome", () => {
  it("opens and closes the menu, closes on Escape and on navigation, and marks the current page", async () => {
    seedSession("viewer");
    const user = userEvent.setup();
    renderApp(<App />, { fetch: mockFetch(...emptyApi).fetch });
    const button = await screen.findByRole("button", { name: "Open menu" });
    expect(button).toHaveAttribute("aria-expanded", "false");
    await user.click(button);
    expect(button).toHaveAttribute("aria-expanded", "true");
    expect(document.body).toHaveClass("menu-open");
    await user.keyboard("{Escape}");
    expect(button).toHaveAttribute("aria-expanded", "false");
    await user.click(button);
    await user.click(within(screen.getByRole("navigation", { name: "Main" })).getByRole("link", { name: "Alerts" }));
    expect(await screen.findByRole("heading", { name: "Alerts", level: 1 })).toBeInTheDocument();
    expect(button).toHaveAttribute("aria-expanded", "false");
    expect(screen.getByRole("link", { name: "Alerts", current: "page" })).toBeInTheDocument();
  });

  it("toggles dark mode and remembers it", async () => {
    seedSession("viewer");
    const user = userEvent.setup();
    renderApp(<App />, { fetch: mockFetch(...emptyApi).fetch });
    await user.click(await screen.findByRole("button", { name: /Switch to dark mode/ }));
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(window.localStorage.getItem("icop.theme")).toBe("dark");
  });

  it("searches pages and actions with Ctrl+K and navigates with the keyboard", async () => {
    seedSession("viewer");
    const user = userEvent.setup();
    renderApp(<App />, { fetch: mockFetch(...emptyApi).fetch });
    await screen.findByRole("heading", { name: "Overview", level: 1 });
    await user.keyboard("{Control>}k{/Control}");
    const box = screen.getByRole("combobox", { name: "Search pages and actions" });
    expect(box).toHaveFocus();
    await user.type(box, "incid");
    await user.keyboard("{Enter}");
    expect(await screen.findByRole("heading", { name: "Incidents", level: 1 })).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("has a skip link, a labelled logo link home, and a footer with the current year", async () => {
    seedSession("viewer");
    renderApp(<App />, { fetch: mockFetch(...emptyApi).fetch, config: { supportEmail: "ops@example.com", grafanaUrl: "https://grafana.example.com/" } });
    expect(await screen.findByRole("link", { name: "Skip to main content" })).toHaveAttribute("href", "#main");
    expect(screen.getByRole("link", { name: /go to overview/ })).toHaveAttribute("href", "/");
    const footer = screen.getByRole("contentinfo");
    expect(footer).toHaveTextContent(`© ${new Date().getFullYear()}`);
    expect(within(footer).getByRole("link", { name: "ops@example.com" })).toHaveAttribute("href", "mailto:ops@example.com");
    const external = within(footer).getByRole("link", { name: "Grafana" });
    expect(external).toHaveAttribute("rel", expect.stringContaining("noopener"));
  });

  it("hides the Grafana/API-docs links entirely when they are not configured (no dead links)", async () => {
    seedSession("viewer");
    renderApp(<App />, { fetch: mockFetch(...emptyApi).fetch });
    await screen.findByRole("navigation", { name: "Main" });
    expect(screen.queryByRole("link", { name: /Grafana/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /API doc/ })).not.toBeInTheDocument();
  });
});

describe("environments: confirmation before anything irreversible", () => {
  const env = { id: "e1", name: "icop-staging", environment_type: "staging", status: "ready", cluster_name: "c", error_message: null, created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-02T00:00:00Z" };

  it("does not call the API until the admin confirms, then reports success", async () => {
    seedSession("admin");
    let provisioned = 0;
    const { fetch, calls } = mockFetch(
      on("POST", "/api/v1/infrastructure/environments", () => { provisioned++; return json({ ...env, status: "pending" }, 202); }),
      on("GET", "/api/v1/infrastructure/environments", () => json([])),
    );
    window.history.replaceState(null, "", "/environments");
    const user = userEvent.setup();
    renderApp(<App />, { fetch });
    await user.click(await screen.findByRole("button", { name: "Provision production" }));
    expect(screen.getByRole("alertdialog", { name: "Provision production?" })).toBeInTheDocument();
    expect(provisioned).toBe(0);
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(provisioned).toBe(0);

    await user.click(screen.getByRole("button", { name: "Provision production" }));
    await user.click(screen.getByRole("button", { name: "Queue provisioning" }));
    await waitFor(() => expect(provisioned).toBe(1));
    expect(await screen.findByText(/Provisioning of production was queued/)).toBeInTheDocument();
    expect(JSON.parse(String(calls.find((c) => c.init.method === "POST")!.init.body))).toEqual({ environment_type: "production" });
  });

  it("shows the API's refusal as an error toast with a copyable reference, and keeps the page usable", async () => {
    seedSession("admin");
    const { fetch } = mockFetch(
      on("POST", "/api/v1/infrastructure/environments", () => json({ detail: "an environment of type 'staging' already exists" }, 409, { "X-Correlation-ID": "11111111-2222" })),
      on("GET", "/api/v1/infrastructure/environments", () => json([])),
    );
    window.history.replaceState(null, "", "/environments");
    const user = userEvent.setup();
    renderApp(<App />, { fetch });
    await user.click(await screen.findByRole("button", { name: "Provision staging" }));
    await user.click(screen.getByRole("button", { name: "Queue provisioning" }));
    const toast = await screen.findByRole("alert");
    expect(toast).toHaveTextContent("already exists");
    expect(toast).toHaveTextContent("11111111");
    expect(screen.getByRole("button", { name: "Provision staging" })).toBeEnabled();
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument(); // not stuck behind a backdrop
  });

  it("lets an operator view environments but not change them", async () => {
    seedSession("operator");
    const { fetch } = mockFetch(on("GET", "/api/v1/infrastructure/environments", () => json([env])));
    window.history.replaceState(null, "", "/environments");
    renderApp(<App />, { fetch });
    expect(await screen.findByText("icop-staging")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Provision/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Destroy" })).not.toBeInTheDocument();
    expect(screen.getByText(/require the admin role/)).toBeInTheDocument();
  });
});

describe("incidents", () => {
  const incident = { id: "i1", title: "Elevated 5xx", description: null, service_name: "gateway", severity: "critical", status: "open", created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z", resolved_at: null };

  it("offers only valid transitions and asks before resolving", async () => {
    seedSession("operator");
    let transitions: unknown[] = [];
    const { fetch } = mockFetch(
      on("POST", "/api/v1/incidents/i1/transition", (_u, init) => { transitions.push(JSON.parse(String(init.body))); return json({ ...incident, status: "resolved" }); }),
      on("GET", "/api/v1/incidents", () => json([incident])),
    );
    window.history.replaceState(null, "", "/incidents");
    const user = userEvent.setup();
    renderApp(<App />, { fetch });
    const select = await screen.findByLabelText("Move “Elevated 5xx” to");
    expect(within(select).getAllByRole("option").map((o) => o.textContent)).toEqual(["Choose…", "acknowledged", "investigating", "resolved"]);
    await user.selectOptions(select, "acknowledged");
    await waitFor(() => expect(transitions).toEqual([{ status: "acknowledged" }])); // reversible: no confirmation
    transitions = [];
    await user.selectOptions(await screen.findByLabelText("Move “Elevated 5xx” to"), "resolved");
    expect(screen.getByRole("alertdialog")).toBeInTheDocument();
    expect(transitions).toEqual([]);
    await user.click(screen.getByRole("button", { name: "Mark resolved" }));
    await waitFor(() => expect(transitions).toEqual([{ status: "resolved" }]));
  });

  it("shows an empty state and an error state with retry", async () => {
    seedSession("viewer");
    let fail = true;
    const { fetch } = mockFetch(on("GET", "/api/v1/incidents", () => (fail ? json({ detail: "db down" }, 503, { "X-Correlation-ID": "abcdef12-0" }) : json([]))));
    window.history.replaceState(null, "", "/incidents");
    const user = userEvent.setup();
    renderApp(<App />, { fetch });
    expect(await screen.findByText("Couldn't load this")).toBeInTheDocument();
    expect(screen.getByText("abcdef12-0")).toBeInTheDocument();
    fail = false;
    await user.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("No incidents")).toBeInTheDocument();
  });
});

describe("overview", () => {
  it("shows real numbers from the analytics API, as percentages", async () => {
    seedSession("viewer");
    const { fetch } = mockFetch(
      on("GET", "/api/v1/analytics/overview", () => json({ service_name: "gateway", deployments: { total: 48, success_rate: 0.9167, deployments_per_day: 2 }, incidents: { total: 3, by_status: { open: 2, resolved: 1 }, avg_resolution_seconds: 120 }, alerts: { total: 5, by_status: { firing: 5 } } })),
      ...emptyApi,
    );
    renderApp(<App />, { fetch });
    expect(await screen.findByText("91.7%")).toBeInTheDocument();
    expect(screen.getByText("Open incidents").nextElementSibling).toHaveTextContent("2");
    expect(screen.getByText("Firing alerts").nextElementSibling).toHaveTextContent("5");
  });
});
