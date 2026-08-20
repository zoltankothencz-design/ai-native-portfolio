"""
Send a mock payment_intent.succeeded webhook to the local service.
Computes a valid Stripe-style HMAC signature so the service accepts it.

Usage:
    python test_send.py           # valid signature
    python test_send.py --bad-sig # invalid signature (should get 400)
"""

import hashlib, hmac, json, sys, time
import httpx

SECRET  = "whsec_demo_secret_1234567890abcdef"
URL     = "http://localhost:8000/webhook/stripe"

PAYLOAD = {
    "id": "evt_test_001",
    "type": "payment_intent.succeeded",
    "data": {
        "object": {
            "id": "pi_test_abc123",
            "amount": 4900,
            "currency": "usd",
            "customer": "cus_test_xyz789",
            "status": "succeeded",
        }
    }
}

body      = json.dumps(PAYLOAD).encode()
timestamp = str(int(time.time()))
signed    = f"{timestamp}.".encode() + body
mac       = hmac.new(SECRET.encode(), signed, hashlib.sha256).hexdigest()

bad_sig = "--bad-sig" in sys.argv
sig_header = f"t={timestamp},v1={'badbadbadbad' if bad_sig else mac}"

r = httpx.post(URL, content=body, headers={
    "Content-Type": "application/json",
    "Stripe-Signature": sig_header,
})
print(f"HTTP {r.status_code}: {r.text}")
