from django.contrib import admin

from core.admin import custom_admin_site
from .models import Notification, NotificationTemplate, WebsiteContent


class NotificationAdmin(admin.ModelAdmin):
    list_display = ('title', 'member', 'notification_type', 'is_read', 'created_at')
    search_fields = ('title', 'message', 'member__member_number')
    list_filter = ('notification_type', 'is_read', 'created_at')
    raw_id_fields = ('member',)
    readonly_fields = ('created_at', 'updated_at')


class NotificationTemplateAdmin(admin.ModelAdmin):
    list_display = ('name', 'event_type', 'active', 'updated_at')
    search_fields = ('name', 'event_type')
    list_filter = ('event_type', 'active')


class WebsiteContentAdmin(admin.ModelAdmin):
    list_display = ('page_slug', 'title', 'is_active', 'updated_at')
    search_fields = ('page_slug', 'title')
    list_filter = ('is_active',)


custom_admin_site.register(Notification, NotificationAdmin)
custom_admin_site.register(NotificationTemplate, NotificationTemplateAdmin)
custom_admin_site.register(WebsiteContent, WebsiteContentAdmin)
