# Use an official Python runtime as a parent image
FROM python:3.10-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set work directory
WORKDIR /app

# Install system dependencies (required if compiling physical PyBaMM solvers or numpy)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gfortran \
    libblas-dev \
    liblapack-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements list
COPY requirements.txt /app/

# Install python packages
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY backend/ /app/backend/
COPY frontend/ /app/frontend/

# Expose standard web traffic port (HTTP)
EXPOSE 80

# Run the server on port 80
CMD ["python3", "backend/server.py", "80"]
