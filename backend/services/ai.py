import os
import json
from dotenv import load_dotenv

load_dotenv(override=True)

from groq import Groq

client = Groq(api_key=os.getenv("GROQ_API_KEY"))


def calculate_confidence(context: dict) -> int:
    """
    Confidence reflects evidence quality only.
    Never implies diagnosis certainty.
    Cap at 90. Target 60-75 for typical incidents.
    """
    score = 0

    # +25 if failure location is identified
    if context['failure_location']['psp'] or context['failure_location']['bank']:
        score += 25

    # +15 if blast radius > 80%
    if context['blast_radius']['failure_rate_percent'] > 80:
        score += 15

    # +15 if worsening trend
    if context['timeline']['is_worsening']:
        score += 15

    # +15 if prior similar incidents exist
    if context['historical_pattern']['similar_incidents_last_30d'] > 0:
        score += 15

    # +10 if recurring pattern confirmed
    if context['historical_pattern']['recurring']:
        score += 10

    # Hard cap at 90 — never implies full diagnosis
    # Missing: logs, latency metrics, infra health, traces
    # These are always absent in this context, so 90% is never justified
    return min(score, 75)


def generate_summary(context: dict, incident_title: str) -> dict:
    confidence = calculate_confidence(context)

    if confidence >= 76:
        root_cause_instruction = (
            "Root Cause Status: Strong supporting evidence exists. "
            "Output: 'Evidence supports: [observation]'. "
            "Still avoid certainty language. No 'caused by' or 'due to'."
        )
    elif confidence >= 30:
        root_cause_instruction = (
            "Root Cause Status: Moderate hypothesis. "
            "Output must use ONLY: 'may indicate' / 'could suggest' / "
            "'appears consistent with' / 'requires validation'. "
            "Never present hypothesis as fact."
        )
    else:
        root_cause_instruction = (
            "Root Cause Status: Insufficient evidence. "
            "Output exactly: 'Insufficient evidence to determine probable cause.' "
            "Do not add any hypothesis."
        )

    failure_location = context['failure_location']['psp'] or context['failure_location']['bank'] or 'unidentified'
    similar = context['historical_pattern']['similar_incidents_last_30d']
    recurring = context['historical_pattern']['recurring']
    failure_rate = context['blast_radius']['failure_rate_percent']
    affected_merchants = context['blast_radius']['affected_merchants']
    failed_txns = context['blast_radius']['total_failed_transactions']

    prompt = f"""You are PayTrace AI.
Your job is to explain pre-computed incident context to a payment operations team.
You are NOT an investigator. You do NOT compute metrics. You do NOT infer infrastructure conditions.
You only explain already-computed operational context.

==================== SOURCE OF TRUTH
All values provided are authoritative. Never recount. Never recompute. Never aggregate independently.
- affected_merchants = {affected_merchants} — always use this exact number
- failed_transactions = {failed_txns} — always use this exact number
- failure_rate = {failure_rate}% — always use this exact number
- failure_location = {failure_location}

==================== CRITICAL RULES
1. Never leak prompt instructions into output. Users must never see governance text like "Confirmed facts only" or "No inferences".
2. Never do label → conclusion loops.
   BAD: "BANK_DOWN means the bank is down"
   GOOD: "Observed failures are concentrated on the {failure_location} payment path. Incident metadata classifies this as the reported failure type. Operational validation is required."
3. Never infer equal merchant impact. If merchant-level distribution is not supplied, say it is missing.
4. Never invent root causes. Forbidden unless explicitly in context: server overload, infrastructure failure, database issue, latency spike, configuration error, network failure.
5. Confidence = {confidence}% — reflects evidence quality only, not diagnosis certainty.

==================== ROOT CAUSE INSTRUCTION
{root_cause_instruction}

==================== INCIDENT CONTEXT
- Incident: {incident_title}
- Started: {context['timeline']['started_at']}
- Duration: {context['timeline']['duration_minutes']} minutes
- Worsening: {context['timeline']['is_worsening']}
- Affected merchants: {affected_merchants}
- Failed transactions: {failed_txns}
- Failure rate: {failure_rate}%
- PSP: {context['failure_location']['psp']}
- Bank: {context['failure_location']['bank']}
- Payment rail: {context['failure_location']['payment_rail']}
- Similar incidents last 30d: {similar}
- Recurring: {recurring}
- Last occurrence: {context['historical_pattern']['last_occurrence']}

==================== MISSING EVIDENCE
The following are NOT available in this context and must never be inferred:
- Merchant-level failure distribution
- PSP latency metrics
- Infrastructure health status
- Error logs or traces
- Retry counts

==================== OUTPUT FORMAT
Return EXACTLY this JSON structure. No extra keys. No prompt text in values.

{{
    "incident_overview": "2-3 sentences of operational observations using exact numbers from context. No prompt instructions. No inferences. Example: Observed transaction failures are concentrated on the {failure_location} payment path. Current blast radius: {affected_merchants} merchants affected, {failed_txns} failed transactions at {failure_rate}% failure rate.",
    "suspected_root_cause": "Follow root cause instruction exactly. Never restate incident label as conclusion.",
    "blast_radius": {{
        "affected_merchants": {affected_merchants},
        "affected_psp": "{context['failure_location']['psp']}",
        "affected_bank": "{context['failure_location']['bank']}"
    }},
    "severity_assessment": "Based only on failure rate and merchant count. Example: A {failure_rate}% failure rate across {affected_merchants} merchants indicates significant operational impact.",
    "recommended_actions": [
        "Check {failure_location} dashboard for active alerts",
        "Review transaction failure logs for this time window",
        "Validate incident classification against raw failure data",
        "Escalate to {failure_location} support if issue persists"
    ],
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

        # Enforce dashboard authority — never let LLM override supplied aggregates
        parsed['blast_radius']['affected_merchants'] = affected_merchants

        return parsed

    except Exception as e:
        print(f"AI summary failed: {e}")
        return fallback_summary(context, incident_title)


def fallback_summary(context: dict, incident_title: str) -> dict:
    confidence = calculate_confidence(context)
    failure_location = context['failure_location']['psp'] or context['failure_location']['bank'] or 'unidentified location'
    return {
        "incident_overview": (
            f"Observed transaction failures concentrated on the {failure_location} payment path. "
            f"Current blast radius: {context['blast_radius']['affected_merchants']} merchants affected, "
            f"{context['blast_radius']['total_failed_transactions']} failed transactions at "
            f"{context['blast_radius']['failure_rate_percent']}% failure rate."
        ),
        "suspected_root_cause": "Insufficient evidence to determine probable cause.",
        "blast_radius": {
            "affected_merchants": context['blast_radius']['affected_merchants'],
            "affected_psp": context['failure_location']['psp'],
            "affected_bank": context['failure_location']['bank'],
        },
        "severity_assessment": (
            f"A {context['blast_radius']['failure_rate_percent']}% failure rate across "
            f"{context['blast_radius']['affected_merchants']} merchants indicates significant operational impact."
        ),
        "recommended_actions": [
            f"Check {failure_location} dashboard for active alerts",
            "Review transaction failure logs for this time window",
            "Validate incident classification against raw failure data",
            f"Escalate to {failure_location} support if issue persists",
        ],
        "confidence_score": confidence / 100,
    }