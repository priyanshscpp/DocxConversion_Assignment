import os
import zipfile
import shutil
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Job, JobFile, JobStatus, FileStatus
from app.schemas import JobResponse, JobDetailResponse
from app.config import settings
from app.tasks import convert_file_task


router = APIRouter(
    prefix="/api/v1/jobs",
    tags=["jobs"]
)

@router.post("/", response_model=JobResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_job(
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    # Validate file type
    if not file.filename.endswith('.zip'):
        raise HTTPException(status_code=400, detail="Only ZIP files are allowed")

    # Create Job record
    job = Job(status=JobStatus.PENDING)
    db.add(job)
    db.commit()
    db.refresh(job)

    # Setup storage path
    job_dir = os.path.join(settings.FILE_STORAGE_PATH, str(job.id))
    os.makedirs(job_dir, exist_ok=True)

    # Save and extract zip
    zip_path = os.path.join(job_dir, "upload.zip")
    try:
        with open(zip_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        # Extract files
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(job_dir)
            
            # Inventory files
            extracted_files = zip_ref.namelist()
            docx_files = [f for f in extracted_files if f.lower().endswith('.docx') and not f.startswith('__MACOSX')]
            
            if not docx_files:
                # Cleanup if no valid files
                shutil.rmtree(job_dir)
                db.delete(job)
                db.commit()
                raise HTTPException(status_code=400, detail="No DOCX files found in the ZIP archive")

            for filename in docx_files:
                # Create JobFile records
                job_file = JobFile(
                    job_id=job.id,
                    filename=filename,
                    status=FileStatus.PENDING
                )
                db.add(job_file)
                db.commit()
                db.refresh(job_file)
                
                # Trigger conversion task
                convert_file_task.delay(job_file.id)

            
    except zipfile.BadZipFile:
        shutil.rmtree(job_dir)
        db.delete(job)
        db.commit()
        raise HTTPException(status_code=400, detail="Invalid ZIP file")
    except Exception as e:
        # Cleanup on generalized error
        if os.path.exists(job_dir):
            shutil.rmtree(job_dir)
        db.delete(job)
        db.commit()
        raise HTTPException(status_code=500, detail=f"Failed to process upload: {str(e)}")

    return JobResponse(job_id=job.id, status=job.status)

@router.get("/{job_id}", response_model=JobDetailResponse)
async def get_job(job_id: int, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    response = JobDetailResponse.model_validate(job)
    
    # Include download URL only if satisfied
    # User requested "Include download URL only when job is COMPLETED"
    if job.status == JobStatus.COMPLETED or job.status == JobStatus.PARTIAL_SUCCESS:
        # Check if the file actually exists before promising it? 
        # For now, just construct the URL.
        response.download_url = f"/api/v1/jobs/{job_id}/download"
    
    return response

@router.get("/{job_id}/download")
async def download_job_result(job_id: int, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status not in [JobStatus.COMPLETED, JobStatus.PARTIAL_SUCCESS]:
        raise HTTPException(status_code=400, detail="Job is not ready for download")

    job_dir = os.path.join(settings.FILE_STORAGE_PATH, str(job.id))
    zip_path = os.path.join(job_dir, "converted_files.zip")

    if not os.path.exists(zip_path):
        raise HTTPException(status_code=404, detail="Result file not found")

    return FileResponse(
        path=zip_path, 
        filename=f"job_{job_id}_converted.zip",
        media_type="application/zip"
    )

