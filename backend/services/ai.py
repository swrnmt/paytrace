import os
import json
from dotenv import load_dotenv

load_dotenv(override=True)

from groq import Groq

client = Groq(api_key=os.getenv("GROQ_API_KEY"))


def generate_summary(context: dict, incident_title: str) -> dict:
    # Build a prompt that gives the AI the context data
    # and tells it exactly what JSON to return
    prompt = f"""
You are an expert fintech operations analyst.
Analyze this payment incident and return a JSON summary.

Incident: {incident_title}

Context Data:
- Timeline: started at {context['timeline']['started_at']}, duration {context['timeline']['duration_minutes']} minutes, worsening: {context['timeline']['is_worsening']}
- Blast Radius: {context['blast_radius']['affected_merchants']} merchants affected, {context['blast_radius']['total_failed_transactions']} failed transactions, {context['blast_radius']['failure_rate_percent']}% failure rate
- Failure Location: PSP={context['failure_location']['psp']}, Bank={context['failure_location']['bank']}, Rail={context['failure_location']['payment_rail']}
- Historical Pattern: {context['historical_pattern']['similar_incidents_last_30d']} similar incidents in last 30 days, recurring={context['historical_pattern']['recurring']}

Return ONLY this JSON structure, nothing else:
{{
    "incident_overview": "2-3 sentence summary of what is happening",
    "suspected_root_cause": "most likely cause based on the data",
    "blast_radius": {{
        "affected_merchants": {context['blast_radius']['affected_merchants']},
        "affected_psp": "{context['failure_location']['psp']}",
        "affected_bank": "{context['failure_location']['bank']}"
    }},
    "severity_assessment": "why this severity level is appropriate",
    "recommended_actions": ["action 1", "action 2", "action 3"],
    "confidence_score": 0.0
}}
"""

    try:
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
            # This tells Groq to return JSON — enforces structured output
            response_format={"type": "json_object"},
        )

        raw = response.choices[0].message.content
        parsed = json.loads(raw)

        # Validate the keys we need are actually there
        # If Groq returns something malformed, we fall back to a safe default
        required_keys = ["incident_overview", "suspected_root_cause", "blast_radius", "severity_assessment", "recommended_actions", "confidence_score"]
        for key in required_keys:
            if key not in parsed:
                raise ValueError(f"Missing key in AI response: {key}")

        return parsed

    except Exception as e:
        # If anything goes wrong with the AI, return a deterministic fallback
        # The frontend should never crash just because Groq is down
        print(f"AI summary failed: {e}")
        return fallback_summary(context, incident_title)


def fallback_summary(context: dict, incident_title: str) -> dict:
    # Built purely from the context data — no AI needed
    # This is what gets returned if Groq is down or returns garbage
    return {
        "incident_overview": f"Incident detected: {incident_title}. {context['blast_radius']['total_failed_transactions']} transactions failed across {context['blast_radius']['affected_merchants']} merchants.",
        "suspected_root_cause": f"Elevated failure rate on {context['failure_location']['psp'] or context['failure_location']['bank']}.",
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
        "confidence_score": 0.0,
    }