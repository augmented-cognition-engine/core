FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir uv

# Install the same complete source surface used to build the wheel. The old
# order installed an editable project before its packages existed and omitted
# the thin MCP client, README, and license metadata from the image entirely.
COPY pyproject.toml uv.lock build_backend.py README.md ROADMAP.md CONTRIBUTING.md SECURITY.md CHANGELOG.md LICENSE NOTICE ./
COPY core/ core/
COPY extensions/ extensions/
COPY ace/ ace/
COPY ace_mcp_client/ ace_mcp_client/
COPY scripts/ scripts/
COPY evaluations/ evaluations/
COPY docs/ docs/
RUN uv pip install --system --no-cache .

# Run as non-root for security — prevents container escapes from writing host files
RUN adduser --disabled-password --gecos "" aceuser && chown -R aceuser /app
USER aceuser

EXPOSE 3000

# Liveness probe: always 200 if the event loop is alive.
# Use /health/live (not /health/ready) so Docker doesn't restart healthy
# instances while the DB is temporarily unavailable at startup.
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:3000/health/live')" || exit 1

CMD ["uvicorn", "core.engine.api.main:app", "--host", "0.0.0.0", "--port", "3000"]
