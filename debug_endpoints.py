import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from django.urls import resolve, path
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model
from members.models import Member, Branch
from contributions.models import TransactionRecord
from decimal import Decimal

# Check URL resolution
print("=== URL Resolution ===")
try:
    match = resolve('/api/members/contributions/summary/')
    print(f"Summary URL resolves to: {match.view_name}")
    print(f"Match kwargs: {match.kwargs}")
except Exception as e:
    print(f"Error resolving summary URL: {e}")

try:
    match = resolve('/api/members/contributions/')
    print(f"List URL resolves to: {match.view_name}")
    print(f"Match kwargs: {match.kwargs}")
except Exception as e:
    print(f"Error resolving list URL: {e}")

User = get_user_model()

# Clean up
User.objects.all().delete()
Branch.objects.all().delete()

branch = Branch.objects.create(name='Test Branch', location='Nairobi')
user = User.objects.create_user(email='member@test.com', full_name='Test Member', password='testpass123', role='member')
member = Member.objects.create(user=user, member_number='MEM001', branch=branch, status='active')

TransactionRecord.objects.create(member=member, transaction_type='contribution', amount=Decimal('5000'), reference='TEST-001')
TransactionRecord.objects.create(member=member, transaction_type='contribution', amount=Decimal('5000'), reference='TEST-002')

client = APIClient()
client.force_authenticate(user=user)

# Test list endpoint
print("\n=== List endpoint ===")
response = client.get('/api/members/contributions/')
print(f"Status: {response.status_code}")
print(f"Response type: {type(response.data)}")
if response.status_code == 200:
    data = response.data
    if isinstance(data, dict) and 'results' in data:
        print(f"Paginated response with {data.get('count')} items")
    else:
        print(f"Response keys: {list(data.keys()) if isinstance(data, dict) else 'Not a dict'}")

# Test summary endpoint
print("\n=== Summary endpoint ===")
response = client.get('/api/members/contributions/summary/')
print(f"Status: {response.status_code}")
print(f"Response type: {type(response.data)}")
if response.status_code == 200:
    data = response.data
    print(f"Response keys: {list(data.keys()) if isinstance(data, dict) else 'Not a dict'}")
    print(f"Response: {data}")

