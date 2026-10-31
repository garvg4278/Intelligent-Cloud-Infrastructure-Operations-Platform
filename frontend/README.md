# ICOP Operations Console

React 19 + TypeScript + Vite single-page app. It talks only to the gateway
(`/api/v1`), through nginx, so the browser stays same-origin: no CORS, and a
strict Content-Security-Policy.

```bash
pnpm install
pnpm dev        # http://localhost:5173, /api proxied to the gateway on :8000
pnpm lint       # type-check
pnpm test       # vitest (unit + component + whole-app tests)
pnpm build      # type-check + production bundle in dist/
```

## Layout

```
src/
  main.tsx          bootstrap only: load config, mount providers
  app/              App, Providers, router, route table, navigation, ErrorBoundary
  config/           constants (no magic strings) and runtime config (/config.json)
  api/              HTTP client (refresh, timeouts, errors), one function per endpoint, wire types
  state/            React context providers: auth, theme, toasts, config
  hooks/            useResource, usePaged, useAction, useHotkey, useScroll, useDocumentTitle
  lib/              pure logic with no React: formatting, JWT claims, overview maths, filters
  components/       presentational building blocks (Button, DataTable, ConfirmDialog, ...)
  layout/           app shell: sidebar/drawer, sticky topbar, footer, command palette
  pages/            one file per route; compose hooks + components, own no HTTP details
  styles/           tokens (light/dark), base, layout, components, print
public/             favicon, 404 page, robots.txt, theme-init.js, dev config.json
docker/             nginx security headers, entrypoint that writes /config.json
```

Dependency direction is one way: `pages -> hooks/components -> api/lib -> config`.
Pages never build URLs or parse responses; `lib/` never imports React.

## Conventions

- Components `PascalCase.tsx`, hooks `useThing.ts`, everything else `camelCase.ts`.
- Every request goes through `api/client.ts`, so every failure is an `ApiError`
  (status, readable message, gateway correlation id). Mutations go through
  `useAction`, so every button reports success and failure the same way (toast).
- No `any`, no non-null assertions outside `main.tsx`.

## State

No state library: the app has four pieces of global state and each is a small
context (`auth`, `theme`, `toast`, `config`). Server data lives in the page that
shows it (`useResource` / `usePaged`), is aborted on unmount or filter change, and
is re-fetched after a mutation. Nothing is cached across pages on purpose: an
ops console should never show stale incident data.

## Configuration (no environment in the bundle)

The image is built once and configured at start-up. `ICOP_ENVIRONMENT_LABEL`,
`ICOP_GRAFANA_URL`, `ICOP_API_DOCS_URL`, `ICOP_SUPPORT_EMAIL` are written to
`/config.json` by `docker/40-icop-config.sh`. A value that is empty or invalid
(anything that isn't an http(s) URL / well-formed email) switches that link off
instead of rendering a dead or hostile one.

## Security model

- **Authorization is the gateway's.** The UI decodes the JWT's role (without
  verifying it) only to hide controls the caller can't use. Editing the stored
  token changes what is drawn, never what is allowed.
- **Token storage:** access + refresh tokens are in `localStorage` (a SPA with no
  server-side session). The defence is the CSP: `script-src 'self'`, no inline
  script, no `eval`, `frame-ancestors 'none'`, so injected script has nowhere to
  run. There is no server-side logout/revocation endpoint yet, so "Sign out"
  forgets the tokens locally; they remain valid until they expire.
- Expired access token: one refresh (shared across parallel requests), then a retry;
  if that fails the user is returned to sign-in with an explanation.
- External links use `rel="noopener noreferrer"`; client-side navigation only accepts
  same-origin paths.

## Deliberate non-features

This is a login-gated operations tool, not a public website. A few common site
features were therefore left out on purpose:

- **Cookie banner:** the app sets no cookies and loads no third-party scripts.
  `localStorage` holds only the session and the theme, both strictly necessary.
  A banner would be noise (and implies tracking that doesn't exist).
- **UTM tracking / analytics:** there is no analytics backend, and campaign
  attribution is meaningless for an authenticated internal tool.
- **Floating contact button:** it would sit on top of tables on phones. Support
  contact (`ICOP_SUPPORT_EMAIL`) is in the footer, clickable and copyable.

## Accessibility

Skip link; one `h1` per page that receives focus on navigation; labelled controls;
a real `<table>` that restacks into labelled cards on phones; focus trap and focus
return in dialogs; `role="alert"` for errors; visible focus rings; `prefers-reduced-motion`
and `prefers-color-scheme` respected. `axe-core` (WCAG 2.0/2.1 A+AA and best practices)
reports no violations on any page in light and dark mode.
