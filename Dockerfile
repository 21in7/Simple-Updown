# Frontend build stage
FROM node:16 AS frontend-builder

WORKDIR /app/frontend

# Install dependencies and build the frontend
COPY simple-updown-frontend/package*.json ./
RUN npm install
COPY simple-updown-frontend/ .
RUN npm run build

# Backend build stage
FROM python:3.12-slim

WORKDIR /app

# Copy backend requirements and install
COPY simple-updown-backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code
COPY simple-updown-backend/ .

# Copy built frontend to backend static files
COPY --from=frontend-builder /app/frontend/dist /app/static

# Expose API port
EXPOSE 9000

# Command to run the application
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "9000", "--reload"]