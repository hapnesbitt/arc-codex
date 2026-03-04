FROM python:3.12-slim

WORKDIR /app

# Install native build tools, graphical libs, and OS packages strategy (Robust Fix)
RUN apt-get update && \
    apt-get install -y --no-install-recommends         build-essential \
        pkg-config \
        gettext \
        gcc \
        librsync-dev \
        libcairo2-dev \
        libgirepository1.0-dev \
        libglib2.0-dev \
        libsystemd-dev && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Expose production backend port
EXPOSE 5005

# Optimized run script
CMD ["./gunicorn_arc.sh"]
