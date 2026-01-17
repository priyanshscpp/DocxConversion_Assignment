"""
Database Configuration and Session Management

Sets up SQLAlchemy engine, session factory, and base model class.
Provides a dependency function for FastAPI route handlers to get database sessions.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from app.config import settings

# Create database engine
# This connects to PostgreSQL in Docker, SQLite for local development
engine = create_engine(settings.DATABASE_URL)

# Create session factory
# Sessions are used to interact with the database (queries, commits, etc.)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for all database models
# All models (Job, JobFile) inherit from this
# Using DeclarativeBase for SQLAlchemy 2.0 compatibility
class Base(DeclarativeBase):
    pass


def get_db():
    """
    Database session dependency for FastAPI.
    
    Yields a database session and ensures it's closed after use.
    Use this in route handlers with Depends(get_db).
    
    Example:
        @app.get("/jobs/{job_id}")
        def get_job(job_id: int, db: Session = Depends(get_db)):
            return db.query(Job).filter(Job.id == job_id).first()
    
    Yields:
        Session: SQLAlchemy database session
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
