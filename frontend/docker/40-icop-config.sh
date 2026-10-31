#!/bin/sh
# Runs on container start (the official nginx image executes /docker-entrypoint.d/*.sh).
# Writes /config.json from environment variables so ONE image serves every
# environment. Values are JSON-escaped here and re-validated by the browser
# (src/config/runtime.ts only accepts http(s) URLs and well-formed emails).
set -eu

escape() {
  # backslash, double quote, then strip control characters
  printf '%s' "${1:-}" | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g' | tr -d '\000-\037'
}

cat > /usr/share/nginx/html/config.json <<JSON
{
  "environmentLabel": "$(escape "${ICOP_ENVIRONMENT_LABEL:-}")",
  "grafanaUrl": "$(escape "${ICOP_GRAFANA_URL:-}")",
  "apiDocsUrl": "$(escape "${ICOP_API_DOCS_URL:-}")",
  "supportEmail": "$(escape "${ICOP_SUPPORT_EMAIL:-}")"
}
JSON
