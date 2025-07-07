from sqlalchemy.orm import Session
from sqlalchemy import desc
from datetime import datetime
from typing import Optional, List
from . import models, schemas

# User CRUD operations
def get_user(db: Session, user_id: int):
    return db.query(models.User).filter(models.User.id == user_id).first()

def get_user_by_username(db: Session, username: str):
    return db.query(models.User).filter(models.User.username == username).first()

def get_user_by_email(db: Session, email: str):
    return db.query(models.User).filter(models.User.email == email).first()

def get_users(db: Session, skip: int = 0, limit: int = 100):
    return db.query(models.User).offset(skip).limit(limit).all()

def create_user(db: Session, user: schemas.UserCreate):
    # In a real app, we would hash the password
    # For now, we're storing it directly as requested (no security)
    db_user = models.User(
        username=user.username,
        email=user.email,
        password_hash=user.password,  # No hashing for now
        full_name=user.full_name,
        phone_number=user.phone_number,
        role=models.UserRole.USER,
        unit_balance=0.0,
        is_active=True,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

def admin_create_user(db: Session, user: schemas.AdminUserCreate):
    # In a real app, we would hash the password
    # For now, we're storing it directly as requested (no security)
    try:
        # Convert string role to UserRole enum
        if hasattr(user, 'role') and user.role:
            user_role = models.UserRole(user.role)
        else:
            user_role = models.UserRole.USER
    except ValueError:
        # Default to USER role if invalid role provided
        user_role = models.UserRole.USER
    
    db_user = models.User(
        username=user.username,
        email=user.email,
        password_hash=user.password,  # No hashing for now
        full_name=user.full_name,
        phone_number=user.phone_number,
        role=user_role,
        unit_balance=user.unit_balance if hasattr(user, 'unit_balance') and user.unit_balance is not None else 0.0,
        is_active=user.is_active if hasattr(user, 'is_active') and user.is_active is not None else True,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

def update_user(db: Session, user_id: int, user_update: schemas.UserUpdate):
    db_user = db.query(models.User).filter(models.User.id == user_id).first()
    if not db_user:
        return None
    
    update_data = user_update.dict(exclude_unset=True)
    if 'password' in update_data:
        # In a real app, we would hash the password
        update_data['password_hash'] = update_data.pop('password')
    
    for field, value in update_data.items():
        setattr(db_user, field, value)
    
    db_user.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(db_user)
    return db_user

def verify_user(db: Session, username: str, password: str):
    user = get_user_by_username(db, username)
    # In a real app, we would check the password hash
    # For now, we're just directly comparing the password_hash field
    # WITHOUT ANY SECURITY, as requested
    if user and user.password_hash == password:
        return user
    return None

# Transaction CRUD operations
def get_user_transactions(db: Session, user_id: int, skip: int = 0, limit: int = 100, status: Optional[str] = None):
    query = db.query(models.Transaction).filter(models.Transaction.user_id == user_id)
    
    if status:
        try:
            transaction_status = models.TransactionStatus(status)
            query = query.filter(models.Transaction.status == transaction_status)
        except ValueError:
            return None
    
    return query.order_by(desc(models.Transaction.created_at)).offset(skip).limit(limit).all()

def get_transaction(db: Session, transaction_id: int):
    return db.query(models.Transaction).filter(models.Transaction.id == transaction_id).first()

def get_all_transactions(db: Session, skip: int = 0, limit: int = 100, status: Optional[str] = None, 
                         payment_method: Optional[str] = None, start_date: Optional[datetime] = None, 
                         end_date: Optional[datetime] = None):
    """
    Get all transactions with optional filtering parameters.
    This is primarily used by admins to monitor purchases and payments.
    """
    query = db.query(models.Transaction)
    
    # Apply filters if provided
    if status:
        try:
            transaction_status = models.TransactionStatus(status)
            query = query.filter(models.Transaction.status == transaction_status)
        except ValueError:
            return None
    
    if payment_method:
        query = query.filter(models.Transaction.payment_method == payment_method)
        
    if start_date:
        query = query.filter(models.Transaction.created_at >= start_date)
        
    if end_date:
        query = query.filter(models.Transaction.created_at <= end_date)
    
    return query.order_by(desc(models.Transaction.created_at)).offset(skip).limit(limit).all()

def create_transaction(db: Session, user_id: int, rate_id: int, units: float, amount: float, payment_method: str, device_id: Optional[str] = None, notes: Optional[str] = None):
    # Get the user
    user = get_user(db, user_id)
    if not user:
        return None
    
    # If no device_id provided, use the primary device
    if not device_id:
        primary_device = get_user_primary_device(db, user_id)
        if primary_device:
            device_id = primary_device.device_id
    else:
        # Verify the device belongs to the user
        device = get_device_by_id(db, device_id)
        if not device or device.user_id != user_id:
            return None
    
    # Create a transaction reference
    transaction_ref = f"TR-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{user_id}"
    
    # Create the transaction
    db_transaction = models.Transaction(
        user_id=user_id,
        rate_id=rate_id,
        amount=amount,
        units_purchased=units,
        transaction_reference=transaction_ref,
        status=models.TransactionStatus.PENDING,
        balance_before=user.unit_balance,
        balance_after=user.unit_balance + units,
        device_id=device_id,
        payment_method=payment_method,
        notes=notes,
        created_at=datetime.utcnow()
    )
    
    db.add(db_transaction)
    db.commit()
    db.refresh(db_transaction)
    return db_transaction
    
def create_json_purchase(db: Session, user_id: int, purchase_data: schemas.JsonPurchase):
    """
    Process a purchase made via JSON payload with direct money transfer to admin
    """
    # Get the user
    user = get_user(db, user_id)
    if not user:
        return None
    
    # Get active electricity rate
    rate = get_active_electricity_rate(db)
    if not rate:
        return None
    
    # Calculate amount based on units and current rate
    amount = purchase_data.units * rate.price_per_unit
    
    # If no device_id provided, use the primary device
    device_id = purchase_data.device_id
    if not device_id:
        primary_device = get_user_primary_device(db, user_id)
        if primary_device:
            device_id = primary_device.device_id
    else:
        # Verify the device belongs to the user
        device = get_device_by_id(db, device_id)
        if not device or device.user_id != user_id:
            return None
    
    # Generate automatic transaction reference
    transaction_ref = f"TR-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{user_id}"
    
    # Create the transaction
    db_transaction = models.Transaction(
        user_id=user_id,
        rate_id=rate.id,
        amount=amount,
        units_purchased=purchase_data.units,
        transaction_reference=transaction_ref,
        status=models.TransactionStatus.PENDING,
        balance_before=user.unit_balance,
        balance_after=user.unit_balance + purchase_data.units,
        device_id=device_id,
        payment_method="direct_transfer",  # Fixed payment method
        notes=purchase_data.notes,
        created_at=datetime.utcnow()
    )
    
    db.add(db_transaction)
    db.commit()
    db.refresh(db_transaction)
    return db_transaction

def update_transaction_status(db: Session, transaction_id: int, status: str):
    db_transaction = get_transaction(db, transaction_id)
    if not db_transaction:
        return None
    
    try:
        new_status = models.TransactionStatus(status)
    except ValueError:
        return None
    
    db_transaction.status = new_status
    
    if new_status == models.TransactionStatus.COMPLETED:
        db_transaction.completed_at = datetime.utcnow()
        
        # Get the user
        user = get_user(db, db_transaction.user_id)
        
        # Update the specific device's balance if a device_id was specified
        if db_transaction.device_id:
            device = db.query(models.DeviceStatus).filter(
                models.DeviceStatus.device_id == db_transaction.device_id
            ).first()
            
            if device:
                device.unit_balance += db_transaction.units_purchased
                # Also update the user's overall balance for tracking purposes
                user.unit_balance += db_transaction.units_purchased
        else:
            # If no device specified, just update the user's overall balance
            user.unit_balance += db_transaction.units_purchased
            
            # And update primary device balance if it exists
            primary_device = get_user_primary_device(db, user.id)
            if primary_device:
                primary_device.unit_balance += db_transaction.units_purchased
    
    db.commit()
    db.refresh(db_transaction)
    return db_transaction

# Electricity Rate CRUD operations
def get_electricity_rate(db: Session, rate_id: int):
    return db.query(models.ElectricityRate).filter(models.ElectricityRate.id == rate_id).first()

def get_active_electricity_rate(db: Session):
    return db.query(models.ElectricityRate).filter(models.ElectricityRate.is_active == True).first()

def get_electricity_rates(db: Session, skip: int = 0, limit: int = 100):
    return db.query(models.ElectricityRate).order_by(models.ElectricityRate.created_at.desc()).offset(skip).limit(limit).all()

def create_electricity_rate(db: Session, rate: schemas.ElectricityRateCreate):
    # If this is an active rate, deactivate all other rates
    if rate.is_active:
        db.query(models.ElectricityRate).filter(models.ElectricityRate.is_active == True).update({"is_active": False})
    
    # Set effective date to now if not provided
    effective_date = rate.effective_date if rate.effective_date else datetime.utcnow()
    
    db_rate = models.ElectricityRate(
        rate_name=rate.rate_name,
        price_per_unit=rate.price_per_unit,
        is_active=rate.is_active,
        effective_date=effective_date,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    db.add(db_rate)
    db.commit()
    db.refresh(db_rate)
    return db_rate

def update_electricity_rate(db: Session, rate_id: int, rate: schemas.ElectricityRateUpdate):
    db_rate = get_electricity_rate(db, rate_id)
    if not db_rate:
        return None
    
    update_data = rate.dict(exclude_unset=True)
    
    # If setting this rate to active, deactivate all other rates
    if update_data.get('is_active', False):
        db.query(models.ElectricityRate).filter(models.ElectricityRate.id != rate_id, models.ElectricityRate.is_active == True).update({"is_active": False})
    
    for field, value in update_data.items():
        setattr(db_rate, field, value)
    
    db_rate.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(db_rate)
    return db_rate

def delete_electricity_rate(db: Session, rate_id: int):
    db_rate = get_electricity_rate(db, rate_id)
    if not db_rate:
        return None
    
    # Don't allow deleting an active rate
    if db_rate.is_active:
        return False
    
    # Check if rate is used in any transactions
    used_in_transactions = db.query(models.Transaction).filter(models.Transaction.rate_id == rate_id).first()
    if used_in_transactions:
        return False
    
    db.delete(db_rate)
    db.commit()
    return True

# System Settings CRUD operations
def get_system_setting(db: Session, setting_key: str):
    return db.query(models.SystemSettings).filter(models.SystemSettings.setting_key == setting_key).first()

def get_system_setting_by_id(db: Session, setting_id: int):
    return db.query(models.SystemSettings).filter(models.SystemSettings.id == setting_id).first()

def get_system_settings(db: Session, skip: int = 0, limit: int = 100):
    return db.query(models.SystemSettings).order_by(models.SystemSettings.setting_key).offset(skip).limit(limit).all()

def create_system_setting(db: Session, setting: schemas.SystemSettingCreate, user_id: Optional[int] = None):
    db_setting = models.SystemSettings(
        setting_key=setting.setting_key,
        setting_value=setting.setting_value,
        description=setting.description,
        updated_by=user_id,
        updated_at=datetime.utcnow()
    )
    db.add(db_setting)
    db.commit()
    db.refresh(db_setting)
    return db_setting

def update_system_setting(db: Session, setting_key: str, setting: schemas.SystemSettingUpdate, user_id: Optional[int] = None):
    db_setting = get_system_setting(db, setting_key)
    if not db_setting:
        return None
    
    db_setting.setting_value = setting.setting_value
    if setting.description is not None:
        db_setting.description = setting.description
    
    db_setting.updated_by = user_id
    db_setting.updated_at = datetime.utcnow()
    
    db.commit()
    db.refresh(db_setting)
    return db_setting

def delete_system_setting(db: Session, setting_key: str):
    db_setting = get_system_setting(db, setting_key)
    if not db_setting:
        return False
    
    db.delete(db_setting)
    db.commit()
    return True

# Device CRUD operations
def get_device_by_id(db: Session, device_id: str):
    return db.query(models.DeviceStatus).filter(models.DeviceStatus.device_id == device_id).first()

def get_device_details(db: Session, device_id: str):
    """Get detailed information about a device, including usage metrics and installation details"""
    device = get_device_by_id(db, device_id)
    if not device:
        return None
    
    # Get the last transaction for this device to determine the last reading
    last_transaction = db.query(models.Transaction).filter(
        models.Transaction.device_id == device_id,
        models.Transaction.status == models.TransactionStatus.COMPLETED
    ).order_by(models.Transaction.created_at.desc()).first()
    
    # Populate the installation date (using created_at as proxy)
    installation_date = device.created_at if device else None
    
    # Populate last reading from the transaction or use unit balance
    last_reading = device.unit_balance
    if last_transaction:
        # We could calculate the actual reading based on transaction history if needed
        pass
    
    return {
        **device.__dict__,
        "serial_number": device.device_id,
        "device_type": "Electricity Meter",
        "last_reading": last_reading,
        "installation_date": installation_date,
        "location": device.device_name or "Unknown Location"
    }

def get_all_devices(db: Session, skip: int = 0, limit: int = 100):
    return db.query(models.DeviceStatus).order_by(models.DeviceStatus.created_at.desc()).offset(skip).limit(limit).all()

def get_user_devices(db: Session, user_id: int):
    """Get all devices assigned to a specific user."""
    return db.query(models.DeviceStatus).filter(models.DeviceStatus.user_id == user_id).all()

def get_user_primary_device(db: Session, user_id: int):
    """Get a user's primary device (if any)."""
    return db.query(models.DeviceStatus).filter(
        models.DeviceStatus.user_id == user_id,
        models.DeviceStatus.is_primary == True
    ).first()

def get_user_with_devices(db: Session, user_id: int):
    """Get a user with all their assigned devices."""
    user = get_user(db, user_id)
    if not user:
        return None
    
    devices = get_user_devices(db, user_id)
    user_dict = {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "full_name": user.full_name,
        "phone_number": user.phone_number,
        "role": user.role.value,
        "unit_balance": user.unit_balance,
        "is_active": user.is_active,
        "created_at": user.created_at,
        "updated_at": user.updated_at,
        "devices": devices
    }
    return user_dict

def update_device_name(db: Session, device_id: str, device_name: str):
    db_device = get_device_by_id(db, device_id)
    if not db_device:
        return None
    
    db_device.device_name = device_name
    db_device.updated_at = datetime.utcnow()
    
    db.commit()
    db.refresh(db_device)
    return db_device

def assign_device_to_user(db: Session, device_id: str, user_id: int, device_name: Optional[str] = None, make_primary: bool = False):
    """Assign a device to a user."""
    db_device = get_device_by_id(db, device_id)
    if not db_device:
        return None
    
    # If making this device primary, update any other primary devices
    if make_primary:
        db.query(models.DeviceStatus).filter(
            models.DeviceStatus.user_id == user_id,
            models.DeviceStatus.is_primary == True
        ).update({"is_primary": False})
    
    # Update device information
    db_device.user_id = user_id
    db_device.is_primary = make_primary
    
    # Update name if provided
    if device_name:
        db_device.device_name = device_name
    elif not db_device.device_name:
        db_device.device_name = f"Meter {device_id}"
    
    db_device.updated_at = datetime.utcnow()
    
    db.commit()
    db.refresh(db_device)
    return db_device

def unassign_device_from_user(db: Session, device_id: str):
    """Unassign a device from a user."""
    db_device = get_device_by_id(db, device_id)
    if not db_device:
        return None
    
    # Update device information
    db_device.user_id = None
    db_device.is_primary = False
    db_device.updated_at = datetime.utcnow()
    
    db.commit()
    db.refresh(db_device)
    return db_device

def update_device_status(db: Session, device_id: str, is_online: bool, signal_strength: Optional[int] = None):
    db_device = get_device_by_id(db, device_id)
    if not db_device:
        return None
    
    db_device.is_online = is_online
    if signal_strength is not None:
        db_device.signal_strength = signal_strength
    
    db_device.last_seen = datetime.utcnow()
    db_device.updated_at = datetime.utcnow()
    
    db.commit()
    db.refresh(db_device)
    return db_device

def make_device_primary(db: Session, device_id: str):
    """Make a device the primary device for its assigned user."""
    db_device = get_device_by_id(db, device_id)
    if not db_device or not db_device.user_id:
        return None
    
    # Update any existing primary devices for this user
    db.query(models.DeviceStatus).filter(
        models.DeviceStatus.user_id == db_device.user_id,
        models.DeviceStatus.is_primary == True,
        models.DeviceStatus.device_id != device_id
    ).update({"is_primary": False})
    
    # Make this device primary
    db_device.is_primary = True
    db_device.updated_at = datetime.utcnow()
    
    db.commit()
    db.refresh(db_device)
    return db_device

def generate_unique_meter_id(db: Session):
    """
    Generate a unique meter ID starting with 'MTR' followed by random digits.
    """
    import random
    import string
    
    # Keep generating until we find a unique ID
    while True:
        # Generate 7 random digits
        random_digits = ''.join(random.choices(string.digits, k=7))
        meter_id = f"MTR{random_digits}"
        
        # Check if this ID already exists
        existing_device = get_device_by_id(db, meter_id)
        if not existing_device:
            return meter_id

def create_device(db: Session, device: schemas.DeviceCreate = None):
    """
    Create a new device with an automatically generated device ID starting with 'MTR'.
    """
    # Generate unique device ID
    device_id = generate_unique_meter_id(db)
    
    # Set default values if device object is not provided
    if device is None:
        device = schemas.DeviceCreate()
    
    # Check if this should be the primary device for the user
    is_primary = device.is_primary if device.is_primary is not None else False
    
    # If marked as primary, ensure any other devices for this user are not primary
    if is_primary and device.user_id:
        db.query(models.DeviceStatus).filter(
            models.DeviceStatus.user_id == device.user_id, 
            models.DeviceStatus.is_primary == True
        ).update({"is_primary": False})
        db.commit()
    
    # Create device record
    db_device = models.DeviceStatus(
        device_id=device_id,
        user_id=device.user_id,
        device_name=device.device_name if device.device_name else f"Meter {device_id}",
        is_online=device.is_online if device.is_online is not None else False,
        unit_balance=device.unit_balance if device.unit_balance is not None else 0.0,
        signal_strength=device.signal_strength,
        is_primary=is_primary,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    
    db.add(db_device)
    db.commit()
    db.refresh(db_device)
    
    return db_device
