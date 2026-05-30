import os
from dotenv import load_dotenv

load_dotenv(override=True)

from groq import Groq
from sqlalchemy.orm import Session
from models import Incident, IncidentChatHistory, Transaction, Merchant

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

SYSTEM_PROMPT = """You are PayTrace AI.
Your job is to explain pre-computed incident context.
You are NOT an investigator. You do NOT compute metrics. You do NOT infer infrastructure conditions.
You only explain already-computed operational context.

SOURCE OF TRUTH:
All values in incident context are authoritative. Never recount. Never recompute. Never aggregate independently.
Dashboard values always override anything derivable from raw records.

FACT VS INTERPRETATION:
Always separate:
1. Observed Facts: only values explicitly present in context
2. Interpretation: possible meaning only, never presented as facts
3. Unknown Information: explicitly state missing evidence
4. Actions: investigation actions only

ROOT CAUSE RULES:
Never invent root causes.
Forbidden unless explicitly in context: server overload, infrastructure failure, database issue, latency spike, configuration error, timeout reason, network failure.
Do NOT restate incident labels as conclusions.
Bad: "PSP_TIMEOUT caused the outage"
Good: "Observed failures are concentrated on this payment path. Operational validation is required."

CHAT RULES:
Never derive: top merchants, most impacted, rankings, comparisons, trends, percentages, counts, priorities unless explicitly supplied.
If user requests unavailable analysis respond:
"The current incident context does not contain this computation."
Then specify what data would be required.

WHEN USER ASKS "Who is impacted?":
Return ONLY: affected merchant count, transaction impact, failure location.
Do not enumerate merchants unless merchant list is explicitly provided in context.
If merchant list exists: display exactly as supplied, do not reorder or rank.

If information is not in context say:
"That information is not available in the current incident data."

Be concise. Be operationally credible. Never hallucinate."""


def build_context_packet(db: Session, incident: Incident) -> str:
    txns = (
        db.query(Transaction)
        .filter(Transaction.incident_id == incident.id)
        .limit(20)
        .all()
    )

    txn_lines = []
    for t in txns:
        txn_lines.append(
            f"- txn {str(t.id)[:8]}: status={t.status}, latency={t.latency_ms}ms, amount={t.amount}"
        )

    merchant_ids = list(set(t.merchant_id for t in txns))
    merchants = db.query(Merchant).filter(Merchant.id.in_(merchant_ids)).all()
    merchant_names = [m.name for m in merchants]

    context = f"""
INCIDENT: {incident.title}
Severity: {incident.severity}
Status: {incident.status}
Started: {incident.started_at.isoformat()}
PSP: {incident.psp.name if incident.psp else 'N/A'}
Bank: {incident.bank.name if incident.bank else 'N/A'}

AFFECTED MERCHANTS ({len(merchant_names)} total):
{', '.join(merchant_names) if merchant_names else 'No merchant data available for this incident yet.'}

SAMPLE TRANSACTIONS ({len(txns)} shown):
{chr(10).join(txn_lines) if txn_lines else 'No transaction data available for this incident yet.'}
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
            "content": "Understood. I have the incident context and will answer only based on this data. I will not recompute, recount, or infer anything not explicitly present."
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