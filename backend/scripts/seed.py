from faker import Faker
from sqlalchemy.orm import Session
import sys, os

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from models import Merchant, PSP, Bank, PaymentRail

fake = Faker("en_IN")  # Indian locale for realistic names


def seed_merchants(db: Session):
    print("Seeding merchants...")

    # 20 merchants across 5 categories
    # The list is weighted — 8 ecommerce, 5 food delivery, etc.
    categories = (
        ["e-commerce"] * 8
        + ["food_delivery"] * 5
        + ["travel"] * 3
        + ["subscriptions"] * 2
        + ["retail"] * 2
    )

    merchants = []
    for category in categories:
        merchant = Merchant(name=fake.company(), category=category)
        db.add(merchant)
        merchants.append(merchant)

    # flush() sends the data to DB and assigns IDs, but doesn't fully commit yet
    # We commit everything together at the end so if anything fails, nothing is saved
    db.flush()
    print(f"  Created {len(merchants)} merchants.")
    return merchants


def seed_psps(db: Session):
    print("Seeding PSPs...")

    psps = []
    for name in ["Razorpay", "PayU", "Cashfree", "Juspay", "Paytm PG"]:
        psp = PSP(name=name)
        db.add(psp)
        psps.append(psp)

    db.flush()
    print(f"  Created {len(psps)} PSPs.")
    return psps


def seed_banks(db: Session):
    print("Seeding banks...")

    banks = []
    for name in ["HDFC", "SBI", "ICICI", "Axis", "Kotak"]:
        bank = Bank(name=name)
        db.add(bank)
        banks.append(bank)

    db.flush()
    print(f"  Created {len(banks)} banks.")
    return banks


def seed_rails(db: Session):
    print("Seeding payment rails...")

    rails = []
    for name in ["UPI", "NEFT", "IMPS", "Cards"]:
        rail = PaymentRail(name=name)
        db.add(rail)
        rails.append(rail)

    db.flush()
    print(f"  Created {len(rails)} payment rails.")
    return rails


def run(db: Session):
    merchants = seed_merchants(db)
    psps = seed_psps(db)
    banks = seed_banks(db)
    rails = seed_rails(db)

    # Now commit everything together
    db.commit()
    print("Seeding complete.\n")
    return merchants, psps, banks, rails