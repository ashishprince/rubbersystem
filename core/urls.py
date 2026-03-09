from django.urls import path
from . import views

urlpatterns = [
    # Dashboard router
    path('', views.dashboard, name='dashboard'),

    # Role-specific dashboards
    path('dashboard/admin/', views.admin_dashboard, name='admin_dashboard'),
    path('dashboard/manager/', views.manager_dashboard, name='manager_dashboard'),
    path('dashboard/tapper/', views.tapper_dashboard, name='tapper_dashboard'),

    # Block management (Admin & Manager)
    path('blocks/', views.block_list, name='block_list'),
    path('blocks/add/', views.block_list, name='block_add'),
    path('blocks/create/', views.block_create, name='block_create'),
    path('blocks/edit/<int:id>/', views.block_edit, name='block_edit'),
    path('blocks/delete/<int:id>/', views.block_delete, name='block_delete'),

    # Block boundary API
    path('api/blocks/<int:id>/boundary/', views.api_block_boundary, name='api_block_boundary'),

    # Tapper management (Admin)
    path('tappers/', views.tapper_list, name='tapper_list'),
    path('tappers/add/', views.tapper_list, name='tapper_add'),
    path('tappers/edit/<int:id>/', views.tapper_edit, name='tapper_edit'),
    path('tappers/delete/<int:id>/', views.tapper_delete, name='tapper_delete'),

    # Tapper assignments (Manager)
    path('assignments/', views.tapper_assignments, name='tapper_assignments'),
    path('assignments/create/', views.assignment_create, name='assignment_create'),
    path('assignments/remove/<int:id>/', views.assignment_remove, name='assignment_remove'),

    # Latex collection
    path('latex/collection/', views.latex_collection, name='latex_collection'),
    
    # Reports
    # Reports
    path('reports/', views.reports, name='reports'),

    # Payroll
    path('payroll/generate/', views.generate_payroll, name='generate_payroll'),
    path('payroll/edit/<int:record_id>/', views.edit_wage_record, name='edit_wage_record'),

    # Attendance
    path('attendance/mark/', views.mark_attendance, name='mark_attendance'),

    # Incident Reporting
    path('api/incidents/report/', views.api_report_incident, name='api_report_incident'),
    path('api/incidents/resolve/<int:incident_id>/', views.api_resolve_incident, name='api_resolve_incident'),

    # Admins only
    path('managers/create/', views.create_manager, name='create_manager'),

    # My Profile
    path('profile/', views.my_profile, name='my_profile'),

    # Market Price (Manager only)
    path('market-price/fetch/', views.fetch_market_price, name='fetch_market_price'),

    # Monthly production trend API (Manager + Admin)
    path('api/monthly-production/', views.api_monthly_production, name='api_monthly_production'),

    # Weather data API — async, avoids blocking the dashboard page load
    path('api/weather/', views.api_weather, name='api_weather'),

    # Manager module pages (separated from dashboard for performance)
    path('payroll/', views.manager_payroll, name='manager_payroll'),
    path('incidents/', views.manager_incidents, name='manager_incidents'),
    path('productivity/', views.manager_productivity, name='manager_productivity'),

    # TEMP: seed demo production data — superuser only, remove after demo
    path('dev/seed-production/', views.dev_seed_production, name='dev_seed_production'),
]
