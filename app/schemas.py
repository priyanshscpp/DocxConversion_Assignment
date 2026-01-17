"""
Pydantic Schemas for API Request/Response Validation

These schemas define the structure of data sent to and from the API.
Pydantic automatically validates types and serializes database models to JSON.
"""

from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
from app.models import JobStatus, FileStatus


class JobFileResponse(BaseModel):
    """
    Schema for individual file information in API responses.
    
    Used in the job status endpoint to show per-file details.
    """
    id: int
    filename: str
    status: FileStatus
    error_message: Optional[str] = None  # Only present if status is FAILED

    class Config:
        from_attributes = True  # Allows creating from SQLAlchemy models


class JobResponse(BaseModel):
    """
    Schema for job creation response (POST /api/v1/jobs).
    
    Returned immediately after job submission (202 Accepted).
    """
    job_id: int
    status: JobStatus
    message: str = "Job created successfully"

    class Config:
        from_attributes = True


class JobDetailResponse(BaseModel):
    """
    Schema for detailed job status (GET /api/v1/jobs/{job_id}).
    
    Includes:
    - Overall job status
    - Creation timestamp
    - List of all files with their individual statuses
    - Download URL (only when job is completed/partial_success)
    """
    id: int
    status: JobStatus
    created_at: datetime
    files: List[JobFileResponse]
    download_url: Optional[str] = None  # Only present when ready for download

    class Config:
        from_attributes = True
