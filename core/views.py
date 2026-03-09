from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User, Group
from django.contrib.auth import logout
from django.contrib import messages
from django.utils import timezone
from django.contrib.gis.db import models
from django.db.models import Sum, Count, F, DecimalField, ExpressionWrapper
from django.contrib.gis.geos import GEOSGeometry, Point
from django.db import IntegrityError, connection
from .models import Block, TapperProfile, TapperAssignment, LatexCollection, ManagerProfile, Attendance, IncidentReport, WageRecord, MarketPrice
from django.contrib.gis.measure import D
from .decorators import role_required, get_user_role
from django.http import JsonResponse
import datetime
import json
from core.services.weather_service import get_weather_for_coordinates
from core.services.market_price_service import get_market_price_for_dashboard, manual_fetch as manual_market_fetch


# ─────────────────────────────────────────────
# DASHBOARD ROUTER
# ─────────────────────────────────────────────

@login_required
def dashboard(request):
    """Route to role-specific dashboard."""
    role = get_user_role(request.user)
    if role == 'Admin':
        return redirect('admin_dashboard')
    elif role == 'Manager':
        return redirect('manager_dashboard')
    elif role == 'Tapper':
        return redirect('tapper_dashboard')
    return redirect('login')


# ─────────────────────────────────────────────
# ADMIN DASHBOARD
# ─────────────────────────────────────────────

@login_required
@role_required('Admin')
def admin_dashboard(request):
    today = timezone.now().date()
    current_month = today.month
    current_year = today.year

    total_blocks = Block.objects.count()
    total_tappers = TapperProfile.objects.filter(active=True).count()
    total_managers = User.objects.filter(groups__name='Manager').count()

    today_latex = LatexCollection.objects.filter(date=today).aggregate(
        total=Sum('quantity'))['total'] or 0
    monthly_latex = LatexCollection.objects.filter(
        date__month=current_month, date__year=current_year
    ).aggregate(total=Sum('quantity'))['total'] or 0

    recent_collections = LatexCollection.objects.select_related(
        'block', 'tapper__user').all()[:10]

    # Block performance: total production per block this month
    block_performance = Block.objects.annotate(
        monthly_total=Sum(
            'collections__quantity',
            filter=models.Q(
                collections__date__month=current_month,
                collections__date__year=current_year
            )
        )
    ).order_by('-monthly_total')[:5]

    # For percentage calculation  
    max_block_total = 1
    if block_performance:
        vals = [b.monthly_total or 0 for b in block_performance]
        if vals and max(vals) > 0:
            max_block_total = max(vals)
    for b in block_performance:
        b.percentage = int(((b.monthly_total or 0) / max_block_total) * 100) if max_block_total > 0 else 0

    # Top tappers this month
    top_tappers = TapperProfile.objects.filter(active=True).annotate(
        monthly_total=Sum(
            'collections__quantity',
            filter=models.Q(
                collections__date__month=current_month,
                collections__date__year=current_year
            )
        )
    ).order_by('-monthly_total')[:5]

    # Today's Attendance
    today_attendance = Attendance.objects.filter(date=today).select_related('tapper', 'block')

    # ── Market Price (auto-fetch once per day, fallback to cached) ──
    try:
        market_price_data = get_market_price_for_dashboard()
    except Exception:
        market_price_data = {'success': False, 'price': None, 'status': 'unavailable',
                             'fetched_at': None, 'message': 'Market price service unavailable.'}

    context = {
        'total_blocks': total_blocks,
        'total_tappers': total_tappers,
        'total_managers': total_managers,
        'today_latex': round(today_latex, 2),
        'monthly_latex': round(monthly_latex, 2),
        'recent_collections': recent_collections,
        'block_performance': block_performance,
        'top_tappers': top_tappers,
        'today_attendance': today_attendance,
        'current_month_name': today.strftime('%B'),
        'current_year': current_year,
        'market_price_data': market_price_data,
    }
    return render(request, 'dashboard_admin.html', context)





# ─────────────────────────────────────────────
# MANAGER DASHBOARD
# ─────────────────────────────────────────────

@login_required
@role_required('Manager')
def manager_dashboard(request):
    from django.core.cache import cache
    from django.db.models import Avg

    today = timezone.now().date()
    current_month = today.month
    current_year = today.year

    selected_month_str = request.GET.get('month', today.strftime('%Y-%m'))
    try:
        selected_month_date = datetime.datetime.strptime(selected_month_str, '%Y-%m').date()
    except ValueError:
        selected_month_date = datetime.date(current_year, current_month, 1)
    first_day_of_selected_month = datetime.date(selected_month_date.year, selected_month_date.month, 1)

    # ── Run DB queries (FileBasedCache keeps individual expensive results shared) ──
    my_blocks = list(Block.objects.filter(manager=request.user))
    my_block_ids = [b.id for b in my_blocks]

    my_tappers = list(TapperProfile.objects.filter(created_by=request.user, active=True))

    active_assignments = list(
        TapperAssignment.objects.filter(
            is_active=True, tapper__created_by=request.user
        ).select_related('tapper__user', 'block')
    )
    assigned_tapper_ids = {a.tapper_id for a in active_assignments}
    unassigned_tappers = [t for t in my_tappers if t.id not in assigned_tapper_ids]

    # Two latex aggregates in ONE query
    latex_agg = LatexCollection.objects.filter(
        block__manager=request.user
    ).aggregate(
        today_total=Sum('quantity', filter=models.Q(date=today)),
        month_total=Sum('quantity', filter=models.Q(
            date__month=current_month, date__year=current_year
        ))
    )
    today_latex   = round(latex_agg['today_total']  or 0, 2)
    monthly_latex = round(latex_agg['month_total']  or 0, 2)

    today_attendance = list(
        Attendance.objects.filter(
            date=today, tapper__tapper_profile__created_by=request.user
        ).select_related('tapper', 'block')
    )

    today_attendance = list(
        Attendance.objects.filter(
            date=today, tapper__tapper_profile__created_by=request.user
        ).select_related('tapper', 'block')
    )

    # Note: open_incidents query has been moved to manager_incidents view
    # Note: wage_records and productivity_blocks query has been moved to separate views

    try:
        market_price_data = get_market_price_for_dashboard()
    except Exception:
        market_price_data = {'success': False, 'price': None, 'status': 'unavailable',
                             'fetched_at': None, 'message': 'Market price service unavailable.'}

    # We just need the count of open incidents to show the badge on the dashboard card
    open_incidents_count = IncidentReport.objects.filter(
        block_id__in=my_block_ids, status__in=['OPEN', 'IN_PROGRESS']
    ).count()

    context = {
        'active_assignments': active_assignments,
        'unassigned_tappers': unassigned_tappers,
        'today_latex': today_latex,
        'monthly_latex': monthly_latex,
        'block_production': [],
        'total_assigned': len(active_assignments),
        'total_unassigned': len(unassigned_tappers),
        'today_attendance': today_attendance,
        'current_month_name': today.strftime('%B'),
        'current_year': current_year,
        'weather_data': None,
        'open_incidents': range(open_incidents_count), # Hack to make {{ open_incidents|length }} work without rewriting the template
        'market_price_data': market_price_data,
        'selected_month_str': first_day_of_selected_month.strftime('%Y-%m')
    }
    return render(request, 'dashboard_manager.html', context)


# ─────────────────────────────────────────────
# PAYROLL PAGE
# ─────────────────────────────────────────────

@login_required
@role_required('Manager')
def manager_payroll(request):
    from django.core.cache import cache

    today = timezone.now().date()
    current_month = today.month
    current_year = today.year

    selected_month_str = request.GET.get('month', today.strftime('%Y-%m'))
    try:
        selected_month_date = datetime.datetime.strptime(selected_month_str, '%Y-%m').date()
    except ValueError:
        selected_month_date = datetime.date(current_year, current_month, 1)
    first_day = datetime.date(selected_month_date.year, selected_month_date.month, 1)

    wage_records = list(
        WageRecord.objects.filter(
            month=first_day,
            tapper__tapper_profile__created_by=request.user
        ).select_related('tapper')
    )

    total_wage_liability  = sum(float(w.total_wage) for w in wage_records)
    perfs = [float(w.performance_percentage) for w in wage_records]
    avg_performance       = (sum(perfs) / len(perfs)) if perfs else 0.0
    underperforming_count = sum(1 for p in perfs if p < 80)
    highest_earning       = max(wage_records, key=lambda w: w.total_wage, default=None)

    return render(request, 'payroll_manager.html', {
        'wage_records': wage_records,
        'selected_month_str': first_day.strftime('%Y-%m'),
        'total_wage_liability': round(total_wage_liability, 2),
        'avg_performance': round(avg_performance, 2),
        'underperforming_count': underperforming_count,
        'highest_earning': highest_earning,
        'current_month_name': today.strftime('%B'),
    })


# ─────────────────────────────────────────────
# INCIDENTS PAGE
# ─────────────────────────────────────────────

@login_required
@role_required('Manager')
def manager_incidents(request):
    today = timezone.now().date()
    my_blocks = Block.objects.filter(manager=request.user)
    my_block_ids = [b.id for b in my_blocks]

    open_incidents = list(
        IncidentReport.objects.filter(
            block_id__in=my_block_ids, status__in=['OPEN', 'IN_PROGRESS']
        ).select_related('tapper', 'block')
    )
    high_severity_count = sum(1 for i in open_incidents if i.severity == 'HIGH')

    start_of_week = today - datetime.timedelta(days=today.weekday())
    resolved_this_week = IncidentReport.objects.filter(
        block_id__in=my_block_ids, status='RESOLVED', resolved_at__gte=start_of_week
    ).count()
    total_resolved = IncidentReport.objects.filter(
        block_id__in=my_block_ids, status='RESOLVED'
    ).count()

    incidents_json = json.dumps([{
        'id': inc.id,
        'type': inc.get_incident_type_display(),
        'severity': inc.severity,
        'description': inc.description,
        'tapper': inc.tapper.get_full_name() or inc.tapper.username,
        'block': inc.block.name,
        'lat': inc.location.y,
        'lng': inc.location.x,
        'date': inc.created_at.strftime('%b %d, %Y %I:%M %p'),
    } for inc in open_incidents])

    return render(request, 'incidents_manager.html', {
        'open_incidents': open_incidents,
        'high_severity_count': high_severity_count,
        'resolved_this_week': resolved_this_week,
        'total_resolved': total_resolved,
        'incidents_json': incidents_json,
    })


# ─────────────────────────────────────────────
# PRODUCTIVITY MAP PAGE
# ─────────────────────────────────────────────

@login_required
def manager_productivity(request):
    """Block Productivity Map. Manager sees own blocks; Admin sees all blocks."""
    from django.core.cache import cache
    from core.services.payroll_service import get_performance_color, get_performance_label

    role = get_user_role(request.user)
    if role not in ('Manager', 'Admin'):
        from django.contrib.auth.views import redirect_to_login
        return redirect_to_login(request.path)

    today = timezone.now().date()
    current_month = today.month
    current_year = today.year
    first_day = datetime.date(current_year, current_month, 1)

    # Admin sees all blocks; Manager sees only their own
    if role == 'Admin':
        my_blocks = list(Block.objects.exclude(boundary__isnull=True))
        wage_qs = WageRecord.objects.filter(month=first_day)
    else:
        my_blocks = list(Block.objects.filter(manager=request.user))
        wage_qs = WageRecord.objects.filter(
            month=first_day,
            tapper__tapper_profile__created_by=request.user
        )

    my_block_ids = [b.id for b in my_blocks]

    _prod_key = f'mgr_prod_{request.user.id}_{first_day}'
    productivity_blocks_json = cache.get(_prod_key)
    if not productivity_blocks_json:
        wage_records = list(wage_qs.values_list('tapper_id', 'performance_percentage'))
        wage_by_tapper = dict(wage_records)

        # Primary: map tappers to blocks via active assignments
        active_tapper_users = User.objects.filter(
            tapper_profile__assignments__block_id__in=my_block_ids,
            tapper_profile__assignments__is_active=True,
        ).values_list('id', 'tapper_profile__assignments__block_id')
        block_to_user_ids = {}
        for user_id, block_id in active_tapper_users:
            block_to_user_ids.setdefault(block_id, []).append(user_id)

        # Fallback: for tappers with WageRecords but no active assignment,
        # map them to the block they most recently collected from this month
        if_months_ago_start = first_day
        unassigned_tapper_ids = [uid for uid in wage_by_tapper if uid not in
                                  [uid2 for uids in block_to_user_ids.values() for uid2 in uids]]
        if unassigned_tapper_ids:
            latex_blocks = (
                LatexCollection.objects
                .filter(
                    tapper__user_id__in=unassigned_tapper_ids,
                    block_id__in=my_block_ids,
                    date__gte=if_months_ago_start,
                )
                .values_list('tapper__user_id', 'block_id')
                .distinct()
            )
            for user_id, block_id in latex_blocks:
                block_to_user_ids.setdefault(block_id, [])
                if user_id not in block_to_user_ids[block_id]:
                    block_to_user_ids[block_id].append(user_id)

        productivity_blocks = []
        for block in my_blocks:
            if not block.boundary:
                continue
            user_ids = block_to_user_ids.get(block.id, [])
            bperfs = [float(wage_by_tapper[uid]) for uid in user_ids if uid in wage_by_tapper]
            avg_perf = sum(bperfs) / len(bperfs) if bperfs else 0.0
            color = get_performance_color(avg_perf) if bperfs else '#9e9e9e'
            label = get_performance_label(avg_perf) if bperfs else 'No data'
            productivity_blocks.append({
                'id': block.id, 'name': block.name,
                'color': color, 'label': label,
                'perf': round(avg_perf, 2),
                'boundary': json.loads(block.boundary.geojson)
            })
        productivity_blocks_json = json.dumps(productivity_blocks)
        cache.set(_prod_key, productivity_blocks_json, 600)

    return render(request, 'productivity_manager.html', {
        'productivity_blocks_json': productivity_blocks_json,
        'current_month_name': today.strftime('%B %Y'),
    })


# ─────────────────────────────────────────────
# MARKET PRICE - MANUAL FETCH ENDPOINT
# ─────────────────────────────────────────────



@login_required
@role_required('Manager')
def fetch_market_price(request):
    """
    Manager-only AJAX endpoint to manually refresh the rubber market price.
    POST: triggers a live fetch from Rubber Board India.
    Returns JSON.
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'POST required.'}, status=405)

    result = manual_market_fetch()

    return JsonResponse({
        'success': result['success'],
        'price': result['price'],
        'status': result['status'],
        'fetched_at': result['fetched_at'].strftime('%d %b %Y, %I:%M %p') if result['fetched_at'] else None,
        'message': result['message'],
    })


@login_required
@role_required('Admin', 'Manager')
def generate_payroll(request):

    """Generates payroll for a specific month for active tappers."""
    if request.method == 'POST':
        month_str = request.POST.get('month')
        try:
            month_date = datetime.datetime.strptime(month_str, '%Y-%m').date()
            first_day = datetime.date(month_date.year, month_date.month, 1)
        except ValueError:
            messages.error(request, 'Invalid month format.')
            return redirect('manager_dashboard')
            
        from core.services.payroll_service import generate_payroll_for_month
        success_count, error_count = generate_payroll_for_month(first_day)
        
        if error_count > 0:
            messages.warning(request, f'Generated payroll for {success_count} tappers, but {error_count} failed.')
        else:
            messages.success(request, f'Payroll generated successfully for {success_count} tappers for {first_day.strftime("%B %Y")}.')
            
        # Redirect back with the selected month
        return redirect(f"/dashboard/manager/?month={first_day.strftime('%Y-%m')}")
        
    return redirect('manager_dashboard')


# ─────────────────────────────────────────────
# TAPPER DASHBOARD
# ─────────────────────────────────────────────

@login_required
@role_required('Tapper')
def tapper_dashboard(request):
    today = timezone.now().date()
    current_month = today.month
    current_year = today.year

    try:
        profile = request.user.tapper_profile
    except TapperProfile.DoesNotExist:
        messages.error(request, 'Your tapper profile has not been set up. Contact an administrator.')
        return render(request, 'dashboard_tapper.html', {'has_profile': False})

    assignment = profile.active_assignment
    assigned_block = assignment.block if assignment else None

    # Today's entry by this tapper
    today_entry = LatexCollection.objects.filter(
        tapper=profile, date=today).aggregate(total=Sum('quantity'))['total'] or 0

    # Monthly total for this tapper
    monthly_total = LatexCollection.objects.filter(
        tapper=profile, date__month=current_month, date__year=current_year
    ).aggregate(total=Sum('quantity'))['total'] or 0

    # Recent collection history
    recent_history = LatexCollection.objects.filter(
        tapper=profile).select_related('block')[:7]

    # Get manager photo if available
    manager_photo = None
    if profile.created_by:
        try:
            mgr_profile = profile.created_by.manager_profile
            if mgr_profile.photo:
                manager_photo = mgr_profile.photo
        except ManagerProfile.DoesNotExist:
            pass

    # Get block boundary for map (serialize PolygonField to GeoJSON)
    block_boundary_json = None
    weather_data = None
    if assigned_block and assigned_block.boundary:
        block_boundary_json = assigned_block.boundary.geojson
        centroid = assigned_block.boundary.centroid
        weather_data = get_weather_for_coordinates(centroid.y, centroid.x)
    else:
        # No boundary on assigned block – try to get weather from any block owned by the manager,
        # or fall back to a default plantation location in Kerala.
        fallback_lat, fallback_lng = None, None
        if profile.created_by:
            fallback_block = Block.objects.filter(
                manager=profile.created_by, boundary__isnull=False
            ).first()
            if fallback_block:
                c = fallback_block.boundary.centroid
                fallback_lat, fallback_lng = c.y, c.x
        if fallback_lat is None:
            # Default: Kottayam district, Kerala – rubber plantation heartland
            fallback_lat, fallback_lng = 9.5916, 76.5222
        weather_data = get_weather_for_coordinates(fallback_lat, fallback_lng)

    # Fetch tapper's WageRecords
    wage_records = WageRecord.objects.filter(tapper=request.user).order_by('-month')

    context = {
        'has_profile': True,
        'profile': profile,
        'assignment': assignment,
        'assigned_block': assigned_block,
        'has_assigned_block': assigned_block is not None,
        'today_entry': round(today_entry, 2),
        'monthly_total': round(monthly_total, 2),
        'recent_history': recent_history,
        'my_manager': profile.created_by,
        'manager_photo': manager_photo,
        'block_boundary_json': block_boundary_json,
        'weather_data': weather_data,
        'wage_records': wage_records,
    }
    return render(request, 'dashboard_tapper.html', context)


# ─────────────────────────────────────────────
# ATTENDANCE
# ─────────────────────────────────────────────

@login_required
@role_required('Tapper')
def mark_attendance(request):
    """Marks daily attendance using geo-fenced GPS validation."""
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid request method.'}, status=405)

    try:
        data = json.loads(request.body)
        latitude = float(data.get('latitude'))
        longitude = float(data.get('longitude'))
        accuracy = float(data.get('accuracy', 0))
    except (ValueError, TypeError, json.JSONDecodeError):
        return JsonResponse({'status': 'error', 'message': 'Invalid GPS data format.'}, status=400)

    # Enforce minimum GPS accuracy (increased to 3000 for desktop testing purposes, production should be 30)
    if accuracy > 3000:
        return JsonResponse({'status': 'error', 'message': 'GPS signal too weak. Please try again.'}, status=400)

    try:
        profile = request.user.tapper_profile
    except TapperProfile.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Tapper profile not found.'}, status=403)

    assignment = profile.active_assignment
    if not assignment or not assignment.block:
        return JsonResponse({'status': 'error', 'message': 'You are not assigned to any block.'}, status=400)

    block = assignment.block
    if not block.boundary:
        return JsonResponse({'status': 'error', 'message': 'Your assigned block has no defined boundary.'}, status=400)

    today = timezone.now().date()

    # Check for duplicate attendance early
    if Attendance.objects.filter(tapper=request.user, date=today).exists():
        return JsonResponse({'status': 'error', 'message': 'Attendance already marked for today.'}, status=409)

    # ── Geo-fence validation with exact 10m tolerance (Geography cast) ──
    # Using Raw SQL to guarantee PostGIS ST_DWithin is called correctly with geography casting
    # Django's exact ORM translation for distance can sometimes be tricky with geography fields
    point = Point(longitude, latitude, srid=4326)
    tolerance_meters = 10

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT ST_DWithin(
                boundary::geography,
                ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography,
                %s
            )
            FROM core_block WHERE id = %s
            """,
            [longitude, latitude, tolerance_meters, block.id]
        )
        row = cursor.fetchone()
        is_inside = row[0] if row else False

    if not is_inside:
        return JsonResponse({'status': 'error', 'message': 'Outside boundary.'}, status=403)

    # Record attendance
    try:
        Attendance.objects.create(
            tapper=request.user,
            block=block,
            date=today,
            location=point,
            accuracy_m=accuracy
        )
        return JsonResponse({'status': 'success', 'message': 'Attendance marked successfully!'})
    except IntegrityError:
        return JsonResponse({'status': 'error', 'message': 'Attendance already marked for today.'}, status=409)


# ─────────────────────────────────────────────
# BLOCK MANAGEMENT (Admin & Manager)
# ─────────────────────────────────────────────

@login_required
@role_required('Admin', 'Manager')
def block_list(request):
    role = get_user_role(request.user)
    # Admin sees all blocks, Manager sees only their blocks
    if role == 'Manager':
        blocks = Block.objects.filter(manager=request.user)
    else:
        blocks = Block.objects.all()
    blocks = blocks.annotate(
        active_tappers=Count('assignments', filter=models.Q(assignments__is_active=True))
    )
    if request.method == 'POST':
        name = request.POST.get('name')
        area = request.POST.get('area')
        location = request.POST.get('location', '')
        trees = request.POST.get('number_of_trees', 0)
        if name and area:
            Block.objects.create(
                name=name, area=area, location=location,
                number_of_trees=trees or 0,
                manager=request.user if role == 'Manager' else None
            )
            messages.success(request, f'Block "{name}" created successfully!')
            return redirect('block_list')
        else:
            messages.error(request, 'Block name and area are required.')
    return render(request, 'block_list.html', {'blocks': blocks})


@login_required
@role_required('Manager')
def block_create(request):
    """Dedicated create-block page with Leaflet map for polygon drawing."""
    if request.method == 'POST':
        name = request.POST.get('name')
        area = request.POST.get('area')
        location = request.POST.get('location', '')
        trees = request.POST.get('number_of_trees', 0)
        boundary_str = request.POST.get('boundary', '')
        area_sq_meters = request.POST.get('area_sq_meters', None)

        if not name or not area:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'status': 'error', 'message': 'Block name and area are required.'}, status=400)
            messages.error(request, 'Block name and area are required.')
            return render(request, 'block_create.html')

        # Parse boundary GeoJSON and convert to GEOSGeometry
        boundary = None
        if boundary_str:
            try:
                boundary = GEOSGeometry(boundary_str, srid=4326)
            except Exception:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'status': 'error', 'message': 'Invalid boundary data.'}, status=400)
                messages.error(request, 'Invalid boundary data.')
                return render(request, 'block_create.html')

        if not boundary:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'status': 'error', 'message': 'Please draw a boundary polygon on the map.'}, status=400)
            messages.error(request, 'Please draw a boundary polygon on the map.')
            return render(request, 'block_create.html')

        # ── Spatial overlap prevention (PostGIS) ──
        # Check if the new polygon intersects ANY existing block in the database
        # (The database ExclusionConstraint applies globally)
        overlapping_blocks = Block.objects.filter(
            boundary__isnull=False,
            boundary__intersects=boundary
        )
        if overlapping_blocks.exists():
            overlap_list = []
            for b in overlapping_blocks[:5]:
                overlap_list.append({
                    'id': b.id,
                    'name': b.name,
                    'boundary': json.loads(b.boundary.geojson) if b.boundary else None,
                })
            overlap_names = ', '.join(o['name'] for o in overlap_list)
            error_msg = f'The drawn boundary overlaps with existing block(s): {overlap_names}. Please redraw to avoid overlap.'

            # Return JSON with overlapping GeoJSON for visual feedback
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'status': 'error',
                    'message': error_msg,
                    'overlapping_blocks': overlap_list,
                }, status=409)

            messages.error(request, error_msg)
            return render(request, 'block_create.html', {
                'overlap_geojson': json.dumps(overlap_list),
            })

        from django.db import IntegrityError
        try:
            Block.objects.create(
                name=name,
                area=area,
                location=location,
                number_of_trees=trees or 0,
                boundary=boundary,
                area_sq_meters=float(area_sq_meters) if area_sq_meters else None,
                manager=request.user
            )
        except IntegrityError:
            error_msg = 'Database error: The drawn boundary may overlap with an existing block in the system.'
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'status': 'error', 'message': error_msg}, status=409)
            
            messages.error(request, error_msg)
            return render(request, 'block_create.html')

        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'status': 'success', 'message': f'Block "{name}" created with boundary!'})

        messages.success(request, f'Block "{name}" created with boundary!')
        return redirect('block_list')

    return render(request, 'block_create.html')


@login_required
def api_block_boundary(request, id):
    """Return block boundary GeoJSON as JSON (for AJAX map loading)."""
    role = get_user_role(request.user)
    if role == 'Manager':
        block = get_object_or_404(Block, id=id, manager=request.user)
    elif role == 'Tapper':
        # Tapper can only see their assigned block
        try:
            profile = request.user.tapper_profile
            assignment = profile.active_assignment
            if not assignment or assignment.block.id != id:
                return JsonResponse({'error': 'Not your assigned block'}, status=403)
            block = assignment.block
        except TapperProfile.DoesNotExist:
            return JsonResponse({'error': 'No profile'}, status=404)
    else:
        block = get_object_or_404(Block, id=id)

    return JsonResponse({
        'id': block.id,
        'name': block.name,
        'area': block.area,
        'area_sq_meters': block.area_sq_meters,
        'boundary': json.loads(block.boundary.geojson) if block.boundary else None,
    })


@login_required
@role_required('Admin', 'Manager')
def block_edit(request, id):
    role = get_user_role(request.user)
    if role == 'Manager':
        block = get_object_or_404(Block, id=id, manager=request.user)
    else:
        block = get_object_or_404(Block, id=id)
    if request.method == 'POST':
        name = request.POST.get('name')
        area = request.POST.get('area')
        location = request.POST.get('location', '')
        trees = request.POST.get('number_of_trees', 0)
        if name and area:
            block.name = name
            block.area = area
            block.location = location
            block.number_of_trees = trees or 0
            block.save()
            messages.success(request, f'Block "{name}" updated successfully!')
        else:
            messages.error(request, 'Block name and area are required.')
    return redirect('block_list')


@login_required
@role_required('Admin', 'Manager')
def block_delete(request, id):
    role = get_user_role(request.user)
    if role == 'Manager':
        block = get_object_or_404(Block, id=id, manager=request.user)
    else:
        block = get_object_or_404(Block, id=id)
    if request.method == 'POST':
        name = block.name
        block.delete()
        messages.success(request, f'Block "{name}" deleted successfully!')
    return redirect('block_list')


# ─────────────────────────────────────────────
# TAPPER MANAGEMENT (Admin & Manager)
# ─────────────────────────────────────────────

@login_required
@role_required('Admin', 'Manager')
def tapper_list(request):
    role = get_user_role(request.user)
    # Admin sees all tappers, Manager sees only tappers they created
    if role == 'Manager':
        tappers = TapperProfile.objects.filter(active=True, created_by=request.user).select_related('user')
    else:
        tappers = TapperProfile.objects.filter(active=True).select_related('user')
    # Add active assignment info
    for t in tappers:
        t.current_assignment = t.active_assignment
    if request.method == 'POST':
        username = request.POST.get('username')
        full_name = request.POST.get('full_name', '')
        phone = request.POST.get('phone', '')
        wage = request.POST.get('wage')
        password = request.POST.get('password', 'tapper123')
        photo = request.FILES.get('photo')

        if username and wage:
            if User.objects.filter(username=username).exists():
                messages.error(request, f'Username "{username}" already exists.')
                return redirect('tapper_list')

            # Create user
            name_parts = full_name.split(' ', 1)
            user = User.objects.create_user(
                username=username,
                password=password,
                first_name=name_parts[0] if name_parts else username,
                last_name=name_parts[1] if len(name_parts) > 1 else ''
            )
            # Add to Tapper group
            tapper_group, _ = Group.objects.get_or_create(name='Tapper')
            user.groups.add(tapper_group)

            # Create profile linked to the creating manager
            TapperProfile.objects.create(
                user=user, phone=phone, wage=wage,
                photo=photo,
                created_by=request.user if role == 'Manager' else None
            )
            messages.success(request, f'Tapper account "{username}" created successfully!')
            return redirect('tapper_list')
        else:
            messages.error(request, 'Username and wage are required.')

    return render(request, 'tapper_list.html', {'tappers': tappers})


@login_required
@role_required('Admin', 'Manager')
def tapper_edit(request, id):
    profile = get_object_or_404(TapperProfile, id=id)
    if request.method == 'POST':
        full_name = request.POST.get('full_name', '')
        phone = request.POST.get('phone', '')
        wage = request.POST.get('wage')
        photo = request.FILES.get('photo')

        if wage:
            name_parts = full_name.split(' ', 1)
            profile.user.first_name = name_parts[0] if name_parts else profile.user.username
            profile.user.last_name = name_parts[1] if len(name_parts) > 1 else ''
            profile.user.save()

            profile.phone = phone
            profile.wage = wage
            if photo:
                profile.photo = photo
            profile.save()
            messages.success(request, 'Tapper updated successfully!')
        else:
            messages.error(request, 'Wage is required.')
    return redirect('tapper_list')


@login_required
@role_required('Admin', 'Manager')
def tapper_delete(request, id):
    profile = get_object_or_404(TapperProfile, id=id)
    if request.method == 'POST':
        profile.active = False
        profile.save()
        profile.user.is_active = False
        profile.user.save()
        # Deactivate assignments
        TapperAssignment.objects.filter(tapper=profile, is_active=True).update(is_active=False)
        messages.success(request, f'Tapper "{profile}" deactivated successfully!')
    return redirect('tapper_list')


# ─────────────────────────────────────────────
# TAPPER ASSIGNMENTS (Manager Only)
# ─────────────────────────────────────────────

@login_required
@role_required('Manager')
def tapper_assignments(request):
    # Manager sees only their own tappers and blocks
    my_tappers = TapperProfile.objects.filter(created_by=request.user, active=True)
    my_blocks = Block.objects.filter(manager=request.user)

    active_assignments = TapperAssignment.objects.filter(
        is_active=True, tapper__created_by=request.user
    ).select_related('tapper__user', 'block', 'assigned_by')
    unassigned_tappers = my_tappers.exclude(assignments__is_active=True)

    context = {
        'active_assignments': active_assignments,
        'unassigned_tappers': unassigned_tappers,
        'blocks': my_blocks,
    }
    return render(request, 'tapper_assignments.html', context)


@login_required
@role_required('Manager')
def assignment_create(request):
    if request.method == 'POST':
        tapper_id = request.POST.get('tapper')
        block_id = request.POST.get('block')
        if tapper_id and block_id:
            # Ensure manager owns both the tapper and the block
            tapper = get_object_or_404(TapperProfile, id=tapper_id, active=True, created_by=request.user)
            block = get_object_or_404(Block, id=block_id, manager=request.user)
            TapperAssignment.objects.create(
                tapper=tapper,
                block=block,
                assigned_by=request.user,
                is_active=True
            )
            messages.success(request, f'{tapper} assigned to {block.name} successfully!')
        else:
            messages.error(request, 'Please select both a tapper and a block.')
    return redirect('tapper_assignments')


@login_required
@role_required('Manager')
def assignment_remove(request, id):
    assignment = get_object_or_404(TapperAssignment, id=id)
    if request.method == 'POST':
        assignment.is_active = False
        assignment.save()
        messages.success(request, f'Assignment for {assignment.tapper} removed.')
    return redirect('tapper_assignments')


# ─────────────────────────────────────────────
# LATEX COLLECTION
# ─────────────────────────────────────────────

@login_required
def latex_collection(request):
    role = get_user_role(request.user)

    if role == 'Tapper':
        return _tapper_latex_entry(request)
    else:
        # Admin and Manager can also add collections manually
        return _admin_latex_entry(request)


def _tapper_latex_entry(request):
    """Tapper sees only: assigned block (read-only), date, quantity."""
    try:
        profile = request.user.tapper_profile
    except TapperProfile.DoesNotExist:
        messages.error(request, 'Tapper profile not found. Contact administrator.')
        return redirect('dashboard')

    assignment = profile.active_assignment
    if not assignment:
        messages.warning(request, 'You are not assigned to any block. Contact your manager.')
        return render(request, 'latex_collection.html', {
            'is_tapper': True, 'has_assignment': False
        })

    if request.method == 'POST':
        date_str = request.POST.get('date')
        quantity = request.POST.get('quantity')
        lat = request.POST.get('latitude')
        lng = request.POST.get('longitude')

        if date_str and quantity:
            # Build GPS point if coordinates provided
            location = None
            if lat and lng:
                try:
                    location = Point(float(lng), float(lat), srid=4326)
                except (ValueError, TypeError):
                    location = None

            # Validate GPS is inside block boundary
            if location and assignment.block.boundary:
                if not assignment.block.boundary.contains(location):
                    messages.warning(request, 'Your GPS location is outside the assigned block boundary.')

            LatexCollection.objects.create(
                date=date_str,
                block=assignment.block,
                tapper=profile,
                quantity=quantity,
                location=location
            )
            messages.success(request, f'{quantity}L recorded for {assignment.block.name}!')
            return redirect('tapper_dashboard')
        else:
            messages.error(request, 'Date and quantity are required.')

    return render(request, 'latex_collection.html', {
        'is_tapper': True,
        'has_assignment': True,
        'assigned_block': assignment.block,
    })


def _admin_latex_entry(request):
    """Admin/Manager: full form with block and tapper dropdowns."""
    role = get_user_role(request.user)
    # Manager sees only their blocks/tappers
    if role == 'Manager':
        blocks = Block.objects.filter(manager=request.user)
        tappers = TapperProfile.objects.filter(active=True, created_by=request.user).select_related('user')
    else:
        blocks = Block.objects.all()
        tappers = TapperProfile.objects.filter(active=True).select_related('user')

    if request.method == 'POST':
        date_str = request.POST.get('date')
        block_id = request.POST.get('block')
        tapper_id = request.POST.get('tapper')
        quantity = request.POST.get('quantity')

        if date_str and block_id and tapper_id and quantity:
            block = get_object_or_404(Block, id=block_id)
            tapper = get_object_or_404(TapperProfile, id=tapper_id)
            LatexCollection.objects.create(
                date=date_str, block=block, tapper=tapper, quantity=quantity
            )
            messages.success(request, 'Collection recorded successfully!')
            return redirect('dashboard')
        else:
            messages.error(request, 'All fields are required.')

    return render(request, 'latex_collection.html', {
        'is_tapper': False,
        'blocks': blocks,
        'tappers': tappers,
    })


# ─────────────────────────────────────────────
# REPORTS (Admin & Manager)
# ─────────────────────────────────────────────

@login_required
@role_required('Admin', 'Manager')
def reports(request):
    today = timezone.now().date()
    current_month = today.month
    current_year = today.year
    role = get_user_role(request.user)

    # Scope data: Manager sees only their blocks/tappers
    if role == 'Manager':
        my_blocks = Block.objects.filter(manager=request.user)
        my_tappers = TapperProfile.objects.filter(created_by=request.user, active=True)
        collection_filter = models.Q(block__manager=request.user)
    else:
        my_blocks = Block.objects.all()
        my_tappers = TapperProfile.objects.filter(active=True)
        collection_filter = models.Q()

    # Daily report
    daily_records = LatexCollection.objects.filter(
        collection_filter, date=today
    ).select_related('block', 'tapper__user')
    daily_total = daily_records.aggregate(total=Sum('quantity'))['total'] or 0

    # Monthly totals
    monthly_records = LatexCollection.objects.filter(
        collection_filter,
        date__month=current_month, date__year=current_year
    )
    monthly_total = monthly_records.aggregate(total=Sum('quantity'))['total'] or 0

    # Block-wise breakdown (scoped)
    block_breakdown = my_blocks.annotate(
        monthly_total=Sum(
            'collections__quantity',
            filter=models.Q(
                collections__date__month=current_month,
                collections__date__year=current_year
            )
        )
    ).order_by('-monthly_total')

    max_block_total = 1
    if block_breakdown:
        vals = [b.monthly_total or 0 for b in block_breakdown]
        if vals and max(vals) > 0:
            max_block_total = max(vals)
    for b in block_breakdown:
        b.percentage = int(((b.monthly_total or 0) / max_block_total) * 100) if max_block_total > 0 else 0

    # Top tappers (scoped)
    top_tappers = my_tappers.annotate(
        monthly_total=Sum(
            'collections__quantity',
            filter=models.Q(
                collections__date__month=current_month,
                collections__date__year=current_year
            )
        )
    ).order_by('-monthly_total')[:10]

    # Wage calculations this month (scoped)
    wage_data = my_tappers.annotate(
        days_worked=Count(
            'collections__date',
            filter=models.Q(
                collections__date__month=current_month,
                collections__date__year=current_year
            ),
            distinct=True
        ),
        total_production=Sum(
            'collections__quantity',
            filter=models.Q(
                collections__date__month=current_month,
                collections__date__year=current_year
            )
        )
    ).select_related('user')

    for w in wage_data:
        w.total_wage = (w.days_worked or 0) * w.wage
        w.total_production = w.total_production or 0

    # Daily average
    days_in_month = today.day
    daily_avg = round(monthly_total / days_in_month, 2) if days_in_month > 0 else 0

    context = {
        'daily_records': daily_records,
        'daily_total': round(daily_total, 2),
        'monthly_total': round(monthly_total, 2),
        'block_breakdown': block_breakdown,
        'top_tappers': top_tappers,
        'wage_data': wage_data,
        'current_month_name': today.strftime('%B'),
        'current_year': current_year,
        'daily_avg': daily_avg,
    }
    return render(request, 'reports.html', context)


# ─────────────────────────────────────────────
# EDIT WAGE (Manager/Admin Only)
# ─────────────────────────────────────────────

@login_required
def edit_wage_record(request, record_id):
    """API endpoint to manually override a tapper's total wage."""
    role = get_user_role(request.user)
    if role not in ['Manager', 'Admin']:
        return JsonResponse({'status': 'error', 'message': 'Unauthorized'}, status=403)

    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid request method'}, status=405)

    try:
        data = json.loads(request.body)
        new_wage = float(data.get('new_wage', 0))
    except (ValueError, TypeError, json.JSONDecodeError):
        return JsonResponse({'status': 'error', 'message': 'Invalid wage amount'}, status=400)

    try:
        record = WageRecord.objects.get(id=record_id)
        record.total_wage = new_wage
        record.save()
        
        return JsonResponse({
            'status': 'success',
            'message': 'Wage updated successfully',
            'new_wage': record.total_wage
        })
    except WageRecord.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Wage record not found'}, status=404)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


# ─────────────────────────────────────────────
# CREATE MANAGER (Admin Only)
# ─────────────────────────────────────────────

@login_required
@role_required('Admin')
def create_manager(request):
    managers = User.objects.filter(groups__name='Manager', is_active=True)
    # Load manager profiles for photo display
    for m in managers:
        try:
            m.mgr_profile = m.manager_profile
        except ManagerProfile.DoesNotExist:
            m.mgr_profile = None
    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email', '')
        password = request.POST.get('password')
        full_name = request.POST.get('full_name', '')
        photo = request.FILES.get('photo')

        if username and password:
            if User.objects.filter(username=username).exists():
                messages.error(request, f'Username "{username}" already exists.')
                return redirect('create_manager')

            name_parts = full_name.split(' ', 1)
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                first_name=name_parts[0] if name_parts else username,
                last_name=name_parts[1] if len(name_parts) > 1 else '',
                is_staff=True
            )
            manager_group, _ = Group.objects.get_or_create(name='Manager')
            user.groups.add(manager_group)
            # Create manager profile with photo
            ManagerProfile.objects.create(user=user, photo=photo)
            messages.success(request, f'Manager account "{username}" created successfully!')
            return redirect('create_manager')
        else:
            messages.error(request, 'Username and password are required.')

    return render(request, 'create_manager.html', {'managers': managers})


# ─────────────────────────────────────────────
# MY PROFILE (Manager & Tapper)
# ─────────────────────────────────────────────

@login_required
def my_profile(request):
    role = get_user_role(request.user)
    user = request.user

    # Get or create the appropriate profile
    if role == 'Manager':
        profile, _ = ManagerProfile.objects.get_or_create(user=user)
    elif role == 'Tapper':
        try:
            profile = user.tapper_profile
        except TapperProfile.DoesNotExist:
            profile = None
    else:
        profile = None

    if request.method == 'POST':
        # Update user info
        full_name = request.POST.get('full_name', '')
        email = request.POST.get('email', '')
        phone = request.POST.get('phone', '')
        photo = request.FILES.get('photo')

        name_parts = full_name.split(' ', 1)
        user.first_name = name_parts[0] if name_parts else user.username
        user.last_name = name_parts[1] if len(name_parts) > 1 else ''
        user.email = email
        user.save()

        if role == 'Manager' and profile:
            if photo:
                profile.photo = photo
                profile.save()
            messages.success(request, 'Profile updated successfully!')
        elif role == 'Tapper' and profile:
            profile.phone = phone
            if photo:
                profile.photo = photo
            profile.save()
            messages.success(request, 'Profile updated successfully!')

        return redirect('my_profile')

    context = {
        'role': role,
        'profile': profile,
    }
    return render(request, 'my_profile.html', context)


# ─────────────────────────────────────────────
# LOGOUT
# ─────────────────────────────────────────────

def users_logout(request):
    logout(request)
    return redirect('login')


# ─────────────────────────────────────────────
# INCIDENT REPORTING API
# ─────────────────────────────────────────────

@login_required
@role_required('Tapper')
def api_report_incident(request):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid request method.'}, status=405)

    try:
        profile = request.user.tapper_profile
        assignment = profile.active_assignment
        assigned_block = assignment.block if assignment else None

        if not assigned_block:
            return JsonResponse({'success': False, 'error': 'No active block assignment.'}, status=400)

        # Extract data
        lat = request.POST.get('lat')
        lng = request.POST.get('lng')
        incident_type = request.POST.get('incident_type')
        description = request.POST.get('description')
        severity = request.POST.get('severity')
        photo = request.FILES.get('photo')

        if not all([lat, lng, incident_type, description, severity]):
            return JsonResponse({'success': False, 'error': 'Missing required fields.'}, status=400)

        try:
            point = Point(float(lng), float(lat), srid=4326)
        except ValueError:
            return JsonResponse({'success': False, 'error': 'Invalid GPS coordinates.'}, status=400)

        # Spatial Validation: Must be inside or within ~10 meters (approx 0.0001 degrees)
        # We compute this in Python/GEOS memory on the retrieved block.boundary object
        distance_degrees = assigned_block.boundary.distance(point)
        is_within = assigned_block.boundary.contains(point) or distance_degrees <= 0.0001
        
        
        if not is_within:
            return JsonResponse({'success': False, 'error': 'Incident location rejected! Coordinates are outside your assigned block geometry.'}, status=403)

        # Save Incident
        incident = IncidentReport.objects.create(
            tapper=request.user,
            block=assigned_block,
            incident_type=incident_type,
            description=description,
            severity=severity,
            location=point,
            photo=photo
        )

        return JsonResponse({'success': True, 'message': 'Incident reported and geofenced successfully.', 'incident_id': incident.id})

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@role_required('Manager')
def api_resolve_incident(request, incident_id):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid method.'}, status=405)
        
    incident = get_object_or_404(IncidentReport, id=incident_id)
    
    # Security: Verify this manager owns the block where the incident happened
    if incident.block.manager != request.user:
         return JsonResponse({'success': False, 'error': 'Unauthorized to resolve this incident.'}, status=403)

    incident.status = 'RESOLVED'
    incident.resolved_at = timezone.now()
    incident.resolved_by = request.user
    incident.save()

    return JsonResponse({'success': True, 'message': 'Incident marked as resolved.'})


# ─────────────────────────────────────────────
# API: MONTHLY PRODUCTION TREND
# ─────────────────────────────────────────────

@login_required
def api_monthly_production(request):
    """
    Returns aggregated monthly latex production data for the last 6 months.
    - Manager: scoped to their own blocks.
    - Admin: system-wide (all blocks).
    JSON: { "labels": ["Oct", ...], "production": [120.5, ...] }
    """
    from django.db.models.functions import TruncMonth

    role = get_user_role(request.user)
    if role not in ('Manager', 'Admin'):
        return JsonResponse({'error': 'Unauthorized'}, status=403)

    today = timezone.now().date()
    # Start of 6 months ago (first day of that month)
    six_months_ago = (today.replace(day=1) - datetime.timedelta(days=150)).replace(day=1)

    qs = LatexCollection.objects.filter(date__gte=six_months_ago)
    if role == 'Manager':
        qs = qs.filter(block__manager=request.user)

    monthly = (
        qs
        .annotate(month=TruncMonth('date'))
        .values('month')
        .annotate(total=Sum('quantity'))
        .order_by('month')
    )

    labels = []
    production = []
    for entry in monthly:
        labels.append(entry['month'].strftime('%b %Y'))
        production.append(round(entry['total'] or 0, 2))

    return JsonResponse({'labels': labels, 'production': production})


# ─────────────────────────────────────────────
# API: ASYNC WEATHER (Manager + Admin)
# ─────────────────────────────────────────────

@login_required
def api_weather(request):
    """
    AJAX endpoint for weather data. Keeps the main dashboard page load fast
    by fetching weather asynchronously after the page renders.
    Manager: uses their first block's centroid.
    Admin: uses Kottayam default.
    """
    role = get_user_role(request.user)
    if role not in ('Manager', 'Admin'):
        return JsonResponse({'error': 'Unauthorized'}, status=403)

    if role == 'Manager':
        rep_block = Block.objects.filter(
            manager=request.user
        ).exclude(boundary__isnull=True).first()
        if rep_block and rep_block.boundary:
            centroid = rep_block.boundary.centroid
            weather = get_weather_for_coordinates(centroid.y, centroid.x)
        else:
            weather = get_weather_for_coordinates(9.5916, 76.5222)
    else:
        # Admin: Kottayam, Kerala default
        weather = get_weather_for_coordinates(9.5916, 76.5222)

    return JsonResponse(weather)


# ─────────────────────────────────────────────
# TEMP DEV: SEED DEMO PRODUCTIVITY MAP DATA
# (superuser only, remove after demo)
# ─────────────────────────────────────────────

# @login_required
def dev_seed_productivity(request):
    """Temporary endpoint — forcefully links WageRecords directly to existing PostGIS Blocks."""
    # if not request.user.is_superuser:
    #     return JsonResponse({'error': 'Superuser only'}, status=403)

    import datetime
    import random
    from django.core.cache import cache
    from core.models import Block, TapperProfile, WageRecord, LatexCollection, User

    today = timezone.now().date()
    first_of_month = today.replace(day=1)

    # 1. Get ALL blocks that have boundaries (so they can actually render on the map)
    blocks_with_boundaries = list(Block.objects.exclude(boundary__isnull=True))
    if not blocks_with_boundaries:
        return JsonResponse({'error': 'No blocks found with boundaries in database.'}, status=400)

    # 2. Get active tappers
    tappers = list(User.objects.filter(tapper_profile__active=True))
    if not tappers:
        return JsonResponse({'error': 'No active tappers found.'}, status=400)

    performance_levels = [95.0, 78.0, 110.0, 62.0, 88.0]
    created = 0

    # 3. For each block, force a WageRecord onto a tapper and link them via LatexCollection
    # This guarantees the productivity view's fallback logic connects them perfectly.
    for i, block in enumerate(blocks_with_boundaries):
        tapper = tappers[i % len(tappers)]
        perf = performance_levels[i % len(performance_levels)]
        
        attendance_days = random.randint(18, 26)
        expected_yield = round(attendance_days * 7.5, 1)
        total_latex = round(expected_yield * (perf / 100) * random.uniform(0.95, 1.05), 1)

        daily_rate = 500.0
        per_kg_rate = 12.0
        base_wage  = round(attendance_days * daily_rate, 2)
        production_wage = round(total_latex * per_kg_rate, 2)
        total_wage = round(base_wage + production_wage, 2)

        # Force WageRecord for this month
        WageRecord.objects.update_or_create(
            tapper=tapper,
            month=first_of_month,
            defaults={
                'attendance_days': attendance_days,
                'total_latex_kg': total_latex,
                'daily_rate': daily_rate,
                'per_kg_rate': per_kg_rate,
                'base_wage': base_wage,
                'production_wage': production_wage,
                'total_wage': total_wage,
                'expected_yield': expected_yield,
                'performance_percentage': perf,
            }
        )
        
        # Force a LatexCollection today for this specific block to trigger the fallback logic
        LatexCollection.objects.get_or_create(
            tapper=tapper.tapper_profile,
            block=block,
            date=today,
            defaults={'quantity': round(total_latex / attendance_days, 1)}
        )
        created += 1

    # Clear maps cache
    cache.delete_many([f'mgr_prod_{u.id}_{first_of_month}' for u in User.objects.all()])

    return JsonResponse({
        'success': True,
        'message': f'Forced mapped {created} blocks to WageRecords. Map should now be full of colors!',
    })

def debug_map_blocks(request):
    """Temporary debug view."""
    from core.models import Block, WageRecord
    from django.contrib.auth.models import User
    
    data = []
    blocks = Block.objects.all()
    for b in blocks:
        data.append({
            'name': b.name,
            'manager': b.manager.username if b.manager else 'None',
            'has_boundary': bool(b.boundary)
        })
        
    shibu = User.objects.filter(username__icontains='shibu').first()
    
    return JsonResponse({
        'blocks': data,
        'shibu_found': bool(shibu),
        'shibu_blocks_with_boundary': Block.objects.filter(manager=shibu).exclude(boundary__isnull=True).count() if shibu else 0,
        'march_wages': WageRecord.objects.filter(month='2026-03-01').count()
    })


