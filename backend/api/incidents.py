from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from database import get_db
from models import Incident, IncidentChatHistory
from services.context import get_full_context
from services.ai import generate_summary
from services.chat import chat

router = APIRouter()


# Pydantic model — validates the request body for the chat endpoint
# When someone POSTs to /chat, FastAPI checks that "message" is present
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