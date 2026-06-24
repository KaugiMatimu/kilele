from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _

from core.admin import custom_admin_site
from .models import AdminInvitation, User


class UserAdmin(BaseUserAdmin):
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        (_('Personal info'), {'fields': ('full_name', 'role', 'branch')}),
        (_('Permissions'), {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        (_('Important dates'), {'fields': ('last_login', 'date_joined')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'full_name', 'role', 'branch', 'password1', 'password2'),
        }),
    )
    list_display = ('email', 'full_name', 'role', 'branch', 'is_staff', 'is_active')
    list_filter = ('role', 'is_staff', 'is_active', 'branch')
    search_fields = ('email', 'full_name')
    ordering = ('email',)
    filter_horizontal = ('groups', 'user_permissions')


custom_admin_site.register(User, UserAdmin)
custom_admin_site.register(AdminInvitation)
