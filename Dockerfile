# ── 1단계: 프론트엔드 빌드 ──────────────────────────────────────────────────────
FROM --platform=${BUILDPLATFORM:-linux/amd64} node:20-slim AS frontend-builder

WORKDIR /app/frontend

COPY simple-updown-frontend/package*.json ./
RUN npm ci --omit=dev
COPY simple-updown-frontend/ .
RUN npm run build

# ── 2단계: 런타임 ────────────────────────────────────────────────────────────────
FROM --platform=${TARGETPLATFORM:-linux/amd64} python:3.12-slim

ARG STORAGE_TYPE=local
ARG BUILD_DATE=""
ARG VERSION="devel"

ENV STORAGE_TYPE=${STORAGE_TYPE} \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

LABEL maintainer="simple-updown" \
      org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.description="Simple Upload/Download Service" \
      storage.type="${STORAGE_TYPE}"

WORKDIR /app

COPY simple-updown-backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY simple-updown-backend/ .

RUN mkdir -p /app/static /app/uploads /app/thumbnails

COPY --from=frontend-builder /app/frontend/dist/ /app/static/

RUN echo "Storage Type: ${STORAGE_TYPE}\nBuild Date: ${BUILD_DATE}\nVersion: ${VERSION}" \
    > /app/static/version.txt

RUN groupadd -r appuser && useradd -r -g appuser appuser && \
    chown -R appuser:appuser /app

USER appuser

EXPOSE 9000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "9000"]