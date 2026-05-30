import os
import json
from dotenv import load_dotenv

load_dotenv(override=True)

from groq import Groq

client = Groq(api_key=os.getenv("GROQ_API_KEY"))


def generate_summary(context: dict, incident_title: str) -> dict:
    prompt = f"""You are the incident explanation engine for PayTrace.
Your job is NOT to diagnose incidents, infer infrastructure conditions, or invent causes.
You MUST only explain the structured investigation context provided.

STRICT RULES:
1. Never state root causes as facts unless explicitly present in the context.
2. Never infer internal conditions (server overload, latency spikes, bad configuration, infra failures, database issues, etc.) unless directly supported by provided fields.
3. Separate observations from hypotheses.
4. If evidence is missing, explicitly say that the information is unavailable.
5. Recommendations must be operationally safe and based only on available context.
6. Confidence should decrease when context is incomplete.
7. Never use phrases like "is causing", "root cause is", "due to infrastructure issues" unless supported by evidence.

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

Return output in EXACTLY this JSON structure, nothing else:
{{
    "incident_overview": "Only confirmed facts. No inferences.",
    "suspected_root_cause": "Use may indicate or could suggest language only. If insufficient evidence say: Available incident context is insufficient to determine root cause.",
    "blast_radius": {{
        "affected_merchants": {context['blast_radius']['affected_merchants']},
        "affected_psp": "{context['failure_location']['psp']}",
        "affected_bank": "{context['failure_location']['bank']}"
    }},
    "severity_assessment": "Based only on failure rate and affected merchant count.",
    "recommended_actions": ["Investigation actions only. No implementation changes without evidence."],
    "confidence_score": 0.0
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
    return {
        "incident_overview": f"Incident detected: {incident_title}. {context['blast_radius']['total_failed_transactions']} transactions failed across {context['blast_radius']['affected_merchants']} merchants.",
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
        "confidence_score": 0.0,
    }