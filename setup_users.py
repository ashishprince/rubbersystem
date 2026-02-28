#!/usr/bin/env python
"""Setup script to create roles, users, and sample data."""

import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rubber_system.settings')
django.setup()

from django.contrib.auth.models import User, Group
from core.models import Block, TapperProfile, TapperAssignment, ManagerProfile

# ── Create Groups ──
manager_group, _ = Group.objects.get_or_create(name='Manager')
tapper_group, _ = Group.objects.get_or_create(name='Tapper')
print("✅ Groups 'Manager' and 'Tapper' created.")

# ── Create Admin (Superuser) ──
if not User.objects.filter(username='admin').exists():
    admin_user = User.objects.create_superuser(
        username='admin', password='admin123',
        first_name='System', last_name='Admin',
        email='admin@plantation.com'
    )
    print(f"   Admin: admin / admin123")
else:
    admin_user = User.objects.get(username='admin')
    print("   Admin already exists.")

# ── Create Manager 1: Rajesh Kumar ──
if not User.objects.filter(username='manager').exists():
    mgr1 = User.objects.create_user(
        username='manager', password='manager123',
        first_name='Rajesh', last_name='Kumar',
        email='rajesh@plantation.com', is_staff=True
    )
    mgr1.groups.add(manager_group)
    print(f"   Manager: manager / manager123")
else:
    mgr1 = User.objects.get(username='manager')
    print("   Manager 'manager' already exists.")

# ── Create Manager 2: Suresh Nair ──
if not User.objects.filter(username='manager2').exists():
    mgr2 = User.objects.create_user(
        username='manager2', password='manager123',
        first_name='Suresh', last_name='Nair',
        email='suresh@plantation.com', is_staff=True
    )
    mgr2.groups.add(manager_group)
    print(f"   Manager: manager2 / manager123")
else:
    mgr2 = User.objects.get(username='manager2')
    print("   Manager 'manager2' already exists.")

# ── Ensure ManagerProfiles exist ──
ManagerProfile.objects.get_or_create(user=mgr1)
ManagerProfile.objects.get_or_create(user=mgr2)
print("✅ Manager profiles ensured.")

# ── Create Blocks (owned by Manager 1) ──
block_a, _ = Block.objects.get_or_create(
    name='North Division A', defaults={'area': 5.0, 'number_of_trees': 200, 'location': 'North sector', 'manager': mgr1}
)
block_b, _ = Block.objects.get_or_create(
    name='South Division B', defaults={'area': 3.5, 'number_of_trees': 150, 'location': 'South sector', 'manager': mgr1}
)
# Block owned by Manager 2
block_c, _ = Block.objects.get_or_create(
    name='East Division C', defaults={'area': 4.0, 'number_of_trees': 180, 'location': 'East sector', 'manager': mgr2}
)
print("✅ Sample blocks created (linked to managers).")

# ── Create Tapper 1 (created by Manager 1) ──
if not User.objects.filter(username='tapper1').exists():
    t1_user = User.objects.create_user(
        username='tapper1', password='tapper123',
        first_name='Biju', last_name='Thomas'
    )
    t1_user.groups.add(tapper_group)
    t1_profile = TapperProfile.objects.create(
        user=t1_user, phone='9876543210', wage=850.00, created_by=mgr1
    )
    # Assign tapper1 to block A (by manager1)
    TapperAssignment.objects.create(
        tapper=t1_profile, block=block_a, assigned_by=mgr1, is_active=True
    )
    print(f"   Tapper: tapper1 / tapper123 (belongs to Rajesh Kumar)")
else:
    print("   Tapper 'tapper1' already exists.")

# ── Create Tapper 2 (created by Manager 2) ──
if not User.objects.filter(username='tapper2').exists():
    t2_user = User.objects.create_user(
        username='tapper2', password='tapper123',
        first_name='Anil', last_name='Raj'
    )
    t2_user.groups.add(tapper_group)
    t2_profile = TapperProfile.objects.create(
        user=t2_user, phone='9876543211', wage=900.00, created_by=mgr2
    )
    # Assign tapper2 to block C (by manager2)
    TapperAssignment.objects.create(
        tapper=t2_profile, block=block_c, assigned_by=mgr2, is_active=True
    )
    print(f"   Tapper: tapper2 / tapper123 (belongs to Suresh Nair)")
else:
    print("   Tapper 'tapper2' already exists.")

print()
print("=" * 50)
print("  SETUP COMPLETE — Login Credentials")
print("=" * 50)
print("  Admin:     admin / admin123    (sees everything)")
print("  Manager 1: manager / manager123 (Rajesh Kumar)")
print("  Manager 2: manager2 / manager123 (Suresh Nair)")
print("  Tapper 1:  tapper1 / tapper123  (under Rajesh)")
print("  Tapper 2:  tapper2 / tapper123  (under Suresh)")
print("=" * 50)
