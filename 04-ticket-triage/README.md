# 04 — Ticket Triage Agent

**What it does:** A three-step agentic pipeline that processes incoming support tickets:

1. **Classify** — sends the ticket to Claude with a few-shot prompt; gets back `{category, urgency, reason}` as JSON.
2. **Decide** — routes `urgent`/`high` tickets to escalation, `medium`/`low` to auto-reply.
3. **Act** — writes to `escalation_log.jsonl` (urgent) or `auto_replies.jsonl` (routine).

## Key techniques

- **Few-shot prompting** — three labelled examples in the system prompt anchor the model to the output schema and category taxonomy, reducing hallucination on edge cases.
- **Structured JSON output** — the model is instructed to return only valid JSON; a fallback handles rare parse errors without crashing the pipeline.
- **Multi-step agent logic** — classify → decide → act are distinct functions; each step can be unit-tested, logged, or replaced independently.
- **JSONL append-only logs** — deterministic, easy to tail, grep, or stream into a data warehouse.

## How to run

```bash
cd 04-ticket-triage
pip install -r requirements.txt
export ANTHROPIC_API_KEY="sk-ant-..."
python triage_agent.py
# → escalation_log.jsonl, auto_replies.jsonl, console output
```

## Sample output

```
TKT-001  category=technical   urgency=urgent  → ESCALATED (on-call-engineer)
TKT-002  category=billing     urgency=high    → ESCALATED (on-call-engineer)
TKT-003  category=feature_req urgency=low     → AUTO_REPLY_DRAFTED
TKT-004  category=technical   urgency=medium  → AUTO_REPLY_DRAFTED
TKT-005  category=technical   urgency=urgent  → ESCALATED (on-call-engineer)
```
