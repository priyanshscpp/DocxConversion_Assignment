# Quick Start Guide

## Prerequisites
- Docker Desktop must be **running** before starting the services

## Step-by-Step Instructions

### 1. Start Docker Desktop
- Open **Docker Desktop** from Windows Start menu
- Wait until you see the Docker whale icon in your system tray
- The icon should be steady (not animating) when Docker is ready

### 2. Start the Services

**Option A: Using the batch script (Windows)**
```bash
start.bat
```

**Option B: Using Docker Compose directly**
```bash
docker compose up --build
```

### 3. Wait for Services to Start
You should see:
- ✔ PostgreSQL database starting
- ✔ Redis starting  
- ✔ API service starting
- ✔ Celery worker starting

### 4. Verify the API is Running
Open your browser and go to:
- **API Documentation**: http://localhost:8000/docs
- **Health Check**: http://localhost:8000/

### 5. Test the Service
You can test the API using the Swagger UI at http://localhost:8000/docs

## Troubleshooting

### Error: "The system cannot find the file specified"
**Solution**: Docker Desktop is not running. Start Docker Desktop and wait for it to fully initialize.

### Error: Port already in use
**Solution**: Another service is using ports 8000, 5432, or 6379. Stop those services or change ports in docker-compose.yml.

### Services won't start
**Solution**: 
1. Make sure Docker Desktop is running
2. Check Docker Desktop settings → Resources → ensure enough memory allocated (8GB+ recommended)
3. Try: `docker compose down` then `docker compose up --build`

## Stopping the Services
Press `Ctrl+C` in the terminal, or run:
```bash
docker compose down
```

To remove all data (volumes):
```bash
docker compose down -v
```

