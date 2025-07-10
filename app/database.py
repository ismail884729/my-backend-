from sqlalchemy import create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import time

SQLALCHEMY_DATABASE_URL = "postgresql://neondb_owner:npg_rbgtUJ63IuDH@ep-rough-dawn-a45dikld-pooler.us-east-1.aws.neon.tech/electricity_management?sslmode=require&channel_binding=require"

# Engine with connection pooling parameters optimized for cloud PostgreSQL
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    pool_pre_ping=True,  # Test connections before using them
    pool_recycle=300,    # Recycle connections every 5 minutes (300s)
    pool_size=5,         # Maximum number of connections to keep
    max_overflow=10,     # Allow up to 10 additional connections when needed
    connect_args={       # Additional connection arguments
        "keepalives": 1,
        "keepalives_idle": 30,
        "keepalives_interval": 10,
        "keepalives_count": 5
    }
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# Dependency with retry logic for cloud database connections
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
