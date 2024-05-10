FROM python:3.11-bullseye

# Installing/Updating system dependencies
RUN apt update -y
RUN apt install postgresql git curl ffmpeg -y

# Install rust toolchain
RUN curl -sSf https://sh.rustup.rs | sh -s -- -y
ENV PATH="/root/.cargo/bin:${PATH}"

# Update pip
RUN pip install --upgrade pip

WORKDIR /deck

# Install python dependencies
COPY requirements.txt ./
RUN pip install -r requirements.txt
RUN pip install gunicorn

# Copy source code
COPY . .

# Get config for deployment
ARG WEB_WORKERS=4
ENV WEB_WORKERS $WEB_WORKERS

CMD gunicorn \
        --access-logfile - \
        -b 0.0.0.0:80 \
        -w $WEB_WORKERS \
        -k uvicorn.workers.UvicornWorker \
        app:api