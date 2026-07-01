import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
import django
django.setup()

import traceback
from rest_framework.test import APIRequestFactory
from contributions.views import AdminReportViewSet

req = APIRequestFactory().get('/api/members/admin/reports/member-balance/?format=csv')
view = AdminReportViewSet.as_view({'get': 'member_balance'})
try:
    resp = view(req)
    print('RESP STATUS', resp.status_code)
    print('RESP DATA', getattr(resp, 'data', None))
except Exception as exc:
    print('EXCEPTION', type(exc), exc)
    traceback.print_exc()
