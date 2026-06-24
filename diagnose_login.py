import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
import django
django.setup()
from django.conf import settings
from django.contrib.auth import get_user_model, authenticate
User = get_user_model()
print('ADMIN_EMAIL', settings.ADMIN_EMAIL)
print('ADMIN_PASSWORD', settings.ADMIN_PASSWORD)
print('DB ENGINE', settings.DATABASES['default']['ENGINE'])
print('DB NAME', settings.DATABASES['default'].get('NAME'))
print('Total users:', User.objects.count())
for u in User.objects.all():
    print('USER', u.email, 'staff', u.is_staff, 'superuser', u.is_superuser, 'role', u.role)
user = User.objects.filter(email__iexact=settings.ADMIN_EMAIL).first()
print('admin exists', bool(user))
if user:
    print('admin flags', user.is_staff, user.is_superuser, user.role)
    print('password hash', user.password)
    print('check_password', user.check_password(settings.ADMIN_PASSWORD))
    print('auth_email', authenticate(email=settings.ADMIN_EMAIL, password=settings.ADMIN_PASSWORD))
    print('auth_username', authenticate(username=settings.ADMIN_EMAIL, password=settings.ADMIN_PASSWORD))
