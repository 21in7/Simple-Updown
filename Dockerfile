# Frontend build stage
FROM --platform=${BUILDPLATFORM:-linux/amd64} node:16 AS frontend-builder

WORKDIR /app/frontend

# Install dependencies and build the frontend
COPY simple-updown-frontend/package*.json ./
RUN npm install
COPY simple-updown-frontend/ .
RUN npm run build

# Backend build stage
FROM --platform=${TARGETPLATFORM:-linux/amd64} python:3.12-slim

WORKDIR /app

# Define build argument and set it as environment variable
ARG STORAGE_TYPE=local
ENV STORAGE_TYPE=${STORAGE_TYPE}

# Add build information (optional)
ARG BUILD_DATE=""
ARG VERSION="devel"
LABEL maintainer="simple-updown"
LABEL org.opencontainers.image.created="${BUILD_DATE}"
LABEL org.opencontainers.image.version="${VERSION}"
LABEL org.opencontainers.image.description="Simple Upload/Download Service"
LABEL storage.type="${STORAGE_TYPE}"

# Copy backend requirements and install
COPY simple-updown-backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code
COPY simple-updown-backend/ .

# Create necessary directories
RUN mkdir -p /app/static /app/uploads /app/file_metadata /app/thumbnails

# Copy built frontend to backend static files
COPY --from=frontend-builder /app/frontend/dist/ /app/static/

# Create version info file
RUN echo "Storage Type: ${STORAGE_TYPE}" > /app/static/version.txt && \
    echo "Build Date: ${BUILD_DATE}" >> /app/static/version.txt && \
    echo "Version: ${VERSION}" >> /app/static/version.txt

# Create a non-root user and group
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Set permissions for app directories
RUN chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Expose API port
EXPOSE 9000

# Command to run the application
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "9000"]