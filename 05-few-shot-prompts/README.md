# 05 — Few-Shot Prompt Example Collection

**What it does:** A curated reference of three production-relevant few-shot prompting patterns, each with:
- The full prompt template (copy-paste ready)
- A concrete input/output pair showing the model's response
- An explanation of *why* the few-shot examples are designed the way they are (not just what they do)

## Covered patterns

| # | Use case | Key insight |
|---|---|---|
| 1 | Sentiment + intent classification | Labelled examples fix label taxonomy and enforce JSON schema without fine-tuning |
| 2 | Entity extraction from job postings | Showing `null` in examples teaches the model correct null-handling vs empty strings |
| 3 | SQL generation with schema context | One CTE-pattern example teaches multi-step reasoning by demonstration |

## How to use

Open `few_shot_examples.md` — each section is self-contained. Copy the prompt template, substitute `{placeholder}` values, and call your preferred LLM API.

## No code dependencies

This is a markdown reference document — no Python, no API keys required to read. The prompts are designed for the Anthropic Claude API but are provider-agnostic in structure.
