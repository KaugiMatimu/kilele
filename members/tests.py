from django.test import TestCase
from django.contrib.auth import get_user_model
from decimal import Decimal
from rest_framework.test import APIClient

from members.models import Member
from contributions.models import TransactionRecord


class MemberReportsTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user_model = get_user_model()
        self.user = self.user_model.objects.create_user(
            email='member@example.com',
            password='secret123',
            full_name='Test Member',
            role='member',
        )
        self.member = Member.objects.create(
            user=self.user,
            member_number='M1001',
            status='active',
        )
        TransactionRecord.objects.create(
            member=self.member,
            transaction_type='contribution',
            amount=Decimal('1200.00'),
            reference='CONTRIB-001',
            notes='Monthly contribution',
        )
        TransactionRecord.objects.create(
            member=self.member,
            transaction_type='share_purchase',
            amount=Decimal('300.00'),
            reference='SHARE-001',
            notes='Share purchase',
        )
        TransactionRecord.objects.create(
            member=self.member,
            transaction_type='withdrawal',
            amount=Decimal('100.00'),
            reference='WDR-001',
            notes='Withdrawal',
        )

    def test_member_can_view_report_summary(self):
        self.client.force_authenticate(self.user)

        response = self.client.get('/api/members/reports/summary/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['member_number'], 'M1001')
        self.assertEqual(response.json()['summary']['contributions'], '1200.00')
        self.assertEqual(response.json()['summary']['shares'], '300.00')
        self.assertEqual(response.json()['summary']['current_balance'], '1100.00')

    def test_member_can_download_report_summary_csv(self):
        self.client.force_authenticate(self.user)

        response = self.client.get('/api/members/reports/summary/?format=csv')

        self.assertEqual(response.status_code, 200)
        self.assertIn('attachment; filename=', response['Content-Disposition'])
        self.assertIn('report_summary', response['Content-Disposition'])
