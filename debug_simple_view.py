import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
import django
django.setup()

from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory

class Foo(viewsets.ViewSet):
    @action(detail=False, methods=['get'])
    def bar(self, request):
        return Response({'ok': 1})

req = APIRequestFactory().get('/bar/?format=csv')
view = Foo.as_view({'get': 'bar'})
resp = view(req)
print('status', resp.status_code)
print('data', getattr(resp, 'data', None))
print('items', list(resp.items()) if hasattr(resp, 'items') else None)
