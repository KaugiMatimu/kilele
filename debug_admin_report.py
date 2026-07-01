import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
import django
django.setup()

from django.urls import resolve
from rest_framework.test import APIRequestFactory, APIClient
from contributions.views import AdminReportViewSet
from django.contrib.auth import get_user_model

print('resolve path')
match = resolve('/api/members/admin/reports/member-balance/')
print('view name', match.view_name)
print('func', match.func)
print('route', getattr(match, 'route', None))
print('--- direct view invocation ---')
req = APIRequestFactory().get('/api/members/admin/reports/member-balance/?format=csv')
view = AdminReportViewSet.as_view({'get': 'member_balance'})
print('view actions', getattr(view, 'actions', None))
print('view cls', getattr(view, 'cls', None))
resp = view(req)
print('status', resp.status_code)
print('data', getattr(resp, 'data', None))
print('type', type(resp))
print('--- APIClient invocation ---')
User = get_user_model()
admin = User.objects.create_user(email='adminx@example.com', password='testpass123', full_name='Admin X', role='admin')
client = APIClient()
client.force_authenticate(user=admin)
resp2 = client.get('/api/members/admin/reports/member-balance/?format=csv')
print('api status', resp2.status_code)
print('api data', getattr(resp2, 'data', None))
print('api items', list(resp2.items()))
print('api path', resp2.wsgi_request.path_info)
print('api resolver', getattr(resp2.wsgi_request, 'resolver_match', None))
print('api resolver name', resp2.wsgi_request.resolver_match.view_name if resp2.wsgi_request.resolver_match else None)
print('api request headers', dict(resp2.wsgi_request.headers))
