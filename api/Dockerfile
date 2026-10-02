# family-history API image: api, worker, migrate and mcp share it (docs/ARCHITECTURE.md).
# Build context: api/.  docker build -t family-history-api api/
#
# - Base pinned by digest (python:3.12-slim, multi-arch index).
# - Dependencies installed only from the hashed lock (api/scripts/lock.sh).
# - Runs as uid 1001 with a read-only root filesystem; only /tmp needs to be writable.

FROM python:3.12-slim@sha256:dddfd7e07f9d15aeeca61529320492139d21cac7f0070c00609243e51e4e0016 AS build

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN python -m venv /opt/venv
COPY requirements/runtime.txt /tmp/runtime.txt
RUN /opt/venv/bin/pip install --require-hashes --no-deps --only-binary=:all: -r /tmp/runtime.txt

COPY src /app/src
# Byte-compile at build time: the root filesystem is read-only at run time.
RUN /opt/venv/bin/python -m compileall -q /app/src /opt/venv/lib


FROM python:3.12-slim@sha256:dddfd7e07f9d15aeeca61529320492139d21cac7f0070c00609243e51e4e0016 AS runtime

LABEL org.opencontainers.image.source="https://github.com/madfam-org/family-history" \
      org.opencontainers.image.licenses="AGPL-3.0-only" \
      org.opencontainers.image.title="family-history-api"

RUN groupadd --system --gid 1001 app \
    && useradd --system --uid 1001 --gid 1001 --home-dir /tmp --no-create-home \
       --shell /usr/sbin/nologin app

COPY --from=build /opt/venv /opt/venv
COPY --from=build /app/src /app/src

ENV PATH=/opt/venv/bin:$PATH \
    PYTHONPATH=/app/src \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOME=/tmp \
    TMPDIR=/tmp

WORKDIR /app
USER 1001:1001

EXPOSE 8000 9090

CMD ["uvicorn", "family_history.app:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
