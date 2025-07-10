from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional

from .. import crud, models, schemas
from ..database import get_db

router = APIRouter()

@router.get("/{device_id}/status", response_model=schemas.DeviceStatusResponse)
def get_meter_status(device_id: str, db: Session = Depends(get_db)):
    """
    Check the status of a meter.
    """
    device = crud.get_device_by_id(db, device_id)
    if not device:
        raise HTTPException(status_code=404, detail=f"Device with ID {device_id} not found")
    
    return device

@router.post("/{device_id}/data")
def send_meter_data(device_id: str, meter_data: schemas.MeterData, db: Session = Depends(get_db)):
    """
    Send data to a meter.
    """
    if device_id != meter_data.device_id:
        raise HTTPException(status_code=400, detail="Device ID in URL does not match device ID in payload")

    device = crud.get_device_by_id(db, device_id)
    if not device:
        raise HTTPException(status_code=404, detail=f"Device with ID {device_id} not found")
    
    # In a real-world scenario, this is where you would send the data to the meter.
    # For now, we'll just return a success message.
    return {"message": "Data sent to meter successfully", "data": meter_data}
