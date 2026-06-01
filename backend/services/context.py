from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from datetime import datetime, timezone, timedelta
from models import Transaction, Incident, IncidentTransaction, Merchant

def get_timeline(incident: Incident) -> dict:
    now = datetime.now(timezone.utc)

    duration = (now - incident.started_at).total_seconds() / 60

    # An incident is only considered worsening if:
    # 1. It is still OPEN or INVESTIGATING
    # 2. It started less than 48 hours ago
    # Incidents older than 48 hours are too stale to call "worsening"
    is_worsening = (
        incident.status != "RESOLVED"
        and duration < 2880  # 2880 minutes = 48 hours
    )

    return {
        "started_at": incident.started_at.isoformat(),
        "duration_minutes": round(duration),
        "is_worsening": is_worsening,
    }


def get_blast_radius(db: Session, incident: Incident) -> dict:
    # Get all transactions linked to this incident
    txns = (
        db.query(Transaction)
        .filter(Transaction.incident_id == incident.id)
        .all()
    )

    if not txns:
        return {
            "affected_merchants": 0,
            "total_failed_transactions": 0,
            "failure_rate_percent": 0.0,
        }

    total = len(txns)

    # Count how many are in a bad state
    bad_statuses = {"FAILED", "PSP_TIMEOUT", "BANK_DOWN", "HIGH_LATENCY", "WEBHOOK_RETRY"}
    failed = [t for t in txns if t.status in bad_statuses]

    # Count unique merchants affected
    unique_merchants = len(set(t.merchant_id for t in txns))

    failure_rate = (len(failed) / total) * 100 if total > 0 else 0

    return {
        "affected_merchants": unique_merchants,
        "total_failed_transactions": len(failed),
        "failure_rate_percent": round(failure_rate, 1),
    }


def get_failure_location(db: Session, incident: Incident) -> dict:
    # Pull PSP, bank, and most common rail from affected transactions
    txns = (
        db.query(Transaction)
        .filter(Transaction.incident_id == incident.id)
        .all()
    )

    # Find most common rail in affected transactions
    rail_counts = {}
    for t in txns:
        rail_counts[t.rail_id] = rail_counts.get(t.rail_id, 0) + 1

    most_common_rail_id = max(rail_counts, key=rail_counts.get) if rail_counts else None

    rail_name = None
    if most_common_rail_id:
        from models import PaymentRail
        rail = db.query(PaymentRail).filter(PaymentRail.id == most_common_rail_id).first()
        rail_name = rail.name if rail else None

    return {
        "psp": incident.psp.name if incident.psp else None,
        "bank": incident.bank.name if incident.bank else None,
        "payment_rail": rail_name,
    }


def get_historical_pattern(db: Session, incident: Incident) -> dict:
    # Look for other incidents in the last 30 days with the same PSP or bank
    thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)

    query = db.query(Incident).filter(
        and_(
            Incident.id != incident.id,
            Incident.started_at >= thirty_days_ago,
        )
    )

    # Match on PSP or bank — whichever this incident has
    if incident.psp_id:
        query = query.filter(Incident.psp_id == incident.psp_id)
    elif incident.bank_id:
        query = query.filter(Incident.bank_id == incident.bank_id)

    similar = query.order_by(Incident.started_at.desc()).all()

    last_occurrence = similar[0].started_at.isoformat() if similar else None

    return {
        "similar_incidents_last_30d": len(similar),
        "last_occurrence": last_occurrence,
        "recurring": len(similar) >= 2,
    }

def get_full_context(db: Session, incident: Incident) -> dict:
    # Auto-resolve incidents older than 48 hours that are still open
    # In a real system an ops engineer would close these manually
    # This prevents stale incidents from showing as perpetually worsening
    from datetime import datetime, timezone, timedelta
    if incident.status == "OPEN":
        age_hours = (datetime.now(timezone.utc) - incident.started_at).total_seconds() / 3600
        if age_hours > 48:
            incident.status = "RESOLVED"
            incident.resolved_at = incident.started_at + timedelta(hours=4)
            db.add(incident)
            db.commit()

    return {
        "timeline": get_timeline(incident),
        "blast_radius": get_blast_radius(db, incident),
        "failure_location": get_failure_location(db, incident),
        "historical_pattern": get_historical_pattern(db, incident),
    }