# Use an official Python runtime as a parent image
FROM python:3.12-slim

# Set the working directory in the container
WORKDIR /app

# Install necessary dependencies for building packages
RUN apt-get update && apt-get install -y \
    build-essential \
    libssl-dev \
    libffi-dev \
    python3-dev \
    gcc \
    make \
    && rm -rf /var/lib/apt/lists/*

# Copy the backend directory to /app/backend in the container
COPY SysCall/backend /app/backend

# Copy the frontend directory to /app/frontend in the container
COPY SysCall/frontend /app/frontend

# Копируем файл beacons.beacons в контейнер
COPY SysCall/backend/beacons.beacons /app/backend/beacons.beacons

# Copy the requirements.txt file from the root directory
COPY requirements.txt /app/

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Expose port 5000 for Flask
EXPOSE 5000

# Define environment variable for Flask
ENV FLASK_APP=/app/backend/app.py
ENV FLASK_RUN_HOST=0.0.0.0

# Run the Flask app
CMD ["flask", "run"]
