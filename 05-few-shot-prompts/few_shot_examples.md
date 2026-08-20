# Few-Shot Prompt Examples

A practical reference showing how few-shot prompting improves LLM output quality — with concrete input/output pairs and a brief explanation of why each example set works better than a zero-shot equivalent.

---

## 1 — Sentiment + Intent Classification (Support Tickets)

### Why few-shot wins here

Zero-shot: "Classify this ticket by sentiment and intent" produces inconsistent label names (`Negative` vs `negative` vs `NEGATIVE`), mixes intent concepts (`complaint` vs `refund_request`), and omits confidence.  
Few-shot: three labelled examples fix the label taxonomy, enforce the JSON schema, and anchor the model to business-relevant intent granularity — without a fine-tuned model.

### Prompt

```
System:
Classify the support ticket below. Return ONLY valid JSON:
{"sentiment": "positive|neutral|negative", "intent": "...", "confidence": 0.0–1.0}

Examples:
---
Ticket: "Your dashboard has been down all morning — this is costing us money!"
{"sentiment": "negative", "intent": "outage_report", "confidence": 0.97}
---
Ticket: "How do I export my data to CSV?"
{"sentiment": "neutral", "intent": "how_to_question", "confidence": 0.95}
---
Ticket: "Just wanted to say the new search feature is incredible, great work!"
{"sentiment": "positive", "intent": "compliment", "confidence": 0.99}
---

Ticket: "{ticket_text}"
```

### Sample output

```json
{"sentiment": "negative", "intent": "billing_dispute", "confidence": 0.91}
```

### Key design choices

- **Three examples** covers the full sentiment range and gives the model a clear schema to mirror.
- **Concrete confidence values** in the examples (0.97, 0.95, 0.99) teach the model what "high confidence" looks like — it will produce lower values for ambiguous inputs without being instructed to.
- Separating examples with `---` lines prevents token boundary confusion on some tokenisers.

---

## 2 — Entity Extraction from Unstructured Job Postings

### Why few-shot wins here

Zero-shot extraction from messy HTML-stripped job ads produces wildly inconsistent field names, misses salary ranges embedded in prose, and sometimes invents fields. Two examples are enough to lock in the exact output schema needed for downstream ETL.

### Prompt

```
System:
Extract structured data from the job posting. Return ONLY valid JSON with these fields:
{"title": "...", "company": "...", "location": "...", "salary_min": int|null,
 "salary_max": int|null, "currency": "...", "remote": true|false, "skills": [...]}

Examples:
---
Posting: "Senior Backend Engineer at Acme Corp — London, UK (hybrid). £70,000–£90,000/yr.
Must know: Python, PostgreSQL, AWS. Nice to have: Kafka, Terraform."
{
  "title": "Senior Backend Engineer",
  "company": "Acme Corp",
  "location": "London, UK",
  "salary_min": 70000,
  "salary_max": 90000,
  "currency": "GBP",
  "remote": false,
  "skills": ["Python", "PostgreSQL", "AWS", "Kafka", "Terraform"]
}
---
Posting: "Product Manager (fully remote, anywhere in EU). Startup, Series A.
Competitive salary $90k–$130k USD. Experience with B2B SaaS required."
{
  "title": "Product Manager",
  "company": null,
  "location": "EU (remote)",
  "salary_min": 90000,
  "salary_max": 130000,
  "currency": "USD",
  "remote": true,
  "skills": ["B2B SaaS"]
}
---

Posting: "{raw_posting_text}"
```

### Sample output (for a new unseen posting)

```json
{
  "title": "Data Engineer",
  "company": "TechFlow GmbH",
  "location": "Berlin, Germany",
  "salary_min": 65000,
  "salary_max": 85000,
  "currency": "EUR",
  "remote": false,
  "skills": ["dbt", "Snowflake", "Python", "Airflow"]
}
```

### Key design choices

- **Null handling shown explicitly** — the `"company": null` in example 2 teaches the model to use null (not `""` or `"unknown"`) when the field is genuinely absent.
- **Mixed currency examples** ensure the model doesn't hard-code USD.
- **Skills from both required and nice-to-have** in example 1 teaches inclusive extraction without needing an explicit instruction.

---

## 3 — SQL Query Generation with Schema Context

### Why few-shot wins here

Zero-shot SQL generation produces syntactically valid queries that reference nonexistent columns or use wrong aggregation logic for the business question. One well-chosen example demonstrating the schema + a multi-step CTE pattern steers the model away from flat JOIN mistakes.

### Prompt

```
System:
You are a SQL expert. Write a single SQLite query for the question below.
Use CTEs for multi-step logic. Return ONLY the SQL, no explanation.

Schema:
  users(user_id, signup_date, plan)
  events(event_id, user_id, event_type, event_date)
  subscriptions(sub_id, user_id, status, mrr, start_date, end_date)

Example:
Question: "How many users signed up each month in 2024 and are still on an active subscription?"
SQL:
WITH monthly_signups AS (
    SELECT
        strftime('%Y-%m', signup_date) AS month,
        user_id
    FROM users
    WHERE signup_date BETWEEN '2024-01-01' AND '2024-12-31'
),
active_subs AS (
    SELECT DISTINCT user_id
    FROM subscriptions
    WHERE status = 'active'
)
SELECT
    ms.month,
    COUNT(*) AS active_signups
FROM monthly_signups ms
JOIN active_subs a USING (user_id)
GROUP BY ms.month
ORDER BY ms.month;

Question: "{user_question}"
```

### Sample output (for "What is the MRR breakdown by plan for active subscribers?")

```sql
SELECT
    u.plan,
    COUNT(DISTINCT s.user_id) AS subscriber_count,
    SUM(s.mrr)                AS total_mrr
FROM subscriptions s
JOIN users u USING (user_id)
WHERE s.status = 'active'
GROUP BY u.plan
ORDER BY total_mrr DESC;
```

### Key design choices

- **Full schema in every call** — the model cannot remember schema between requests; repeating it prevents column hallucination.
- **CTE pattern in the example** teaches multi-step reasoning by demonstration, not instruction. The model will apply CTEs unprompted to complex follow-up questions.
- **One well-chosen example beats three mediocre ones** — the example shows `WHERE`, `JOIN`, `GROUP BY`, `CTE`, and date filtering in a single coherent query that mirrors real analytical patterns.

---

## Summary: Zero-shot vs Few-shot

| Scenario | Zero-shot failure mode | Few-shot fix |
|---|---|---|
| Classification | Inconsistent labels, no schema | Examples anchor taxonomy + JSON shape |
| Extraction | Wrong field names, null handling | Explicit nulls + mixed examples |
| SQL generation | Hallucinated columns, bad aggregation | Schema + CTE pattern example |

**Rule of thumb:** add a few-shot example whenever the output must conform to a specific schema, the task involves domain-specific terminology, or zero-shot produces inconsistent formatting. Three examples is usually the sweet spot — enough to establish a pattern, short enough to fit in a shared system prompt across many user turns.
