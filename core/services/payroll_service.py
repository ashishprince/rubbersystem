from datetime import date
from django.db import transaction
from django.db.models import Sum, Count
from django.utils import timezone
from core.models import User, Attendance, LatexCollection, TapperAssignment, WageRecord

def generate_payroll_for_month(month_date: date):
    """
    Generates payroll for all active tappers for a specific month.
    Expects `month_date` to be the first day of the respective month.
    Returns (success_count, error_count)
    """
    if month_date.day != 1:
        month_date = date(month_date.year, month_date.month, 1)

    if month_date.month == 12:
        next_month = date(month_date.year + 1, 1, 1)
    else:
        next_month = date(month_date.year, month_date.month + 1, 1)

    # Find User IDs of tappers who have attendance this month
    attendance_tapper_users = Attendance.objects.filter(
        date__gte=month_date, 
        date__lt=next_month
    ).values_list('tapper_id', flat=True).distinct()
    
    # Find User IDs of tappers who have latex collection this month
    # LatexCollection.tapper -> TapperProfile; TapperProfile.user -> User
    latex_tapper_users = LatexCollection.objects.filter(
        date__gte=month_date, 
        date__lt=next_month
    ).values_list('tapper__user_id', flat=True).distinct()

    tapper_user_ids = set(attendance_tapper_users) | set(latex_tapper_users)

    success_count = 0
    error_count = 0

    with transaction.atomic():
        # Prevent duplication: Clean up any existing records for this month to allow manual overwrite
        WageRecord.objects.filter(month=month_date).delete()

        for user_id in tapper_user_ids:
            try:
                user = User.objects.select_related('tapper_profile').get(id=user_id)
                # Ensure the user actually has a profile
                if not hasattr(user, 'tapper_profile'):
                    continue
                profile = user.tapper_profile

                # Step 1: Attendance Count
                attendance_days = Attendance.objects.filter(
                    tapper=user,
                    date__gte=month_date,
                    date__lt=next_month
                ).count()

                if attendance_days == 0 and not LatexCollection.objects.filter(tapper=profile, date__gte=month_date, date__lt=next_month).exists():
                    continue

                # Step 2: Latex Sum
                total_latex = LatexCollection.objects.filter(
                    tapper=profile,
                    date__gte=month_date,
                    date__lt=next_month
                ).aggregate(total=Sum('quantity'))['total'] or 0.0

                # Step 3: Get Block Minimum (from the tapper's current or previous assignment)
                minimum_daily_yield = 30.0  # default
                assignment = TapperAssignment.objects.filter(tapper=profile, is_active=True).first()
                if not assignment:
                    # check if they had an assignment in the past
                     assignment = TapperAssignment.objects.filter(tapper=profile).order_by('-assigned_date').first()
                
                if assignment and assignment.block:
                    minimum_daily_yield = assignment.block.minimum_daily_yield

                # Step 4: Compute Wages (Simplified to Attendance Only)
                daily_rate = float(profile.wage) if profile.wage else 500.0
                per_kg_rate = 0.0  # Removed performance/production wage
                
                base_wage = attendance_days * daily_rate
                production_wage = 0.0
                total_wage = base_wage  # Purely based on attendance

                # Step 5: Compute Performance (Monitoring Only)
                expected_yield = attendance_days * minimum_daily_yield
                
                if expected_yield > 0:
                    performance_percentage = (total_latex / expected_yield) * 100
                else:
                    performance_percentage = 0.0

                # Step 6: Create WageRecord
                WageRecord.objects.create(
                    tapper=user,
                    month=month_date,
                    attendance_days=attendance_days,
                    total_latex_kg=total_latex,
                    daily_rate=daily_rate,
                    per_kg_rate=per_kg_rate,
                    base_wage=base_wage,
                    production_wage=production_wage,
                    total_wage=total_wage,
                    expected_yield=expected_yield,
                    performance_percentage=performance_percentage
                )
                success_count += 1
            except Exception as e:
                print(f"Error processing tapper {user_id}: {e}")
                error_count += 1

    return success_count, error_count

def get_performance_label(percentage):
    if percentage >= 110:
        return 'Excellent'
    elif percentage >= 95:
        return 'Good'
    elif percentage >= 80:
        return 'Moderate'
    else:
        return 'Needs Review'

def get_performance_color(percentage):
    label = get_performance_label(percentage)
    if label == 'Excellent':
        return '#1b5e20' # Dark Green
    elif label == 'Good':
        return '#4caf50' # Light Green
    elif label == 'Moderate':
        return '#ff9800' # Orange
    else:
        return '#f44336' # Red
