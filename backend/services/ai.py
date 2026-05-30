import os
import json
from dotenv import load_dotenv

load_dotenv(override=True)

from groq import Groq

client = Groq(api_key=os.getenv("GROQ_API_KEY"))


def calculate_confidence(context: dict) -> int:
    score = 0
    if context['failure_location']['psp'] or context['failure_location']['bank']:
        score += 25
    if context['historical_pattern']['similar_incidents_last_30d'] > 0:
        score += 20
    if context['blast_radius']['failure_rate_percent'] > 80:
        score += 20
    if context['timeline']['is_worsening']:
        score += 15
    if context['historical_pattern']['recurring']:
        score += 20
    return min(score, 90)


def generate_summary(context: dict, incident_title: str) -> dict:
    confidence = calculate_confidence(context)

    if confidence >= 80:
        root_cause_instruction = "Root Cause Status: Evidence supports: [use careful language, avoid certainty, no 'caused by' or 'due to']"
    elif confidence >= 30:
        root_cause_instruction = "Root Cause Status: Available evidence suggests: [use only: may indicate / could suggest / requires validation / appears consistent with]"
    else:
        root_cause_instruction = "Root Cause Status: Insufficient evidence to determine probable cause."

    prompt = f"""You are PayTrace AI.
Your job is to explain pre-computed incident context.
You are NOT an investigator. You do NOT compute metrics. You do NOT infer infrastructure conditions.
You only explain already-computed operational context.

SOURCE OF TRUTH:
All values in incident context are authoritative. Never recount. Never recompute.
If context says affected_merchants = {context['blast_radius']['affected_merchants']}, always return exactly {context['blast_radius']['affected_merchants']} merchants. Never derive a different number.

FACT VS INTERPRETATION:
Separate all statements into:
1. Observed Facts: only values explicitly present in context
2. Interpretation: explain possible meaning, never present hypotheses as facts
3. Unknown Information: explicitly state missing evidence
4. Actions: investigation actions only

ROOT CAUSE RULES:
Never invent root causes.
Forbidden unless explicitly in context: server overload, infrastructure failure, database issue, latency spike, configuration error, timeout reason, network failure.
Do NOT restate incident labels as conclusions.
Bad: "PSP_TIMEOUT caused the outage"
Good: "Observed failures are concentrated on the {context['failure_location']['psp'] or context['failure_location']['bank']} payment path. Incident metadata classifies this as the reported failure type. Operational validation is required."

CONFIDENCE: {confidence}/100
{root_cause_instruction}

INCIDENT CONTEXT:
- Incident: {incident_title}
- Started: {context['timeline']['started_at']}
- Duration: {context['timeline']['duration_minutes']} minutes
- Worsening: {context['timeline']['is_worsening']}
- Affected merchants: {context['blast_radius']['affected_merchants']}
- Failed transactions: {context['blast_radius']['total_failed_transactions']}
- Failure rate: {context['blast_radius']['failure_rate_percent']}%
- PSP: {context['failure_location']['psp']}
- Bank: {context['failure_location']['bank']}
- Payment rail: {context['failure_location']['payment_rail']}
- Similar incidents last 30d: {context['historical_pattern']['similar_incidents_last_30d']}
- Recurring: {context['historical_pattern']['recurring']}
- Last occurrence: {context['historical_pattern']['last_occurrence']}

Return EXACTLY this JSON, nothing else:
{{
    "incident_overview": "Confirmed facts only. No inferences. No restatement of incident labels as conclusions.",
    "suspected_root_cause": "{root_cause_instruction}",
    "blast_radius": {{
        "affected_merchants": {context['blast_radius']['affected_merchants']},
        "affected_psp": "{context['failure_location']['psp']}",
        "affected_bank": "{context['failure_location']['bank']}"
    }},
    "severity_assessment": "Based only on failure rate and merchant count from context.",
    "recommended_actions": ["Investigation actions only. No implementation changes without evidence."],
    "confidence_score": {confidence / 100}
}}"""

    try:
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
        )

        raw = response.choices[0].message.content
        parsed = json.loads(raw)

        required_keys = [
            "incident_overview",
            "suspected_root_cause",
            "blast_radius",
            "severity_assessment",
            "recommended_actions",
            "confidence_score",
        ]
        for key in required_keys:
            if key not in parsed:
                raise ValueError(f"Missing key in AI response: {key}")

        return parsed

    except Exception as e:
        print(f"AI summary failed: {e}")
        return fallback_summary(context, incident_title)


def fallback_summary(context: dict, incident_title: str) -> dict:
    confidence = calculate_confidence(context)
    return {
        "incident_overview": f"{incident_title}. {context['blast_radius']['total_failed_transactions']} transactions failed across {context['blast_radius']['affected_merchants']} merchants.",
        "suspected_root_cause": "Insufficient evidence to determine probable cause.",
        "blast_radius": {
            "affected_merchants": context['blast_radius']['affected_merchants'],
            "affected_psp": context['failure_location']['psp'],
            "affected_bank": context['failure_location']['bank'],
        },
        "severity_assessment": "Assess manually — AI summary unavailable.",
        "recommended_actions": [
            "Check PSP dashboard for alerts",
            "Review recent transaction failure logs",
            "Contact PSP support if issue persists",
        ],
        "confidence_score": confidence / 100,
    }