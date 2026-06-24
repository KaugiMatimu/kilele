from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import MemberNotificationViewSet

router = DefaultRouter(trailing_slash='/?')
router.register(r'notifications', MemberNotificationViewSet, basename='member-notification')

urlpatterns = [
    path('', include(router.urls)),
]
