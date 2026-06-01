from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from database import get_db
from models import Incident, IncidentChatHistory
from services.context import get_full_context
from services.ai import generate_summary
from services.chat import chat

router = APIRouter()


class ChatRequest(BaseModel):
    message: str


@router.get("/incidents")
def list_incidents(db: Session = Depends(get_db)):
    incidents = (
        db.query(Incident)
        .order_by(Incident.severity, Incident.created_at.desc())
        .all()
    )

    result = []
    for inc in incidents:
        result.append({
            "id": str(inc.id),
            "title": inc.title,
            "severity": inc.severity,
            "status": inc.status,
            "started_at": inc.started_at.isoformat(),
            "resolved_at": inc.resolved_at.isoformat() if inc.resolved_at else None,
            "psp": inc.psp.name if inc.psp else None,
            "bank": inc.bank.name if inc.bank else None,
        })

    return result


# simulate must be ABOVE /{incident_id} routes or FastAPI treats "simulate" as an ID
@router.post("/incidents/simulate")
def simulate_incident(db: Session = Depends(get_db)):
    import random
    from datetime import datetime, timezone, timedelta
    from models import PSP, Bank, Transaction, IncidentTransaction

    psps = db.query(PSP).all()
    banks = db.query(Bank).all()

    incident_types = [
        ("PSP timeout storm — PSP_TIMEOUT surging", "CRITICAL", "psp"),
        ("Bank outage — BANK_DOWN on majority of transactions", "CRITICAL", "bank"),
        ("Webhook retry storm — top merchants failing delivery", "HIGH", "psp"),
        ("High latency surge — p99 exceeding 2000ms", "HIGH", "psp"),
        ("Merchant degradation — elevated failure rate detected", "MEDIUM", "bank"),
    ]

    title_template, severity, culprit = random.choice(incident_types)
    psp = random.choice(psps)
    bank = random.choice(banks)

    if culprit == "psp":
        title = f"{psp.name} {title_template}"
        psp_id = psp.id
        bank_id = None
        # Grab real transactions for this PSP from the last 7 days
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        txns = (
            db.query(Transaction)
            .filter(
                Transaction.psp_id == psp.id,
                Transaction.created_at >= cutoff,
                Transaction.incident_id == None,
            )
            .limit(40)
            .all()
        )
    else:
        title = f"{bank.name} {title_template}"
        psp_id = None
        bank_id = bank.id
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        txns = (
            db.query(Transaction)
            .filter(
                Transaction.bank_id == bank.id,
                Transaction.created_at >= cutoff,
                Transaction.incident_id == None,
            )
            .limit(40)
            .all()
        )

    # If no transactions in last 7 days, go back 30 days
    if not txns:
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        if culprit == "psp":
            txns = (
                db.query(Transaction)
                .filter(
                    Transaction.psp_id == psp.id,
                    Transaction.incident_id == None,
                )
                .limit(40)
                .all()
            )
        else:
            txns = (
                db.query(Transaction)
                .filter(
                    Transaction.bank_id == bank.id,
                    Transaction.incident_id == None,
                )
                .limit(40)
                .all()
            )

    incident = Incident(
        title=title,
        severity=severity,
        status="OPEN",
        psp_id=psp_id,
        bank_id=bank_id,
        started_at=datetime.now(timezone.utc),
        resolved_at=None,
    )
    db.add(incident)
    db.flush()

    # Degrade a portion of transactions and link them to this incident
    failed_statuses = {
        "PSP timeout storm": "PSP_TIMEOUT",
        "Bank outage": "BANK_DOWN",
        "Webhook retry storm": "WEBHOOK_RETRY",
        "High latency surge": "HIGH_LATENCY",
        "Merchant degradation": "FAILED",
    }

    # Pick the right status based on title
    new_status = "FAILED"
    for key, status in failed_statuses.items():
        if key.lower() in title_template.lower():
            new_status = status
            break

    # Degrade 60-80% of the grabbed transactions
    degrade_rate = random.uniform(0.6, 0.8)
    for txn in txns:
        if random.random() < degrade_rate:
            txn.status = new_status
            txn.incident_id = incident.id
            db.add(IncidentTransaction(
                incident_id=incident.id,
                transaction_id=txn.id,
            ))

    db.commit()

    return {
        "id": str(incident.id),
        "title": incident.title,
        "severity": incident.severity,
        "status": incident.status,
    }

@router.get("/incidents/{incident_id}")
def get_incident(incident_id: str, db: Session = Depends(get_db)):
    incident = db.query(Incident).filter(Incident.id == incident_id).first()

    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    return {
        "id": str(incident.id),
        "title": incident.title,
        "severity": incident.severity,
        "status": incident.status,
        "started_at": incident.started_at.isoformat(),
        "resolved_at": incident.resolved_at.isoformat() if incident.resolved_at else None,
        "psp": incident.psp.name if incident.psp else None,
        "bank": incident.bank.name if incident.bank else None,
    }


@router.get("/incidents/{incident_id}/context")
def get_incident_context(incident_id: str, db: Session = Depends(get_db)):
    incident = db.query(Incident).filter(Incident.id == incident_id).first()

    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    return get_full_context(db, incident)


@router.post("/incidents/{incident_id}/summary")
def get_incident_summary(incident_id: str, db: Session = Depends(get_db)):
    incident = db.query(Incident).filter(Incident.id == incident_id).first()

    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    context = get_full_context(db, incident)
    summary = generate_summary(context, incident.title)

    return summary


@router.post("/incidents/{incident_id}/chat")
def chat_with_incident(incident_id: str, body: ChatRequest, db: Session = Depends(get_db)):
    incident = db.query(Incident).filter(Incident.id == incident_id).first()

    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    return chat(db, incident, body.message)


@router.get("/incidents/{incident_id}/chat/history")
def get_chat_history(incident_id: str, db: Session = Depends(get_db)):
    incident = db.query(Incident).filter(Incident.id == incident_id).first()

    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    history = (
        db.query(IncidentChatHistory)
        .filter(IncidentChatHistory.incident_id == incident_id)
        .order_by(IncidentChatHistory.created_at)
        .all()
    )

    return [
        {
            "role": h.role,
            "content": h.content,
            "created_at": h.created_at.isoformat(),
        }
        for h in history
    ]