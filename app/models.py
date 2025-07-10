from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, ForeignKey, Text, Enum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime
import enum

Base = declarative_base()

class UserRole(enum.Enum):
    USER = "user"
    ADMIN = "admin"

class TransactionStatus(enum.Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(100), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(100), nullable=False)
    phone_number = Column(String(15), nullable=True)
    role = Column(Enum(UserRole), default=UserRole.USER, nullable=False)
    
    # Updated:  amount  of  money in local currency
    unit_balance = Column(Float, default=0.0, nullable=False)
    
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Remove unique device_id field to support multiple devices per user
    # Instead, we'll use the relationship to devices
    
    transactions = relationship("Transaction", back_populates="user")
    devices = relationship("DeviceStatus", back_populates="user")
    
    def __repr__(self):
        return f"<User(username='{self.username}', unit_balance={self.unit_balance})>"

class ElectricityRate(Base):
    __tablename__ = "electricity_rates"
    
    id = Column(Integer, primary_key=True, index=True)
    rate_name = Column(String(50), nullable=False)
    price_per_unit = Column(Float, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    effective_date = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    transactions = relationship("Transaction", back_populates="rate")
    
    def __repr__(self):
        return f"<ElectricityRate(name='{self.rate_name}', price={self.price_per_unit})>"

class Transaction(Base):
    __tablename__ = "transactions"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    rate_id = Column(Integer, ForeignKey("electricity_rates.id"), nullable=False)
    
    amount = Column(Float, nullable=False)  # in local currency
    units_purchased = Column(Float, nullable=False)  # electricity units (kWh)
    transaction_reference = Column(String(100), unique=True, nullable=False)
    status = Column(Enum(TransactionStatus), default=TransactionStatus.PENDING)
    
    balance_before = Column(Float, nullable=False)
    balance_after = Column(Float, nullable=False)
    
    device_id = Column(String(50), ForeignKey("device_status.device_id"), nullable=True)
    payment_method = Column(String(50), nullable=True)
    notes = Column(Text, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    
    user = relationship("User", back_populates="transactions")
    rate = relationship("ElectricityRate", back_populates="transactions")
    device = relationship("DeviceStatus")
    
    def __repr__(self):
        return f"<Transaction(ref='{self.transaction_reference}', amount={self.amount}, units={self.units_purchased})>"

class SystemSettings(Base):
    __tablename__ = "system_settings"
    
    id = Column(Integer, primary_key=True, index=True)
    setting_key = Column(String(100), unique=True, nullable=False)
    setting_value = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    updated_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f"<SystemSettings(key='{self.setting_key}', value='{self.setting_value}')>"

class DeviceStatus(Base):
    __tablename__ = "device_status"
    
    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(String(50), unique=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    device_name = Column(String(100), nullable=True)
    is_online = Column(Boolean, default=False)
    last_seen = Column(DateTime, nullable=True)
    
    # Updated: current_balance in electricity units
    unit_balance = Column(Float, default=0.0)
    signal_strength = Column(Integer, nullable=True)
    is_primary = Column(Boolean, default=False)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Add relationship back to user
    user = relationship("User", back_populates="devices")
    
    # Add relationship to transactions
    transactions = relationship("Transaction", foreign_keys=[Transaction.device_id], overlaps="device")
    
    def __repr__(self):
        return f"<DeviceStatus(device_id='{self.device_id}', unit_balance={self.unit_balance}, online={self.is_online})>"
