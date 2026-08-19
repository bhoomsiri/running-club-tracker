# Backend image for Cloud Run.
#
# Two things Cloud Run dictates:
#   - the port is chosen by the platform and handed over as $PORT, so it is read from
#     the environment at start rather than baked into the image;
#   - the container should stop promptly on SIGTERM, hence `exec` below (uvicorn becomes
#     PID 1 instead of hiding behind a shell).
#
# Migrations are NOT run here. Several instances start at once, and they would race on
# the schema — `alembic upgrade head` is its own deploy step (see deploy.yml).

# ---------------------------------------------------------------------- build stage
FROM python:3.12-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /src

# pyproject is the single source of truth for dependencies — no second list to drift.
COPY pyproject.toml ./
COPY app ./app

# Installed into its own prefix so only the finished site-packages crosses into the
# runtime image: no pip cache, no build tooling, nothing to exploit later.
RUN pip install --prefix=/install .

# -------------------------------------------------------------------- runtime stage
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

# The base image is rebuilt on its own schedule, so it lags Debian's security updates by
# days at a time — long enough for the image scan in deploy.yml to hold a release over a
# patch that already exists upstream. Applying them here closes that window at build
# time, which is the only place this image can be patched: Cloud Run containers are
# replaced, never updated in place.
RUN apt-get update \
    && apt-get upgrade -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /install /usr/local

WORKDIR /app
COPY app ./app
COPY alembic.ini ./

# Non-root: a process that gets compromised should not also own the filesystem.
# A fixed high uid, so the identity is the same in every environment.
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8080

# Through `sh` because $PORT has to expand at run time, not at build time; `exec` so
# uvicorn replaces the shell as PID 1 and receives Cloud Run's SIGTERM directly.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
