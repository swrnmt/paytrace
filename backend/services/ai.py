import os
import json
from dotenv import load_dotenv

load_dotenv(override=True)

from groq import Groq

client = Groq(api_key=os.getenv("GROQ_API_KEY"))


def calculate_confidence(context: dict) -> int:
    score = 0

    # +25 if failure location is identified
    if context['failure_location']['psp'] or context['failure_location']['bank']:
        score += 25

    # +20 if recurring pattern exists
    if context['historical_pattern']['recurring']:
        score += 20

    # +20 if blast radius > 80%
    if context['blast_radius']['failure_rate_percent'] > 80:
        score += 20

    # +15 if worsening trend
    if context['timeline']['is_worsening']:
        score += 15

    # +20 if prior similar incidents exist
    if context['historical_pattern']['similar_incidents_last_30d'] > 0:
        score += 20

    return min(score, 90)


def generate_summary(context: dict, incident_title: str) -> dict:
    confidence = calculate_confidence(context)

    if confidence >= 80:
        root_cause_instruction = "Root cause state: CONFIRMED. Output must start with 'Evidence supports:'"
    elif confidence >= 30:
        root_cause_instruction = "Root cause state: HYPOTHESIS. Output must use 'Available evidence suggests...' or 'This may indicate...' and end with 'Requires validation.'"
    else:
        root_cause_instruction = "Root cause state: UNKNOWN. Output must be exactly: 'Available incident context is insufficient to determine root cause.'"

    prompt = f"""You are the incident explanation engine for PayTrace.
Your goal is to explain incident context without inventing facts.

STRICT RULES:
1. Only state information directly present in the provided context.
2. Never infer internal conditions unless explicitly supported by context fields.
3. {root_cause_instruction}
4. Recommendations must be investigation actions only — no implementation changes without evidence.
5. Never use phrases like "is causing", "root cause is", "due to infrastructure issues" unless confidence is CONFIRMED.

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
- Confidence score: {confidence}/100

Return output in EXACTLY this JSON structure, nothing else:
{{
    "incident_overview": "Only confirmed facts from context. No inferences.",
    "suspected_root_cause": "Follow the root cause state instruction above exactly.",
    "blast_radius": {{
        "affected_merchants": {context['blast_radius']['affected_merchants']},
        "affected_psp": "{context['failure_location']['psp']}",
        "affected_bank": "{context['failure_location']['bank']}"
    }},
    "severity_assessment": "Based only on failure rate and affected merchant count from context.",
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
        "suspected_root_cause": "Available incident context is insufficient to determine root cause.",
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