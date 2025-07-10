from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from jose import JWTError, jwt
from passlib.context import CryptContext

from . import crud, models, schemas
from .database import get_db

# Security settings
SECRET_KEY = "your-secret-key"  # In a real app, use a secure, environment-variable-based key
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

router = APIRouter()

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
        token_data = schemas.TokenData(username=username)
    except JWTError:
        raise credentials_exception
    user = crud.get_user_by_username(db, username=token_data.username)
    if user is None:
        raise credentials_exception
    return user

@router.post("/login", response_model=schemas.Token)
def login_for_access_token(user_data: schemas.UserLogin, db: Session = Depends(get_db)):
    user = crud.verify_user(db, username=user_data.username, password=user_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@router.post("/change-password", response_model=schemas.UserResponse)
def change_password(password_data: schemas.PasswordChange, db: Session = Depends(get_db)):
    # This will be replaced with actual user authentication later
    # For now, we'll just use the username to find the user
    user = crud.get_user_by_username(db, password_data.username)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Verify current password
    if user.password_hash != password_data.current_password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Current password is incorrect"
        )
    
    # Update the password
    user.password_hash = password_data.new_password
    user.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(user)
    
    return user

# Electricity Rate Check Endpoint
@router.get("/check-rates", response_model=List[schemas.ElectricityRateResponse])
def check_rates(db: Session = Depends(get_db)):
    """
    Get all electricity rates available in the system.
    This endpoint is accessible to anyone and doesn't require authentication.
    """
    rates = crud.get_electricity_rates(db)
    return rates

@router.get("/active-rate", response_model=schemas.ElectricityRateResponse)
def get_active_rate(db: Session = Depends(get_db)):
    """
    Get the currently active electricity rate.
    This endpoint is accessible to anyone and doesn't require authentication.
    """
    rate = crud.get_active_electricity_rate(db)
    if not rate:
        raise HTTPException(status_code=404, detail="No active electricity rate found")
    return rate

@router.get("/calculate-purchase/{units}")
def calculate_purchase(units: float, db: Session = Depends(get_db)):
    """
    Calculate how much a purchase will cost based on the active rate.
    This helps users see the cost before making a transaction.
    """
    if units <= 0:
        raise HTTPException(status_code=400, detail="Units must be greater than zero")
        
    # Get active electricity rate
    rate = crud.get_active_electricity_rate(db)
    if not rate:
        raise HTTPException(status_code=404, detail="No active electricity rate found")
    
    # Calculate amount based on units and current rate
    amount = units * rate.price_per_unit
    
    return {
        "units": units,
        "rate_name": rate.rate_name,
        "price_per_unit": rate.price_per_unit,
        "total_amount": amount,
        "rate_id": rate.id
    }
    
@router.get("/user/{user_id}")
def get_user_info(user_id: int, db: Session = Depends(get_db)):
    """
    Get information about a specific user by their ID.
    """
    user = crud.get_user(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail=f"User with ID {user_id} not found")
    
    # Get the user's primary device if any
    primary_device = crud.get_user_primary_device(db, user_id)
    primary_device_id = primary_device.device_id if primary_device else None
    
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role.value,
        "unit_balance": user.unit_balance,
        "is_active": user.is_active,
        "primary_device_id": primary_device_id
    }

@router.get("/calculate-purchase/{user_id}/{units}")
def calculate_purchase_for_user(
    user_id: int, 
    units: float, 
    device_id: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Calculate how much a purchase will cost for a specific user based on the active rate.
    This helps users see the cost before making a transaction.
    Optional: Provide a device_id to calculate for a specific device.
    """
    if units <= 0:
        raise HTTPException(status_code=400, detail="Units must be greater than zero")
    
    # Get the user
    user = crud.get_user(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail=f"User with ID {user_id} not found")
    
    # Handle device selection
    device = None
    if device_id:
        device = crud.get_device_by_id(db, device_id)
        if not device or device.user_id != user_id:
            raise HTTPException(status_code=404, detail=f"Device with ID {device_id} not found or doesn't belong to the user")
    else:
        device = crud.get_user_primary_device(db, user_id)
        
    # Get active electricity rate
    rate = crud.get_active_electricity_rate(db)
    if not rate:
        raise HTTPException(status_code=404, detail="No active electricity rate found")
    
    # Calculate amount based on units and current rate
    amount = units * rate.price_per_unit
    
    response = {
        "user_id": user_id,
        "username": user.username,
        "current_balance": user.unit_balance,
        "units_to_purchase": units,
        "new_balance_after_purchase": user.unit_balance + units,
        "rate_name": rate.rate_name,
        "price_per_unit": rate.price_per_unit,
        "total_amount": amount,
        "rate_id": rate.id
    }
    
    # Add device-specific information if a device was found
    if device:
        response["device_id"] = device.device_id
        response["device_name"] = device.device_name
        response["device_current_balance"] = device.unit_balance
        response["device_new_balance"] = device.unit_balance + units
        response["is_primary_device"] = device.is_primary
        
    return response

# Add new electricity rate via JSON
from pydantic import BaseModel

class RateJsonPayload(BaseModel):
    rate_name: str
    price_per_unit: float
    is_active: bool = False
    effective_date: Optional[str] = None

class DeviceCreatePayload(BaseModel):
    user_id: Optional[int] = None
    device_name: Optional[str] = None
    is_primary: Optional[bool] = False
    
@router.post("/create-device", response_model=schemas.DeviceStatusResponse)
def create_new_device(device_data: Optional[DeviceCreatePayload] = None, db: Session = Depends(get_db)):
    """
    Create a new device (electric meter) with an automatically generated meter ID.
    The device ID will be in the format MTRxxxxxxx (where x is a digit).
    
    Example JSON payload (all fields are optional):
    {
        "user_id": 1,
        "device_name": "Custom Meter Name",
        "is_primary": true
    }
    """
    try:
        device_create = None
        if device_data:
            # Create the device create object
            device_create = schemas.DeviceCreate(
                user_id=device_data.user_id,
                device_name=device_data.device_name,
                is_primary=device_data.is_primary if hasattr(device_data, 'is_primary') else False
            )
        
        # Create the device with auto-generated ID
        device = crud.create_device(db, device_create)
        return device
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error creating device: {str(e)}"
        )

@router.post("/add-rate-json", response_model=schemas.ElectricityRateResponse)
def add_rate_via_json(rate_data: RateJsonPayload, db: Session = Depends(get_db)):
    """
    Add a new electricity rate using JSON payload.
    Example JSON payload:
    {
        "rate_name": "Standard Rate",
        "price_per_unit": 10.5,
        "is_active": true
    }
    """
    # Process the JSON data
    try:
        # Extract values directly from the Pydantic model
        rate_name = rate_data.rate_name
        price_per_unit = rate_data.price_per_unit
        is_active = rate_data.is_active
        effective_date = rate_data.effective_date
            
        # Convert effective_date if provided
        effective_date_obj = None
        if effective_date:
            try:
                effective_date_obj = datetime.fromisoformat(effective_date.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                effective_date_obj = None
                
        # Create rate data object
        rate = schemas.ElectricityRateCreate(
            rate_name=rate_name,
            price_per_unit=float(price_per_unit),
            is_active=is_active,
            effective_date=effective_date_obj
        )
        
        # Create the rate
        return crud.create_electricity_rate(db, rate)
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error creating rate: {str(e)}"
        )
