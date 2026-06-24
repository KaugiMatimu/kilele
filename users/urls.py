from django.urls import path
from .views import AdminRegistrationView, PasswordResetRequestView, PasswordResetConfirmView

app_name = 'users'

urlpatterns = [
    path('register/', AdminRegistrationView.as_view(), name='admin-register'),
    path('register', AdminRegistrationView.as_view(), name='admin-register-no-slash'),
    path('password-reset/', PasswordResetRequestView.as_view(), name='password-reset'),
    path('password-reset', PasswordResetRequestView.as_view(), name='password-reset-no-slash'),
    path('password-reset-confirm/<uidb64>/<token>/', PasswordResetConfirmView.as_view(), name='password-reset-confirm'),
    path('password-reset-confirm/<uidb64>/<token>', PasswordResetConfirmView.as_view(), name='password-reset-confirm-no-slash'),
]
