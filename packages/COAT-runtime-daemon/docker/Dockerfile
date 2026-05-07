FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

# uv provides reliable, fast workspace installs.
RUN pip install --no-cache-dir uv

WORKDIR /app

COPY pyproject.toml uv.lock* /app/
COPY packages/ /app/packages/

RUN uv sync --frozen --no-dev

EXPOSE 7878

ENTRYPOINT ["uv", "run", "COAT-runtime-daemon"]
CMD ["--config", "/etc/COAT-runtime/config.yaml"]
