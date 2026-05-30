import numpy as np
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from sqlalchemy import and_
from models import Transaction, Incident, IncidentTransaction, PSP, Bank, PaymentRail
import sys, os

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))


def get_psp(db, name):
    return db.query(PSP).filter(PSP.name == name).first()

def get_bank(db, name):
    return db.query(Bank).filter(Bank.name == name).first()

def get_rail(db, name):
    return db.query(PaymentRail).filter(PaymentRail.name == name).first()


def random_window(now, days_back, min_hours, max_hours):
    # Pick a random start time somewhere in the last 30 days
    offset = np.random.randint(1, days_back)
    start = (now - timedelta(days=offset)).replace(minute=0, second=0, microsecond=0)
    end = start + timedelta(hours=np.random.randint(min_hours, max_hours))
    return start, end


def degrade(db, transactions, new_status, rate, min_latency=None, max_latency=None):
    # Flip a percentage of transactions to a bad status
    # rate=0.6 means 60% of transactions in this window get degraded
    degraded = []
    for txn in transactions:
        if np.random.random() < rate:
            txn.status = new_status
            if min_latency and max_latency:
                txn.latency_ms = np.random.randint(min_latency, max_latency)
            degraded.append(txn)
    return degraded


def create_incident(db, title, severity, started_at, ended_at, psp=None, bank=None):
    incident = Incident(
        title=title,
        severity=severity,
        # If the end time is in the past, mark it resolved
        status="RESOLVED" if ended_at < datetime.now(timezone.utc) else "OPEN",
        psp_id=psp.id if psp else None,
        bank_id=bank.id if bank else None,
        started_at=started_at,
        resolved_at=ended_at,
    )
    db.add(incident)
    db.flush()  # need the incident ID before we can link transactions
    return incident


def link(db, incident, transactions):
    # Create a row in incident_transactions for each affected transaction
    # Also stamp incident_id directly on the transaction for fast queries
    for txn in transactions:
        txn.incident_id = incident.id
        db.add(IncidentTransaction(incident_id=incident.id, transaction_id=txn.id))


# --- INCIDENT TYPE 1: PSP timeout storm ---
def inject_psp_timeout(db, now, days):
    print("  Injecting PSP timeout storm...")
    psp = get_psp(db, np.random.choice(["Razorpay", "PayU"]))
    start, end = random_window(now, days, 2, 5)

    txns = db.query(Transaction).filter(
        and_(Transaction.psp_id == psp.id, Transaction.created_at >= start, Transaction.created_at <= end)
    ).all()

    if not txns:
        print("    No transactions in window, skipping.")
        return

    degraded = degrade(db, txns, "PSP_TIMEOUT", rate=np.random.uniform(0.4, 0.6), min_latency=800, max_latency=2000)
    incident = create_incident(db, f"{psp.name} timeout storm — PSP_TIMEOUT surging", "CRITICAL", start, end, psp=psp)
    link(db, incident, degraded)
    print(f"    Done. {len(degraded)} transactions affected.")


# --- INCIDENT TYPE 2: Bank outage ---
def inject_bank_outage(db, now, days):
    print("  Injecting bank outage...")
    bank = get_bank(db, np.random.choice(["HDFC", "SBI"]))
    start, end = random_window(now, days, 1, 4)

    txns = db.query(Transaction).filter(
        and_(Transaction.bank_id == bank.id, Transaction.created_at >= start, Transaction.created_at <= end)
    ).all()

    if not txns:
        print("    No transactions in window, skipping.")
        return

    degraded = degrade(db, txns, "BANK_DOWN", rate=np.random.uniform(0.7, 0.85))
    incident = create_incident(db, f"{bank.name} outage — BANK_DOWN on majority of transactions", "CRITICAL", start, end, bank=bank)
    link(db, incident, degraded)
    print(f"    Done. {len(degraded)} transactions affected.")


# --- INCIDENT TYPE 3: Webhook retry storm ---
def inject_webhook_storm(db, now, days, merchants):
    print("  Injecting webhook retry storm...")
    # Only affects the top 3 merchants (highest traffic ones)
    top_merchants = merchants[:3]
    start, end = random_window(now, days, 3, 6)

    txns = db.query(Transaction).filter(
        and_(
            Transaction.merchant_id.in_([m.id for m in top_merchants]),
            Transaction.created_at >= start,
            Transaction.created_at <= end,
        )
    ).all()

    if not txns:
        print("    No transactions in window, skipping.")
        return

    degraded = degrade(db, txns, "WEBHOOK_RETRY", rate=np.random.uniform(0.35, 0.5))
    incident = create_incident(db, "Webhook retry storm — top merchants failing delivery", "HIGH", start, end)
    link(db, incident, degraded)
    print(f"    Done. {len(degraded)} transactions affected.")


# --- INCIDENT TYPE 4: High latency surge ---
def inject_latency_surge(db, now, days):
    print("  Injecting high latency surge...")
    psp = get_psp(db, "Cashfree")
    rail = get_rail(db, "UPI")
    start, end = random_window(now, days, 2, 4)

    txns = db.query(Transaction).filter(
        and_(
            Transaction.psp_id == psp.id,
            Transaction.rail_id == rail.id,
            Transaction.created_at >= start,
            Transaction.created_at <= end,
        )
    ).all()

    if not txns:
        print("    No transactions in window, skipping.")
        return

    degraded = degrade(db, txns, "HIGH_LATENCY", rate=0.8, min_latency=1500, max_latency=3000)
    incident = create_incident(db, "Cashfree + UPI latency surge — p99 exceeding 2000ms", "MEDIUM", start, end, psp=psp)
    link(db, incident, degraded)
    print(f"    Done. {len(degraded)} transactions affected.")


# --- INCIDENT TYPE 5: Merchant degradation ---
def inject_merchant_degradation(db, now, days, merchants):
    print("  Injecting merchant degradation...")
    affected = list(np.random.choice(merchants, size=3, replace=False))
    start, end = random_window(now, days, 4, 7)

    txns = db.query(Transaction).filter(
        and_(
            Transaction.merchant_id.in_([m.id for m in affected]),
            Transaction.created_at >= start,
            Transaction.created_at <= end,
        )
    ).all()

    if not txns:
        print("    No transactions in window, skipping.")
        return

    degraded = degrade(db, txns, "FAILED", rate=np.random.uniform(0.3, 0.45))
    names = ", ".join(m.name for m in affected[:2])
    incident = create_incident(db, f"Merchant degradation — elevated failures for {names} and others", "MEDIUM", start, end)
    link(db, incident, degraded)
    print(f"    Done. {len(degraded)} transactions affected.")


# --- RECURRING CLUSTERS ---
# These create the same PSP/bank combo multiple times across 30 days
# so the historical_pattern context can say "this has happened 3 times before"
def inject_recurring_clusters(db, now, days):
    print("  Injecting recurring clusters...")
    hdfc = get_bank(db, "HDFC")
    razorpay = get_psp(db, "Razorpay")

    # HDFC degradation — 3 times, always 8pm-11pm
    for _ in range(3):
        offset = np.random.randint(1, days - 1)
        start = (now - timedelta(days=offset)).replace(hour=20, minute=0, second=0, microsecond=0)
        end = start + timedelta(hours=3)

        txns = db.query(Transaction).filter(
            and_(Transaction.bank_id == hdfc.id, Transaction.created_at >= start, Transaction.created_at <= end)
        ).all()

        if not txns:
            continue

        degraded = degrade(db, txns, "BANK_DOWN", rate=0.45)
        incident = create_incident(db, "HDFC UPI degradation — recurring evening pattern", "HIGH", start, end, bank=hdfc)
        link(db, incident, degraded)

    # Razorpay timeouts — 2 times, always weekday mornings
    for _ in range(2):
        offset = np.random.randint(1, days - 1)
        start = (now - timedelta(days=offset)).replace(hour=9, minute=0, second=0, microsecond=0)
        end = start + timedelta(hours=2)

        txns = db.query(Transaction).filter(
            and_(Transaction.psp_id == razorpay.id, Transaction.created_at >= start, Transaction.created_at <= end)
        ).all()

        if not txns:
            continue

        degraded = degrade(db, txns, "PSP_TIMEOUT", rate=0.4, min_latency=900, max_latency=1800)
        incident = create_incident(db, "Razorpay timeout storm — recurring weekday morning pattern", "HIGH", start, end, psp=razorpay)
        link(db, incident, degraded)

    print("  Recurring clusters done.")


def run(db, merchants, psps, banks, rails):
    print("Injecting incidents...")
    now = datetime.now(timezone.utc)
    days = 30

    inject_psp_timeout(db, now, days)
    inject_psp_timeout(db, now, days)
    inject_bank_outage(db, now, days)
    inject_bank_outage(db, now, days)
    inject_webhook_storm(db, now, days, merchants)
    inject_latency_surge(db, now, days)
    inject_merchant_degradation(db, now, days, merchants)
    inject_recurring_clusters(db, now, days)

    db.commit()
    print("All incidents injected.\n")