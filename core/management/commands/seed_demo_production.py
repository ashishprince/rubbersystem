"""
Management command: seed_demo_production

Seeds 6 months of realistic LatexCollection records for a demo.
Safe to run multiple times — skips dates that already have records.

Usage (on the server):
    python manage.py seed_demo_production
"""

import datetime
import random

from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import LatexCollection, TapperProfile, Block


class Command(BaseCommand):
    help = "Seeds 6 months of demo latex production data for the Monthly Production Trend graph."

    def handle(self, *args, **options):
        tappers = list(TapperProfile.objects.filter(active=True).select_related('user'))
        blocks  = list(Block.objects.all())

        if not tappers:
            self.stderr.write(self.style.ERROR("No active tappers found. Create at least one tapper first."))
            return
        if not blocks:
            self.stderr.write(self.style.ERROR("No blocks found. Create at least one block first."))
            return

        self.stdout.write(f"Found {len(tappers)} tapper(s) and {len(blocks)} block(s).")

        today = timezone.now().date()
        # Start from 6 months ago (first day of that month)
        start = (today.replace(day=1) - datetime.timedelta(days=150)).replace(day=1)

        # Use first tapper + their assigned block if available, else first block
        tapper = tappers[0]
        # Try to get the block this tapper is actually assigned to
        assignment = tapper.assignments.filter(is_active=True).first()
        block = assignment.block if assignment else blocks[0]

        self.stdout.write(
            self.style.SUCCESS(f"Seeding data for tapper: {tapper} | block: {block}")
        )

        # Realistic monthly yield targets (in litres)
        monthly_targets = [195, 215, 185, 230, 210, 225]  # 6 months of realistic variation

        created = 0
        skipped = 0
        month_index = 0
        current = start

        while True:
            if current.year == today.year and current.month == today.month:
                break

            # Last day of the current month
            if current.month == 12:
                month_end = current.replace(year=current.year + 1, month=1, day=1) - datetime.timedelta(days=1)
                next_month_start = current.replace(year=current.year + 1, month=1, day=1)
            else:
                month_end = current.replace(month=current.month + 1, day=1) - datetime.timedelta(days=1)
                next_month_start = current.replace(month=current.month + 1, day=1)

            # Working days: Monday–Saturday
            working_days = [
                datetime.date(current.year, current.month, d)
                for d in range(current.day, month_end.day + 1)
                if datetime.date(current.year, current.month, d).weekday() < 6
            ]

            target_yield = monthly_targets[month_index % 6]
            per_day = target_yield / max(len(working_days), 1)

            for day in working_days:
                quantity = round(per_day * random.uniform(0.75, 1.25), 1)
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

            current = next_month_start
            month_index += 1

        self.stdout.write(self.style.SUCCESS(
            f"\n✅  Done! Created {created} records, skipped {skipped} already-existing records."
        ))
        self.stdout.write("Refresh the Manager Dashboard to see the Monthly Latex Production Trend graph.")
