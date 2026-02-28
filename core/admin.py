from django.contrib import admin
from .models import Block, TapperProfile, TapperAssignment, LatexCollection, ManagerProfile


@admin.register(Block)
class BlockAdmin(admin.ModelAdmin):
    list_display = ('name', 'area', 'number_of_trees', 'location', 'created_at')
    search_fields = ('name', 'location')


@admin.register(TapperProfile)
class TapperProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'phone', 'wage', 'active', 'created_at')
    list_filter = ('active',)
    search_fields = ('user__username', 'user__first_name', 'phone')


@admin.register(TapperAssignment)
class TapperAssignmentAdmin(admin.ModelAdmin):
    list_display = ('tapper', 'block', 'assigned_by', 'assigned_date', 'is_active')
    list_filter = ('is_active', 'block')


@admin.register(LatexCollection)
class LatexCollectionAdmin(admin.ModelAdmin):
    list_display = ('date', 'time', 'block', 'tapper', 'quantity')
    list_filter = ('date', 'block')
    date_hierarchy = 'date'


@admin.register(ManagerProfile)
class ManagerProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'photo', 'created_at')
