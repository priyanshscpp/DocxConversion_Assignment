"""
Main FastAPI Application Entry Point

This file initializes the FastAPI application and sets up:
1. Database tables (auto-created on startup)
2. API routes (job submission, status, download)
3. Health check endpoint
"""

from fastapi import FastAPI
from app.routers import jobs
from app.database import engine, Base

# Initialize database tables on startup
# NOTE: In production, use Alembic migrations instead of create_all()
# This is acceptable for the assignment as it simplifies deployment
Base.metadata.create_all(bind=engine)

# Create FastAPI application instance
app = FastAPI(
    title="Bulk DOCX to PDF Service",
    version="0.1.0",
    description="Asynchronous DOCX to PDF conversion service with bulk upload support"
)

# Register API routes
# All job-related endpoints are under /api/v1/jobs
app.include_router(jobs.router)


@app.get("/", tags=["Health"])
async def root():
    """
    Health check endpoint.
    
    Returns:
        dict: Simple message indicating service is running
    
    Use this to verify the API is accessible and responding.
    """
    return {"message": "Service is running successfully"}
