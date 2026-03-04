FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Expose the production backend port
EXPOSE 5005

# Command to run the application (using your optimized script)
CMD ["./gunicorn_arc.sh"]
