import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from django.contrib.auth import get_user_model
from django.test import Client
from rest_framework_simplejwt.tokens import RefreshToken
from members.models import Member

User = get_user_model()
user = User.objects.filter(email='testprofile@example.com').first()
if not user:
    user = User.objects.create_user(email='testprofile@example.com', password='testpass123', full_name='Test Profile')
    Member.objects.create(user=user, member_number='TP123', status='active')
refresh = RefreshToken.for_user(user)
access = str(refresh.access_token)
print('accessToken=' + access)
client = Client()
resp = client.get('/api/members/profile/', HTTP_AUTHORIZATION=f'Bearer {access}')
print('status=', resp.status_code)
print(resp.content.decode())
