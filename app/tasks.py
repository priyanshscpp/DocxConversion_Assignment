"""
Celery Task: DOCX to PDF Conversion

This module contains the background task that converts individual DOCX files to PDF.
Each file is processed independently, allowing parallel processing and per-file error handling.

Key Design Decisions:
1. One task per file (not per job) - Allows parallel processing
2. LibreOffice subprocess - Free, Linux-compatible converter
3. Per-file error handling - One bad file doesn't fail the entire job
4. Timeout protection - Prevents hanging on corrupted files
"""

import os
import logging
import subprocess
from app.celery_app import celery_app
from app.database import SessionLocal
from app.models import JobFile, Job, FileStatus, JobStatus
from app.config import settings

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="app.tasks.convert_file_task")
def convert_file_task(self, file_id: int):
    """
    Convert a single DOCX file to PDF using LibreOffice.
    
    This task is executed by Celery workers in the background.
    Each file is processed independently to allow parallel execution.
    
    Args:
        file_id: Database ID of the JobFile to convert
    
    Flow:
        1. Fetch file record from database
        2. Update status to PROCESSING
        3. Run LibreOffice conversion (subprocess)
        4. Update status to COMPLETED or FAILED
        5. Trigger job finalization check
    
    Error Handling:
        - File not found: Logs error and returns
        - Conversion timeout: Marks file as FAILED
        - Conversion error: Marks file as FAILED with error message
        - Individual failures don't crash the worker
    """
    db = SessionLocal()
    try:
        # Fetch file record from database
        file_record = db.query(JobFile).filter(JobFile.id == file_id).first()
        if not file_record:
            logger.error(f"File with id {file_id} not found in database")
            return "File not found"

        # Update file status to PROCESSING
        file_record.status = FileStatus.PROCESSING
        
        # Update job status to PROCESSING if it's still PENDING
        job = db.query(Job).filter(Job.id == file_record.job_id).first()
        if job and job.status == JobStatus.PENDING:
            job.status = JobStatus.PROCESSING
        
        db.commit()

        # Construct file paths
        # File structure: /app/storage/{job_id}/{filename}
        job_dir = os.path.join(settings.FILE_STORAGE_PATH, str(file_record.job_id))
        input_path = os.path.join(job_dir, file_record.filename)
        
        # Output PDF will have same name but .pdf extension
        base_name = os.path.splitext(file_record.filename)[0]
        output_filename = f"{base_name}.pdf"
        output_path = os.path.join(job_dir, output_filename)

        # Verify input file exists
        if not os.path.exists(input_path):
            raise FileNotFoundError(f"Input file not found at {input_path}")

        try:
            # Convert DOCX to PDF using LibreOffice
            # Why LibreOffice?
            # - Free and open-source
            # - Works on Linux (docx2pdf requires Microsoft Word)
            # - Reliable and widely used
            # - Supports headless mode (no GUI)
            
            abs_input_path = os.path.abspath(input_path)
            abs_job_dir = os.path.abspath(job_dir)
            
            # Run LibreOffice in headless mode
            result = subprocess.run(
                [
                    'libreoffice',
                    '--headless',              # No GUI
                    '--convert-to', 'pdf',     # Output format
                    '--outdir', abs_job_dir,   # Output directory
                    abs_input_path             # Input file
                ],
                capture_output=True,  # Capture stdout/stderr
                text=True,            # Decode output as text
                timeout=60            # 60 second timeout per file
            )
            
            # Check if conversion succeeded
            if result.returncode != 0:
                raise Exception(f"LibreOffice conversion failed: {result.stderr}")
            
            # Verify output PDF was created
            if not os.path.exists(output_path):
                 raise Exception("Conversion failed: Output PDF not created")

            # Mark file as successfully converted
            file_record.status = FileStatus.COMPLETED
            db.commit()
            logger.info(f"Successfully converted file {file_id}: {file_record.filename}")
            
        except subprocess.TimeoutExpired:
            # Conversion took too long (>60 seconds)
            # This can happen with very large files or corrupted files
            logger.error(f"Conversion timeout for file {file_id}")
            file_record.status = FileStatus.FAILED
            file_record.error_message = "Conversion timeout (exceeded 60 seconds)"
            db.commit()
            
        except Exception as e:
            # Any other conversion error (corrupted file, invalid format, etc.)
            logger.error(f"Conversion error for file {file_id}: {str(e)}")
            file_record.status = FileStatus.FAILED
            file_record.error_message = str(e)
            db.commit()
            
        # Trigger job finalization check
        # This checks if all files in the job are done and creates the final ZIP
        # It's safe to call this multiple times - it only runs when all files are done
        from app.finalize_task import finalize_job_task
        finalize_job_task.delay(file_record.job_id)

    except Exception as e:
        # Catch-all for unexpected errors
        logger.error(f"Unexpected error in convert_file_task for file {file_id}: {str(e)}")
    finally:
        # Always close the database session
        db.close()
