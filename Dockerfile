# PIXELSLIME — one image, two entrypoints.
#
# The Container App runs `uvicorn` and serves both the API and the built SPA, so
# there is a single origin and therefore no CORS problem with asmDB. The Container
# Apps Job runs the same image with `python -m app.jobs daily`, which is why the
# frontend build has to be present in the runtime layer even though the job never
# serves a page: one image, one tag, one thing to promote.

# ── stage 1: build the SPA ────────────────────────────────────────────────────
FROM node:22-alpine AS frontend

WORKDIR /build

# The design system is a workspace-local dependency of the app, so its manifest
# has to be present before `npm ci` or the install graph is incomplete.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund

COPY frontend/ ./
COPY contracts/ ../contracts/

# VITE_USE_MOCK must be false here. The mock is constant-folded out of the
# bundle, and shipping it would put a fake API in production.
ENV VITE_USE_MOCK=false
RUN npm run build


# ── stage 2: python dependencies ──────────────────────────────────────────────
FROM python:3.12-slim AS deps

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /install

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY backend/pyproject.toml ./
# Install dependencies only, without the project itself, so this layer survives
# any change to application code.
RUN python - <<'PY' > /tmp/requirements.txt
import tomllib, pathlib
cfg = tomllib.loads(pathlib.Path("pyproject.toml").read_text())
deps = cfg["project"]["dependencies"] + cfg["project"]["optional-dependencies"]["chain"]
print("\n".join(deps))
PY
RUN pip install -r /tmp/requirements.txt


# ── stage 3: runtime ──────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH" \
    FRONTEND_DIST=/app/frontend/dist

COPY --from=deps /opt/venv /opt/venv

WORKDIR /app

COPY backend/app/ ./app/
COPY contracts/ ./contracts/
COPY assets/ ./assets/
COPY --from=frontend /build/dist ./frontend/dist

# Never run as root. The app writes nothing to disk - blobs go to Storage and
# rows go to asmDB - so a read-only home is fine.
RUN useradd --create-home --shell /usr/sbin/nologin slime \
 && chown -R slime:slime /app
USER slime

EXPOSE 8000

# The Container App probes this; a sleeping asmDB degrades it rather than
# failing it, so a cold database does not take the site down.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status == 200 else 1)"

# Default entrypoint: the API. The daily job overrides this with
#   ["python", "-m", "app.jobs", "daily"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
