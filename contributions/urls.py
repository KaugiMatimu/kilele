from django.urls import path, include
from rest_framework.routers import DefaultRouter
from contributions.views import (
    ContributionViewSet,
    ContributionSummaryView,
    ContributionPlansView,
    ShareViewSet,
    AdminContributionViewSet,
    AdminReportViewSet,
    AdminConfigurationView,
    AdminAuditView,
)

# Create router for standard list/retrieve operations
router = DefaultRouter(trailing_slash='/?')
router.register(r'contributions', ContributionViewSet, basename='contribution')

urlpatterns = [
    # Custom summary and plans endpoints (non-paginated)
    path('contributions/summary/', ContributionSummaryView.as_view(), name='contribution-summary'),
    path('contributions/plans/', ContributionPlansView.as_view(), name='contribution-plans'),
    path('contributions/pay/', ContributionViewSet.as_view({'post': 'pay'}), name='contribution-pay'),
    # Router URLs (for standard list/retrieve)
    path('', include(router.urls)),
    path('shares/', ShareViewSet.as_view({
        'get': 'holdings',
    }), name='shares-holdings'),
    path('shares/transactions/', ShareViewSet.as_view({
        'get': 'transactions',
    }), name='shares-transactions'),
    path('shares/purchase/', ShareViewSet.as_view({
        'post': 'purchase',
    }), name='shares-purchase'),
    # Admin endpoints
    path('admin/config/', AdminConfigurationView.as_view(), name='admin-config'),
    path('admin/audit/', AdminAuditView.as_view(), name='admin-audit'),
    path('admin/contributions/post/', AdminContributionViewSet.as_view({
        'post': 'post_contributions',
    }), name='admin-post-contributions'),
    path('admin/dividends/post/', AdminContributionViewSet.as_view({
        'post': 'post_dividends',
    }), name='admin-post-dividends'),
    # Reporting endpoints
    path('admin/reports/member-balance/', AdminReportViewSet.as_view({
        'get': 'member_balance',
    }), name='admin-report-member-balance'),
    path('admin/reports/branch-summary/', AdminReportViewSet.as_view({
        'get': 'branch_summary',
    }), name='admin-report-branch-summary'),
    path('admin/reports/organization-summary/', AdminReportViewSet.as_view({
        'get': 'organization_summary',
    }), name='admin-report-organization-summary'),
    path('admin/reports/loan-summary/', AdminReportViewSet.as_view({
        'get': 'loan_summary',
    }), name='admin-report-loan-summary'),
    path('admin/reports/interest-report/', AdminReportViewSet.as_view({
        'get': 'interest_report',
    }), name='admin-report-interest-report'),
    path('admin/reports/penalty-report/', AdminReportViewSet.as_view({
        'get': 'penalty_report',
    }), name='admin-report-penalty-report'),
    path('admin/reports/transaction-audit/', AdminReportViewSet.as_view({
        'get': 'transaction_audit',
    }), name='admin-report-transaction-audit'),
]
