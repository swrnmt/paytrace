import sys, os, time

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from database import SessionLocal, create_tables
from scripts import seed, traffic_generator, incident_injector


def print_summary(db):
    from models import Merchant, PSP, Bank, PaymentRail, Transaction, Incident, IncidentTransaction

    print("=" * 50)
    print("SUMMARY")
    print("=" * 50)
    print(f"Merchants:          {db.query(Merchant).count()}")
    print(f"PSPs:               {db.query(PSP).count()}")
    print(f"Banks:              {db.query(Bank).count()}")
    print(f"Rails:              {db.query(PaymentRail).count()}")
    print(f"Transactions:       {db.query(Transaction).count():,}")
    print(f"Incidents:          {db.query(Incident).count()}")
    print(f"Incident-txn links: {db.query(IncidentTransaction).count():,}")
    print("=" * 50)

    print("\nIncidents created:")
    for inc in db.query(Incident).order_by(Incident.started_at).all():
        print(f"  [{inc.severity}] {inc.title}")


def main():
    start = time.time()
    print("\nPayTrace Data Generator")
    print("=" * 50)

    create_tables()

    db = SessionLocal()
    try:
        merchants, psps, banks, rails = seed.run(db)
        traffic_generator.generate_transactions(db, merchants, psps, banks, rails)
        incident_injector.run(db, merchants, psps, banks, rails)
        print_summary(db)
    except Exception as e:
        db.rollback()
        print(f"Something went wrong: {e}")
        raise
    finally:
        db.close()

    print(f"\nDone in {time.time() - start:.1f}s")


if __name__ == "__main__":
    main()