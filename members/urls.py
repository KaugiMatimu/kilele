from django.urls import path, include
from rest_framework.routers import DefaultRouter
from members.views import (
    MemberRegistrationView,
    MemberProfileView,
    ContributionsHistoryView,
    SharesAndBalancesView,
    LoanApplicationViewSet,
    WorkflowRequestViewSet,
    MemberDashboardView,
    StatementsExportView
)

router = DefaultRouter(trailing_slash='/?')
router.register(r'loans', LoanApplicationViewSet, basename='loan-application')
router.register(r'requests', WorkflowRequestViewSet, basename='workflow-request')

urlpatterns = [
    path('register/', MemberRegistrationView.as_view(), name='member-register'),
    # Accept requests both with and without a trailing slash to avoid RuntimeError
    # when POSTs arrive without the trailing slash (common from proxies/frontend).
    path('register', MemberRegistrationView.as_view(), name='member-register-no-slash'),
    path('', include(router.urls)),
    path('profile', MemberProfileView.as_view(), name='member-profile-no-slash'),
    path('profile/', MemberProfileView.as_view(), name='member-profile'),
    path('contributions/', ContributionsHistoryView.as_view(), name='contributions-history'),
    path('contributions/summary/', ContributionsHistoryView.as_view(), name='contributions-summary'),
    path('shares-balances/', SharesAndBalancesView.as_view(), name='shares-balances'),
    path('dashboard/', MemberDashboardView.as_view(), name='member-dashboard'),
    path('statements/export/', StatementsExportView.as_view(), name='statements-export'),
]
