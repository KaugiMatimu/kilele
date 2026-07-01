import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
import django
django.setup()

from rest_framework.test import APIRequestFactory
from contributions.views import AdminReportViewSet

class DebugReportViewSet(AdminReportViewSet):
    def dispatch(self, request, *args, **kwargs):
        print('dispatch called', request.method, request.path)
        print('action_map', getattr(self, 'action_map', None))
        print('has get', hasattr(self, 'get'))
        return super().dispatch(request, *args, **kwargs)


req = APIRequestFactory().get('/api/members/admin/reports/member-balance/?format=csv')
view = DebugReportViewSet.as_view({'get': 'member_balance'})
print('view actions', getattr(view, 'actions', None))
print('view cls', getattr(view, 'cls', None))
resp = view(req)
print('status', resp.status_code)
print('data', getattr(resp, 'data', None))
print('has rendered', hasattr(resp, 'rendered_content'))
