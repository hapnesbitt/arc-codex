FROM python:3.12-slim

WORKDIR /app

# Install standard endemic build tools, graphic libraries, AND python3-apt.
# Combined update, install, and list cleanup.
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        pkg-config \
        gettext \
        gcc \
        librsync-dev \
        libcairo2-dev \
        libgirepository1.0-dev \
        libglib2.0-dev \
        python3-apt && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# Surgical fix for previous steps (captured here to ensure repeatability).
# Relax Mako dependency to a stable version.
sed -i 's/^Mako==1.3.9.dev0/Mako>=1.3.0/' requirements.txt

# Final attempt for backend dependencies using legacy flag to bypass peer conflicts.
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Expose the production backend port
EXPOSE 5005

# Command to run the application (using your optimized script)
CMD ["./gunicorn_arc.sh"]
