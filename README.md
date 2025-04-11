# Simple-Updown

Simple-Updown is a lightweight file upload and download service with a clean and intuitive web interface.

## Features

- Easy file uploading and downloading functionality
- Clean, responsive user interface
- Support for multiple storage backends:
  - Local file storage
  - Cloudflare R2 bucket storage (S3-compatible)
- Docker containerization for simple deployment

## Quick Start

### Using Docker
Pull the image
``` bash
docker pull gihyeon21/simple-updown
```
Run with default configuration
``` bash
docker run -p 9000:9000 gihyeon21/simple-updown
```

The service will be available at http://localhost:9000

### Using Docker Compose

Choose one of the following deployment options:

#### Local Storage Version
Run with local storage configuration
``` bash
docker-compose -f docker-compose.local.yml up -d
```
#### Cloudflare R2 Storage Version
Run with R2 storage configuration
``` bash
docker-compose -f docker-compose.r2.yml up -d
```
## Configuration

Copy the sample environment file to create your configuration:
``` bash
cp .env_sample .env
```
Edit the .env file with your preferred settings.

## Project Structure

- `simple-updown-frontend/`: Vue.js frontend application
- `simple-updown-backend/`: Python backend service
- `templates/`: HTML templates