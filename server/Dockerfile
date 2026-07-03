FROM python:3.13-slim

# uv provides fast, reproducible installs from the committed uv.lock.
COPY --from=ghcr.io/astral-sh/uv:0.9.13 /uv /uvx /bin/

WORKDIR /app

# Use the project virtualenv uv creates, without needing to activate it.
ENV PATH="/app/.venv/bin:$PATH" \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1

# WeasyPrint runtime dependencies (Pango/GdkPixbuf/libffi) plus the ATS-safe
# fonts the resume template targets ('Liberation Sans', 'DejaVu Sans'). These
# are small apt packages (tens of MB) — far lighter and faster to build than
# the previous Playwright+Chromium install (several hundred MB).
RUN apt-get update && apt-get install -y --no-install-recommends \
      libpango-1.0-0 \
      libpangoft2-1.0-0 \
      libharfbuzz-subset0 \
      libgdk-pixbuf-2.0-0 \
      libffi8 \
      fonts-liberation \
      fonts-dejavu-core \
      fontconfig \
 && rm -rf /var/lib/apt/lists/*

# Install dependencies first (cached until the lockfile changes), production only.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

COPY . .

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/entrypoint.sh"]
