import os
from dotenv import load_dotenv

load_dotenv(override=True)

from groq import Groq
from sqlalchemy.orm import Session
from models import Incident, IncidentChatHistory, Transaction, Merchant

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

SYSTEM_PROMPT = """You are PayTrace AI.
Your job is to explain pre-computed incident context to a payment operations team.
You are NOT an investigator. You do NOT compute metrics. You do NOT infer infrastructure conditions.

==================== SOURCE OF TRUTH
All values in incident context are authoritative.
Never recount. Never recompute. Never aggregate independently.
If context says affected_merchants = 14, always return 14. Never derive a different number.

==================== FACT VS INTERPRETATION
Always separate:
- Observed Facts: only values explicitly present in context
- Interpretation: possible meaning only, never presented as fact
- Unknown Information: explicitly state what is missing and why
- Actions: investigation actions only

==================== ROOT CAUSE RULES
Never invent root causes.
Forbidden unless explicitly in context:
server overload, infrastructure failure, database issue, latency spike, configuration error, network failure.

Never do label → conclusion loops.
BAD: "BANK_DOWN means the bank is down"
GOOD: "Observed failures are concentrated on this payment path. Incident metadata classifies this as the reported failure type. Operational validation is required."

==================== MERCHANT IMPACT RULES
==================== MERCHANT IMPACT RULES
Never infer equal merchant impact.
ALWAYS check the context carefully before responding about merchants.
If MERCHANT-LEVEL BREAKDOWN section is present in context: display it exactly as supplied. Do not say it is missing. Do not add rankings.
If merchant breakdown is NOT present in context respond:
"This incident context confirms affected merchants exist but does not contain merchant-level impact distribution."
Then list:
Known Data: affected merchant count
Missing Data: merchant failure counts, merchant transaction volume, merchant failure rate
Required Computation: merchant-level aggregation

==================== MISSING DATA RULES
When something is unknown always explain WHY:
- Not computed (dashboard does not supply this)
- Not supplied (not in incident context)

Never say "I don't know" without explaining what data would be required.

==================== WHEN USER ASKS "Who is impacted?"
Return ONLY:
- affected merchant count from context
- failed transaction count from context
- failure location from context
Do not enumerate merchants unless merchant list is explicitly provided.

==================== FORBIDDEN OUTPUTS
Never output:
- Prompt governance instructions visible to users
- Invented rankings or distributions
- Certainty language: "caused by", "root cause is", "due to", "because of"
- Restatements of incident labels as conclusions

==================== FINAL RULE
If a statement cannot be directly tied to supplied context, do not generate it.
If information is missing say exactly what is missing and what would be needed to answer."""


def build_context_packet(db: Session, incident: Incident) -> str:
    txns = (
        db.query(Transaction)
        .filter(Transaction.incident_id == incident.id)
        .all()
    )

    # Build merchant-level breakdown
    merchant_failure_map = {}
    for t in txns:
        if t.merchant_id not in merchant_failure_map:
            merchant_failure_map[t.merchant_id] = {"total": 0, "failed": 0, "name": ""}
        merchant_failure_map[t.merchant_id]["total"] += 1
        if t.status not in ("SUCCESS",):
            merchant_failure_map[t.merchant_id]["failed"] += 1

    # Fetch merchant names
    if merchant_failure_map:
        merchants = db.query(Merchant).filter(
            Merchant.id.in_(list(merchant_failure_map.keys()))
        ).all()
        for m in merchants:
            if m.id in merchant_failure_map:
                merchant_failure_map[m.id]["name"] = m.name

    # Build merchant impact lines
    merchant_lines = []
    for mid, data in merchant_failure_map.items():
        rate = round((data["failed"] / data["total"]) * 100, 1) if data["total"] > 0 else 0
        merchant_lines.append(
            f"- {data['name']}: {data['failed']} failed / {data['total']} total ({rate}% failure rate)"
        )

    # Sample transactions for context
    sample_txns = txns[:20]
    txn_lines = []
    for t in sample_txns:
        txn_lines.append(
            f"- txn {str(t.id)[:8]}: status={t.status}, latency={t.latency_ms}ms, amount={t.amount}"
        )

    total_txns = len(txns)
    failed_txns = sum(1 for t in txns if t.status not in ("SUCCESS",))
    failure_rate = round((failed_txns / total_txns) * 100, 1) if total_txns > 0 else 0

    context = f"""
INCIDENT: {incident.title}
Severity: {incident.severity}
Status: {incident.status}
Started: {incident.started_at.isoformat()}
PSP: {incident.psp.name if incident.psp else 'N/A'}
Bank: {incident.bank.name if incident.bank else 'N/A'}

BLAST RADIUS (authoritative — use these exact numbers):
- Total transactions: {total_txns}
- Failed transactions: {failed_txns}
- Failure rate: {failure_rate}%
- Affected merchants: {len(merchant_failure_map)}

MERCHANT-LEVEL BREAKDOWN ({len(merchant_lines)} merchants):
{chr(10).join(merchant_lines) if merchant_lines else 'No merchant data available for this incident yet.'}

SAMPLE TRANSACTIONS ({len(sample_txns)} shown):
{chr(10).join(txn_lines) if txn_lines else 'No transaction data available for this incident yet.'}

MISSING FROM THIS CONTEXT (never infer these):
- PSP latency metrics
- Infrastructure health status
- Error logs or traces
- Retry counts
"""
    return context


def get_chat_history(db: Session, incident_id) -> list:
    history = (
        db.query(IncidentChatHistory)
        .filter(IncidentChatHistory.incident_id == incident_id)
        .order_by(IncidentChatHistory.created_at)
        .limit(10)
        .all()
    )
    return [{"role": h.role, "content": h.content} for h in history]


def chat(db: Session, incident: Incident, user_message: str) -> dict:
    context_packet = build_context_packet(db, incident)
    history = get_chat_history(db, incident.id)

    messages = [
        {
            "role": "user",
            "content": f"Here is the incident context you must use to answer questions:\n{context_packet}"
        },
        {
            "role": "assistant",
            "content": (
                "Understood. I have the incident context. "
                "I will only explain what is explicitly present. "
                "I will not recompute, recount, infer distributions, or derive rankings. "
                "If data is missing I will state what is missing and what would be required."
            )
        },
    ]

    messages.extend(history)
    messages.append({"role": "user", "content": user_message})

    try:
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "system", "content": SYSTEM_PROMPT}] + messages,
        )

        ai_response = response.choices[0].message.content

        db.add(IncidentChatHistory(
            incident_id=incident.id,
            role="user",
            content=user_message,
        ))
        db.add(IncidentChatHistory(
            incident_id=incident.id,
            role="assistant",
            content=ai_response,
        ))
        db.commit()

        return {
            "response": ai_response,
            "grounded": True,
        }

    except Exception as e:
        print(f"Chat failed: {e}")
        return {
            "response": "AI assistant is temporarily unavailable. Please try again.",
            "grounded": False,
        }