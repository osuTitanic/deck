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
    pip install --no-compile --root /install gunicorn

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
ENV WEB_WORKERS=${WEB_WORKERS} \
    API_WORKERS=${WEB_WORKERS}

WORKDIR /deck
COPY . .

# Precompile application modules to lower start latency
RUN python -m compileall -q app

STOPSIGNAL SIGTERM
ENTRYPOINT ["/sbin/tini", "--"]

CMD ["/bin/sh", "-c", "gunicorn --access-logfile - --preload -b 0.0.0.0:80 -w ${WEB_WORKERS} -k uvicorn.workers.UvicornWorker --max-requests 10000 --max-requests-jitter 5000 --graceful-timeout 5 --timeout 10 app:api"]