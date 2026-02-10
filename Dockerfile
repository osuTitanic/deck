FROM python:3.14-alpine AS builder

ENV PYO3_USE_ABI3_FORWARD_COMPATIBILITY=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Build dependencies for pillow, psycopg2, rosu-pp-py, etc.
RUN apk add --no-cache \
    build-base \
    cargo \
    curl \
    freetype-dev \
    git \
    lcms2-dev \
    libffi-dev \
    libjpeg-turbo-dev \
    linux-headers \
    openjpeg-dev \
    openssl-dev \
    pkgconf \
    postgresql-dev \
    rust \
    tiff-dev \
    zlib-dev

WORKDIR /tmp/build
COPY requirements.txt ./
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip setuptools wheel && \
    pip install --no-compile --root /install -r requirements.txt && \
    pip install --no-compile --root /install granian[pname,uvloop]

FROM python:3.14-alpine

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Install runtime dependencies
RUN apk add --no-cache \
    ca-certificates \
    curl \
    ffmpeg \
    freetype \
    lcms2 \
    libffi \
    libjpeg-turbo \
    libstdc++ \
    openjpeg \
    openssl \
    postgresql-libs \
    tini \
    tiff \
    zlib

# Copy only the installed python packages and entry points from the builder image
COPY --from=builder /install/usr/local /usr/local

ARG WEB_WORKERS=4
ENV WEB_WORKERS=${WEB_WORKERS}

ARG WEB_THREADS_RUNTIME=2
ENV WEB_THREADS_RUNTIME=${WEB_THREADS_RUNTIME}

WORKDIR /deck
COPY . .

# Precompile application modules to lower start latency
RUN python -m compileall -q app

STOPSIGNAL SIGTERM
ENTRYPOINT ["/sbin/tini", "--"]

CMD ["/bin/sh", "-c", "granian --host 0.0.0.0 --port 80 --interface asgi --workers ${WEB_WORKERS} --runtime-threads ${WEB_THREADS_RUNTIME} --loop uvloop --http 1 --no-ws --backpressure 128 --respawn-failed-workers --access-log --process-name deck-worker --workers-kill-timeout 5 --workers-lifetime 43200 --workers-max-rss 512 app:api"]