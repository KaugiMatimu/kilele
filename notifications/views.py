from rest_framework import viewsets, status, generics
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Q

from .models import Notification
from .serializers import NotificationSerializer, NotificationUpdateSerializer


class MemberNotificationViewSet(viewsets.ModelViewSet):
    """
    API endpoint for member notifications.
    - GET /api/members/notifications/ - List all notifications for the logged-in member
    - GET /api/members/notifications/?unread=true - List only unread notifications
    - PATCH /api/members/notifications/{id}/ - Mark as read/unread
    - POST /api/members/notifications/mark_all_as_read/ - Mark all as read
    """
    permission_classes = [IsAuthenticated]
    serializer_class = NotificationSerializer

    def get_queryset(self):
        """Return notifications for the logged-in member"""
        if not hasattr(self.request.user, 'member_profile'):
            return Notification.objects.none()
        
        member = self.request.user.member_profile
        queryset = Notification.objects.filter(member=member)
        
        # Filter by unread if specified
        unread = self.request.query_params.get('unread')
        if unread and unread.lower() == 'true':
            queryset = queryset.filter(is_read=False)
        
        return queryset

    def get_serializer_class(self):
        if self.action in ['partial_update', 'update']:
            return NotificationUpdateSerializer
        return NotificationSerializer

    @action(detail=False, methods=['post'])
    def mark_all_as_read(self, request):
        """Mark all notifications as read for the logged-in member"""
        if not hasattr(request.user, 'member_profile'):
            return Response(
                {'detail': 'User is not a member'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        member = request.user.member_profile
        unread_count = Notification.objects.filter(
            member=member,
            is_read=False
        ).update(is_read=True)
        
        return Response({
            'message': f'{unread_count} notification(s) marked as read'
        })

    def partial_update(self, request, *args, **kwargs):
        """Allow patching of notifications"""
        return super().partial_update(request, *args, **kwargs)

