import numpy as np
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from models import Transaction
import sys, os

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))


def build_weights(items, weights):
    # Normalize weights so they add up to 1.0
    # numpy needs this — it won't accept weights like [35, 25, 20, 12, 8]
    total = sum(weights)
    return [w / total for w in weights]


def pick_status():
    # 94% success, small tails of failures — this is baseline healthy traffic
    roll = np.random.random()
    if roll < 0.94:
        return "SUCCESS"
    elif roll < 0.97:
        return "FAILED"
    elif roll < 0.99:
        return "HIGH_LATENCY"
    else:
        return "WEBHOOK_RETRY"


def pick_latency(status):
    # Normal transactions: mean 180ms, std 60ms
    # High latency transactions get a much bigger number
    if status == "HIGH_LATENCY":
        return int(np.random.normal(1200, 300))
    return max(50, int(np.random.normal(180, 60)))


def generate_transactions(db: Session, merchants, psps, banks, rails, total=30_000, days=30):
    print(f"Generating {total:,} transactions over {days} days...")

    # Weighted distributions — Razorpay gets 35% of traffic, PayU 25%, etc.
    psp_weights = build_weights(psps, [0.35, 0.25, 0.20, 0.12, 0.08])
    bank_weights = build_weights(banks, [0.30, 0.25, 0.20, 0.15, 0.10])
    rail_weights = build_weights(rails, [0.55, 0.25, 0.12, 0.08])

    # Top 3 merchants get 55% of traffic, rest share the remaining 45%
    n = len(merchants)
    merchant_weights_raw = [0.20, 0.20, 0.15] + [0.45 / (n - 3)] * (n - 3)
    merchant_weights = build_weights(merchants, merchant_weights_raw)

    now = datetime.now(timezone.utc)
    start_date = now - timedelta(days=days)

    for i in range(total):
        # Pick a random day in the 30 day window
        day_offset = np.random.randint(0, days)
        day = start_date + timedelta(days=day_offset)

        # Evening hours (6pm-10pm) are 2.5x busier — simulate real traffic
        hour_weights_raw = []
        for h in range(24):
            if 18 <= h <= 22:
                hour_weights_raw.append(2.5)
            elif 0 <= h <= 6:
                hour_weights_raw.append(0.3)
            else:
                hour_weights_raw.append(1.0)

        hour = np.random.choice(24, p=build_weights(list(range(24)), hour_weights_raw))

        ts = day.replace(
            hour=int(hour),
            minute=np.random.randint(0, 60),
            second=np.random.randint(0, 60),
            microsecond=0,
        )

        status = pick_status()
        latency = pick_latency(status)

        txn = Transaction(
            merchant_id=np.random.choice([m.id for m in merchants], p=merchant_weights),
            psp_id=np.random.choice([p.id for p in psps], p=psp_weights),
            bank_id=np.random.choice([b.id for b in banks], p=bank_weights),
            rail_id=np.random.choice([r.id for r in rails], p=rail_weights),
            amount=round(np.random.uniform(10, 5000), 2),
            status=status,
            latency_ms=latency,
            created_at=ts,
        )
        db.add(txn)

        # Commit every 500 rows so we don't hold 30,000 objects in memory
        if (i + 1) % 500 == 0:
            db.flush()
            print(f"  {i + 1:,} / {total:,}...")

    db.commit()
    print(f"Done. {total:,} transactions created.\n")