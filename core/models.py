from django.contrib.gis.db import models
from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.auth.models import User
from django.utils import timezone


class Block(models.Model):
    name = models.CharField(max_length=100)
    area = models.FloatField(help_text="Area in acres")
    number_of_trees = models.PositiveIntegerField(default=0, help_text="Number of rubber trees")
    location = models.TextField(blank=True, null=True)
    boundary = models.PolygonField(srid=4326, spatial_index=True, blank=True, null=True, help_text="PostGIS polygon boundary")
    area_sq_meters = models.FloatField(blank=True, null=True, help_text="Computed area in square meters")
    area_sq_m = models.FloatField(null=True, blank=True, help_text="PostGIS calculated area in square meters")
    area_hectares = models.FloatField(null=True, blank=True, help_text="PostGIS calculated area in hectares")
    minimum_daily_yield = models.FloatField(default=30)
    manager = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='managed_blocks',
        help_text="Manager who owns this block", null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.boundary:
            from django.db import connection
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE core_block SET "
                    "area_sq_m = ST_Area(boundary::geography), "
                    "area_hectares = ST_Area(boundary::geography) / 10000.0 "
                    "WHERE id = %s", [self.id]
                )

    class Meta:
        constraints = [
            ExclusionConstraint(
                name='exclude_overlapping_blocks',
                expressions=[
                    ('boundary', '&&'),
                ],
            ),
        ]


class TapperProfile(models.Model):
    """One-to-one link between a Django User and a Tapper identity."""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='tapper_profile')
    phone = models.CharField(max_length=15, blank=True, null=True)
    wage = models.DecimalField(max_digits=10, decimal_places=2, help_text="Daily wage in Rupees")
    active = models.BooleanField(default=True)
    photo = models.ImageField(upload_to='profile_photos/tappers/', blank=True, null=True)
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='created_tappers', help_text="Manager who created this tapper"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.user.get_full_name() or self.user.username

    @property
    def active_assignment(self):
        """Return the currently active TapperAssignment, or None."""
        return self.assignments.filter(is_active=True).first()


class TapperAssignment(models.Model):
    """Tracks which block a tapper is currently assigned to. Only one active at a time."""
    tapper = models.ForeignKey(TapperProfile, on_delete=models.CASCADE, related_name='assignments')
    block = models.ForeignKey(Block, on_delete=models.CASCADE, related_name='assignments')
    assigned_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='assignments_made')
    assigned_date = models.DateField(default=timezone.now)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-assigned_date']

    def __str__(self):
        status = "Active" if self.is_active else "Inactive"
        return f"{self.tapper} → {self.block.name} ({status})"

    def save(self, *args, **kwargs):
        # Deactivate any previous active assignment for this tapper
        if self.is_active:
            TapperAssignment.objects.filter(
                tapper=self.tapper, is_active=True
            ).exclude(pk=self.pk).update(is_active=False)
        super().save(*args, **kwargs)


class LatexCollection(models.Model):
    date = models.DateField(default=timezone.now)
    time = models.TimeField(auto_now_add=True)
    block = models.ForeignKey(Block, on_delete=models.CASCADE, related_name='collections')
    tapper = models.ForeignKey(TapperProfile, on_delete=models.CASCADE, related_name='collections')
    quantity = models.FloatField(help_text="Quantity in liters")
    location = models.PointField(srid=4326, blank=True, null=True, help_text="GPS location at time of collection")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date', '-time']
        unique_together = ['tapper', 'date']

    def __str__(self):
        return f"{self.quantity}L from {self.block.name} by {self.tapper} on {self.date}"


class ManagerProfile(models.Model):
    """Profile for managers — stores photo and optional extras."""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='manager_profile')
    photo = models.ImageField(upload_to='profile_photos/managers/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.user.get_full_name() or self.user.username


class Attendance(models.Model):
    tapper = models.ForeignKey(User, on_delete=models.CASCADE, related_name='attendance_records')
    block = models.ForeignKey(Block, on_delete=models.CASCADE, related_name='attendance_records')
    date = models.DateField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    location = models.PointField(srid=4326, help_text="GPS location at time of check-in")
    accuracy_m = models.FloatField(null=True, blank=True, help_text="GPS accuracy in meters")

    class Meta:
        ordering = ['-date', '-created_at']
        unique_together = ['tapper', 'date']

    def __str__(self):
        return f"Attendance: {self.tapper.username} at {self.block.name} on {self.date}"

class IncidentReport(models.Model):
    """Geo-tagged incident reports submitted by tappers."""
    INCIDENT_TYPES = [
        ('PEST', 'Pest Attack'),
        ('DAMAGE', 'Tree Damage'),
        ('FLOOD', 'Flooding'),
        ('EQUIP', 'Equipment Issue'),
        ('INJURY', 'Injury'),
        ('THEFT', 'Theft'),
        ('OTHER', 'Other'),
    ]

    SEVERITY_LEVELS = [
        ('LOW', 'Low'),
        ('MEDIUM', 'Medium'),
        ('HIGH', 'High'),
    ]

    STATUS_CHOICES = [
        ('OPEN', 'Open'),
        ('IN_PROGRESS', 'In Progress'),
        ('RESOLVED', 'Resolved'),
    ]

    tapper = models.ForeignKey(User, on_delete=models.CASCADE, related_name='incident_reports')
    block = models.ForeignKey(Block, on_delete=models.CASCADE, related_name='incident_reports')
    incident_type = models.CharField(max_length=20, choices=INCIDENT_TYPES)
    description = models.TextField(help_text="Detailed description of the incident")
    photo = models.ImageField(upload_to='incident_photos/', null=True, blank=True)
    
    # GPS geometry with explicit spatial index
    location = models.PointField(srid=4326, spatial_index=True, help_text="GPS coordinates of the incident")
    
    severity = models.CharField(max_length=10, choices=SEVERITY_LEVELS)
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='OPEN')
    
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='resolved_incidents')

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.get_incident_type_display()} in {self.block.name} by {self.tapper.username}"


class WageRecord(models.Model):
    tapper = models.ForeignKey(User, on_delete=models.CASCADE)
    month = models.DateField()  # first day of month

    attendance_days = models.IntegerField()
    total_latex_kg = models.FloatField()

    daily_rate = models.FloatField(default=500)
    per_kg_rate = models.FloatField(default=12)

    base_wage = models.FloatField()
    production_wage = models.FloatField()
    total_wage = models.FloatField()

    expected_yield = models.FloatField()
    performance_percentage = models.FloatField()

    generated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('tapper', 'month')

    def __str__(self):
        return f"WageRecord: {self.tapper.username} - {self.month.strftime('%Y-%m')} - ₹{self.total_wage}"
