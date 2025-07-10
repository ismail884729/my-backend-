from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from sqlalchemy.orm import Session
from typing import List, Optional
import httpx
import os

from .. import crud, models, schemas
from ..database import get_db

router = APIRouter()

# Load environment variables
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
WHATSAPP_ACCESS_TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN")
WHATSAPP_API_URL = "https://graph.facebook.com/v19.0" # Or the latest version

# Helper function to send WhatsApp messages
async def send_whatsapp_message(to_number: str, message_body: str, phone_number_id: str):
    headers = {
        "Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": "text",
        "text": {"body": message_body},
    }
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{WHATSAPP_API_URL}/{phone_number_id}/messages",
            headers=headers,
            json=payload,
        )
        response.raise_for_status()
        return response.json()

@router.get("/webhook")
async def whatsapp_webhook_verification(request: Request):
    """
    Endpoint for WhatsApp webhook verification.
    Meta will send a GET request to this endpoint to verify the webhook.
    """
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    if mode and token:
        if mode == "subscribe" and token == VERIFY_TOKEN:
            print("WEBHOOK_VERIFIED")
            return Response(content=challenge, media_type="text/plain")
        else:
            raise HTTPException(status_code=403, detail="Verification failed")
    raise HTTPException(status_code=400, detail="Missing hub.mode or hub.verify_token")

@router.post("/webhook")
async def whatsapp_webhook_events(request: Request, db: Session = Depends(get_db)):
    """
    Endpoint to receive incoming messages and events from WhatsApp.
    """
    payload = await request.json()
    print("Received WhatsApp webhook payload:", payload)

    # Process incoming messages
    if "object" in payload and "entry" in payload["object"]:
        for entry in payload["object"]["entry"]:
            for change in entry["changes"]:
                if "value" in change and "messages" in change["value"]:
                    for message in change["value"]["messages"]:
                        if message["type"] == "text":
                            from_number = message["from"]  # WhatsApp ID of the sender
                            msg_body = message["text"]["body"]
                            phone_number_id = change["value"]["metadata"]["phone_number_id"]

                            # Simple command parsing
                            response_text = "I'm sorry, I didn't understand that. Try 'buy <units> for <device_id>' or 'rate' or 'cost <units> for <device_id>'."

                            if msg_body.lower() == "rate":
                                try:
                                    rate = crud.get_active_electricity_rate(db)
                                    if rate:
                                        response_text = f"The current active electricity rate is {rate.price_per_unit} KES per unit."
                                    else:
                                        response_text = "No active electricity rate found."
                                except Exception as e:
                                    response_text = f"Error getting rate: {str(e)}"
                            elif msg_body.lower().startswith("cost "):
                                parts = msg_body.lower().split()
                                try:
                                    units = float(parts[1])
                                    device_id = parts[3] if len(parts) > 3 else None
                                    
                                    if device_id:
                                        cost = await calculate_cost_for_device(device_id, units, db)
                                        response_text = f"The cost for {units} units for device {device_id} is {cost} KES."
                                    else:
                                        cost = await calculate_cost(units, db)
                                        response_text = f"The cost for {units} units is {cost} KES."
                                except (ValueError, IndexError):
                                    response_text = "Invalid cost command format. Use 'cost <units> for <device_id>' or 'cost <units>'."
                                except HTTPException as e:
                                    response_text = f"Error calculating cost: {e.detail}"
                            elif msg_body.lower().startswith("buy "):
                                parts = msg_body.lower().split()
                                try:
                                    units = float(parts[1])
                                    device_id = parts[3]
                                    payment_method = "WhatsApp" # Or extract from message if more complex
                                    
                                    # Call the buy_electricity function
                                    transaction_response = await buy_electricity_internal(
                                        device_id=device_id,
                                        units=units,
                                        payment_method=payment_method,
                                        notes="Purchase via WhatsApp",
                                        db=db
                                    )
                                    response_text = (
                                        f"Purchase successful! Transaction ID: {transaction_response.id}. "
                                        f"Units: {transaction_response.units_purchased}, Amount: {transaction_response.amount} KES. "
                                        f"New device balance: {transaction_response.balance_after} units."
                                    )
                                except (ValueError, IndexError):
                                    response_text = "Invalid buy command format. Use 'buy <units> for <device_id>'."
                                except HTTPException as e:
                                    response_text = f"Purchase failed: {e.detail}"
                            
                            await send_whatsapp_message(from_number, response_text, phone_number_id)

    return Response(status_code=200)

@router.post("/buy-electricity", response_model=schemas.TransactionResponse)
async def buy_electricity_internal(
    device_id: str,
    units: float,
    payment_method: str,
    notes: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Buy electricity units via WhatsApp using a device ID."""
    
    device = crud.get_device_by_id(db, device_id)
    if not device:
        raise HTTPException(status_code=404, detail=f"Device with ID {device_id} not found")
    
    user = crud.get_user(db, device.user_id)
    if not user:
        raise HTTPException(status_code=404, detail=f"User associated with device {device_id} not found")

    rate = crud.get_active_electricity_rate(db)
    if not rate:
        raise HTTPException(status_code=404, detail="No active electricity rate found")
    
    amount = units * rate.price_per_unit
    
    transaction = crud.create_transaction(
        db=db,
        user_id=user.id,
        rate_id=rate.id,
        units=units,
        amount=amount,
        payment_method=payment_method,
        device_id=device_id,
        notes=notes
    )
    
    if not transaction:
        raise HTTPException(status_code=400, detail="Failed to create transaction")
    
    completed_transaction = crud.update_transaction_status(db, transaction.id, models.TransactionStatus.COMPLETED.value)
    
    if not completed_transaction:
        raise HTTPException(status_code=500, detail="Failed to complete transaction")
        
    transaction_dict = {
        **completed_transaction.__dict__,
        "rate_name": rate.rate_name,
        "price_per_unit": rate.price_per_unit
    }
    if "_sa_instance_state" in transaction_dict:
        del transaction_dict["_sa_instance_state"]
        
    return transaction_dict

@router.get("/active-rate", response_model=schemas.ElectricityRateResponse)
def get_active_rate_endpoint(db: Session = Depends(get_db)):
    """Get the currently active electricity rate."""
    rate = crud.get_active_electricity_rate(db)
    if not rate:
        raise HTTPException(status_code=404, detail="No active electricity rate found")
    return rate

@router.get("/calculate-cost/{units}", response_model=float)
async def calculate_cost(units: float, db: Session = Depends(get_db)):
    """Calculate how much a purchase will cost based on the active rate."""
    rate = crud.get_active_electricity_rate(db)
    if not rate:
        raise HTTPException(status_code=404, detail="No active electricity rate found")
    return units * rate.price_per_unit

@router.get("/calculate-cost/{device_id}/{units}", response_model=float)
async def calculate_cost_for_device(device_id: str, units: float, db: Session = Depends(get_db)):
    """
    Calculate how much a purchase will cost for a specific device based on the active rate.
    This helps users see the cost before making a transaction.
    """
    device = crud.get_device_by_id(db, device_id)
    if not device:
        raise HTTPException(status_code=404, detail=f"Device with ID {device_id} not found")

    rate = crud.get_active_electricity_rate(db)
    if not rate:
        raise HTTPException(status_code=404, detail="No active electricity rate found")
    
    return units * rate.price_per_unit
