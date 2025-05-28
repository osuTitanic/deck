FROM python:3.12-slim-bookworm

# Installing/Updating system dependencies
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
RUN pip install --no-cache-dir gunicorn
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Get config for deployment
ARG WEB_WORKERS=4
ENV WEB_WORKERS $WEB_WORKERS

# Generate __pycache__ directories
ENV PYTHONDONTWRITEBYTECODE=1
RUN python -m compileall -q app

CMD gunicorn \
        --access-logfile - \
        --preload \
        -b 0.0.0.0:80 \
        -w $WEB_WORKERS \
        -k uvicorn.workers.UvicornWorker \
        --max-requests 10000 \
        --max-requests-jitter 5000 \
        app:api