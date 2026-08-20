"""
Ticket Triage Agent
-------------------
Multi-step agentic pipeline:
  Step 1 — Classify: categorise + severity via few-shot prompt (Claude API)
  Step 2 — Decide:   route based on classification result
  Step 3 — Act:      escalate urgent tickets to mock escalation log;
                     routine tickets get an auto-reply draft

Set ANTHROPIC_API_KEY in your environment before running.
"""

import json, logging, os, datetime, pathlib
from anthropic import Anthropic

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

client    = Anthropic()
MODEL     = "claude-haiku-4-5-20251001"   # fast + cheap for triage
ESC_LOG   = pathlib.Path("escalation_log.jsonl")
DRAFT_LOG = pathlib.Path("auto_replies.jsonl")

# ── Few-shot classification prompt ────────────────────────────────────────────

SYSTEM_CLASSIFY = """\
You are a support ticket triage assistant for a B2B SaaS product.
Classify each ticket into exactly one category and one urgency level.

Categories: billing | technical | account | feature_request | other
Urgency:    urgent | high | medium | low

Rules:
- urgent = service down, data loss, security incident, payment blocked
- high   = significant feature broken, close to SLA breach
- medium = degraded performance, workaround exists
- low    = general question, feature request, cosmetic issue

Respond ONLY with valid JSON: {"category": "...", "urgency": "...", "reason": "..."}
No other text.

Examples:
---
Ticket: "We cannot log in at all — our entire team is locked out since 09:00."
{"category": "technical", "urgency": "urgent", "reason": "Full service outage for entire team."}
---
Ticket: "Our invoice from last month shows the wrong amount, please correct."
{"category": "billing", "urgency": "high", "reason": "Incorrect charge requiring correction."}
---
Ticket: "Would love a dark mode option in the dashboard."
{"category": "feature_request", "urgency": "low", "reason": "UI enhancement request, no business impact."}
---
"""

def classify_ticket(subject: str, body: str) -> dict:
    """Step 1: Call Claude to classify the ticket."""
    user_msg = f"Ticket subject: {subject}\n\nTicket body:\n{body}"
    log.info("Step 1 — Classifying ticket: %s", subject[:60])
    response = client.messages.create(
        model=MODEL,
        max_tokens=256,
        system=SYSTEM_CLASSIFY,
        messages=[{"role": "user", "content": user_msg}],
    )
    raw = response.content[0].text.strip()
    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        log.warning("Bad JSON from model, falling back. Raw: %s", raw)
        result = {"category": "other", "urgency": "medium", "reason": "Parse error"}
    log.info("  → category=%s  urgency=%s", result.get("category"), result.get("urgency"))
    return result

def decide(ticket: dict, classification: dict) -> str:
    """Step 2: Route decision based on classification."""
    urgency = classification.get("urgency", "medium")
    if urgency == "urgent":
        return "escalate"
    if urgency == "high":
        return "escalate"
    return "auto_reply"

def escalate(ticket: dict, classification: dict) -> None:
    """Step 3a: Log urgent/high tickets to escalation log."""
    record = {
        "ts":           datetime.datetime.utcnow().isoformat() + "Z",
        "ticket_id":    ticket["id"],
        "subject":      ticket["subject"],
        "urgency":      classification["urgency"],
        "category":     classification["category"],
        "reason":       classification["reason"],
        "assigned_to":  "on-call-engineer",
        "action":       "ESCALATED",
    }
    with open(ESC_LOG, "a") as f:
        f.write(json.dumps(record) + "\n")
    log.warning("ESCALATED  ticket_id=%s  urgency=%s  → on-call-engineer",
                ticket["id"], classification["urgency"])

def auto_reply(ticket: dict, classification: dict) -> None:
    """Step 3b: Draft a canned reply for routine tickets."""
    templates = {
        "billing":          "Thank you for reaching out. Our billing team will review your account within 1 business day.",
        "feature_request":  "Thanks for the suggestion! We've logged your request in our product backlog.",
        "technical":        "We've received your report. Our support team will investigate and follow up within 4 hours.",
        "account":          "Thanks for contacting us. We'll verify your account details and respond within 2 hours.",
        "other":            "Thank you for writing in. A support agent will respond shortly.",
    }
    category = classification.get("category", "other")
    draft = templates.get(category, templates["other"])
    record = {
        "ts":        datetime.datetime.utcnow().isoformat() + "Z",
        "ticket_id": ticket["id"],
        "subject":   ticket["subject"],
        "category":  category,
        "urgency":   classification["urgency"],
        "draft":     draft,
        "action":    "AUTO_REPLY_DRAFTED",
    }
    with open(DRAFT_LOG, "a") as f:
        f.write(json.dumps(record) + "\n")
    log.info("AUTO_REPLY  ticket_id=%s  category=%s", ticket["id"], category)

def process_ticket(ticket: dict) -> dict:
    """Full pipeline: classify → decide → act."""
    classification = classify_ticket(ticket["subject"], ticket["body"])
    action         = decide(ticket, classification)
    if action == "escalate":
        escalate(ticket, classification)
    else:
        auto_reply(ticket, classification)
    return {"ticket_id": ticket["id"], "classification": classification, "action": action}

# ── Sample tickets ─────────────────────────────────────────────────────────────

TICKETS = [
    {
        "id": "TKT-001",
        "subject": "URGENT: Cannot access the platform — all users locked out",
        "body": "Since 08:45 this morning none of our 40 users can log in. We get a 503 error. "
                "This is blocking our entire operations team.",
    },
    {
        "id": "TKT-002",
        "subject": "Invoice #INV-2024-089 overcharged by $400",
        "body": "We were billed $1,400 but our contract clearly states $1,000/month. "
                "Please issue a corrected invoice and refund.",
    },
    {
        "id": "TKT-003",
        "subject": "Feature request: CSV export for the analytics dashboard",
        "body": "It would be very helpful to export the analytics table to CSV. "
                "Currently we have to copy-paste manually.",
    },
    {
        "id": "TKT-004",
        "subject": "Search results slow — taking 8–12 seconds",
        "body": "Search has been noticeably slower over the last two days. "
                "It used to respond under 2 seconds. Not blocking but frustrating.",
    },
    {
        "id": "TKT-005",
        "subject": "Possible data breach — unexpected login from unknown IP",
        "body": "Our admin account shows a login from 185.x.x.x at 03:12 UTC. "
                "We did not authorise this. Please investigate immediately and lock the account.",
    },
]

if __name__ == "__main__":
    print(f"\nProcessing {len(TICKETS)} tickets...\n{'─'*60}")
    results = []
    for t in TICKETS:
        r = process_ticket(t)
        results.append(r)
        print()

    print(f"{'─'*60}")
    print(f"Done. Escalated: {sum(1 for r in results if r['action']=='escalate')}  "
          f"Auto-replied: {sum(1 for r in results if r['action']=='auto_reply')}")
    print(f"Logs: {ESC_LOG}  |  {DRAFT_LOG}")
