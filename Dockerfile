FROM python:3.14-slim-trixie AS builder

ENV PYO3_USE_ABI3_FORWARD_COMPATIBILITY=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Build dependencies for pillow, psycopg2, rosu-pp-py, etc.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cargo \
    curl \
    git \
    libfreetype-dev \
    libffi-dev \
    libjpeg62-turbo-dev \
    liblcms2-dev \
    libopenjp2-7-dev \
    libpq-dev \
    libssl-dev \
    libtiff-dev \
    linux-libc-dev \
    pkg-config \
    rustc \
    zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /tmp/build
COPY requirements.txt ./
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip setuptools wheel && \
    pip install --no-compile --root /install -r requirements.txt && \
    pip install --no-compile --root /install granian[pname,uvloop] && \
    native_dir=/install/usr/local/lib/python3.14/site-packages/osu_native_py/native/bin && \
    find "$native_dir" -type f -name osu.Native.so -print -quit | grep -q .

FROM python:3.14-slim-trixie

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    ffmpeg \
    libffi8 \
    libfreetype6 \
    libicu76 \
    libjpeg62-turbo \
    liblcms2-2 \
    libopenjp2-7 \
    libpq5 \
    libstdc++6 \
    libtiff6 \
    openssl \
    tini \
    zlib1g \
    && rm -rf /var/lib/apt/lists/*

# Copy only the installed python packages and entry points from the builder image
COPY --from=builder /install/usr/local /usr/local

ARG WEB_WORKERS=4
ENV WEB_WORKERS=${WEB_WORKERS}

ARG WEB_THREADS_RUNTIME=2
ENV WEB_THREADS_RUNTIME=${WEB_THREADS_RUNTIME}

WORKDIR /deck
COPY . .

# Precompile python modules & verify osu-native is installed correctly
RUN python -c 'from osu_native_py.native import LIB_PATH; assert LIB_PATH.is_file(), LIB_PATH' && \
    python -m compileall -q /usr/local/lib/python3.14/site-packages app

STOPSIGNAL SIGINT
ENTRYPOINT ["/usr/bin/tini", "--"]

CMD ["/bin/sh", "-c", "granian --host 0.0.0.0 --port 80 --interface asgi --workers ${WEB_WORKERS} --runtime-threads ${WEB_THREADS_RUNTIME} --loop uvloop --http 1 --no-ws --backpressure 128 --respawn-failed-workers --access-log --process-name deck-worker --workers-kill-timeout 5 --workers-lifetime 43200 --workers-max-rss 512 app:api"]
