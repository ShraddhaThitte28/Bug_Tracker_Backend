from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.auth import router as auth_router
from app.projects import router as projects_router
from app.tickets import router as tickets_router
from app.comments import router as comments_router

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.PROJECT_VERSION,
    description="Backend API for Jira-like Bug Tracker / Issue Tracker",
    swagger_ui_parameters={"persistAuthorization": True},
)

# CORS: only the explicit origins from ALLOWED_ORIGINS (defaults to the local
# Vite dev server). No wildcard origin is used together with credentials.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(auth_router)
app.include_router(projects_router)
app.include_router(tickets_router)
app.include_router(comments_router)


@app.get("/", tags=["General"])
def read_root():
    """Root endpoint to check service status."""
    return {
        "status": "online",
        "message": "Welcome to the Bug Tracker / Issue Tracker API",
        "version": settings.PROJECT_VERSION,
        "docs": "/docs",
    }




@app.get(
    "/health",
    tags=["Health"],
    status_code=status.HTTP_200_OK,
)
def health_check(db: Session = Depends(get_db)):
    """Health check endpoint to verify application and database connectivity."""
    try:
        db.execute(text("SELECT 1"))
        return {
            "status": "healthy",
            "database": "connected",
        }
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "status": "unhealthy",
                "database": "disconnected",
            },
        )
