# syntax=docker/dockerfile:1
FROM ghcr.io/astral-sh/uv:0.13.4 AS uv

FROM python:3.13-slim-bookworm AS python-base
RUN python -m pip uninstall --yes pip

FROM python-base AS dependencies
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN --mount=from=uv,source=/uv,target=/bin/uv \
    UV_PYTHON_DOWNLOADS=never UV_LINK_MODE=copy \
    uv sync --frozen --no-dev --no-editable --no-cache

FROM python-base AS runtime
ARG APP_UID=1002
ARG APP_GID=1002
ARG APP_HOME=/home/alex
ARG REVISION=development
RUN groupadd --gid "$APP_GID" developer && useradd --uid "$APP_UID" --gid "$APP_GID" \
    --home-dir "$APP_HOME" --create-home developer
WORKDIR /app
COPY --from=dependencies /app /app
COPY scripts/entrypoint.sh /usr/local/bin/telegram-vibecoding-entrypoint
RUN chmod 755 /usr/local/bin/telegram-vibecoding-entrypoint
ENV TELEGRAM_VIBECODING_REVISION=$REVISION
ENV PATH="/app/.venv/bin:$PATH"
USER developer
ENTRYPOINT ["/usr/local/bin/telegram-vibecoding-entrypoint"]
