"""
Unit Tests for Database Models and Business Logic

These tests verify the database models and core business logic
without requiring the full API stack.
"""

import pytest
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database import Base
from app.models import Job, JobFile, JobStatus, FileStatus


@pytest.fixture(scope="function")
def test_db():
    """Create a test database for each test."""
    # Use in-memory SQLite for testing
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    
    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = TestSessionLocal()
    
    yield db
    
    db.close()
    Base.metadata.drop_all(bind=engine)


class TestJobModel:
    """Test cases for Job model."""
    
    def test_create_job(self, test_db):
        """Test creating a new job."""
        job = Job(status=JobStatus.PENDING)
        test_db.add(job)
        test_db.commit()
        test_db.refresh(job)
        
        assert job.id is not None
        assert job.status == JobStatus.PENDING
        assert isinstance(job.created_at, datetime)
    
    def test_job_status_enum(self, test_db):
        """Test all job status values."""
        statuses = [
            JobStatus.PENDING,
            JobStatus.PROCESSING,
            JobStatus.COMPLETED,
            JobStatus.FAILED,
            JobStatus.PARTIAL_SUCCESS
        ]
        
        for status in statuses:
            job = Job(status=status)
            test_db.add(job)
            test_db.commit()
            test_db.refresh(job)
            assert job.status == status
            test_db.delete(job)
            test_db.commit()


class TestJobFileModel:
    """Test cases for JobFile model."""
    
    def test_create_job_file(self, test_db):
        """Test creating a job file."""
        job = Job(status=JobStatus.PENDING)
        test_db.add(job)
        test_db.commit()
        test_db.refresh(job)
        
        job_file = JobFile(
            job_id=job.id,
            filename="test.docx",
            status=FileStatus.PENDING
        )
        test_db.add(job_file)
        test_db.commit()
        test_db.refresh(job_file)
        
        assert job_file.id is not None
        assert job_file.job_id == job.id
        assert job_file.filename == "test.docx"
        assert job_file.status == FileStatus.PENDING
    
    def test_job_file_relationship(self, test_db):
        """Test relationship between Job and JobFile."""
        job = Job(status=JobStatus.PENDING)
        test_db.add(job)
        test_db.commit()
        test_db.refresh(job)
        
        # Add multiple files
        for i in range(3):
            job_file = JobFile(
                job_id=job.id,
                filename=f"file{i}.docx",
                status=FileStatus.PENDING
            )
            test_db.add(job_file)
        
        test_db.commit()
        
        # Verify relationship
        assert len(job.files) == 3
        assert all(f.job_id == job.id for f in job.files)
    
    def test_job_file_error_message(self, test_db):
        """Test storing error messages in job files."""
        job = Job(status=JobStatus.PENDING)
        test_db.add(job)
        test_db.commit()
        
        job_file = JobFile(
            job_id=job.id,
            filename="error.docx",
            status=FileStatus.FAILED,
            error_message="Conversion failed: Invalid file format"
        )
        test_db.add(job_file)
        test_db.commit()
        test_db.refresh(job_file)
        
        assert job_file.error_message == "Conversion failed: Invalid file format"
    
    def test_cascade_delete(self, test_db):
        """Test that deleting a job deletes its files."""
        job = Job(status=JobStatus.PENDING)
        test_db.add(job)
        test_db.commit()
        test_db.refresh(job)
        
        # Add files
        for i in range(2):
            job_file = JobFile(
                job_id=job.id,
                filename=f"file{i}.docx",
                status=FileStatus.PENDING
            )
            test_db.add(job_file)
        
        test_db.commit()
        
        # Delete job
        job_id = job.id
        test_db.delete(job)
        test_db.commit()
        
        # Verify files are deleted
        remaining_files = test_db.query(JobFile).filter(JobFile.job_id == job_id).all()
        assert len(remaining_files) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
