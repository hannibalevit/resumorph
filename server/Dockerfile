FROM python:3.13-slim

# uv provides fast, reproducible installs from the committed uv.lock.
COPY --from=ghcr.io/astral-sh/uv:0.9.13 /uv /uvx /bin/

WORKDIR /app

# Use the project virtualenv uv creates, without needing to activate it.
ENV PATH="/app/.venv/bin:$PATH" \
    HOME="/root" \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1

# Install dependencies first (cached until the lockfile changes), production only.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

COPY . .

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/entrypoint.sh"]
