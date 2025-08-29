FROM python:3.13-slim-bookworm AS builder

# Installing build dependencies
RUN apt update -y && \
    apt install -y --no-install-recommends \
    postgresql-client git curl ffmpeg libavcodec-extra \
    && rm -rf /var/lib/apt/lists/*

# Install rust toolchain
RUN curl -sSf https://sh.rustup.rs | sh -s -- -y
ENV PATH="/root/.cargo/bin:${PATH}"

# Switch to project directory
WORKDIR /deck

# Install python dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir gunicorn

FROM python:3.13-slim-bookworm

# Installing runtime dependencies
RUN apt update -y && \
    apt install -y --no-install-recommends \
    ffmpeg libavcodec-extra tini curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from builder
COPY --from=builder /usr/local /usr/local

# Get config for deployment
ARG WEB_WORKERS=4
ENV WEB_WORKERS=$WEB_WORKERS

# Disable output buffering
ENV PYTHONUNBUFFERED=1

# Copy source code
WORKDIR /deck
COPY . .

# Generate __pycache__ directories
ENV PYTHONDONTWRITEBYTECODE=1
RUN python -m compileall -q app

STOPSIGNAL SIGTERM
ENTRYPOINT ["/usr/bin/tini", "--"]

CMD gunicorn \
    --access-logfile - \
    --preload \
    -b 0.0.0.0:80 \
    -w $WEB_WORKERS \
    -k uvicorn.workers.UvicornWorker \
    --max-requests 10000 \
    --max-requests-jitter 5000 \
    --graceful-timeout 5 \
    --timeout 10 \
    app:api