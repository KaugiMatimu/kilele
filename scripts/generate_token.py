import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import RefreshToken

User = get_user_model()
email = 'felixkaugi@gmail.com'
try:
    user = User.objects.get(email=email)
    refresh = RefreshToken.for_user(user)
    print('ACCESS_TOKEN=' + str(refresh.access_token))
    print('REFRESH_TOKEN=' + str(refresh))
except Exception as e:
    print('ERROR', e)
