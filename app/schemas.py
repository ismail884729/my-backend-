from pydantic import BaseModel, EmailStr, Field, validator
from typing import Optional, List, Union, Dict, Any
from datetime import datetime
from enum import Enum

# User schemas
class UserLogin(BaseModel):
    username: str
    password: str

class UserBase(BaseModel):
    username: str
    email: str
    full_name: str
    phone_number: Optional[str] = None

class UserCreate(UserBase):
    password: str

class AdminUserCreate(UserCreate):
    role: Optional[str] = "user"  # Default to regular user if not specified
    is_active: Optional[bool] = True
    unit_balance: Optional[float] = 0.0

class UserUpdate(BaseModel):
    email: Optional[str] = None
    full_name: Optional[str] = None
    phone_number: Optional[str] = None
    password: Optional[str] = None
    
class AdminUserUpdate(UserUpdate):
    username: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None
    unit_balance: Optional[float] = None

class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    full_name: str
    phone_number: Optional[str] = None
    role: str
    unit_balance: float
    is_active: bool
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True  # Updated from orm_mode

class UserWithDevicesResponse(UserResponse):
    devices: Optional[List["DeviceStatusResponse"]] = []
    
    class Config:
        from_attributes = True

# Transaction schemas
class TransactionStatus(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"

class UnitPurchase(BaseModel):
    units: float = Field(..., gt=0)
    payment_method: str
    device_id: Optional[str] = None  # Device ID to apply the purchase to
    notes: Optional[str] = None
    
class JsonPurchase(BaseModel):
    units: float = Field(..., gt=0)
    device_id: Optional[str] = None  # Device ID to apply the purchase to
    notes: Optional[str] = None

class TransactionResponse(BaseModel):
    id: int
    amount: float
    units_purchased: float
    transaction_reference: str
    status: str
    balance_before: float
    balance_after: float
    payment_method: Optional[str] = None
    device_id: Optional[str] = None  # Device ID the transaction was applied to
    notes: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None
    # Include rate information
    rate_id: int
    rate_name: Optional[str] = None
    price_per_unit: Optional[float] = None
    
    class Config:
        from_attributes = True  # Updated from orm_mode

class AdminTransactionResponse(TransactionResponse):
    """Extended transaction response with user details for admin view"""
    user_id: int
    username: Optional[str] = None
    user_email: Optional[str] = None
    user_full_name: Optional[str] = None
    user_phone_number: Optional[str] = None
    device_name: Optional[str] = None

# Electricity Rate schemas
class ElectricityRateBase(BaseModel):
    rate_name: str
    price_per_unit: float = Field(..., gt=0)
    is_active: Optional[bool] = True

class ElectricityRateCreate(ElectricityRateBase):
    effective_date: Optional[datetime] = None

class ElectricityRateUpdate(BaseModel):
    rate_name: Optional[str] = None
    price_per_unit: Optional[float] = Field(None, gt=0)
    is_active: Optional[bool] = None
    effective_date: Optional[datetime] = None

class ElectricityRateResponse(ElectricityRateBase):
    id: int
    effective_date: datetime
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True  # Updated from orm_mode

# Device schemas
class DeviceUpdate(BaseModel):
    device_name: str
    
class DeviceCreate(BaseModel):
    user_id: Optional[int] = None
    device_name: Optional[str] = None
    is_online: Optional[bool] = False
    unit_balance: Optional[float] = 0.0
    signal_strength: Optional[int] = None
    is_primary: Optional[bool] = False

class DeviceAssign(BaseModel):
    device_id: str
    device_name: Optional[str] = None
    is_primary: Optional[bool] = False

class DeviceRegistration(BaseModel):
    """Schema for device registration that can either create a new device or assign an existing one"""
    device_id: Optional[str] = None  # If provided, assign existing device; if None, create new device
    device_name: Optional[str] = None
    is_primary: Optional[bool] = False
    unit_balance: Optional[float] = 0.0  # Only used when creating a new device

class DeviceStatusResponse(BaseModel):
    id: int
    device_id: str
    user_id: Optional[int] = None
    device_name: Optional[str] = None
    is_online: bool
    last_seen: Optional[datetime] = None
    unit_balance: float
    signal_strength: Optional[int] = None
    is_primary: Optional[bool] = False
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True  # Updated from orm_mode
        
class DeviceDetailResponse(DeviceStatusResponse):
    """Detailed device information including usage metrics and installation details"""
    # Additional fields for detailed view
    device_type: Optional[str] = "Electricity Meter"
    serial_number: str  # Using device_id as the serial number
    last_reading: Optional[float] = 0.0
    installation_date: Optional[datetime] = None
    location: Optional[str] = None
    
    class Config:
        from_attributes = True

# System Settings schemas
class SystemSettingBase(BaseModel):
    setting_key: str
    setting_value: str
    description: Optional[str] = None

class SystemSettingCreate(SystemSettingBase):
    pass

class SystemSettingUpdate(BaseModel):
    setting_value: str
    description: Optional[str] = None

class SystemSettingResponse(SystemSettingBase):
    id: int
    updated_by: Optional[int] = None
    updated_at: datetime
    
    class Config:
        from_attributes = True  # Updated from orm_mode

# Authentication schemas
class Token(BaseModel):
    access_token: str
    token_type: str
    
# Update forward references for circular imports
UserWithDevicesResponse.update_forward_refs()

class TokenData(BaseModel):
    username: Optional[str] = None
    
class PasswordChange(BaseModel):
    username: str
    current_password: str
    new_password: str
