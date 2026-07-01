import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
import django
django.setup()
from rest_framework.test import APIRequestFactory
from contributions.views import AdminReportViewSet

class DebugAdminReportViewSet(AdminReportViewSet):
    def initial(self, request, *args, **kwargs):
        try:
            print('get_format_suffix')
            self.format_kwarg = self.get_format_suffix(**kwargs)
        except Exception as exc:
            print('get_format_suffix exception', type(exc), exc)
            raise
        try:
            print('perform_content_negotiation')
            request = self.initialize_request(request, *args, **kwargs)
            neg = self.perform_content_negotiation(request)
            request.accepted_renderer, request.accepted_media_type = neg
        except Exception as exc:
            print('perform_content_negotiation exception', type(exc), exc)
            raise
        try:
            print('determine_version')
            version, scheme = self.determine_version(request, *args, **kwargs)
            request.version, request.versioning_scheme = version, scheme
        except Exception as exc:
            print('determine_version exception', type(exc), exc)
            raise
        try:
            print('perform_authentication')
            self.perform_authentication(request)
        except Exception as exc:
            print('perform_authentication exception', type(exc), exc)
            raise
        try:
            print('check_permissions')
            self.check_permissions(request)
        except Exception as exc:
            print('check_permissions exception', type(exc), exc)
            raise
        try:
            print('check_throttles')
            self.check_throttles(request)
        except Exception as exc:
            print('check_throttles exception', type(exc), exc)
            raise
        super().initial(request, *args, **kwargs)

req = APIRequestFactory().get('/api/members/admin/reports/member-balance/?format=csv')
view = DebugAdminReportViewSet.as_view({'get': 'member_balance'})
try:
    resp = view(req)
    print('status', resp.status_code)
    print('data', getattr(resp, 'data', None))
except Exception as exc:
    import traceback
    print('exception:', type(exc), exc)
    traceback.print_exc()
