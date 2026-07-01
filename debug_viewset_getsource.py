import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
import django
django.setup()
import inspect
from rest_framework.viewsets import ViewSetMixin
from rest_framework.views import APIView

print('ViewSetMixin.dispatch source:')
print(inspect.getsource(ViewSetMixin.dispatch))
print('APIView.dispatch source:')
print(inspect.getsource(APIView.dispatch))
