FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH=/srv \
    PYTHONUNBUFFERED=1

WORKDIR /srv

# DejaVu fonts give the invoice PDF Slovak diacritics (fpdf2 core fonts are Latin-1 only).
RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies first so this layer is cached between code changes.
# Dev group (pytest, ruff) is included on purpose: tests and lint run inside this image.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen

COPY . .

EXPOSE 8000
CMD ["./entrypoint.sh"]
