from django.contrib import admin

from core.admin import custom_admin_site
from .models import ContributionPlan, ShareProduct, ContributionDeadline, DividendRule, TransactionRecord, AuditLog


class ContributionPlanAdmin(admin.ModelAdmin):
    list_display = ('name', 'amount', 'frequency', 'active')
    search_fields = ('name',)
    list_filter = ('frequency', 'active')


class ShareProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'price_per_share', 'minimum_shares', 'active')
    search_fields = ('name',)
    list_filter = ('active',)


class ContributionDeadlineAdmin(admin.ModelAdmin):
    list_display = ('name', 'due_date', 'active')
    search_fields = ('name',)
    list_filter = ('active',)


class DividendRuleAdmin(admin.ModelAdmin):
    list_display = ('name', 'year', 'percentage', 'active')
    search_fields = ('name',)
    list_filter = ('year', 'active')


class TransactionRecordAdmin(admin.ModelAdmin):
    list_display = ('member', 'transaction_type', 'amount', 'reference', 'created_at')
    search_fields = ('member__member_number', 'member__user__full_name', 'reference')
    list_filter = ('transaction_type', 'created_at')
    raw_id_fields = ('member',)


class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('timestamp', 'user', 'action', 'content_object')
    search_fields = ('user__email', 'action', 'content_object')
    list_filter = ('timestamp',)
    readonly_fields = ('timestamp',)


custom_admin_site.register(ContributionPlan, ContributionPlanAdmin)
custom_admin_site.register(ShareProduct, ShareProductAdmin)
custom_admin_site.register(ContributionDeadline, ContributionDeadlineAdmin)
custom_admin_site.register(DividendRule, DividendRuleAdmin)
custom_admin_site.register(TransactionRecord, TransactionRecordAdmin)
custom_admin_site.register(AuditLog, AuditLogAdmin)
