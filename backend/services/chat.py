import os
import json
from dotenv import load_dotenv

load_dotenv(override=True)

from groq import Groq
from sqlalchemy.orm import Session
from models import Incident, IncidentChatHistory, Transaction, Merchant

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# This is the system prompt — it tells the AI who it is and what rules to follow
# The key rule: only answer from the provided context, never make things up
SYSTEM_PROMPT = """You are an operational assistant for a fintech incident investigation system.
Answer ONLY using the provided operational context.
If the information is not in the context, say: 'That information is not available in the current incident data.'
Use fintech terminology. Be concise. Be operationally credible."""


def build_context_packet(db: Session, incident: Incident) -> str:
    # Grab the top 20 affected transactions for this incident
    txns = (
        db.query(Transaction)
        .filter(Transaction.incident_id == incident.id)
        .limit(20)
        .all()
    )

    # Summarize each transaction
    txn_lines = []
    for t in txns:
        txn_lines.append(
            f"- txn {str(t.id)[:8]}: status={t.status}, latency={t.latency_ms}ms, amount={t.amount}"
        )

    # Get affected merchants and their failure rates
    merchant_ids = list(set(t.merchant_id for t in txns))
    merchants = db.query(Merchant).filter(Merchant.id.in_(merchant_ids)).all()
    merchant_names = [m.name for m in merchants]

    # Build the full context string we inject into the prompt
    context = f"""
INCIDENT: {incident.title}
Severity: {incident.severity}
Status: {incident.status}
Started: {incident.started_at.isoformat()}
PSP: {incident.psp.name if incident.psp else 'N/A'}
Bank: {incident.bank.name if incident.bank else 'N/A'}

AFFECTED MERCHANTS ({len(merchant_names)} total):
{', '.join(merchant_names)}

SAMPLE TRANSACTIONS ({len(txns)} shown):
{chr(10).join(txn_lines)}
"""
    return context


def get_chat_history(db: Session, incident_id) -> list:
    # Fetch previous messages so the AI remembers the conversation
    history = (
        db.query(IncidentChatHistory)
        .filter(IncidentChatHistory.incident_id == incident_id)
        .order_by(IncidentChatHistory.created_at)
        .limit(10)  # last 10 messages to keep context window small
        .all()
    )
    return [{"role": h.role, "content": h.content} for h in history]


def chat(db: Session, incident: Incident, user_message: str) -> dict:
    # Build the grounded context from real incident data
    context_packet = build_context_packet(db, incident)

    # Get previous messages in this conversation
    history = get_chat_history(db, incident.id)

    # First message always contains the context so the AI knows what it's working with
    messages = [
        {
            "role": "user",
            "content": f"Here is the incident context you must use to answer questions:\n{context_packet}"
        },
        {
            "role": "assistant",
            "content": "Understood. I have the incident context and will answer only based on this data."
        },
    ]

    # Add the conversation history so the AI remembers previous exchanges
    messages.extend(history)

    # Add the new user message
    messages.append({"role": "user", "content": user_message})

    try:
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "system", "content": SYSTEM_PROMPT}] + messages,
        )

        ai_response = response.choices[0].message.content

        # Save both the user message and AI response to the database
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