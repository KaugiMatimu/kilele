from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from decimal import Decimal
from datetime import date, timedelta

from rest_framework.test import APIClient

from loans.models import LoanProduct, LoanApplication, LoanPayment, PenaltyRule
from loans.utils import calculate_monthly_payment, get_days_overdue, calculate_penalty_accrual
from members.models import Member, Branch

User = get_user_model()


class LoanUtilsTestCase(TestCase):
    """Test loan calculation utilities"""

    def test_calculate_monthly_payment_zero_interest(self):
        """Test monthly payment calculation with zero interest"""
        principal = Decimal('10000')
        annual_rate = Decimal('0')
        months = 12
        
        result = calculate_monthly_payment(principal, annual_rate, months)
        expected = Decimal('833.33')
        
        # Allow small rounding differences
        self.assertAlmostEqual(float(result), float(expected), places=2)

    def test_calculate_monthly_payment_with_interest(self):
        """Test monthly payment calculation with interest"""
        principal = Decimal('50000')
        annual_rate = Decimal('10')  # 10% per year
        months = 12
        
        result = calculate_monthly_payment(principal, annual_rate, months)
        # Result should be a positive decimal
        self.assertGreater(result, Decimal('0'))
        self.assertLess(result, principal)  # Monthly payment should be less than principal

    def test_get_days_overdue_not_overdue(self):
        """Test days overdue when payment is not overdue"""
        today = date(2026, 6, 25)
        due_date = date(2026, 6, 30)
        
        days = get_days_overdue(due_date, today)
        self.assertEqual(days, 0)

    def test_get_days_overdue_is_overdue(self):
        """Test days overdue when payment is overdue"""
        today = date(2026, 6, 25)
        due_date = date(2026, 6, 20)
        
        days = get_days_overdue(due_date, today)
        self.assertEqual(days, 5)

    def test_calculate_penalty_accrual(self):
        """Test penalty accrual calculation"""
        due_date = date(2026, 6, 20)
        days_overdue = 5
        penalty_rules = [
            {'name': 'Late Payment Fee', 'penalty_amount': Decimal('100')},
            {'name': 'Admin Fee', 'penalty_amount': Decimal('50')},
        ]
        
        penalty = calculate_penalty_accrual(due_date, days_overdue, penalty_rules)
        expected = Decimal('150')  # 100 + 50
        
        self.assertEqual(penalty, expected)


class LoanApplicationTestCase(TestCase):
    """Test loan application models and calculations"""

    def setUp(self):
        """Set up test data"""
        # Create a branch
        self.branch = Branch.objects.create(name='Test Branch', location='Nairobi')
        
        # Create a user and member
        self.user = User.objects.create_user(
            email='member@test.com',
            full_name='Test Member',
            password='testpass123'
        )
        self.member = Member.objects.create(
            user=self.user,
            member_number='MEM001',
            branch=self.branch,
            status='active'
        )
        
        # Create a loan product
        self.product = LoanProduct.objects.create(
            name='Personal Loan',
            min_amount=Decimal('10000'),
            max_amount=Decimal('100000'),
            interest_rate=Decimal('10'),
            duration_months=12
        )
        
        # Create penalty rule
        self.penalty_rule = PenaltyRule.objects.create(
            loan_product=self.product,
            name='Late Payment Penalty',
            penalty_amount=Decimal('500')
        )

    def test_loan_application_creation(self):
        """Test creating a loan application"""
        loan = LoanApplication.objects.create(
            member=self.member,
            product=self.product,
            amount=Decimal('50000'),
            term_months=12,
            purpose='Business Expansion'
        )
        
        self.assertEqual(loan.status, 'pending')
        self.assertEqual(loan.amount, Decimal('50000'))
        self.assertEqual(str(loan), 'Personal Loan application for MEM001 (pending)')

    def test_loan_payment_creation(self):
        """Test creating loan payment records"""
        loan = LoanApplication.objects.create(
            member=self.member,
            product=self.product,
            amount=Decimal('50000'),
            term_months=12,
            purpose='Business Expansion',
            status='disbursed'
        )
        
        due_date = date.today() + timedelta(days=30)
        payment = LoanPayment.objects.create(
            loan_application=loan,
            month=1,
            due_date=due_date,
            scheduled_amount=Decimal('4500'),
            principal=Decimal('4166.67'),
            interest=Decimal('333.33')
        )
        
        self.assertEqual(payment.is_paid, False)
        self.assertEqual(payment.amount_paid, Decimal('0'))
        self.assertEqual(payment.days_overdue, 0)

    def test_loan_payment_mark_paid(self):
        """Test marking a loan payment as paid"""
        loan = LoanApplication.objects.create(
            member=self.member,
            product=self.product,
            amount=Decimal('50000'),
            term_months=12,
            status='disbursed'
        )
        
        payment = LoanPayment.objects.create(
            loan_application=loan,
            month=1,
            due_date=date.today(),
            scheduled_amount=Decimal('4500'),
            principal=Decimal('4166.67'),
            interest=Decimal('333.33')
        )
        
        # Mark as paid
        payment.is_paid = True
        payment.amount_paid = Decimal('4500')
        payment.paid_date = date.today()
        payment.save()
        
        payment.refresh_from_db()
        self.assertEqual(payment.is_paid, True)
        self.assertEqual(payment.amount_paid, Decimal('4500'))

    def test_loan_payment_overdue_calculation(self):
        """Test overdue day calculation for loan payment"""
        loan = LoanApplication.objects.create(
            member=self.member,
            product=self.product,
            amount=Decimal('50000'),
            term_months=12,
            status='disbursed'
        )
        
        # Create payment that was due 5 days ago
        due_date = date.today() - timedelta(days=5)
        payment = LoanPayment.objects.create(
            loan_application=loan,
            month=1,
            due_date=due_date,
            scheduled_amount=Decimal('4500'),
            principal=Decimal('4166.67'),
            interest=Decimal('333.33')
        )
        
        days_overdue = get_days_overdue(payment.due_date)
        self.assertEqual(days_overdue, 5)

    def test_loan_payment_unique_constraint(self):
        """Test that loan can only have one payment per month"""
        loan = LoanApplication.objects.create(
            member=self.member,
            product=self.product,
            amount=Decimal('50000'),
            term_months=12,
            status='disbursed'
        )
        
        due_date = date.today() + timedelta(days=30)
        
        # Create first payment
        LoanPayment.objects.create(
            loan_application=loan,
            month=1,
            due_date=due_date,
            scheduled_amount=Decimal('4500'),
            principal=Decimal('4166.67'),
            interest=Decimal('333.33')
        )
        
        # Try to create duplicate - should raise IntegrityError
        with self.assertRaises(Exception):
            LoanPayment.objects.create(
                loan_application=loan,
                month=1,
                due_date=due_date,
                scheduled_amount=Decimal('4500'),
                principal=Decimal('4166.67'),
                interest=Decimal('333.33')
            )


class RepaymentScheduleEndpointTestCase(TestCase):
    """Test repayment schedule API endpoint"""

    def setUp(self):
        """Set up test data"""
        self.branch = Branch.objects.create(name='Test Branch', location='Nairobi')
        
        self.user = User.objects.create_user(
            email='member@test.com',
            full_name='Test Member',
            password='testpass123'
        )
        self.member = Member.objects.create(
            user=self.user,
            member_number='MEM001',
            branch=self.branch,
            status='active'
        )
        
        self.product = LoanProduct.objects.create(
            name='Personal Loan',
            min_amount=Decimal('10000'),
            max_amount=Decimal('100000'),
            interest_rate=Decimal('12'),
            duration_months=12
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_repayment_schedule_has_all_months(self):
        """Test that repayment schedule contains all months"""
        loan = LoanApplication.objects.create(
            member=self.member,
            product=self.product,
            amount=Decimal('50000'),
            term_months=12,
            status='disbursed'
        )

        response = self.client.get(f'/api/members/loans/{loan.id}/repayment_schedule/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['loan_id'], loan.id)
        self.assertEqual(len(data['schedule']), loan.term_months)
        self.assertIn('payment_status', data['schedule'][0])

    def test_penalties_endpoint_returns_breakdown(self):
        """Test that penalties endpoint returns penalty and interest breakdown"""
        loan = LoanApplication.objects.create(
            member=self.member,
            product=self.product,
            amount=Decimal('50000'),
            term_months=12,
            status='disbursed'
        )

        PenaltyRule.objects.create(
            loan_product=self.product,
            name='Late Fee',
            penalty_amount=Decimal('500')
        )

        response = self.client.get(f'/api/members/loans/{loan.id}/penalties/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['loan_id'], loan.id)
        self.assertIn('outstanding_principal', data)
        self.assertIn('total_accrued_penalty', data)
        self.assertIn('penalty_rules', data)
        self.assertIsInstance(data['penalty_rules'], list)

    def test_penalties_endpoint_accrues_unpaid_overdue_penalty(self):
        """Test that overdue unpaid schedule installments still accrue penalties"""
        loan = LoanApplication.objects.create(
            member=self.member,
            product=self.product,
            amount=Decimal('50000'),
            term_months=12,
            status='disbursed'
        )

        PenaltyRule.objects.create(
            loan_product=self.product,
            name='Late Fee',
            penalty_amount=Decimal('500')
        )

        due_date = date.today() - timedelta(days=10)
        LoanPayment.objects.create(
            loan_application=loan,
            month=1,
            due_date=due_date,
            scheduled_amount=Decimal('4500'),
            principal=Decimal('4166.67'),
            interest=Decimal('333.33')
        )

        response = self.client.get(f'/api/members/loans/{loan.id}/penalties/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertGreater(Decimal(data['unpaid_overdue_penalty']), Decimal('0'))
        self.assertEqual(int(data['overdue_payment_count']), 1)

    def test_repayment_schedule_marks_paid_payments(self):
        """Test that scheduled payments with payment records are marked as paid"""
        loan = LoanApplication.objects.create(
            member=self.member,
            product=self.product,
            amount=Decimal('50000'),
            term_months=12,
            status='disbursed'
        )

        due_date = date.today() + timedelta(days=30)
        LoanPayment.objects.create(
            loan_application=loan,
            month=1,
            due_date=due_date,
            scheduled_amount=Decimal('4500'),
            principal=Decimal('4166.67'),
            interest=Decimal('333.33'),
            amount_paid=Decimal('4500'),
            is_paid=True,
            paid_date=date.today(),
            penalty_accrued=Decimal('0'),
            days_overdue=0,
        )

        response = self.client.get(f'/api/members/loans/{loan.id}/repayment_schedule/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        paid_schedule = next((item for item in data['schedule'] if item['month'] == 1), None)
        self.assertIsNotNone(paid_schedule)
        self.assertEqual(paid_schedule['payment_status'], 'paid')
        self.assertEqual(Decimal(paid_schedule['amount_paid']), Decimal('4500'))
        self.assertEqual(Decimal(paid_schedule['penalty_accrued']), Decimal('0'))
