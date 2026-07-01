import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
import django
django.setup()
from rest_framework.test import APIRequestFactory
from contributions.views import AdminReportViewSet

req = APIRequestFactory().get('/api/members/admin/reports/member-balance/?format=csv')
view = AdminReportViewSet.as_view({'get': 'member_balance'})
resp = view(req)
print('view actions', getattr(view, 'actions', None))
print('status', resp.status_code)
print('data', getattr(resp, 'data', None))
print('headers', dict(resp.items()) if hasattr(resp, 'items') else None)
