from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime

from .. import models
from ..database import get_db

router = APIRouter()

@router.post("/setup", status_code=status.HTTP_201_CREATED)
def seed_initial_data(db: Session = Depends(get_db)):
    """
    Create initial admin and user accounts. This is for development only.
    """
    try:
        # Check if we already have users
        user_count = db.query(models.User).count()
        
        # Track what we've added
        created = {
            "users": [],
            "devices": [],
            "rates": []
        }
        
        # Create user1 if doesn't exist
        user1 = db.query(models.User).filter(models.User.username == "user1").first()
        if not user1:
            user1 = models.User(
                username="user1",
                email="user1@example.com",
                password_hash="password123",  # In a real app, this would be hashed
                full_name="Regular User One",
                phone_number="1234567890",
                role=models.UserRole.USER,
                unit_balance=50.0,
                is_active=True,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
                device_id="device-001"
            )
            db.add(user1)
            db.commit()
            db.refresh(user1)
            created["users"].append("user1")
        
        # Create user2 if doesn't exist
        user2 = db.query(models.User).filter(models.User.username == "user2").first()
        if not user2:
            user2 = models.User(
                username="user2",
                email="user2@example.com",
                password_hash="password123",  # In a real app, this would be hashed
                full_name="Regular User Two",
                phone_number="2345678901",
                role=models.UserRole.USER,
                unit_balance=75.0,
                is_active=True,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
                device_id="device-002"
            )
            db.add(user2)
            db.commit()
            db.refresh(user2)
            created["users"].append("user2")
        else:
            if not user2.id:
                db.refresh(user2)
        
        # Create admin if doesn't exist
        admin = db.query(models.User).filter(models.User.username == "admin").first()
        if not admin:
            admin = models.User(
                username="admin",
                email="admin@example.com",
                password_hash="admin123",  # In a real app, this would be hashed
                full_name="System Administrator",
                phone_number="9876543210",
                role=models.UserRole.ADMIN,
                unit_balance=100.0,
                is_active=True,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            db.add(admin)
            db.commit()
            db.refresh(admin)
            created["users"].append("admin")
        
        # Create electricity rate if it doesn't exist
        rate = db.query(models.ElectricityRate).filter(models.ElectricityRate.is_active == True).first()
        if not rate:
            rate = models.ElectricityRate(
                rate_name="Standard Rate",
                price_per_unit=10.0,  # $10 per unit
                is_active=True,
                effective_date=datetime.utcnow(),
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            db.add(rate)
            db.commit()
            db.refresh(rate)
            created["rates"].append("Standard Rate")
        
        # Ensure user1 has a device
        if user1 and not db.query(models.DeviceStatus).filter(models.DeviceStatus.device_id == "device-001").first():
            device1 = models.DeviceStatus(
                device_id="device-001",
                user_id=user1.id,
                device_name="User1's Device",
                is_online=True,
                last_seen=datetime.utcnow(),
                unit_balance=50.0,
                signal_strength=85,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            db.add(device1)
            db.commit()
            created["devices"].append("device-001")
        
        # Ensure user2 has a device
        if user2 and not db.query(models.DeviceStatus).filter(models.DeviceStatus.device_id == "device-002").first():
            device2 = models.DeviceStatus(
                device_id="device-002",
                user_id=user2.id,
                device_name="User2's Device",
                is_online=False,
                last_seen=datetime.utcnow(),
                unit_balance=75.0,
                signal_strength=70,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            db.add(device2)
            db.commit()
            created["devices"].append("device-002")
        
        return {
            "message": "Database setup completed successfully",
            "created": created
        }
        
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error setting up database: {str(e)}"
        )
