FROM python:3.12-slim

WORKDIR /app

# Install standard endemic build tools and graphic libraries.
# Combined update, install, and list cleanup.
RUN apt-get update && \
    apt-get install -y --no-install-recommends         build-essential \
        gettext \
        gcc \
        librsync-dev \
        libcairo2-dev \
        libgirepository1.0-dev \
        libglib2.0-dev && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Expose the production backend port
EXPOSE 5005

# Command to run the application (using your optimized script)
CMD ["./gunicorn_arc.sh"]
