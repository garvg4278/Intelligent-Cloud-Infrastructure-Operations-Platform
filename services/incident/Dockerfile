FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Run unprivileged: a code-exec bug in the service should not be root in the container.
# Fixed numeric UID so Kubernetes runAsNonRoot can verify it (the chart sets runAsUser 10001).
RUN useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin icop
USER 10001

EXPOSE 8000

CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
