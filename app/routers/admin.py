from fastapi import APIRouter, Depends, HTTPException, status, Response
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from datetime import datetime
import csv
import io
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from .. import crud, models, schemas
from ..database import get_db

router = APIRouter()

@router.get("/dashboard")
def admin_dashboard(db: Session = Depends(get_db)):
    # This will be replaced with actual admin authentication later
    # Get counts for dashboard
    user_count = db.query(models.User).count()
    device_count = db.query(models.DeviceStatus).count()
    online_devices = db.query(models.DeviceStatus).filter(models.DeviceStatus.is_online == True).count()
    total_transactions = db.query(models.Transaction).count()
    
    return {
        "message": "Admin dashboard",
        "stats": {
            "total_users": user_count,
            "total_devices": device_count,
            "online_devices": online_devices,
            "total_transactions": total_transactions
        }
    }

# System Settings Management Endpoints for Admins

@router.get("/settings", response_model=List[schemas.SystemSettingResponse])
def list_system_settings(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """List all system settings"""
    # This will be replaced with actual admin authentication later
    
    settings = crud.get_system_settings(db, skip=skip, limit=limit)
    return settings

@router.get("/settings/{setting_key}", response_model=schemas.SystemSettingResponse)
def get_system_setting(setting_key: str, db: Session = Depends(get_db)):
    """Get a specific system setting by key"""
    # This will be replaced with actual admin authentication later
    
    setting = crud.get_system_setting(db, setting_key)
    if not setting:
        raise HTTPException(status_code=404, detail="System setting not found")
    return setting

@router.post("/settings", response_model=schemas.SystemSettingResponse, status_code=status.HTTP_201_CREATED)
def create_system_setting(setting: schemas.SystemSettingCreate, db: Session = Depends(get_db)):
    """Create a new system setting"""
    # This will be replaced with actual admin authentication later
    
    # Check if setting already exists
    db_setting = crud.get_system_setting(db, setting.setting_key)
    if db_setting:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Setting with key '{setting.setting_key}' already exists"
        )
    
    # For now, we'll use admin ID 1 as the updater (this should be changed when auth is implemented)
    admin_id = 1
    return crud.create_system_setting(db, setting, admin_id)

@router.put("/settings/{setting_key}", response_model=schemas.SystemSettingResponse)
def update_system_setting(setting_key: str, setting: schemas.SystemSettingUpdate, db: Session = Depends(get_db)):
    """Update a system setting"""
    # This will be replaced with actual admin authentication later
    
    # For now, we'll use admin ID 1 as the updater (this should be changed when auth is implemented)
    admin_id = 1
    db_setting = crud.update_system_setting(db, setting_key, setting, admin_id)
    if not db_setting:
        raise HTTPException(status_code=404, detail="System setting not found")
    return db_setting

@router.delete("/settings/{setting_key}", status_code=status.HTTP_204_NO_CONTENT)
def delete_system_setting(setting_key: str, db: Session = Depends(get_db)):
    """Delete a system setting"""
    # This will be replaced with actual admin authentication later
    
    result = crud.delete_system_setting(db, setting_key)
    if not result:
        raise HTTPException(status_code=404, detail="System setting not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)

# User Management Endpoints for Admins

@router.get("/users", response_model=List[schemas.UserResponse])
def list_all_users(
    skip: int = 0, 
    limit: int = 100,
    is_active: Optional[bool] = None,
    role: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """List all users with optional filtering"""
    # This will be replaced with actual admin authentication later
    
    query = db.query(models.User)
    
    # Apply filters if provided
    if is_active is not None:
        query = query.filter(models.User.is_active == is_active)
    
    if role:
        try:
            user_role = models.UserRole(role)
            query = query.filter(models.User.role == user_role)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid role value. Must be one of: {[r.value for r in models.UserRole]}"
            )
    
    users = query.offset(skip).limit(limit).all()
    return users

@router.get("/users/{user_id}", response_model=schemas.UserResponse)
def get_user(user_id: int, db: Session = Depends(get_db)):
    """Get a specific user by ID"""
    # This will be replaced with actual admin authentication later
    
    user = crud.get_user(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user

@router.post("/users", response_model=schemas.UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(user: schemas.AdminUserCreate, db: Session = Depends(get_db)):
    """Create a new user with admin privileges"""
    # This will be replaced with actual admin authentication later
    
    # Check if username or email already exists
    db_user = crud.get_user_by_username(db, user.username)
    if db_user:
        raise HTTPException(status_code=400, detail="Username already registered")
    
    db_user = crud.get_user_by_email(db, user.email)
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    # Create new user with admin privileges
    created_user = crud.admin_create_user(db, user)
    
    return created_user

class UserWithDevices(BaseModel):
    user: schemas.AdminUserCreate
    create_devices: Optional[int] = 0  # Number of new devices to create
    make_primary: Optional[int] = 0    # Index of device to make primary (0-based)

@router.post("/users-with-devices", response_model=schemas.UserWithDevicesResponse, status_code=status.HTTP_201_CREATED)
def create_user_with_devices(data: UserWithDevices, db: Session = Depends(get_db)):
    """
    Create a new user with optional devices.
    You can specify how many devices to create for this user and which one should be primary.
    
    Example payload:
    {
        "user": {
            "username": "newuser",
            "email": "user@example.com",
            "full_name": "New User",
            "phone_number": "1234567890",
            "password": "password123",
            "role": "user",
            "unit_balance": 100.0
        },
        "create_devices": 3,
        "make_primary": 0
    }
    """
    # Check if username already exists
    db_user = crud.get_user_by_username(db, data.user.username)
    if db_user:
        raise HTTPException(status_code=400, detail="Username already registered")
    
    # Check if email already exists
    db_user = crud.get_user_by_email(db, data.user.email)
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    # Create new user
    created_user = crud.admin_create_user(db, data.user)
    
    # Create requested devices
    devices = []
    for i in range(data.create_devices):
        is_primary = (i == data.make_primary)
        device = crud.create_device(db, schemas.DeviceCreate(
            user_id=created_user.id,
            device_name=f"{data.user.username}'s Device {i+1}",
            is_primary=is_primary,
            unit_balance=data.user.unit_balance if hasattr(data.user, 'unit_balance') and data.user.unit_balance is not None else 0.0
        ))
        devices.append(device)
    
    # Return user with devices
    result = crud.get_user_with_devices(db, created_user.id)
    return result

@router.post("/users/bulk", response_model=List[schemas.UserResponse], status_code=status.HTTP_201_CREATED)
def create_users_bulk(users: List[schemas.AdminUserCreate], db: Session = Depends(get_db)):
    """Create multiple users at once with admin privileges"""
    # This will be replaced with actual admin authentication later
    
    created_users = []
    errors = []
    
    for i, user in enumerate(users):
        try:
            # Check if username or email already exists
            db_user = crud.get_user_by_username(db, user.username)
            if db_user:
                errors.append(f"Item {i}: Username '{user.username}' already registered")
                continue
            
            db_user = crud.get_user_by_email(db, user.email)
            if db_user:
                errors.append(f"Item {i}: Email '{user.email}' already registered")
                continue
            
            # Check device ID if provided
            if user.device_id:
                device = db.query(models.DeviceStatus).filter(models.DeviceStatus.device_id == user.device_id).first()
                if device and device.user_id is not None:
                    errors.append(f"Item {i}: Device '{user.device_id}' is already assigned to another user")
                    continue
            
            # Create new user with admin privileges
            created_user = crud.admin_create_user(db, user)
            
            # If device ID was provided and user was created successfully, create or update device
            if created_user and user.device_id:
                device = db.query(models.DeviceStatus).filter(models.DeviceStatus.device_id == user.device_id).first()
                
                if not device:
                    # Create new device
                    device = models.DeviceStatus(
                        device_id=user.device_id,
                        user_id=created_user.id,
                        device_name=f"{user.username}'s Device",
                        is_online=False,
                        unit_balance=user.unit_balance if hasattr(user, 'unit_balance') and user.unit_balance is not None else 0.0,
                        created_at=datetime.utcnow(),
                        updated_at=datetime.utcnow()
                    )
                    db.add(device)
                else:
                    # Update existing device
                    device.user_id = created_user.id
                    device.unit_balance = user.unit_balance if hasattr(user, 'unit_balance') and user.unit_balance is not None else 0.0
                    device.updated_at = datetime.utcnow()
                
                db.commit()
            
            created_users.append(created_user)
            
        except Exception as e:
            errors.append(f"Item {i}: {str(e)}")
    
    # If there were errors but some users were created
    if errors and created_users:
        raise HTTPException(
            status_code=status.HTTP_207_MULTI_STATUS,
            detail={
                "message": "Some users were created, but others had errors",
                "created_count": len(created_users),
                "error_count": len(errors),
                "errors": errors
            }
        )
    # If all failed
    elif errors and not created_users:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": "Failed to create any users",
                "errors": errors
            }
        )
        
    return created_users
    
@router.get("/users/export", response_class=StreamingResponse)
def export_users(
    role: Optional[str] = None,
    is_active: Optional[bool] = None,
    db: Session = Depends(get_db)
):
    """Export users to CSV format"""
    # This will be replaced with actual admin authentication later
    
    query = db.query(models.User)
    
    # Apply filters if provided
    if is_active is not None:
        query = query.filter(models.User.is_active == is_active)
    
    if role:
        try:
            user_role = models.UserRole(role)
            query = query.filter(models.User.role == user_role)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid role value. Must be one of: {[r.value for r in models.UserRole]}"
            )
    
    users = query.all()
    
    # Create CSV in memory
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write header
    writer.writerow([
        "id", "username", "email", "full_name", "phone_number", 
        "role", "unit_balance", "is_active", "device_id", 
        "created_at", "updated_at"
    ])
    
    # Write user data
    for user in users:
        writer.writerow([
            user.id, user.username, user.email, user.full_name, user.phone_number,
            user.role.value, user.unit_balance, user.is_active, user.device_id,
            user.created_at.isoformat(), user.updated_at.isoformat()
        ])
    
    # Reset the cursor to the beginning of the StringIO object
    output.seek(0)
    
    # Return the CSV as a downloadable file
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment;filename=users.csv"}
    )
    
@router.post("/users/{user_id}/assign-device", response_model=schemas.UserResponse)
def assign_device_to_user(
    user_id: int,
    device_data: schemas.DeviceAssign,
    db: Session = Depends(get_db)
):
    """Assign a device to a user"""
    # This will be replaced with actual admin authentication later
    
    # Check if user exists
    user = crud.get_user(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Check if device exists
    device = crud.get_device_by_id(db, device_data.device_id)
    
    # If device doesn't exist, create it
    if not device:
        device = models.DeviceStatus(
            device_id=device_data.device_id,
            user_id=user.id,
            device_name=device_data.device_name if device_data.device_name else f"{user.username}'s Device",
            is_online=False,
            unit_balance=user.unit_balance,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        db.add(device)
    else:
        # Check if device is already assigned to another user
        if device.user_id is not None and device.user_id != user.id:
            raise HTTPException(
                status_code=400, 
                detail=f"Device is already assigned to user ID {device.user_id}"
            )
        
        # Update device
        device.user_id = user.id
        device.unit_balance = user.unit_balance
        if device_data.device_name:
            device.device_name = device_data.device_name
        device.updated_at = datetime.utcnow()
    
    db.commit()
    db.refresh(user)
    
    return user

# Create a new device with auto-generated meter ID
@router.post("/devices", response_model=schemas.DeviceStatusResponse)
def create_device(
    device: schemas.DeviceCreate = None,
    db: Session = Depends(get_db)
):
    """
    Create a new device (electricity meter) with an automatically generated device ID.
    The device ID will be in the format MTRxxxxxxx (where x is a random digit).
    
    Optionally, you can assign a user to the device and set other properties.
    """
    try:
        # Create the device
        new_device = crud.create_device(db, device)
        return new_device
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error creating device: {str(e)}"
        )

@router.get("/devices", response_model=List[schemas.DeviceStatusResponse])
def list_all_devices(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """
    List all devices (electricity meters) in the system.
    """
    devices = crud.get_all_devices(db, skip=skip, limit=limit)
    return devices

@router.get("/users/{user_id}/devices", response_model=List[schemas.DeviceStatusResponse])
def get_user_devices(
    user_id: int,
    db: Session = Depends(get_db)
):
    """
    Get all devices assigned to a specific user.
    """
    # Check if user exists
    user = crud.get_user(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail=f"User with ID {user_id} not found")
    
    # Get all devices for the user
    devices = crud.get_user_devices(db, user_id)
    return devices

@router.post("/users/{user_id}/devices", response_model=schemas.DeviceStatusResponse)
def assign_device_to_user(
    user_id: int,
    device_data: schemas.DeviceAssign,
    db: Session = Depends(get_db)
):
    """
    Assign an existing device to a user.
    """
    # Check if user exists
    user = crud.get_user(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail=f"User with ID {user_id} not found")
    
    # Check if device exists
    device = crud.get_device_by_id(db, device_data.device_id)
    if not device:
        raise HTTPException(status_code=404, detail=f"Device with ID {device_data.device_id} not found")
    
    # Check if device is already assigned to another user
    if device.user_id is not None and device.user_id != user_id:
        raise HTTPException(
            status_code=400, 
            detail=f"Device is already assigned to user ID {device.user_id}"
        )
    
    # Assign device to user
    updated_device = crud.assign_device_to_user(
        db, 
        device_data.device_id, 
        user_id, 
        device_data.device_name, 
        device_data.is_primary
    )
    
    return updated_device

@router.delete("/devices/{device_id}/user-assignment")
def unassign_device_from_user(
    device_id: str,
    db: Session = Depends(get_db)
):
    """
    Unassign a device from a user.
    """
    # Check if device exists and is assigned to a user
    device = crud.get_device_by_id(db, device_id)
    if not device:
        raise HTTPException(status_code=404, detail=f"Device with ID {device_id} not found")
    
    if device.user_id is None:
        raise HTTPException(status_code=400, detail="Device is not assigned to any user")
    
    # Unassign the device
    crud.unassign_device_from_user(db, device_id)
    
    return {"message": f"Device {device_id} has been unassigned successfully"}

@router.put("/devices/{device_id}/make-primary")
def make_device_primary(
    device_id: str,
    db: Session = Depends(get_db)
):
    """
    Make a device the primary device for its assigned user.
    """
    # Check if device exists and is assigned to a user
    device = crud.get_device_by_id(db, device_id)
    if not device:
        raise HTTPException(status_code=404, detail=f"Device with ID {device_id} not found")
    
    if device.user_id is None:
        raise HTTPException(status_code=400, detail="Device is not assigned to any user")
    
    # Make the device primary
    updated_device = crud.make_device_primary(db, device_id)
    
    return updated_device

@router.put("/users/{user_id}", response_model=schemas.UserResponse)
def update_user(user_id: int, user_update: schemas.AdminUserUpdate, db: Session = Depends(get_db)):
    """
    Update a user (admin can update more fields than a regular user)
    Special protection: Role changes for user with ID 3 (main admin) are not allowed
    """
    # Check if user exists
    user = crud.get_user(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Special protection for the main admin (ID 3)
    update_data = user_update.dict(exclude_unset=True)
    if user_id == 3 and "role" in update_data and update_data["role"] != models.UserRole.ADMIN.value:
        raise HTTPException(
            status_code=403,
            detail="Cannot change the role of the main administrator account (ID 3)"
        )
    
    # Update user with admin privileges
    update_data = user_update.dict(exclude_unset=True)
    
    # Handle password update specially
    if "password" in update_data:
        # In a real app, we would hash the password
        user.password_hash = update_data.pop("password")
    
    # Handle role update
    if "role" in update_data:
        try:
            role_value = update_data.pop("role")
            user.role = models.UserRole(role_value)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid role value. Must be one of: {[r.value for r in models.UserRole]}"
            )
    
    # Update remaining fields
    for field, value in update_data.items():
        setattr(user, field, value)
    
    user.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(user)
    return user

@router.delete("/users/{user_id}", response_model=dict)
def delete_user(user_id: int, db: Session = Depends(get_db)):
    """
    Delete a user from the system.
    Special protection: User with ID 3 (main admin) cannot be deleted.
    """
    # Prevent deletion of the protected admin (ID 3)
    if user_id == 3:
        raise HTTPException(
            status_code=403,
            detail="Cannot delete the main administrator account (ID 3)"
        )
    
    # Check if user exists
    user = crud.get_user(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Check if user has any devices assigned
    devices = db.query(models.DeviceStatus).filter(models.DeviceStatus.user_id == user_id).all()
    if devices:
        # Unassign devices first
        for device in devices:
            device.user_id = None
            device.is_primary = False
            device.updated_at = datetime.utcnow()
    
    # Delete the user
    db.delete(user)
    db.commit()
    
    return {
        "success": True,
        "message": f"User {user.username} has been deleted",
        "unassigned_devices": len(devices) if devices else 0
    }

@router.post("/users/{user_id}/set-admin-role", response_model=schemas.UserResponse)
def set_admin_role(user_id: int, make_admin: bool = True, db: Session = Depends(get_db)):
    """
    Promote a user to admin or demote an admin to regular user.
    Special protection: User with ID 3 (main admin) cannot be demoted.
    """
    # Check if user exists
    user = crud.get_user(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Special protection for the main admin (ID 3)
    if user_id == 3 and not make_admin:
        raise HTTPException(
            status_code=403,
            detail="Cannot demote the main administrator account (ID 3)"
        )
    
    # Set role
    user.role = models.UserRole.ADMIN if make_admin else models.UserRole.USER
    user.updated_at = datetime.utcnow()
    
    db.commit()
    db.refresh(user)
    
    return user

@router.patch("/users/{user_id}/activate", response_model=schemas.UserResponse)
def activate_user(user_id: int, db: Session = Depends(get_db)):
    """Activate a user account"""
    # This will be replaced with actual admin authentication later
    
    user = crud.get_user(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    user.is_active = True
    user.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(user)
    return user

@router.patch("/users/{user_id}/deactivate", response_model=schemas.UserResponse)
def deactivate_user(user_id: int, db: Session = Depends(get_db)):
    """Deactivate a user account"""
    # This will be replaced with actual admin authentication later
    
    user = crud.get_user(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    user.is_active = False
    user.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(user)
    return user

# Electricity Rate Management Endpoints for Admins

@router.get("/rates", response_model=List[schemas.ElectricityRateResponse])
def list_electricity_rates(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """List all electricity rates"""
    # This will be replaced with actual admin authentication later
    
    rates = crud.get_electricity_rates(db, skip=skip, limit=limit)
    return rates

@router.get("/rates/{rate_id}", response_model=schemas.ElectricityRateResponse)
def get_electricity_rate(rate_id: int, db: Session = Depends(get_db)):
    """Get a specific electricity rate by ID"""
    # This will be replaced with actual admin authentication later
    
    rate = crud.get_electricity_rate(db, rate_id)
    if not rate:
        raise HTTPException(status_code=404, detail="Electricity rate not found")
    return rate

@router.post("/rates", response_model=schemas.ElectricityRateResponse, status_code=status.HTTP_201_CREATED)
def create_electricity_rate(rate: schemas.ElectricityRateCreate, db: Session = Depends(get_db)):
    """Create a new electricity rate"""
    # This will be replaced with actual admin authentication later
    
    return crud.create_electricity_rate(db, rate)

@router.put("/rates/{rate_id}", response_model=schemas.ElectricityRateResponse)
def update_electricity_rate(rate_id: int, rate: schemas.ElectricityRateUpdate, db: Session = Depends(get_db)):
    """Update an electricity rate"""
    # This will be replaced with actual admin authentication later
    
    db_rate = crud.update_electricity_rate(db, rate_id, rate)
    if not db_rate:
        raise HTTPException(status_code=404, detail="Electricity rate not found")
    return db_rate

@router.delete("/rates/{rate_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_electricity_rate(rate_id: int, db: Session = Depends(get_db)):
    """Delete an electricity rate if it's not active and not used in transactions"""
    # This will be replaced with actual admin authentication later
    
    result = crud.delete_electricity_rate(db, rate_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Electricity rate not found")
    if result is False:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Cannot delete an active rate or a rate that is used in transactions"
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)

@router.patch("/rates/{rate_id}/activate", response_model=schemas.ElectricityRateResponse)
def activate_electricity_rate(rate_id: int, db: Session = Depends(get_db)):
    """Activate a specific electricity rate and deactivate all others"""
    # This will be replaced with actual admin authentication later
    
    rate = crud.get_electricity_rate(db, rate_id)
    if not rate:
        raise HTTPException(status_code=404, detail="Electricity rate not found")
    
    # Deactivate all other rates
    db.query(models.ElectricityRate).filter(models.ElectricityRate.id != rate_id).update({"is_active": False})
    
    # Activate this rate
    rate.is_active = True
    rate.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(rate)
    
    return rate

# Device Management Endpoints for Admins

@router.get("/devices", response_model=List[schemas.DeviceStatusResponse])
def list_all_devices(
    skip: int = 0,
    limit: int = 100,
    is_online: Optional[bool] = None,
    db: Session = Depends(get_db)
):
    """List all devices with optional filtering"""
    # This will be replaced with actual admin authentication later
    
    query = db.query(models.DeviceStatus)
    
    if is_online is not None:
        query = query.filter(models.DeviceStatus.is_online == is_online)
    
    devices = query.offset(skip).limit(limit).all()
    return devices

@router.get("/devices/{device_id}", response_model=schemas.DeviceStatusResponse)
def get_device(device_id: str, db: Session = Depends(get_db)):
    """Get a specific device by ID"""
    # This will be replaced with actual admin authentication later
    
    device = crud.get_device_by_id(db, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    return device
    
@router.get("/device-details/{device_id}", response_model=schemas.DeviceDetailResponse)
def get_device_details(device_id: str, db: Session = Depends(get_db)):
    """
    Get detailed information about a specific device including usage metrics 
    and installation details for admin monitoring.
    """
    # Get detailed device information
    device_details = crud.get_device_details(db, device_id)
    if not device_details:
        raise HTTPException(status_code=404, detail=f"Device with ID {device_id} not found")
    
    return device_details

# Transaction management endpoints
@router.get("/transactions", response_model=List[schemas.AdminTransactionResponse])
def get_all_transactions(
    skip: int = 0, 
    limit: int = 100,
    status: Optional[str] = None,
    payment_method: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Get all transactions with detailed user information.
    Allows filtering by status, payment method, and date range.
    This endpoint is for admins to monitor who is buying units and track payments.
    """
    # Parse date strings if provided
    parsed_start_date = None
    parsed_end_date = None
    
    if start_date:
        try:
            parsed_start_date = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid start_date format. Use ISO format (YYYY-MM-DDTHH:MM:SS)")
    
    if end_date:
        try:
            parsed_end_date = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid end_date format. Use ISO format (YYYY-MM-DDTHH:MM:SS)")
    
    # Get transactions with filters
    transactions = crud.get_all_transactions(
        db, 
        skip=skip, 
        limit=limit,
        status=status,
        payment_method=payment_method,
        start_date=parsed_start_date,
        end_date=parsed_end_date
    )
    
    if transactions is None:
        raise HTTPException(status_code=400, detail=f"Invalid status value. Must be one of: {[s.value for s in models.TransactionStatus]}")
    
    # Prepare detailed response with user info
    detailed_transactions = []
    for transaction in transactions:
        # Get user information
        user = db.query(models.User).filter(models.User.id == transaction.user_id).first()
        
        # Get rate information
        rate = db.query(models.ElectricityRate).filter(models.ElectricityRate.id == transaction.rate_id).first()
        
        # Get device information if available
        device_name = None
        if transaction.device_id:
            device = db.query(models.DeviceStatus).filter(models.DeviceStatus.device_id == transaction.device_id).first()
            if device:
                device_name = device.device_name
        
        # Prepare response object
        transaction_dict = {
            **transaction.__dict__,
            "rate_name": rate.rate_name if rate else None,
            "price_per_unit": rate.price_per_unit if rate else None,
            "username": user.username if user else None,
            "user_email": user.email if user else None,
            "user_full_name": user.full_name if user else None,
            "user_phone_number": user.phone_number if user else None,
            "device_name": device_name
        }
        
        # Remove SQLAlchemy state
        if "_sa_instance_state" in transaction_dict:
            del transaction_dict["_sa_instance_state"]
        
        detailed_transactions.append(transaction_dict)
    
    return detailed_transactions

@router.get("/transactions/summary")
def get_transactions_summary(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Get a summary of transactions, including total amount, units sold, and payment methods breakdown.
    This endpoint helps admins monitor financial aspects of electricity sales.
    """
    # Parse date strings if provided
    parsed_start_date = None
    parsed_end_date = None
    
    if start_date:
        try:
            parsed_start_date = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid start_date format. Use ISO format (YYYY-MM-DDTHH:MM:SS)")
    
    if end_date:
        try:
            parsed_end_date = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid end_date format. Use ISO format (YYYY-MM-DDTHH:MM:SS)")
    
    # Base query
    query = db.query(models.Transaction)
    
    # Apply date filters if provided
    if parsed_start_date:
        query = query.filter(models.Transaction.created_at >= parsed_start_date)
    
    if parsed_end_date:
        query = query.filter(models.Transaction.created_at <= parsed_end_date)
    
    # Get only completed transactions
    query = query.filter(models.Transaction.status == models.TransactionStatus.COMPLETED)
    
    # Execute query
    transactions = query.all()
    
    # Calculate summary data
    total_amount = sum(t.amount for t in transactions)
    total_units = sum(t.units_purchased for t in transactions)
    total_transactions = len(transactions)
    
    # Group by payment method
    payment_methods = {}
    for transaction in transactions:
        payment_method = transaction.payment_method or "unknown"
        if payment_method not in payment_methods:
            payment_methods[payment_method] = {"count": 0, "amount": 0, "units": 0}
        
        payment_methods[payment_method]["count"] += 1
        payment_methods[payment_method]["amount"] += transaction.amount
        payment_methods[payment_method]["units"] += transaction.units_purchased
    
    return {
        "total_transactions": total_transactions,
        "total_amount": total_amount,
        "total_units": total_units,
        "average_transaction_amount": total_amount / total_transactions if total_transactions > 0 else 0,
        "payment_methods": payment_methods,
        "period": {
            "start_date": parsed_start_date.isoformat() if parsed_start_date else "all time",
            "end_date": parsed_end_date.isoformat() if parsed_end_date else "present"
        }
    }

@router.get("/transactions/export")
def export_transactions_csv(
    status: Optional[str] = None,
    payment_method: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Export transactions as CSV file for accounting and reporting purposes.
    """
    # Parse date strings if provided
    parsed_start_date = None
    parsed_end_date = None
    
    if start_date:
        try:
            parsed_start_date = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid start_date format. Use ISO format (YYYY-MM-DDTHH:MM:SS)")
    
    if end_date:
        try:
            parsed_end_date = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid end_date format. Use ISO format (YYYY-MM-DDTHH:MM:SS)")
    
    # Get transactions with filters
    transactions = crud.get_all_transactions(
        db, 
        skip=0, 
        limit=10000,  # Large limit for export
        status=status,
        payment_method=payment_method,
        start_date=parsed_start_date,
        end_date=parsed_end_date
    )
    
    if transactions is None:
        raise HTTPException(status_code=400, detail=f"Invalid status value. Must be one of: {[s.value for s in models.TransactionStatus]}")
    
    # Create CSV file in memory
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write headers
    writer.writerow([
        "Transaction ID", "Reference", "Date", "Time", "User ID", "Username", "Full Name", 
        "Email", "Phone", "Device ID", "Device Name", "Units", "Amount", 
        "Status", "Payment Method", "Rate Name", "Price Per Unit", "Notes"
    ])
    
    # Write transaction data
    for transaction in transactions:
        # Get user information
        user = db.query(models.User).filter(models.User.id == transaction.user_id).first()
        
        # Get rate information
        rate = db.query(models.ElectricityRate).filter(models.ElectricityRate.id == transaction.rate_id).first()
        
        # Get device information if available
        device_name = None
        if transaction.device_id:
            device = db.query(models.DeviceStatus).filter(models.DeviceStatus.device_id == transaction.device_id).first()
            if device:
                device_name = device.device_name
        
        # Format date and time
        created_date = transaction.created_at.strftime("%Y-%m-%d")
        created_time = transaction.created_at.strftime("%H:%M:%S")
        
        # Write row
        writer.writerow([
            transaction.id,
            transaction.transaction_reference,
            created_date,
            created_time,
            transaction.user_id,
            user.username if user else "",
            user.full_name if user else "",
            user.email if user else "",
            user.phone_number if user else "",
            transaction.device_id or "",
            device_name or "",
            transaction.units_purchased,
            transaction.amount,
            transaction.status.value,
            transaction.payment_method or "",
            rate.rate_name if rate else "",
            rate.price_per_unit if rate else "",
            transaction.notes or ""
        ])
    
    # Return CSV file
    output.seek(0)
    date_str = datetime.now().strftime("%Y%m%d")
    return StreamingResponse(
        output, 
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=transactions_export_{date_str}.csv"}
    )

# User Management Actions
class BulkUserAction(BaseModel):
    user_ids: List[int]
    action: str  # "delete", "activate", "deactivate", "make_admin", "remove_admin"

@router.post("/users/bulk-action", response_model=dict)
def bulk_user_action(action_data: BulkUserAction, db: Session = Depends(get_db)):
    """
    Perform bulk actions on multiple users at once.
    Available actions: delete, activate, deactivate, make_admin, remove_admin
    Special protection: User with ID 3 (main admin) is protected from certain actions.
    """
    results = {
        "success": 0,
        "failed": 0,
        "skipped": 0,
        "details": []
    }
    
    for user_id in action_data.user_ids:
        # Skip the protected admin for certain actions
        if user_id == 3 and action_data.action in ["delete", "deactivate", "remove_admin"]:
            results["skipped"] += 1
            results["details"].append({
                "user_id": user_id,
                "status": "skipped",
                "message": "Protected admin account"
            })
            continue
        
        # Get the user
        user = db.query(models.User).filter(models.User.id == user_id).first()
        if not user:
            results["failed"] += 1
            results["details"].append({
                "user_id": user_id,
                "status": "failed",
                "message": "User not found"
            })
            continue
        
        try:
            if action_data.action == "delete":
                # Handle devices before deletion
                devices = db.query(models.DeviceStatus).filter(models.DeviceStatus.user_id == user_id).all()
                for device in devices:
                    device.user_id = None
                    device.is_primary = False
                
                db.delete(user)
                message = f"User {user.username} deleted"
                
            elif action_data.action == "activate":
                user.is_active = True
                message = f"User {user.username} activated"
                
            elif action_data.action == "deactivate":
                user.is_active = False
                message = f"User {user.username} deactivated"
                
            elif action_data.action == "make_admin":
                user.role = models.UserRole.ADMIN
                message = f"User {user.username} promoted to admin"
                
            elif action_data.action == "remove_admin":
                user.role = models.UserRole.USER
                message = f"User {user.username} demoted to regular user"
                
            else:
                results["failed"] += 1
                results["details"].append({
                    "user_id": user_id,
                    "status": "failed",
                    "message": "Invalid action"
                })
                continue
                
            user.updated_at = datetime.utcnow()
            results["success"] += 1
            results["details"].append({
                "user_id": user_id,
                "status": "success",
                "message": message
            })
            
        except Exception as e:
            results["failed"] += 1
            results["details"].append({
                "user_id": user_id,
                "status": "failed",
                "message": str(e)
            })
    
    db.commit()
    return results

@router.post("/users/{user_id}/set-admin-role", response_model=schemas.UserResponse)
def set_admin_role(user_id: int, make_admin: bool = True, db: Session = Depends(get_db)):
    """
    Promote a user to admin or demote an admin to regular user.
    Special protection: User with ID 3 (main admin) cannot be demoted.
    """
    # Check if user exists
    user = crud.get_user(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Special protection for the main admin (ID 3)
    if user_id == 3 and not make_admin:
        raise HTTPException(
            status_code=403,
            detail="Cannot demote the main administrator account (ID 3)"
        )
    
    # Set role
    user.role = models.UserRole.ADMIN if make_admin else models.UserRole.USER
    user.updated_at = datetime.utcnow()
    
    db.commit()
    db.refresh(user)
    
    return user
