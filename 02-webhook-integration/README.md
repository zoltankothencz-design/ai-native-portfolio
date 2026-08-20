# 02 — API Webhook Integration

**What it does:** A FastAPI service that acts as a bridge between Stripe and Slack. It receives a `payment_intent.succeeded` webhook, verifies the HMAC-SHA256 signature (Stripe's signature scheme), formats a Slack Block Kit message, and forwards it to a Slack webhook URL — with up to 3 retries and exponential back-off.

## Key techniques

- **HMAC-SHA256 auth** using `hmac.compare_digest` (timing-safe) to verify Stripe-Signature headers.
- **Retry with exponential back-off** (1 s → 2 s → 4 s) for transient network failures.
- Separation of concerns: signature verification, message formatting, and forwarding are distinct functions — each unit-testable in isolation.
- Mock target: defaults to `https://httpbin.org/post` (echoes the payload), swap `SLACK_WEBHOOK_URL` env var to point at a real Slack Incoming Webhook.

## How to run

```bash
cd 02-webhook-integration
pip install -r requirements.txt
uvicorn app:app --reload          # starts on http://localhost:8000

# In another terminal:
python test_send.py               # valid webhook → 200 OK, forwarded: true
python test_send.py --bad-sig     # bad signature → 400, Invalid signature
```

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `WEBHOOK_SECRET` | `whsec_demo_secret_…` | Shared secret for HMAC verification |
| `SLACK_WEBHOOK_URL` | `https://httpbin.org/post` | Target Slack (or mock) webhook URL |
