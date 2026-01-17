"""
Database Models

Defines the database schema for jobs and files using SQLAlchemy ORM.

Schema:
- Job: Represents a conversion job (one ZIP upload)
- JobFile: Represents an individual DOCX file within a job

Relationships:
- One Job has many JobFiles (one-to-many)
- Deleting a Job cascades to delete all its JobFiles
"""

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Enum as SqEnum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
from app.database import Base


class JobStatus(str, enum.Enum):
    """
    Overall status of a conversion job.
    
    - PENDING: Job created, files not yet being processed
    - PROCESSING: At least one file is being converted
    - COMPLETED: All files converted successfully
    - FAILED: All files failed to convert
    - PARTIAL_SUCCESS: Some files succeeded, some failed
    """
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL_SUCCESS = "partial_success"  # Assignment requirement: partial results


class FileStatus(str, enum.Enum):
    """
    Status of an individual file within a job.
    
    - PENDING: File extracted, waiting for conversion
    - PROCESSING: Currently being converted by a worker
    - COMPLETED: Successfully converted to PDF
    - FAILED: Conversion failed (error_message contains details)
    """
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class Job(Base):
    """
    Represents a bulk conversion job.
    
    A job is created when a user uploads a ZIP file.
    It tracks the overall status and contains multiple files.
    """
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, index=True)
    status = Column(SqEnum(JobStatus), default=JobStatus.PENDING)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # One-to-many relationship with JobFile
    # cascade="all, delete-orphan" means deleting a Job deletes all its files
    files = relationship("JobFile", back_populates="job", cascade="all, delete-orphan")


class JobFile(Base):
    """
    Represents an individual DOCX file within a job.
    
    Each file has its own status and optional error message.
    This allows tracking which files succeeded/failed independently.
    """
    __tablename__ = "job_files"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, ForeignKey("jobs.id"))  # Foreign key to Job
    filename = Column(String, nullable=False)
    status = Column(SqEnum(FileStatus), default=FileStatus.PENDING)
    
    # Error message is only populated if status is FAILED
    # Contains details about why the conversion failed
    error_message = Column(String, nullable=True)

    # Many-to-one relationship back to Job
    job = relationship("Job", back_populates="files")
