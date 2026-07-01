from django.contrib import admin

from core.admin import custom_admin_site
from .models import LoanProduct, InterestRateRule, PenaltyRule, PaymentAllocationRule, LoanApplication, LoanPayment


class InterestRateRuleInline(admin.TabularInline):
    model = InterestRateRule
    extra = 0


class PenaltyRuleInline(admin.TabularInline):
    model = PenaltyRule
    extra = 0


class LoanPaymentInline(admin.TabularInline):
    model = LoanPayment
    extra = 0
    fields = ('month', 'due_date', 'scheduled_amount', 'is_paid', 'amount_paid', 'paid_date', 'penalty_accrued', 'days_overdue')
    readonly_fields = ('penalty_accrued', 'days_overdue')


class PaymentAllocationRuleInline(admin.TabularInline):
    model = PaymentAllocationRule
    extra = 0
    fields = ('name', 'allocation_order', 'active')


class LoanProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'min_amount', 'max_amount', 'interest_rate', 'duration_months', 'active')
    search_fields = ('name',)
    list_filter = ('active', 'duration_months')
    inlines = (InterestRateRuleInline, PenaltyRuleInline, PaymentAllocationRuleInline)


class LoanApplicationAdmin(admin.ModelAdmin):
    list_display = ('member', 'product', 'amount', 'term_months', 'status', 'submitted_at', 'reviewed_by')
    search_fields = ('member__member_number', 'member__user__full_name', 'product__name')
    list_filter = ('status', 'product')
    raw_id_fields = ('member', 'product', 'reviewed_by')
    inlines = (LoanPaymentInline,)


class LoanPaymentAdmin(admin.ModelAdmin):
    list_display = ('loan_application', 'month', 'due_date', 'is_paid', 'amount_paid', 'days_overdue', 'penalty_accrued')
    search_fields = ('loan_application__member__member_number',)
    list_filter = ('is_paid', 'due_date')
    raw_id_fields = ('loan_application',)
    readonly_fields = ('penalty_accrued', 'days_overdue', 'created_at', 'updated_at')


custom_admin_site.register(LoanProduct, LoanProductAdmin)
custom_admin_site.register(LoanApplication, LoanApplicationAdmin)
custom_admin_site.register(LoanPayment, LoanPaymentAdmin)
