import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
import django
django.setup()
from rest_framework.test import APIRequestFactory
from contributions.views import AdminReportViewSet

class DebugAdminReportViewSet(AdminReportViewSet):
    def member_balance(self, request):
        print('member_balance invoked')
        return super().member_balance(request)

req = APIRequestFactory().get('/api/members/admin/reports/member-balance/?format=csv')
view = DebugAdminReportViewSet.as_view({'get': 'member_balance'})
print('view actions', view.actions)
resp = view(req)
print('response status', resp.status_code)
print('response data', getattr(resp, 'data', None))
