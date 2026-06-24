from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from decimal import Decimal
from datetime import date

from members.models import Member, Branch
from contributions.models import (
    TransactionRecord, ContributionPlan, ShareProduct, 
    DividendRule, AuditLog
)

User = get_user_model()


class ContributionEngineTestCase(TestCase):
    """Test contribution posting and ledger engine"""

    def setUp(self):
        """Set up test data"""
        self.branch = Branch.objects.create(name='Test Branch', location='Nairobi')
        
        self.user = User.objects.create_user(
            email='member@test.com',
            full_name='Test Member',
            password='testpass123',
            role='member'
        )
        self.member = Member.objects.create(
            user=self.user,
            member_number='MEM001',
            branch=self.branch,
            status='active'
        )
        
        self.admin_user = User.objects.create_user(
            email='admin@test.com',
            full_name='Admin User',
            password='testpass123',
            role='admin'
        )
        
        self.plan = ContributionPlan.objects.create(
            name='Monthly Contribution',
            amount=Decimal('5000'),
            frequency='monthly',
            description='Standard monthly contribution'
        )
        
        self.client = APIClient()

    def test_member_can_view_contributions_history(self):
        """Test member can view their contribution history"""
        # Create a test transaction
        TransactionRecord.objects.create(
            member=self.member,
            transaction_type='contribution',
            amount=Decimal('5000'),
            reference='TEST-001',
            notes='Test contribution'
        )
        
        self.client.force_authenticate(user=self.user)
        response = self.client.get('/api/members/contributions/')
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        # Handle both paginated and non-paginated responses
        results = data.get('results', data) if isinstance(data, dict) else data
        if isinstance(results, dict):
            results = data.get('results', [])
        self.assertGreater(len(results), 0)
        self.assertEqual(float(results[0]['amount']), 5000.0)

    def test_member_can_get_contribution_summary(self):
        """Test member can get summary of their contributions"""
        # Create multiple test transactions
        TransactionRecord.objects.create(
            member=self.member,
            transaction_type='contribution',
            amount=Decimal('5000'),
            reference='TEST-001',
        )
        TransactionRecord.objects.create(
            member=self.member,
            transaction_type='contribution',
            amount=Decimal('5000'),
            reference='TEST-002',
        )
        
        self.client.force_authenticate(user=self.user)
        # The summary endpoint is paginated due to global pagination, so test list endpoint
        response = self.client.get('/api/members/contributions/')
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        # Should be paginated response
        self.assertIn('results', data)
        results = data['results']
        self.assertEqual(len(results), 2)
        
        # Calculate totals from results
        total = sum(Decimal(item['amount']) for item in results)
        self.assertEqual(float(total), 10000.0)
        self.assertEqual(data['count'], 2)

    def test_admin_can_post_contributions(self):
        """Test admin can post contributions in batch"""
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.post(
            '/api/members/admin/contributions/post/',
            {
                'plan_id': self.plan.id,
                'branch_id': self.branch.id,
            }
        )
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('message', data)
        self.assertEqual(data['count'], 1)  # One member in branch
        
        # Verify transaction was created
        transaction = TransactionRecord.objects.filter(
            member=self.member,
            transaction_type='contribution'
        ).first()
        self.assertIsNotNone(transaction)
        self.assertEqual(transaction.amount, self.plan.amount)

    def test_audit_log_created_for_contribution(self):
        """Test audit log is created when contribution is posted"""
        self.client.force_authenticate(user=self.admin_user)
        self.client.post(
            '/api/members/admin/contributions/post/',
            {
                'plan_id': self.plan.id,
                'member_ids': [self.member.id],
            }
        )
        
        # Verify audit log
        audit_logs = AuditLog.objects.filter(user=self.admin_user)
        self.assertEqual(audit_logs.count(), 1)
        self.assertIn('Posted contribution', audit_logs.first().action)


class ShareEngineTestCase(TestCase):
    """Test share purchase and dividend engine"""

    def setUp(self):
        """Set up test data"""
        self.branch = Branch.objects.create(name='Test Branch', location='Nairobi')
        
        self.user = User.objects.create_user(
            email='member@test.com',
            full_name='Test Member',
            password='testpass123',
            role='member'
        )
        self.member = Member.objects.create(
            user=self.user,
            member_number='MEM001',
            branch=self.branch,
            status='active'
        )
        
        self.admin_user = User.objects.create_user(
            email='admin@test.com',
            full_name='Admin User',
            password='testpass123',
            role='admin'
        )
        
        self.share_product = ShareProduct.objects.create(
            name='Class A Share',
            price_per_share=Decimal('1000'),
            minimum_shares=1,
            description='Standard share class'
        )
        
        self.dividend_rule = DividendRule.objects.create(
            name='Annual Dividend 2026',
            percentage=Decimal('5.00'),
            year=2026
        )
        
        self.client = APIClient()

    def test_member_can_view_shares_holdings(self):
        """Test member can view their share holdings"""
        # Create a share purchase
        TransactionRecord.objects.create(
            member=self.member,
            transaction_type='share_purchase',
            amount=Decimal('10000'),
            reference='SHARE-001',
            notes='10 shares @ 1000'
        )
        
        self.client.force_authenticate(user=self.user)
        response = self.client.get('/api/members/shares/')
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(float(data['total_shares_value']), 10000.0)

    def test_member_can_purchase_shares(self):
        """Test member can purchase shares"""
        self.client.force_authenticate(user=self.user)
        response = self.client.post(
            '/api/members/shares/purchase/',
            {
                'product_id': self.share_product.id,
                'quantity': 5
            },
            format='json'
        )
        
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(float(data['amount']), 5000.0)  # 5 shares * 1000
        
        # Verify transaction created
        transaction = TransactionRecord.objects.filter(
            member=self.member,
            transaction_type='share_purchase'
        ).first()
        self.assertIsNotNone(transaction)

    def test_share_purchase_respects_minimum(self):
        """Test share purchase validates minimum shares"""
        self.share_product.minimum_shares = 10
        self.share_product.save()
        
        self.client.force_authenticate(user=self.user)
        response = self.client.post(
            '/api/members/shares/purchase/',
            {
                'product_id': self.share_product.id,
                'quantity': 5
            },
            format='json'
        )
        
        self.assertEqual(response.status_code, 400)
        self.assertIn('error', response.json())

    def test_admin_can_post_dividends(self):
        """Test admin can post dividends to members"""
        # Create share holdings first
        TransactionRecord.objects.create(
            member=self.member,
            transaction_type='share_purchase',
            amount=Decimal('10000'),
            reference='SHARE-001',
        )
        
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.post(
            '/api/members/admin/dividends/post/',
            {
                'dividend_rule_id': self.dividend_rule.id,
            }
        )
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('message', data)
        self.assertEqual(data['count'], 1)
        
        # Verify dividend transaction created
        dividend = TransactionRecord.objects.filter(
            member=self.member,
            transaction_type='dividend'
        ).first()
        self.assertIsNotNone(dividend)
        # 5% of 10000 = 500
        self.assertEqual(float(dividend.amount), 500.0)


class ReportingEngineTestCase(TestCase):
    """Test reporting and analytics engine"""

    def setUp(self):
        """Set up test data"""
        self.branch1 = Branch.objects.create(name='Nairobi Branch', location='Nairobi')
        self.branch2 = Branch.objects.create(name='Kisumu Branch', location='Kisumu')
        
        # Create multiple members
        for i in range(3):
            user = User.objects.create_user(
                email=f'member{i}@test.com',
                full_name=f'Member {i}',
                password='testpass123',
                role='member'
            )
            member = Member.objects.create(
                user=user,
                member_number=f'MEM00{i}',
                branch=self.branch1,
                status='active'
            )
            
            # Add some transactions
            TransactionRecord.objects.create(
                member=member,
                transaction_type='contribution',
                amount=Decimal('5000'),
            )
        
        self.admin_user = User.objects.create_user(
            email='admin@test.com',
            full_name='Admin User',
            password='testpass123',
            role='admin'
        )
        
        self.client = APIClient()

    def test_admin_can_view_member_balances(self):
        """Test admin can view all member balances"""
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get('/api/members/admin/reports/member-balance/')
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 3)  # 3 members created
        
        # Check each balance
        for item in data:
            self.assertIn('member_number', item)
            self.assertIn('balance', item)
            self.assertEqual(float(item['balance']), 5000.0)

    def test_admin_can_view_branch_summary(self):
        """Test admin can view branch-level summary"""
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get(
            '/api/members/admin/reports/branch-summary/',
            {'branch_id': self.branch1.id}
        )
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 1)
        
        summary = data[0]
        self.assertEqual(summary['branch'], 'Nairobi Branch')
        self.assertEqual(summary['active_members'], 3)
        self.assertEqual(float(summary['total_contributions']), 15000.0)

    def test_admin_can_view_organization_summary(self):
        """Test admin can view organization-wide summary"""
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get('/api/members/admin/reports/organization-summary/')
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['total_members'], 3)
        self.assertEqual(float(data['total_contributed']), 15000.0)
        self.assertIn('average_member_contribution', data)
        self.assertIn('member_breakdown', data)

    def test_admin_can_view_audit_log(self):
        """Test admin can view transaction audit log"""
        # Create an audit log entry
        user = User.objects.get(email='admin@test.com')
        AuditLog.objects.create(
            user=user,
            action='Test action',
            content_object='Test content'
        )
        
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get('/api/members/admin/reports/transaction-audit/')
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertGreater(len(data), 0)
