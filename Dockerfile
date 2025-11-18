FROM python:3.13-slim-bookworm AS builder

ENV DEBIAN_FRONTEND=noninteractive \
    PYO3_USE_ABI3_FORWARD_COMPATIBILITY=1

# Installing build dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        curl \
        git \
        libpq-dev \
        libssl-dev \
        pkg-config \
    && rm -rf /var/lib/apt/lists/*

# Install rust toolchain
RUN curl -sSf https://sh.rustup.rs | sh -s -- -y --profile minimal
ENV PATH="/root/.cargo/bin:${PATH}"

WORKDIR /tmp/build
COPY requirements.txt ./

RUN pip install --upgrade pip setuptools wheel && \
    pip install --no-cache-dir --no-compile --root /install -r requirements.txt && \
    pip install --no-cache-dir --no-compile --root /install gunicorn

FROM python:3.13-slim-bookworm

ENV DEBIAN_FRONTEND=noninteractive

# Installing runtime dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ffmpeg \
        libavcodec-extra \
        libpq5 \
        libssl3 \
        tini \
    && apt-get clean && rm -rf /var/lib/apt/lists/* /var/cache/apt/archives

# Copy only installed site-packages from builder
COPY --from=builder /install/usr/local /usr/local

# Runtime configuration
ARG WEB_WORKERS=4
ENV WEB_WORKERS=${WEB_WORKERS} \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Copy source code
WORKDIR /deck
COPY . .

# Precompile python files for faster startup
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