FROM python:3.12-slim

WORKDIR /app

# Install system dependencies needed to build some Python packages
# We combine the apt update/install/cleanup to keep the image slim.
RUN apt-get update &&     apt-get install -y --no-install-recommends gcc gettext librsync-dev &&     rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Expose the production backend port
EXPOSE 5005

# Command to run the application (using your optimized script)
CMD ["./gunicorn_arc.sh"]
