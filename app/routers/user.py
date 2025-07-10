from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional, Union
from datetime import datetime

from .. import crud, models, schemas, auth
from ..database import get_db

router = APIRouter()

@router.get("/me", response_model=schemas.UserResponse)
async def read_users_me(current_user: models.User = Depends(auth.get_current_user)):
    return current_user

# Get user profile by ID
@router.get("/{user_id}", response_model=schemas.UserResponse)
def read_user(user_id: str, db: Session = Depends(get_db)):
    if not user_id.isdigit():
        raise HTTPException(status_code=400, detail="Invalid user ID")
    user = crud.get_user(db, int(user_id))
    if not user:
        raise HTTPException(status_code=404, detail=f"User with ID {user_id} not found")
    return user

@router.get("/{user_id}/with-devices", response_model=schemas.UserWithDevicesResponse)
def read_user_with_devices(user_id: str, db: Session = Depends(get_db)):
    """
    Get a user with all their assigned devices.
    """
    if not user_id.isdigit():
        raise HTTPException(status_code=400, detail="Invalid user ID")
    user_with_devices = crud.get_user_with_devices(db, int(user_id))
    if not user_with_devices:
        raise HTTPException(status_code=404, detail=f"User with ID {user_id} not found")
    return user_with_devices

@router.put("/me", response_model=schemas.UserResponse)
async def update_current_user(
    user_update: schemas.UserUpdate,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db)
):
    # Update user fields
    for field, value in user_update.dict(exclude_unset=True).items():
        setattr(current_user, field, value)
    
    current_user.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(current_user)
    return current_user

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
@router.get("/{user_id}/transactions", response_model=List[schemas.TransactionResponse])
def get_user_transactions(
    user_id: str,
    skip: int = 0,
    limit: int = 100,
    status: Optional[str] = None,
    db: Session = Depends(get_db)
):
    # Get the specific user by ID
    if not user_id.isdigit():
        raise HTTPException(status_code=400, detail="Invalid user ID")
    user = crud.get_user(db, int(user_id))
    if not user:
        raise HTTPException(status_code=404, detail=f"User with ID {user_id} not found")

    # Get transactions using the CRUD function
    transactions = crud.get_user_transactions(db, int(user_id), skip, limit, status)
    if transactions is None:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status value. Must be one of: {[s.value for s in models.TransactionStatus]}"
        )

    # Process results to include rate info in transaction objects
    processed_transactions = []
    for transaction in transactions:
        rate = crud.get_electricity_rate(db, transaction.rate_id)
        transaction_dict = {
            **transaction.__dict__,
            "rate_name": rate.rate_name if rate else "N/A",
            "price_per_unit": rate.price_per_unit if rate else 0.0
        }
        if "_sa_instance_state" in transaction_dict:
            del transaction_dict["_sa_instance_state"]
        processed_transactions.append(transaction_dict)

    return processed_transactions

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
        balance_before=user.unit_balance, # Monetary balance before transaction
        balance_after=user.unit_balance - amount, # Monetary balance after transaction
        device_id=device_id,
        payment_method="direct_transfer",  # Fixed payment method
        notes=purchase.notes,
        created_at=datetime.utcnow()
    )
    
    db.add(transaction)
    
    # Set transaction to completed
    transaction.status = models.TransactionStatus.COMPLETED
    transaction.completed_at = datetime.utcnow()
    
    # Transfer money from user to admin (update admin's balance)
    admin.unit_balance += transaction.amount
    
    # Update user balance (in money)
    user.unit_balance -= amount
    
    # Update the specified device's balance (in units)
    if device_id:
        device = db.query(models.DeviceStatus).filter(models.DeviceStatus.device_id == device_id).first()
        if device:
            device.unit_balance += purchase.units # Device balance still tracks units
    
    db.commit()
    db.refresh(transaction)
    db.refresh(user) # Refresh user to ensure latest balance is reflected
    if device_id: # Refresh device if it was updated
        db.refresh(device)
    elif not device_id and primary_device: # Refresh primary device if it was updated
        db.refresh(primary_device)
    
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

@router.get("/devices/{identifier}", response_model=Union[List[schemas.DeviceStatusResponse], schemas.DeviceStatusResponse])
def get_devices(identifier: str, db: Session = Depends(get_db)):
    """
    Get all devices for a user or a single device by its ID.
    - If the identifier is numeric, it's treated as a user ID.
    - If the identifier is a string (non-numeric), it's treated as a device ID.
    """
    if identifier.isdigit():
        user_id = int(identifier)
        user = db.query(models.User).filter(models.User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail=f"User with ID {user_id} not found")
        
        devices = crud.get_user_devices(db, user_id)
        return devices
    else:
        device_id = identifier
        device = crud.get_device_by_id(db, device_id)
        if not device:
            raise HTTPException(status_code=404, detail=f"Device with ID {device_id} not found")
        return device


@router.get("/{user_id}/usage", response_model=schemas.UsageData)
def get_user_usage_data(user_id: str, db: Session = Depends(get_db)):
    """
    Get a user's usage summary and transaction history.
    """
    # Check if user exists
    if not user_id.isdigit():
        raise HTTPException(status_code=400, detail="Invalid user ID")
    user = crud.get_user(db, int(user_id))
    if not user:
        raise HTTPException(status_code=404, detail=f"User with ID {user_id} not found")
    
    # Get usage data
    usage_data = crud.get_user_usage(db, int(user_id))
    
    return usage_data
