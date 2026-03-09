"""
Demo Data Seeder — Monthly Latex Production Trend
Run with:  python manage.py shell < seed_demo_production.py
Or:        python seed_demo_production.py  (if run from project root)

This script adds realistic latex collection records spread across the last 6
months so the Monthly Production Trend graph has visible data for the demo.
It is SAFE to run multiple times — it skips dates that already have records.
"""

import os
import sys
import django

# Allow running directly: python seed_demo_production.py
if __name__ == '__main__':
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rubber_system.settings')
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    django.setup()

import datetime
import random
from django.utils import timezone
from core.models import LatexCollection, TapperProfile, Block

# ─── Grab existing tappers + blocks ───────────────────────────────────────────
tappers = list(TapperProfile.objects.filter(active=True).select_related('user'))
blocks  = list(Block.objects.all())

if not tappers:
    print("❌  No active tappers found. Please create at least one tapper first.")
    sys.exit(1)
if not blocks:
    print("❌  No blocks found. Please create at least one block first.")
    sys.exit(1)

print(f"✅  Found {len(tappers)} tapper(s) and {len(blocks)} block(s).")

# ─── Build date range: first day 6 months ago → yesterday ────────────────────
today = timezone.now().date()
# Go back 6 complete months
start = (today.replace(day=1) - datetime.timedelta(days=150)).replace(day=1)

tapper = tappers[0]   # use first tapper for simplicity
block  = blocks[0]    # use their first block

# Monthly yield targets (in litres) — realistic rubber plantation numbers
# Sept → Feb  (adjust labels to match real months automatically)
monthly_targets = [185, 210, 195, 230, 205, 220]  # 6 months

created = 0
skipped = 0

current = start
month_index = 0

while current.month != today.month or current.year != today.year:
    # Work out how many days to spread this month's yield across
    # (tappers typically tap 22 working days a month)
    if current.month == today.month and current.year == today.year:
        break  # don't go into the current month

    # last day of current month
    if current.month == 12:
        month_end = current.replace(year=current.year + 1, month=1, day=1) - datetime.timedelta(days=1)
    else:
        month_end = current.replace(month=current.month + 1, day=1) - datetime.timedelta(days=1)

    target_yield = monthly_targets[month_index % 6]
    working_days = [d for d in range(current.day, month_end.day + 1)
                    if datetime.date(current.year, current.month, d).weekday() < 6]  # Mon-Sat

    # Spread the target yield across working days with some realistic variation
    if working_days:
        per_day_base = target_yield / len(working_days)
        for d in working_days:
            day = datetime.date(current.year, current.month, d)
            quantity = round(per_day_base * random.uniform(0.7, 1.3), 1)
            # unique_together = ['tapper', 'date'] — skip if record already exists
            if not LatexCollection.objects.filter(tapper=tapper, date=day).exists():
                LatexCollection.objects.create(
                    date=day,
                    block=block,
                    tapper=tapper,
                    quantity=quantity,
                )
                created += 1
            else:
                skipped += 1

    # Move to first day of next month
    if current.month == 12:
        current = current.replace(year=current.year + 1, month=1, day=1)
    else:
        current = current.replace(month=current.month + 1, day=1)

    month_index += 1

print(f"\n🌿  Demo production data seeded!")
print(f"    Created : {created} records")
print(f"    Skipped (already existed): {skipped} records")
print(f"\n✅  Refresh the Manager Dashboard — the Monthly Latex Production Trend graph should now show data!")
