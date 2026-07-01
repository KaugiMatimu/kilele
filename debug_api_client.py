import os
import uuid
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
import django
django.setup()
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

User = get_user_model()
admin_email = f'admin_{uuid.uuid4().hex[:8]}@example.com'
admin = User.objects.create_user(email=admin_email, password='testpass123', full_name='Admin X', role='admin')
client = APIClient()
client.force_authenticate(user=admin)
resp = client.get('/api/members/admin/reports/member-balance/?format=csv')
print('status', resp.status_code)
print('data', getattr(resp, 'data', None))
print('items', list(resp.items()) if hasattr(resp, 'items') else None)
print('wsgi path', resp.wsgi_request.path_info)
print('resolver', getattr(resp.wsgi_request, 'resolver_match', None))
print('user', resp.wsgi_request.user)
print('auth', resp.wsgi_request.auth)
