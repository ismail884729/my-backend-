from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
import datetime
from sqlalchemy.orm import Session
from sqlalchemy import text

from . import models
from .database import engine, get_db
from .auth import router as auth_router
from .routers import admin, user, setup

# Create the database tables
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Electricity Management API")

# Set up CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",     # React default
        "http://localhost:8080",     # Vue.js default
        "http://localhost:4200",     # Angular default
        "http://127.0.0.1:3000",
        "http://127.0.0.1:8080",
        "http://127.0.0.1:4200",
        # Add your production frontend URL when deployed
        # "https://your-frontend-domain.com",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["Content-Type", "Authorization", "Accept", "X-Requested-With"],
)

# Include routers
app.include_router(auth_router, tags=["Authentication"])
app.include_router(user.router, prefix="/users", tags=["Users"])
app.include_router(admin.router, prefix="/admin", tags=["Admin"])
app.include_router(setup.router, prefix="/setup", tags=["Setup"])

@app.get("/")
def read_root():
    return {"message": "Welcome to the Electricity Management API"}

@app.get("/health")
async def health_check(db: Session = Depends(get_db)):
    """Health check endpoint that tests database connectivity"""
    try:
        # Test database connection with proper SQLAlchemy 2.0 syntax
        result = db.execute(text("SELECT 1")).fetchone()
        return {
            "status": "healthy",
            "database": "connected",
            "timestamp": datetime.datetime.now().isoformat()
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "database": "disconnected",
            "error": str(e),
            "timestamp": datetime.datetime.now().isoformat()
        }
