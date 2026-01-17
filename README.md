# Bulk DOCX to PDF Conversion Service

A production-ready, scalable microservice for converting DOCX files to PDF using FastAPI, Celery, Redis, and LibreOffice. Supports bulk uploads with asynchronous processing and per-file error handling.

---

## 🏗️ Architecture Overview

### System Components

```
┌─────────────┐         ┌──────────────┐         ┌─────────────┐
│   Client    │────────▶│  FastAPI API │────────▶│    Redis    │
│             │         │   (Port 8000)│         │   (Queue)   │
└─────────────┘         └──────────────┘         └─────────────┘
                               │                        │
                               │                        ▼
                               │                 ┌─────────────┐
                               │                 │   Celery    │
                               │                 │   Worker    │
                               │                 └─────────────┘
                               │                        │
                               ▼                        ▼
                        ┌──────────────────────────────────┐
                        │       PostgreSQL Database        │
                        │    (Job & File Status Storage)   │
                        └──────────────────────────────────┘
                               │                        │
                               ▼                        ▼
                        ┌──────────────────────────────────┐
                        │      Shared Docker Volume        │
                        │   /app/storage (File Storage)    │
                        └──────────────────────────────────┘
```

### Key Architecture Decisions

#### 1. **Asynchronous Processing with Celery**
**Why?** The assignment explicitly requires non-blocking job submission.

- **Problem:** Converting large DOCX files can take 10-60 seconds each
- **Solution:** Celery workers process conversions in the background
- **Benefit:** API responds immediately (202 Accepted), users can poll for status

**Flow:**
```
1. Client uploads ZIP → API extracts files → Creates job in DB
2. API enqueues tasks to Redis → Returns job_id immediately
3. Celery workers pick up tasks → Convert DOCX to PDF using LibreOffice
4. Workers update DB status → Trigger finalization when all files done
5. Finalization task creates ZIP of PDFs → Job marked as completed
6. Client downloads ZIP via download endpoint
```

#### 2. **Message Queue (Redis)**
**Why?** Decouples API from workers for scalability.

- **API Service:** Stateless, can scale horizontally
- **Worker Service:** Stateless, can scale horizontally
- **Redis:** Acts as task broker and result backend
- **Benefit:** Can run multiple API instances and multiple workers independently

#### 3. **Shared File Storage (Docker Volume)**
**Why?** Multiple containers need access to the same files.

**Challenge:** API uploads files, workers read them, users download results.

**Solution:** Docker named volume `shared_storage` mounted at `/app/storage` in both API and worker containers.

```yaml
# docker-compose.yml
volumes:
  shared_storage:  # Named volume shared across containers

services:
  api:
    volumes:
      - shared_storage:/app/storage  # Mounted in API
  
  worker:
    volumes:
      - shared_storage:/app/storage  # Mounted in worker
```

**File Structure:**
```
/app/storage/
  ├── 1/                    # Job ID 1
  │   ├── upload.zip        # Original upload
  │   ├── file1.docx        # Extracted DOCX
  │   ├── file1.pdf         # Converted PDF
  │   ├── file2.docx
  │   ├── file2.pdf
  │   └── converted_files.zip  # Final downloadable ZIP
  ├── 2/                    # Job ID 2
  │   └── ...
```

#### 4. **Database for State Management (PostgreSQL)**
**Why?** Persistent, ACID-compliant storage for job and file status.

- **Jobs Table:** Stores job-level status (pending, processing, completed, failed, partial_success)
- **JobFiles Table:** Stores per-file status and error messages
- **Relationship:** One-to-Many (Job → JobFiles) with cascade delete
- **Benefit:** Allows precise status tracking and error reporting per file

#### 5. **LibreOffice for Conversion**
**Why?** Free, open-source, Linux-compatible DOCX to PDF converter.

**Alternatives considered:**
- `docx2pdf` library: ❌ Requires Microsoft Word (Windows/Mac only)
- `unoconv`: ❌ Deprecated, unreliable
- **LibreOffice (headless):** ✅ Works on Linux, reliable, widely used

**Implementation:**
```python
subprocess.run([
    'libreoffice',
    '--headless',           # No GUI
    '--convert-to', 'pdf',  # Output format
    '--outdir', output_dir, # Where to save PDF
    input_file              # DOCX file path
])
```

#### 6. **Per-File Error Handling**
**Why?** Assignment requires: "A single file failure should not stop the entire job."

**Implementation:**
- Each file conversion is a separate Celery task
- Try-catch around each conversion
- Failed files marked as `FAILED` with error message
- Successful files marked as `COMPLETED`
- Job status determined after all files processed:
  - All success → `COMPLETED`
  - All failed → `FAILED`
  - Mixed → `PARTIAL_SUCCESS`

**Benefit:** Users can download successfully converted files even if some fail.

---

## 🔄 Asynchronous Processing Flow

### Detailed Flow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. CLIENT UPLOADS ZIP                                           │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ 2. API HANDLER (POST /api/v1/jobs)                              │
│    - Validates ZIP file                                         │
│    - Creates Job record (status=PENDING)                        │
│    - Saves ZIP to /app/storage/{job_id}/upload.zip             │
│    - Extracts DOCX files                                        │
│    - Creates JobFile records for each DOCX                      │
│    - Enqueues conversion tasks to Redis                         │
│    - Returns 202 Accepted with job_id                           │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ 3. REDIS QUEUE                                                  │
│    - Stores tasks: [convert_file_task(file_id=1),              │
│                     convert_file_task(file_id=2), ...]          │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ 4. CELERY WORKER (Background)                                   │
│    For each file:                                               │
│    - Picks up task from Redis                                   │
│    - Updates JobFile status to PROCESSING                       │
│    - Reads DOCX from /app/storage/{job_id}/{filename}          │
│    - Runs LibreOffice conversion                                │
│    - Saves PDF to /app/storage/{job_id}/{filename}.pdf         │
│    - Updates JobFile status to COMPLETED or FAILED              │
│    - Triggers finalize_job_task                                 │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ 5. FINALIZATION TASK (After each file)                          │
│    - Checks if all files are processed (no PENDING/PROCESSING)  │
│    - If yes:                                                    │
│      * Creates ZIP of all successful PDFs                       │
│      * Determines overall job status                            │
│      * Updates Job status to COMPLETED/FAILED/PARTIAL_SUCCESS   │
│    - If no: Exits (will be triggered again by next file)        │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ 6. CLIENT POLLS STATUS (GET /api/v1/jobs/{job_id})             │
│    - Returns current job status and per-file breakdown          │
│    - Includes download_url when status is COMPLETED             │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ 7. CLIENT DOWNLOADS (GET /api/v1/jobs/{job_id}/download)       │
│    - Streams /app/storage/{job_id}/converted_files.zip         │
└─────────────────────────────────────────────────────────────────┘
```

### Why This Design?

1. **Non-blocking:** API returns immediately, doesn't wait for conversion
2. **Scalable:** Can add more workers to process files in parallel
3. **Resilient:** Individual file failures don't crash the entire job
4. **Transparent:** Users can track progress via status endpoint
5. **Efficient:** Workers process files concurrently (Celery handles this)

---

## 🗄️ Database Schema

```sql
-- Jobs Table
CREATE TABLE jobs (
    id SERIAL PRIMARY KEY,
    status VARCHAR(20) NOT NULL,  -- pending, processing, completed, failed, partial_success
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Job Files Table
CREATE TABLE job_files (
    id SERIAL PRIMARY KEY,
    job_id INTEGER REFERENCES jobs(id) ON DELETE CASCADE,
    filename VARCHAR(255) NOT NULL,
    status VARCHAR(20) NOT NULL,  -- pending, processing, completed, failed
    error_message TEXT NULL
);
```

**Design Notes:**
- `ON DELETE CASCADE`: Deleting a job deletes all its files
- `created_at`: Useful for cleanup jobs (delete old jobs after X days)
- `error_message`: Stores conversion errors for debugging

---

## 📡 API Endpoints

### Base URL
```
http://localhost:8000
```

### 1. Health Check
```http
GET /
```

**Response (200 OK):**
```json
{
  "message": "Service is running successfully"
}
```

---

### 2. Submit Conversion Job
```http
POST /api/v1/jobs/
Content-Type: multipart/form-data
```

**Request:**
- **Body:** `file` (ZIP file containing DOCX files)

**Example (cURL):**
```bash
curl -X POST "http://localhost:8000/api/v1/jobs/" \
  -F "file=@documents.zip"
```

**Response (202 Accepted):**
```json
{
  "job_id": 1,
  "status": "pending",
  "message": "Job created successfully"
}
```

**Error Responses:**
- `400 Bad Request`: Invalid file type, empty ZIP, no DOCX files
- `500 Internal Server Error`: Server error during processing

---

### 3. Get Job Status
```http
GET /api/v1/jobs/{job_id}
```

**Example:**
```bash
curl http://localhost:8000/api/v1/jobs/1
```

**Response (200 OK):**

**Pending/Processing:**
```json
{
  "id": 1,
  "status": "pending",
  "created_at": "2025-12-15T14:37:16.609641Z",
  "files": [
    {
      "id": 1,
      "filename": "report.docx",
      "status": "processing",
      "error_message": null
    },
    {
      "id": 2,
      "filename": "proposal.docx",
      "status": "pending",
      "error_message": null
    }
  ],
  "download_url": null
}
```

**Completed:**
```json
{
  "id": 1,
  "status": "completed",
  "created_at": "2025-12-15T14:37:16.609641Z",
  "files": [
    {
      "id": 1,
      "filename": "report.docx",
      "status": "completed",
      "error_message": null
    },
    {
      "id": 2,
      "filename": "proposal.docx",
      "status": "completed",
      "error_message": null
    }
  ],
  "download_url": "/api/v1/jobs/1/download"
}
```

**Partial Success (some files failed):**
```json
{
  "id": 1,
  "status": "partial_success",
  "created_at": "2025-12-15T14:37:16.609641Z",
  "files": [
    {
      "id": 1,
      "filename": "report.docx",
      "status": "completed",
      "error_message": null
    },
    {
      "id": 2,
      "filename": "corrupted.docx",
      "status": "failed",
      "error_message": "LibreOffice conversion failed: Invalid file format"
    }
  ],
  "download_url": "/api/v1/jobs/1/download"
}
```

**Error Responses:**
- `404 Not Found`: Job ID doesn't exist
- `422 Unprocessable Entity`: Invalid job ID format

---

### 4. Download Converted Files
```http
GET /api/v1/jobs/{job_id}/download
```

**Example:**
```bash
curl -O http://localhost:8000/api/v1/jobs/1/download
```

**Response (200 OK):**
- **Content-Type:** `application/zip`
- **Body:** ZIP file containing all successfully converted PDFs

**Error Responses:**
- `400 Bad Request`: Job not ready for download (still processing)
- `404 Not Found`: Job doesn't exist or result file not found

---

### 5. API Documentation (Swagger UI)
```http
GET /docs
```

Interactive API documentation with "Try it out" functionality.

---

## 🚀 Running the Project

### Prerequisites
- Docker Desktop installed and running
- 8GB+ RAM recommended
- Ports 8000, 5432, 6379 available

### Quick Start

1. **Clone the repository:**
```bash
cd /path/to/Backend-Repo
```

2. **Start all services:**
```bash
docker-compose up --build
```

This starts:
- **PostgreSQL** (port 5432): Database
- **Redis** (port 6379): Message queue
- **API** (port 8000): FastAPI application
- **Worker**: Celery worker for background processing

3. **Wait for services to be ready:**
```
✔ Container backend-repo-db-1      Healthy
✔ Container backend-repo-redis-1   Started
✔ Container backend-repo-api-1     Started
✔ Container backend-repo-worker-1  Started
```

4. **Verify API is running:**
```bash
curl http://localhost:8000/
# Response: {"message": "Service is running successfully"}
```

5. **Access API documentation:**
```
http://localhost:8000/docs
```

### Testing the Service

#### Quick Manual Test
```bash
./quick-test.sh
```

This script:
- Creates sample DOCX files
- Submits a conversion job
- Polls for completion
- Downloads and verifies results

#### Full Test Suite (31 tests)
```bash
./run-tests.sh
```

Or manually:
```bash
pip install -r requirements-test.txt
pytest tests/ -v
```

### Stopping the Service

```bash
# Stop containers
docker-compose down

# Stop and remove all data (volumes)
docker-compose down -v
```

---

## 🛠️ Local Development (Without Docker)

### Prerequisites
- Python 3.10+
- PostgreSQL installed and running
- Redis installed and running
- LibreOffice installed

### Setup

1. **Install dependencies:**
```bash
pip install -r requirements.txt
```

2. **Set environment variables:**
```bash
export DATABASE_URL="postgresql://user:password@localhost:5432/docx_converter"
export REDIS_URL="redis://localhost:6379/0"
export FILE_STORAGE_PATH="storage"
```

3. **Create database:**
```bash
createdb docx_converter
```

4. **Run API server:**
```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

5. **Run Celery worker (in separate terminal):**
```bash
celery -A app.celery_app worker --loglevel=info
```

---

## 📁 Project Structure

```
Backend-Repo/
├── app/
│   ├── __init__.py
│   ├── celery_app.py        # Celery configuration
│   ├── config.py             # Environment settings
│   ├── database.py           # SQLAlchemy setup
│   ├── models.py             # Database models (Job, JobFile)
│   ├── schemas.py            # Pydantic schemas for API
│   ├── tasks.py              # Celery task: convert_file_task
│   ├── finalize_task.py      # Celery task: finalize_job_task
│   └── routers/
│       └── jobs.py           # API endpoints
├── tests/
│   ├── __init__.py
│   ├── test_api.py           # API endpoint tests (25 tests)
│   └── test_models.py        # Database model tests (6 tests)
├── main.py                   # FastAPI application entry point
├── docker-compose.yml        # Docker orchestration
├── Dockerfile                # Container definition
├── requirements.txt          # Python dependencies
├── requirements-test.txt     # Test dependencies
├── pytest.ini                # Pytest configuration
├── quick-test.sh             # Quick manual test script
├── run-tests.sh              # Test suite runner
└── README.md                 # This file
```

---

## 🔧 Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `sqlite:///./test.db` | PostgreSQL connection string |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection string |
| `FILE_STORAGE_PATH` | `storage` | Directory for file storage |
| `APP_NAME` | `Bulk DOCX to PDF Service` | Application name |
| `DEBUG` | `False` | Debug mode |

### Docker Compose Configuration

```yaml
# Key configurations in docker-compose.yml

# Shared storage volume
volumes:
  shared_storage:  # Accessible by both API and worker

# API service
api:
  environment:
    - DATABASE_URL=postgresql://user:password@db:5432/docx_converter
    - REDIS_URL=redis://redis:6379/0
    - FILE_STORAGE_PATH=/app/storage
  volumes:
    - shared_storage:/app/storage  # Mounted volume

# Worker service
worker:
  environment:
    - DATABASE_URL=postgresql://user:password@db:5432/docx_converter
    - REDIS_URL=redis://redis:6379/0
    - FILE_STORAGE_PATH=/app/storage
  volumes:
    - shared_storage:/app/storage  # Same volume as API
```

---

## 🎯 Design Highlights

### 1. Scalability
- **Stateless API:** Can run multiple instances behind a load balancer
- **Stateless Workers:** Can scale workers independently based on load
- **Shared Storage:** Docker volume accessible by all containers
- **Message Queue:** Decouples API from workers

### 2. Reliability
- **Per-file error handling:** One bad file doesn't fail the entire job
- **Database persistence:** Job status survives container restarts
- **Timeout handling:** 60-second timeout per file conversion
- **Graceful degradation:** Partial success allows downloading successful files

### 3. Observability
- **Detailed status tracking:** Job-level and file-level status
- **Error messages:** Specific error details for failed files
- **Timestamps:** Created_at for all jobs
- **Logging:** Structured logging in workers

### 4. User Experience
- **Immediate response:** 202 Accepted, no waiting
- **Progress tracking:** Poll status endpoint for updates
- **Partial results:** Download successful files even if some fail
- **Clear errors:** Specific error messages per file

---

## 🧪 Testing

### Test Coverage
- **Total Tests:** 31
- **API Tests:** 25 (all endpoints, error cases, edge cases)
- **Model Tests:** 6 (database models, relationships)
- **Coverage:** ~90% of application code

### Running Tests
```bash
# Quick test
./quick-test.sh

# Full suite
./run-tests.sh

# Specific test file
pytest tests/test_api.py -v

# With coverage
pytest tests/ --cov=app --cov-report=html
```

See [TEST_DOCUMENTATION.md](TEST_DOCUMENTATION.md) for detailed test information.

---

## 🚀 Production Deployment

### Deployment Checklist
- [ ] Set strong database passwords
- [ ] Use managed PostgreSQL (AWS RDS, etc.)
- [ ] Use managed Redis (AWS ElastiCache, etc.)
- [ ] Set up persistent volume for file storage
- [ ] Configure environment variables
- [ ] Set up monitoring (Prometheus, Grafana)
- [ ] Configure log aggregation (ELK, CloudWatch)
- [ ] Set up health checks
- [ ] Configure auto-scaling for workers
- [ ] Set up backup strategy for database

### Recommended Platforms
- **Railway:** Easiest, one-click deploy
- **Render:** Good for microservices
- **AWS ECS/Fargate:** Full control, scalable
- **Google Cloud Run:** Serverless option

---

## 📝 License

This project is created as an assignment submission.

---

## 👨‍💻 Author

Built with ❤️ for the Backend Developer Technical Assignment
# DocxConversion_Assignment
