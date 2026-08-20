"""
Webhook Integration Service
---------------------------
FastAPI service that:
  1. Receives a Stripe-like payment_intent.succeeded webhook
  2. Verifies the HMAC-SHA256 signature (Stripe webhook signature style)
  3. Formats and POST-forwards to a Slack-like endpoint
  4. Retries failed forwarding up to 3 times with exponential back-off

Test with:  python test_send.py  (or see README for curl example)
"""

import hashlib, hmac, json, logging, os, time
import httpx
from fastapi import FastAPI, Request, HTTPException, status
from fastapi.responses import JSONResponse

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

app = FastAPI(title="Payment Webhook Bridge", version="0.1.0")

# ── Config (env or demo defaults) ─────────────────────────────────────────────
WEBHOOK_SECRET  = os.getenv("WEBHOOK_SECRET", "whsec_demo_secret_1234567890abcdef")
SLACK_WEBHOOK   = os.getenv("SLACK_WEBHOOK_URL", "https://httpbin.org/post")  # mock target
MAX_RETRIES     = 3
RETRY_BASE_S    = 1.0   # seconds, doubled each attempt

# ── Signature verification ─────────────────────────────────────────────────────

def verify_stripe_signature(payload: bytes, sig_header: str, secret: str) -> bool:
    """
    Stripe sends: Stripe-Signature: t=<timestamp>,v1=<hmac>
    We recompute HMAC-SHA256(secret, f"{t}.{payload}") and compare.
    """
    try:
        parts = {k: v for k, v in (p.split("=", 1) for p in sig_header.split(","))}
        timestamp = parts["t"]
        expected  = parts["v1"]
    except (KeyError, ValueError):
        return False

    signed_payload = f"{timestamp}.".encode() + payload
    mac = hmac.new(secret.encode(), signed_payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(mac, expected)

# ── Slack forwarding with retry ────────────────────────────────────────────────

def build_slack_message(event: dict) -> dict:
    pi = event.get("data", {}).get("object", {})
    amount  = pi.get("amount", 0) / 100
    ccy     = pi.get("currency", "usd").upper()
    cust_id = pi.get("customer", "cus_unknown")
    pi_id   = pi.get("id", "pi_unknown")
    return {
        "text": f":white_check_mark: *Payment succeeded* — `{pi_id}`",
        "blocks": [
            {"type": "section", "text": {"type": "mrkdwn",
                "text": f":white_check_mark: *Payment succeeded*\n"
                        f"• Amount: *{ccy} {amount:.2f}*\n"
                        f"• Customer: `{cust_id}`\n"
                        f"• PaymentIntent: `{pi_id}`"}},
        ]
    }

def post_to_slack(message: dict) -> bool:
    delay = RETRY_BASE_S
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = httpx.post(SLACK_WEBHOOK, json=message, timeout=5)
            if r.status_code < 300:
                log.info("Forwarded to Slack (attempt %d): HTTP %d", attempt, r.status_code)
                return True
            log.warning("Slack returned %d on attempt %d", r.status_code, attempt)
        except httpx.RequestError as exc:
            log.warning("Network error on attempt %d: %s", attempt, exc)
        if attempt < MAX_RETRIES:
            time.sleep(delay)
            delay *= 2
    log.error("All %d forwarding attempts failed.", MAX_RETRIES)
    return False

# ── Endpoint ───────────────────────────────────────────────────────────────────

@app.post("/webhook/stripe", status_code=status.HTTP_200_OK)
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig     = request.headers.get("Stripe-Signature", "")

    if not verify_stripe_signature(payload, sig, WEBHOOK_SECRET):
        log.warning("Invalid Stripe-Signature received.")
        raise HTTPException(status_code=400, detail="Invalid signature")

    try:
        event = json.loads(payload)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Malformed JSON")

    event_type = event.get("type", "")
    log.info("Received event: %s", event_type)

    if event_type == "payment_intent.succeeded":
        message = build_slack_message(event)
        success = post_to_slack(message)
        return JSONResponse({"ok": success, "forwarded": success})

    # Acknowledge other events without action
    return JSONResponse({"ok": True, "forwarded": False, "note": f"Unhandled event type: {event_type}"})


@app.get("/health")
def health():
    return {"ok": True}
