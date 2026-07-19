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

# Claude Code CLI (native binary, no Node.js needed) — powers the Claude
# provider's Pro/Max subscription (CLAUDE_CODE_OAUTH_TOKEN) auth mode, used
# instead of a regular Anthropic API key when the stored secret is an OAuth
# token. DISABLE_AUTOUPDATER/DISABLE_UPDATES must NOT be set yet here: the
# installer treats them as an "updates disabled by administrator" policy and
# refuses to install anything at all (while still printing a misleading
# "Installation complete!") if they're already set at install time.
#
# The native installer places the binary under $HOME (/root/.local/...),
# which is only readable by root. But `claude` itself refuses to run with
# --permission-mode bypassPermissions as root at all ("cannot be used with
# root/sudo privileges") — a hard safety check with no override flag — so
# app/llm/claude_cli.py runs the CLI subprocess as the unprivileged
# `claudecli` user below, not as root. Relocate the (fully self-contained,
# single-binary) install to a world-readable path so that user can exec it.
ARG CLAUDE_CODE_VERSION=2.1.214
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && curl -fsSL https://claude.ai/install.sh | bash -s "${CLAUDE_CODE_VERSION}" \
    && apt-get purge -y curl && apt-get autoremove -y && rm -rf /var/lib/apt/lists/* \
    && install -d -m 755 /opt/claude-code \
    && install -m 755 "$(readlink -f /root/.local/bin/claude)" /opt/claude-code/claude \
    && ln -s /opt/claude-code/claude /usr/local/bin/claude \
    && rm -rf /root/.local/share/claude /root/.local/bin/claude \
    && useradd --system --no-create-home --shell /usr/sbin/nologin claudecli \
    && claude --version

# Only disable auto-updates for the running container, now that install is done.
ENV DISABLE_AUTOUPDATER=1 \
    DISABLE_UPDATES=1

COPY . .

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/entrypoint.sh"]
