from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional, Union
from datetime import datetime

from .. import crud, models, schemas
from ..database import get_db

router = APIRouter()

# Get user profile by ID
@router.get("/{user_id}", response_model=schemas.UserResponse)
def read_user(user_id: int, db: Session = Depends(get_db)):
    user = crud.get_user(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail=f"User with ID {user_id} not found")
    return user

@router.get("/{user_id}/with-devices", response_model=schemas.UserWithDevicesResponse)
def read_user_with_devices(user_id: int, db: Session = Depends(get_db)):
    """
    Get a user with all their assigned devices.
    """
    user_with_devices = crud.get_user_with_devices(db, user_id)
    if not user_with_devices:
        raise HTTPException(status_code=404, detail=f"User with ID {user_id} not found")
    return user_with_devices

# Update user profile
@router.put("/{user_id}", response_model=schemas.UserResponse)
def update_user_profile(
    user_id: int,
    user_update: schemas.UserUpdate, 
    db: Session = Depends(get_db)
):
    # Get the specific user by ID
    user = crud.get_user(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail=f"User with ID {user_id} not found")
    
    # Update user fields
    for field, value in user_update.dict(exclude_unset=True).items():
        setattr(user, field, value)
    
    user.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(user)
    return user

# Get user's transaction history
@router.get("/transactions", response_model=List[schemas.TransactionResponse])
def get_user_transactions(
    user_id: int,
    skip: int = 0, 
    limit: int = 100,
    status: Optional[str] = None,
    db: Session = Depends(get_db)
):
    # Get the specific user by ID
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail=f"User with ID {user_id} not found")
    
    # Create a joined query to get transaction and rate information
    query = db.query(
        models.Transaction, 
        models.ElectricityRate.rate_name,
        models.ElectricityRate.price_per_unit
    ).join(
        models.ElectricityRate, 
        models.Transaction.rate_id == models.ElectricityRate.id
    ).filter(models.Transaction.user_id == user.id)
    
    # Filter by status if provided
    if status:
        try:
            transaction_status = models.TransactionStatus(status)
            query = query.filter(models.Transaction.status == transaction_status)
        except ValueError:
            raise HTTPException(
                status_code=400, 
                detail=f"Invalid status value. Must be one of: {[s.value for s in models.TransactionStatus]}"
            )
    
    # Get results with rate information
    results = query.order_by(models.Transaction.created_at.desc()).offset(skip).limit(limit).all()
    
    # Process results to include rate info in transaction objects
    transactions = []
    for transaction, rate_name, price_per_unit in results:
        transaction_dict = {
            **transaction.__dict__,
            "rate_name": rate_name,
            "price_per_unit": price_per_unit
        }
        if "_sa_instance_state" in transaction_dict:
            del transaction_dict["_sa_instance_state"]
        transactions.append(transaction_dict)
    
    return transactions

# Create new transaction (buy units)
@router.post("/buy-units/{user_id}", response_model=schemas.TransactionResponse)
def buy_units(
    user_id: int,
    purchase: schemas.UnitPurchase, 
    db: Session = Depends(get_db)
):
    # Get the specific user by ID
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail=f"User with ID {user_id} not found")
    
    # Find admin with ID 3
    admin = db.query(models.User).filter(models.User.id == 3).first()
    if not admin:
        raise HTTPException(status_code=404, detail="Admin not found")
    
    # Get active electricity rate
    rate = db.query(models.ElectricityRate).filter(
        models.ElectricityRate.is_active == True
    ).first()
    
    if not rate:
        raise HTTPException(status_code=404, detail="No active electricity rate found")
    
    # Calculate amount based on units and current rate
    amount = purchase.units * rate.price_per_unit
    
    # Handle device selection
    device_id = purchase.device_id
    
    # If no device_id provided, use the primary device
    if not device_id:
        primary_device = crud.get_user_primary_device(db, user_id)
        if primary_device:
            device_id = primary_device.device_id
    else:
        # Verify the device belongs to the user
        device = crud.get_device_by_id(db, device_id)
        if not device or device.user_id != user_id:
            raise HTTPException(status_code=404, detail=f"Device with ID {device_id} not found or doesn't belong to the user")
    
    # Create transaction
    transaction = models.Transaction(
        user_id=user.id,
        rate_id=rate.id,
        amount=amount,
        units_purchased=purchase.units,
        transaction_reference=f"TR-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{user.id}",
        status=models.TransactionStatus.PENDING,
        balance_before=user.unit_balance,
        balance_after=user.unit_balance + purchase.units,
        device_id=device_id,
        payment_method="direct_transfer",  # Fixed payment method
        notes=purchase.notes,
        created_at=datetime.utcnow()
    )
    
    db.add(transaction)
    db.commit()
    db.refresh(transaction)
    
    # Set transaction to completed
    transaction.status = models.TransactionStatus.COMPLETED
    transaction.completed_at = datetime.utcnow()
    
    # Transfer money from user to admin (update admin's balance)
    admin.unit_balance += transaction.amount
    
    # Update user balance
    user.unit_balance += purchase.units
    
    # Update the specified device's balance
    if device_id:
        device = db.query(models.DeviceStatus).filter(models.DeviceStatus.device_id == device_id).first()
        if device:
            device.unit_balance += purchase.units
    # If no specific device, update primary device balance if exists
    elif not device_id:
        primary_device = crud.get_user_primary_device(db, user.id)
        if primary_device:
            primary_device.unit_balance += purchase.units
    
    db.commit()
    db.refresh(transaction)
    
    # Fetch rate details to include in response
    transaction_dict = {
        **transaction.__dict__,
        "rate_name": rate.rate_name,
        "price_per_unit": rate.price_per_unit
    }
    if "_sa_instance_state" in transaction_dict:
        del transaction_dict["_sa_instance_state"]
        
    return transaction_dict

# Purchase units with JSON payload
@router.post("/purchase-json/{user_id}", response_model=schemas.TransactionResponse)
def purchase_with_json(
    user_id: int,
    purchase_data: schemas.JsonPurchase, 
    db: Session = Depends(get_db)
):
    # Get the specific user by ID
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail=f"User with ID {user_id} not found")
        
    # Find admin with ID 3
    admin = db.query(models.User).filter(models.User.id == 3).first()
    if not admin:
        raise HTTPException(status_code=404, detail="Admin not found")
    
    # Get active electricity rate first
    rate = db.query(models.ElectricityRate).filter(models.ElectricityRate.is_active == True).first()
    if not rate:
        raise HTTPException(status_code=404, detail="No active electricity rate found")
    
    # Validate device_id if provided
    device_id = purchase_data.device_id
    if device_id:
        device = crud.get_device_by_id(db, device_id)
        if not device or device.user_id != user_id:
            raise HTTPException(status_code=404, detail=f"Device with ID {device_id} not found or doesn't belong to the user")
    
    # Create transaction using the JSON purchase data
    transaction = crud.create_json_purchase(db, user.id, purchase_data)
    
    if not transaction:
        raise HTTPException(status_code=400, detail="Failed to create transaction")
    
    # Set transaction to completed
    transaction.status = models.TransactionStatus.COMPLETED
    transaction.completed_at = datetime.utcnow()
    
    # Transfer money from user to admin (update admin's balance)
    admin.unit_balance += transaction.amount
    
    # Update user's unit balance for tracking purposes
    user.unit_balance += purchase_data.units
    
    # Update the specific device balance if a device_id was provided
    if transaction.device_id:
        device = db.query(models.DeviceStatus).filter(models.DeviceStatus.device_id == transaction.device_id).first()
        if device:
            device.unit_balance += purchase_data.units
    # If no specific device, update primary device balance if exists
    else:
        primary_device = crud.get_user_primary_device(db, user.id)
        if primary_device:
            primary_device.unit_balance += purchase_data.units
    
    db.commit()
    db.refresh(transaction)
    
    # Fetch rate details to include in response
    transaction_dict = {
        **transaction.__dict__,
        "rate_name": rate.rate_name,
        "price_per_unit": rate.price_per_unit
    }
    if "_sa_instance_state" in transaction_dict:
        del transaction_dict["_sa_instance_state"]
        
    return transaction_dict
    
    return transaction

# Get user's device status
@router.get("/device/{user_id}", response_model=schemas.DeviceStatusResponse)
def get_device_status(user_id: int, db: Session = Depends(get_db)):
    # Get the specific user by ID
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail=f"User with ID {user_id} not found")
    
    if not user.device_id:
        raise HTTPException(status_code=404, detail="No device associated with this user")
    
    device = db.query(models.DeviceStatus).filter(
        models.DeviceStatus.device_id == user.device_id
    ).first()
    
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    
    return device

# Update device name
@router.put("/devices/{user_id}/{device_id}", response_model=schemas.DeviceStatusResponse)
def update_user_device(
    user_id: int,
    device_id: str,
    device_update: schemas.DeviceUpdate, 
    db: Session = Depends(get_db)
):
    """
    Update the name of a device belonging to a user.
    """
    # Get the specific user by ID
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail=f"User with ID {user_id} not found")
    
    # Get the device and check it belongs to the user
    device = db.query(models.DeviceStatus).filter(
        models.DeviceStatus.device_id == device_id,
        models.DeviceStatus.user_id == user_id
    ).first()
    
    if not device:
        raise HTTPException(status_code=404, detail=f"Device {device_id} not found or not assigned to this user")
    
    # Update device name
    device.device_name = device_update.device_name
    device.updated_at = datetime.utcnow()
    
    db.commit()
    db.refresh(device)
    
    return device

@router.post("/{user_id}/devices", response_model=schemas.DeviceStatusResponse)
def add_device_to_user(
    user_id: int,
    device_data: schemas.DeviceAssign,
    db: Session = Depends(get_db)
):
    """
    Assign a device to a user's account.
    This endpoint allows a user to add a device to their account via JSON payload.
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
            detail=f"Device is already assigned to another user"
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

@router.post("/{user_id}/register-device", response_model=schemas.DeviceStatusResponse)
def register_device_for_user(
    user_id: int,
    device_data: schemas.DeviceRegistration,
    db: Session = Depends(get_db)
):
    """
    Register a device for a user. This can either:
    1. Create a new device and assign it to the user (when no device_id is provided)
    2. Assign an existing device to the user (when device_id is provided)
    
    Use this endpoint with a JSON payload in Postman:
    - To assign an existing device: {"device_id": "MTR123", "device_name": "Kitchen Meter", "is_primary": true}
    - To create a new device: {"device_name": "Kitchen Meter", "is_primary": true, "unit_balance": 10.0}
    """
    # Check if user exists
    user = crud.get_user(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail=f"User with ID {user_id} not found")
    
    # Determine if we're creating a new device or assigning an existing one
    if device_data.device_id:
        # Assigning existing device
        device = crud.get_device_by_id(db, device_data.device_id)
        if not device:
            raise HTTPException(status_code=404, detail=f"Device with ID {device_data.device_id} not found")
        
        # Check if device is already assigned to another user
        if device.user_id is not None and device.user_id != user_id:
            raise HTTPException(
                status_code=400, 
                detail=f"Device is already assigned to another user"
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
    else:
        # Creating new device and assigning to user
        new_device_data = schemas.DeviceCreate(
            user_id=user_id,
            device_name=device_data.device_name,
            is_primary=device_data.is_primary,
            unit_balance=device_data.unit_balance
        )
        
        new_device = crud.create_device(db, new_device_data)
        return new_device

@router.get("/devices/{user_id}", response_model=List[schemas.DeviceStatusResponse])
def get_user_devices(user_id: int, db: Session = Depends(get_db)):
    """
    Get all devices associated with a user.
    """
    # Get the specific user by ID
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail=f"User with ID {user_id} not found")
    
    # Get all devices for this user
    devices = crud.get_user_devices(db, user_id)
    if not devices:
        return []
    
    return devices

@router.get("/devices/{user_id}/primary", response_model=schemas.DeviceStatusResponse)
def get_user_primary_device(user_id: int, db: Session = Depends(get_db)):
    """
    Get the primary device associated with a user.
    """
    # Get the specific user by ID
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail=f"User with ID {user_id} not found")
    
    # Get primary device
    device = crud.get_user_primary_device(db, user_id)
    if not device:
        raise HTTPException(status_code=404, detail="No primary device associated with this user")
    
@router.get("/device-details/{device_id}", response_model=schemas.DeviceDetailResponse)
def get_device_details(device_id: str, db: Session = Depends(get_db)):
    """
    Get detailed information about a specific device including usage metrics and installation details.
    This endpoint is designed for the "My Devices" view in the frontend.
    """
    # Get detailed device information
    device_details = crud.get_device_details(db, device_id)
    if not device_details:
        raise HTTPException(status_code=404, detail=f"Device with ID {device_id} not found")
    
    return device_details
    return device