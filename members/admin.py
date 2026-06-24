from django.contrib import admin

from core.admin import custom_admin_site
from .models import Branch, Member, WorkflowRequest


class BranchAdmin(admin.ModelAdmin):
    list_display = ('name', 'location', 'created_at')
    search_fields = ('name', 'location')
    list_filter = ('location',)


class MemberAdmin(admin.ModelAdmin):
    list_display = ('member_number', 'user', 'branch', 'status', 'joined_date')
    search_fields = ('member_number', 'user__email', 'user__full_name')
    list_filter = ('status', 'branch')
    raw_id_fields = ('user', 'branch')


class WorkflowRequestAdmin(admin.ModelAdmin):
    list_display = ('member', 'request_type', 'amount', 'status', 'submitted_at', 'reviewed_by')
    search_fields = ('member__member_number', 'member__user__full_name', 'reference')
    list_filter = ('request_type', 'status', 'submitted_at')
    raw_id_fields = ('member', 'reviewed_by')


custom_admin_site.register(Branch, BranchAdmin)
custom_admin_site.register(Member, MemberAdmin)
custom_admin_site.register(WorkflowRequest, WorkflowRequestAdmin)
