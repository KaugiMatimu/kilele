from rest_framework import serializers
from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    type = serializers.CharField(source='notification_type', read_only=True)
    date = serializers.DateTimeField(source='created_at', read_only=True)
    read = serializers.BooleanField(source='is_read')

    class Meta:
        model = Notification
        fields = ['id', 'type', 'title', 'message', 'date', 'read']
        read_only_fields = ['id', 'type', 'title', 'message', 'date']


class NotificationUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ['is_read']
