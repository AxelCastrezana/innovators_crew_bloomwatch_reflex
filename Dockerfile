# Use Python 3.11 as base image (compatible with geospatial libraries)
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive

# Install system dependencies required for geospatial libraries
RUN apt-get update && apt-get install -y \
    # Essential build tools
    build-essential \
    gcc \
    g++ \
    # GDAL and geospatial libraries
    gdal-bin \
    libgdal-dev \
    libgeos-dev \
    libproj-dev \
    libspatialindex-dev \
    # Additional dependencies for cartopy and other libs
    libcairo2-dev \
    libgirepository1.0-dev \
    pkg-config \
    # Network and utilities
    curl \
    wget \
    git \
    unzip \
    # Cleanup
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Set GDAL environment variables
ENV GDAL_CONFIG=/usr/bin/gdal-config \
    CPLUS_INCLUDE_PATH=/usr/include/gdal \
    C_INCLUDE_PATH=/usr/include/gdal

# Create app directory
WORKDIR /app

# Copy requirements first for better Docker layer caching
COPY requirements.txt .

# Upgrade pip and install Python dependencies
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

# Install GDAL Python bindings first (version must match system GDAL)
RUN pip install --no-cache-dir GDAL==$(gdal-config --version)

# Install other Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . .

# Create necessary directories
RUN mkdir -p assets uploaded_files .states

# Set proper permissions
RUN chmod -R 755 /app

# Expose port 8000 (default Reflex port)
EXPOSE 8000

# Add healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/ || exit 1

# Command to run the application
CMD ["python", "-m", "reflex", "run", "--backend-host", "0.0.0.0", "--backend-port", "8000"]