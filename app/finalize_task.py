"""
Celery Task: Job Finalization

This task is triggered after each file conversion completes.
It checks if all files in a job are done, determines the overall job status,
and creates a ZIP archive of successfully converted PDFs.

Key Design Decisions:
1. Called after EVERY file conversion - Safe because it exits early if files are pending
2. Determines job status based on file results (all success, all failed, or partial)
3. Creates downloadable ZIP only when at least one file succeeded
4. Idempotent - Can be called multiple times safely
"""

import os
import zipfile
import logging
from app.celery_app import celery_app
from app.database import SessionLocal
from app.models import Job, JobFile, JobStatus, FileStatus
from app.config import settings

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="app.tasks.finalize_job_task")
def finalize_job_task(self, job_id: int):
    """
    Finalize a job after all files are processed.
    
    This task:
    1. Checks if all files are done (no PENDING or PROCESSING files)
    2. Determines overall job status based on file results
    3. Creates a ZIP archive of successfully converted PDFs
    4. Updates job status in database
    
    Args:
        job_id: Database ID of the job to finalize
    
    Job Status Logic:
        - All files succeeded → COMPLETED
        - All files failed → FAILED
        - Mixed results → PARTIAL_SUCCESS
    
    Note: This task is called after EVERY file conversion completes.
    It's safe because it exits early if any files are still pending.
    """
    db = SessionLocal()
    try:
        # Fetch job from database
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            logger.error(f"Job {job_id} not found in database")
            return "Job not found"

        # Check if all files are processed
        # A file is "processed" if it's either COMPLETED or FAILED
        # If any files are still PENDING or PROCESSING, we exit early
        pending_files = db.query(JobFile).filter(
            JobFile.job_id == job_id,
            JobFile.status.in_([FileStatus.PENDING, FileStatus.PROCESSING])
        ).count()

        if pending_files > 0:
            # Not all files are done yet, exit early
            # This task will be called again when the next file finishes
            logger.info(f"Job {job_id} still has {pending_files} pending files. Skipping finalization.")
            return "Pending files"

        # All files are processed, determine overall job status
        failed_count = db.query(JobFile).filter(
            JobFile.job_id == job_id,
            JobFile.status == FileStatus.FAILED
        ).count()
        
        total_count = len(job.files)
        
        # Determine job status based on file results
        if failed_count == total_count and total_count > 0:
            # All files failed
            job.status = JobStatus.FAILED
        elif failed_count > 0:
            # Some files failed, some succeeded
            job.status = JobStatus.PARTIAL_SUCCESS
        else:
            # All files succeeded
            job.status = JobStatus.COMPLETED

        # Create ZIP archive of successfully converted PDFs
        # This is only done if at least one file succeeded
        if job.status in [JobStatus.COMPLETED, JobStatus.PARTIAL_SUCCESS]:
            job_dir = os.path.join(settings.FILE_STORAGE_PATH, str(job.id))
            output_zip = os.path.join(job_dir, "converted_files.zip")
            
            # Get all successfully converted files
            completed_files = db.query(JobFile).filter(
                JobFile.job_id == job_id,
                JobFile.status == FileStatus.COMPLETED
            ).all()

            if completed_files:
                try:
                    # Create ZIP archive with all PDFs
                    with zipfile.ZipFile(output_zip, 'w', zipfile.ZIP_DEFLATED) as zipf:
                        for file_record in completed_files:
                            # Convert filename from .docx to .pdf
                            # Example: "report.docx" → "report.pdf"
                            base_name = os.path.splitext(file_record.filename)[0]
                            pdf_filename = f"{base_name}.pdf"
                            pdf_path = os.path.join(job_dir, pdf_filename)
                            
                            # Add PDF to ZIP if it exists
                            if os.path.exists(pdf_path):
                                zipf.write(pdf_path, pdf_filename)
                            else:
                                logger.warning(f"Expected PDF file missing: {pdf_path}")
                                
                    logger.info(f"Created ZIP archive for job {job_id} with {len(completed_files)} PDFs")
                    
                except Exception as e:
                    logger.error(f"Failed to create ZIP archive for job {job_id}: {str(e)}")
                    # We preserve the job status even if ZIP creation fails
                    # The user can still see which files succeeded/failed
                    # In production, you might want to mark the job as FAILED here

        # Save job status to database
        db.commit()
        logger.info(f"Finalized job {job_id} with status: {job.status}")
    
    except Exception as e:
        logger.error(f"Unexpected error during finalization of job {job_id}: {str(e)}")
    finally:
        # Always close the database session
        db.close()
