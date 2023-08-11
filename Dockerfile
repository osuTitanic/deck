FROM python:3.9-bullseye

# Installing/Updating system dependencies
RUN apt update -y
RUN apt install postgresql git curl -y

# Install rust toolchain
RUN curl -sSf https://sh.rustup.rs | sh -s -- -y
ENV PATH="/root/.cargo/bin:${PATH}"

# Update pip
RUN pip install --upgrade pip

WORKDIR /deck

# Install python dependencies
COPY requirements.txt ./
RUN pip install -r requirements.txt

# Copy source code
COPY . .

# Get config for deployment
ENV WEB_HOST $WEB_HOST
ENV WEB_PORT $WEB_PORT
ENV WEB_WORKERS $WEB_WORKERS

EXPOSE $WEB_PORT

CMD gunicorn app:api \
        --workers $WEB_WORKERS \
        --worker-class uvicorn.workers.UvicornWorker \
        --bind $WEB_HOST:$WEB_PORT \
        --access-logfile '-'