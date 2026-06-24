from django.urls import path, include
from rest_framework.routers import DefaultRouter
from contributions.views import (
    ContributionViewSet,
    ContributionSummaryView,
    ContributionPlansView,
    ShareViewSet,
    AdminContributionViewSet,
    AdminReportViewSet,
)

# Create router for standard list/retrieve operations
router = DefaultRouter(trailing_slash='/?')
router.register(r'contributions', ContributionViewSet, basename='contribution')

urlpatterns = [
    # Custom summary and plans endpoints (non-paginated)
    path('contributions/summary/', ContributionSummaryView.as_view(), name='contribution-summary'),
    path('contributions/plans/', ContributionPlansView.as_view(), name='contribution-plans'),
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
    path('admin/reports/transaction-audit/', AdminReportViewSet.as_view({
        'get': 'transaction_audit',
    }), name='admin-report-transaction-audit'),
]
