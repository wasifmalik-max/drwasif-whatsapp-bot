import os
import re
from typing import Any, Dict, Optional

import httpx
from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Request
from pydantic import BaseModel

app = FastAPI(title="Dr Wasif WhatsApp Bot")

# In-memory only. Use DB/Redis in production.
PAYMENT_STATE: Dict[str, Dict[str, Any]] = {}
VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "")

# Optional: if set, /payment/* and /payment/states require X-Admin-Key header.
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "")

DOCTOR_ALERT_NUMBER = os.getenv("DOCTOR_ALERT_NUMBER", "").replace("+", "").replace(" ", "")
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN", "")
WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
GRAPH_API_VERSION = os.getenv("GRAPH_API_VERSION", "v21.0")

MCB_ACCOUNT_NAME = os.getenv("MCB_ACCOUNT_NAME", "WASIF RIZWAN MALIK")
MCB_ACCOUNT_SUFFIX = os.getenv("MCB_ACCOUNT_SUFFIX", "9297")
MCB_QR_IMAGE_URL = os.getenv("MCB_QR_IMAGE_URL", "")
FEE_VIDEO_PKR = os.getenv("FEE_VIDEO_PKR", "3000")
FEE_PRESCRIPTION_PKR = os.getenv("FEE_PRESCRIPTION_PKR", "1000")

# Tier-1 emergency (English + Urdu roman / keywords) — bypass payment, escalate.
EMERGENCY_TERMS_EN = (
    "chest pain",
    "can't breathe",
    "stroke",
    "unconscious",
    "bleeding heavily",
    "suicide",
    "kill myself",
)
EMERGENCY_TERMS_UR = (
    "فالج",
    "بے ہوش",
    "خون",
    "سینے کا درد",
    "سانس",
)


def require_admin(
    x_admin_key: Optional[str] = Header(None, alias="X-Admin-Key"),
) -> None:
    if not ADMIN_API_KEY:
        return
    if x_admin_key != ADMIN_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing X-Admin-Key")


async def send_whatsapp_text(to_e164_digits: str, body: str) -> None:
    """Send outbound text via WhatsApp Cloud API."""
    if not WHATSAPP_TOKEN or not WHATSAPP_PHONE_NUMBER_ID:
        return
    url = (
        f"https://graph.facebook.com/{GRAPH_API_VERSION}/"
        f"{WHATSAPP_PHONE_NUMBER_ID}/messages"
    )
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to_e164_digits,
        "type": "text",
        "text": {"preview_url": False, "body": body[:4096]},
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(url, headers=headers, json=payload)
        if r.status_code >= 400:
            # Log only; webhook must still return 200
            print(f"WhatsApp send error {r.status_code}: {r.text[:500]}")


def _payment_instructions_text() -> str:
    lines = [
        "💳 *Fee* — Video consult: PKR "
        + FEE_VIDEO_PKR
        + " | Prescription renewal: PKR "
        + FEE_PRESCRIPTION_PKR,
        "🏦 *MCB* — " + MCB_ACCOUNT_NAME + " (ref " + MCB_ACCOUNT_SUFFIX + ")",
    ]
    if MCB_QR_IMAGE_URL:
        lines.append("📷 QR image URL: " + MCB_QR_IMAGE_URL)
    lines.extend(
        [
            "",
            "After paying, send: (1) screenshot (2) bank reference ID.",
            "Verification is manual — never trust screenshot alone.",
        ]
    )
    return "\n".join(lines)


def _emergency_reply() -> str:
    return (
        "⚠️ If this is an emergency (severe pain, breathing problem, stroke signs, "
        "heavy bleeding, unconsciousness), go to the *nearest ER* or call emergency services.\n\n"
        "This WhatsApp line is *not* for emergencies. Clinic staff will follow up when possible."
    )


async def maybe_alert_doctor(sender: str, note: str) -> None:
    if not DOCTOR_ALERT_NUMBER or not WHATSAPP_TOKEN:
        return
    msg = f"📋 Alert\nFrom: {sender}\n{note}"
    await send_whatsapp_text(DOCTOR_ALERT_NUMBER, msg[:4096])


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.get("/webhook")
def verify_webhook(
    hub_mode: str = "",
    hub_verify_token: str = "",
    hub_challenge: str = "",
):
    if hub_mode == "subscribe" and hub_verify_token == VERIFY_TOKEN and hub_challenge:
        return int(hub_challenge)
    raise HTTPException(status_code=403, detail="Webhook verification failed")


def _extract_message(payload: Dict[str, Any]) -> Dict[str, Any]:
    entries = payload.get("entry", [])
    if not entries:
        return {"from": "", "text": "", "type": ""}
    changes = entries[0].get("changes", [])
    if not changes:
        return {"from": "", "text": "", "type": ""}
    value = changes[0].get("value", {})
    messages = value.get("messages", [])
    if not messages:
        return {"from": "", "text": "", "type": ""}
    msg = messages[0]
    sender = msg.get("from", "")
    mtype = msg.get("type", "")
    text = ""
    if mtype == "text":
        text = msg.get("text", {}).get("body", "").strip()
    return {"from": sender, "text": text, "type": mtype}


def _contains_reference_id(text: str) -> bool:
    return re.search(r"\b[A-Za-z0-9]{6,}\b", text) is not None


def _is_emergency(text: str) -> bool:
    low = text.lower()
    if any(t in low for t in EMERGENCY_TERMS_EN):
        return True
    if any(t in text for t in EMERGENCY_TERMS_UR):
        return True
    return False


class PaymentDecision(BaseModel):
    sender: str
    note: str = ""


@app.post("/webhook")
async def inbound_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
):
    try:
        payload = await request.json()
    except Exception:
        return {"success": True}

    msg = _extract_message(payload)
    sender = msg["from"]
    text = msg.get("text") or ""
    mtype = msg.get("type") or ""

    if not sender:
        return {"success": True}

    # Emergency path
    if text and _is_emergency(text):
        background_tasks.add_task(send_whatsapp_text, sender, _emergency_reply())
        background_tasks.add_task(
            maybe_alert_doctor,
            sender,
            f"Emergency keywords in message: {text[:500]}",
        )
        return {"success": True}

    state = PAYMENT_STATE.get(sender, {"status": "idle"})
    lowered = text.lower()

    # Payment / consult intent
    if any(
        k in lowered
        for k in [
            "payment",
            "consult",
            "fee",
            "video",
            "prescription",
            "renewal",
            "online",
            "appointment",
        ]
    ):
        PAYMENT_STATE[sender] = {"status": "awaiting_screenshot"}
        instructions = _payment_instructions_text()
        background_tasks.add_task(send_whatsapp_text, sender, instructions)
        return {"success": True}

    # Screenshot (keyword or image attachment)
    if state["status"] == "awaiting_screenshot":
        if mtype == "image" or any(
            k in lowered for k in ["screenshot", "receipt", "paid", "payment done"]
        ):
            PAYMENT_STATE[sender] = {"status": "awaiting_reference"}
            background_tasks.add_task(
                send_whatsapp_text,
                sender,
                "✅ Received. Please send your *bank transaction reference ID* (digits/code from receipt).",
            )
            return {"success": True}

    if state["status"] == "awaiting_reference":
        if text and _contains_reference_id(text):
            PAYMENT_STATE[sender] = {
                "status": "pending_manual_verification",
                "reference_text": text,
            }
            background_tasks.add_task(
                send_whatsapp_text,
                sender,
                "⏳ Reference received. Payment verification in progress.",
            )
            background_tasks.add_task(
                maybe_alert_doctor,
                sender,
                f"Payment pending verify.\nReference: {text}\nApprove via API /payment/approve",
            )
            return {"success": True}
        background_tasks.add_task(
            send_whatsapp_text,
            sender,
            "Please send a valid *transaction reference ID* (usually 6+ characters).",
        )
        return {"success": True}

    return {"success": True}


@app.post("/payment/approve")
async def approve_payment(
    decision: PaymentDecision,
    _auth: None = Depends(require_admin),
):
    state = PAYMENT_STATE.get(decision.sender)
    if not state:
        raise HTTPException(status_code=404, detail="Sender state not found")
    if state.get("status") != "pending_manual_verification":
        raise HTTPException(status_code=400, detail="Payment is not pending manual verification")

    PAYMENT_STATE[decision.sender] = {
        **state,
        "status": "approved",
        "doctor_note": decision.note,
    }
    await send_whatsapp_text(
        decision.sender,
        "✅ Payment verified. Please send your name, age, and brief problem — we will confirm next steps.",
    )
    return {
        "ok": True,
        "action": "notify_patient_approved",
        "sender": decision.sender,
        "new_state": "approved",
    }


@app.post("/payment/reject")
async def reject_payment(
    decision: PaymentDecision,
    _auth: None = Depends(require_admin),
):
    state = PAYMENT_STATE.get(decision.sender)
    if not state:
        raise HTTPException(status_code=404, detail="Sender state not found")
    if state.get("status") != "pending_manual_verification":
        raise HTTPException(status_code=400, detail="Payment is not pending manual verification")

    PAYMENT_STATE[decision.sender] = {
        **state,
        "status": "rejected",
        "doctor_note": decision.note,
    }
    await send_whatsapp_text(
        decision.sender,
        "❌ Payment could not be verified. Please check your transaction or contact clinic.",
    )
    return {
        "ok": True,
        "action": "notify_patient_rejected",
        "sender": decision.sender,
        "new_state": "rejected",
    }


@app.get("/payment/state/{sender}")
def payment_state(
    sender: str,
    _auth: None = Depends(require_admin),
):
    state = PAYMENT_STATE.get(sender)
    if not state:
        raise HTTPException(status_code=404, detail="Sender state not found")
    return {"ok": True, "sender": sender, "state": state}


@app.get("/payment/states")
def payment_states(_auth: None = Depends(require_admin)):
    return {"ok": True, "states": PAYMENT_STATE}
