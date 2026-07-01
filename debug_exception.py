import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
import django
django.setup()
from rest_framework.test import APIRequestFactory
from contributions.views import AdminReportViewSet

class DebugAdminReportViewSet(AdminReportViewSet):
    def initialize_request(self, request, *args, **kwargs):
        print('initialize_request', type(request), getattr(request, 'path', None), getattr(request, 'method', None))
        return super().initialize_request(request, *args, **kwargs)

    def initial(self, request, *args, **kwargs):
        print('initial called')
        try:
            return super().initial(request, *args, **kwargs)
        except Exception as e:
            print('initial exception', type(e), e)
            raise

    def dispatch(self, request, *args, **kwargs):
        print('dispatch called', request.method, request.path)
        resp = super().dispatch(request, *args, **kwargs)
        print('after dispatch resp', getattr(resp, 'status_code', None))
        return resp

    def handle_exception(self, exc):
        print('handle_exception', type(exc), exc)
        return super().handle_exception(exc)

    def member_balance(self, request):
        print('member_balance handler reached')
        return super().member_balance(request)

req = APIRequestFactory().get('/api/members/admin/reports/member-balance/?format=csv')
view = DebugAdminReportViewSet.as_view({'get': 'member_balance'})
resp = view(req)
print('final status', resp.status_code)
print('final data', getattr(resp, 'data', None))
