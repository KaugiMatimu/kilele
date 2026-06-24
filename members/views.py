from rest_framework import viewsets, status, generics
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from django.db.models import Sum, Q
from django.http import FileResponse
from io import BytesIO
from datetime import datetime, timedelta, date
from decimal import Decimal
import csv

from members.models import Member, Branch, WorkflowRequest
from contributions.models import TransactionRecord, ContributionPlan, ShareProduct, DividendRule
from loans.models import LoanApplication, LoanProduct, LoanPayment
from loans.utils import get_days_overdue, calculate_penalty_accrual
from notifications.models import NotificationTemplate
from members.serializers import (
    MemberProfileSerializer, MemberProfileUpdateSerializer,
    MemberRegistrationSerializer,
    UserProfileUpdateSerializer,
    TransactionRecordSerializer,
    ContributionPlanSerializer, ShareProductSerializer,
    LoanApplicationSerializer, LoanApplicationCreateSerializer,
    WorkflowRequestSerializer, WorkflowRequestCreateSerializer,
    MemberDashboardSerializer
)


class MemberPermission(IsAuthenticated):
    """Ensure user is an authenticated member"""
    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        return hasattr(request.user, 'member_profile')


class MemberRegistrationView(generics.CreateAPIView):
    """Register a new member account"""
    permission_classes = [AllowAny]
    serializer_class = MemberRegistrationSerializer

    def create(self, request, *args, **kwargs):
        # Development-time logging to help diagnose JSON parse issues.
        try:
            raw = request.body
        except Exception:
            raw = b''
        content_type = request.META.get('CONTENT_TYPE', '')
        print(f"[MemberRegistrationView] CONTENT_TYPE={content_type}")
        try:
            # print as repr to show hidden characters
            print(f"[MemberRegistrationView] raw body repr: {repr(raw)}")
        except Exception:
            pass
        return super().create(request, *args, **kwargs)


class MemberProfileView(generics.RetrieveUpdateAPIView):
    """Get and update member profile"""
    permission_classes = [MemberPermission]
    serializer_class = MemberProfileSerializer

    def get_object(self):
        return self.request.user.member_profile

    def get_serializer_class(self):
        if self.request.method == 'PUT' or self.request.method == 'PATCH':
            return MemberProfileUpdateSerializer
        return MemberProfileSerializer

    @action(detail=False, methods=['put', 'patch'])
    def update_user_profile(self, request):
        """Update user's basic info (email, full_name)"""
        serializer = UserProfileUpdateSerializer(request.user, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ContributionsHistoryView(generics.ListAPIView):
    """View member's contribution history"""
    permission_classes = [MemberPermission]
    serializer_class = TransactionRecordSerializer
    
    def get_queryset(self):
        member = self.request.user.member_profile
        return TransactionRecord.objects.filter(
            member=member,
            transaction_type__in=['contribution', 'dividend']
        ).order_by('-created_at')

    @action(detail=False, methods=['get'])
    def summary(self, request):
        """Get contribution summary statistics"""
        member = request.user.member_profile
        total = TransactionRecord.objects.filter(
            member=member,
            transaction_type='contribution'
        ).aggregate(total=Sum('amount'))['total'] or 0
        
        this_year = TransactionRecord.objects.filter(
            member=member,
            transaction_type='contribution',
            created_at__year=datetime.now().year
        ).aggregate(total=Sum('amount'))['total'] or 0
        
        return Response({
            'total_contributed': str(total),
            'contributed_this_year': str(this_year),
            'transaction_count': TransactionRecord.objects.filter(
                member=member,
                transaction_type='contribution'
            ).count()
        })


class SharesAndBalancesView(generics.ListAPIView):
    """View member's shares and balances"""
    permission_classes = [MemberPermission]
    
    def list(self, request, *args, **kwargs):
        member = request.user.member_profile
        
        # Calculate total shares held
        shares_value = TransactionRecord.objects.filter(
            member=member,
            transaction_type='share_purchase'
        ).aggregate(total=Sum('amount'))['total'] or 0
        
        # Calculate current balance (contributions - withdrawals)
        contributions = TransactionRecord.objects.filter(
            member=member,
            transaction_type='contribution'
        ).aggregate(total=Sum('amount'))['total'] or 0
        
        withdrawals = TransactionRecord.objects.filter(
            member=member,
            transaction_type='withdrawal'
        ).aggregate(total=Sum('amount'))['total'] or 0
        
        available_share_products = ShareProduct.objects.filter(active=True)
        
        return Response({
            'total_shares_value': str(shares_value),
            'total_balance': str(contributions - withdrawals),
            'contributions': str(contributions),
            'withdrawals': str(withdrawals),
            'available_products': ShareProductSerializer(available_share_products, many=True).data
        })


class LoanApplicationViewSet(viewsets.ModelViewSet):
    """Manage loan applications"""
    permission_classes = [MemberPermission]
    
    def get_queryset(self):
        member = self.request.user.member_profile
        return LoanApplication.objects.filter(member=member)

    def get_serializer_class(self):
        if self.action == 'create':
            return LoanApplicationCreateSerializer
        return LoanApplicationSerializer

    def perform_create(self, serializer):
        member = self.request.user.member_profile
        serializer.save(member=member)

    @action(detail=False, methods=['get'])
    def available_products(self, request):
        """Get available loan products"""
        products = LoanProduct.objects.filter(active=True)
        serializer = LoanProductSerializer(products, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def repayment_schedule(self, request, pk=None):
        """Get loan repayment schedule with payment history"""
        loan = self.get_object()
        
        # Calculate monthly payment
        monthly_rate = (Decimal(str(loan.product.interest_rate)) / Decimal('100')) / Decimal('12')
        n_payments = loan.term_months
        principal = Decimal(str(loan.amount))
        
        if monthly_rate == 0:
            monthly_payment = principal / Decimal(str(n_payments))
        else:
            numerator = monthly_rate * (1 + monthly_rate) ** n_payments
            denominator = (1 + monthly_rate) ** n_payments - 1
            monthly_payment = principal * numerator / denominator
        
        # Generate schedule with payment tracking
        schedule = []
        balance = principal
        start_date = loan.submitted_at.date() if loan.submitted_at else date.today()
        total_paid = Decimal('0')
        total_penalty = Decimal('0')
        
        for month in range(1, n_payments + 1):
            interest = balance * monthly_rate
            principal_payment = monthly_payment - interest
            balance -= principal_payment
            due_date = start_date + timedelta(days=30*month)
            
            # Get payment record if it exists
            payment_record = LoanPayment.objects.filter(
                loan_application=loan,
                month=month
            ).first()
            
            # Calculate current penalty if overdue and not paid
            penalty = Decimal('0')
            days_overdue = 0
            is_paid = False
            amount_paid = Decimal('0')
            paid_date = None
            
            if payment_record:
                is_paid = payment_record.is_paid
                amount_paid = payment_record.amount_paid
                paid_date = payment_record.paid_date
                penalty = payment_record.penalty_accrued
                days_overdue = payment_record.days_overdue
            else:
                # Calculate dynamic penalty if overdue
                days_overdue = get_days_overdue(due_date)
                if days_overdue > 0:
                    penalty_rules = list(loan.product.penalty_rules.filter(active=True).values(
                        'name', 'penalty_amount', 'description'
                    ))
                    penalty = calculate_penalty_accrual(due_date, days_overdue, penalty_rules)
            
            if is_paid:
                total_paid += amount_paid
            
            total_penalty += penalty
            
            schedule.append({
                'month': month,
                'due_date': str(due_date),
                'principal': str(round(principal_payment, 2)),
                'interest': str(round(interest, 2)),
                'payment': str(round(monthly_payment, 2)),
                'balance': str(round(max(Decimal('0'), balance), 2)),
                'is_paid': is_paid,
                'amount_paid': str(round(amount_paid, 2)),
                'paid_date': str(paid_date) if paid_date else None,
                'days_overdue': days_overdue,
                'penalty_accrued': str(round(penalty, 2)),
                'payment_status': 'paid' if is_paid else ('overdue' if days_overdue > 0 else 'pending')
            })
        
        return Response({
            'loan_id': loan.id,
            'amount': str(loan.amount),
            'interest_rate': str(loan.product.interest_rate),
            'term_months': loan.term_months,
            'monthly_payment': str(round(monthly_payment, 2)),
            'total_paid': str(round(total_paid, 2)),
            'total_penalty_accrued': str(round(total_penalty, 2)),
            'schedule': schedule
        })

    @action(detail=True, methods=['get'])
    def penalties(self, request, pk=None):
        """Return penalty and interest breakdown with accrued amounts"""
        loan = self.get_object()
        product = loan.product

        # Get penalty and interest rules
        penalty_rules = list(product.penalty_rules.filter(active=True).values('name', 'penalty_amount', 'description'))
        interest_rules = list(product.interest_rules.filter(active=True).values('name', 'rate'))

        # Calculate totals from payment records
        monthly_rate = Decimal(str(product.interest_rate)) / Decimal('100') / Decimal('12')
        outstanding_principal = Decimal(str(loan.amount))
        
        # Get all payments for this loan
        payments = LoanPayment.objects.filter(loan_application=loan)
        
        total_accrued_penalty = payments.aggregate(total=Sum('penalty_accrued'))['total'] or Decimal('0')
        total_paid = payments.aggregate(total=Sum('amount_paid'))['total'] or Decimal('0')
        total_principal_paid = payments.filter(is_paid=True).aggregate(total=Sum('principal'))['total'] or Decimal('0')
        
        # Estimate monthly interest on remaining balance
        remaining_balance = outstanding_principal - total_principal_paid
        estimated_monthly_interest = remaining_balance * monthly_rate
        
        # Count overdue payments and accumulate dynamic penalties for missed installments
        today = date.today()
        overdue_payments = 0
        unpaid_penalty = Decimal('0')
        start_date = loan.submitted_at.date() if loan.submitted_at else today
        penalty_rules = list(product.penalty_rules.filter(active=True).values('name', 'penalty_amount', 'description'))
        
        for month in range(1, loan.term_months + 1):
            scheduled_due_date = start_date + timedelta(days=30 * month)
            existing_payment = payments.filter(month=month).first()
            due_date = existing_payment.due_date if existing_payment else scheduled_due_date
            
            if due_date < today and (not existing_payment or not existing_payment.is_paid):
                overdue_payments += 1
                days_overdue = get_days_overdue(due_date, today)
                if days_overdue > 0:
                    if not existing_payment:
                        unpaid_penalty += calculate_penalty_accrual(due_date, days_overdue, penalty_rules)
                    elif not existing_payment.is_paid and existing_payment.penalty_accrued == Decimal('0'):
                        unpaid_penalty += calculate_penalty_accrual(due_date, days_overdue, penalty_rules)
        
        total_accrued_penalty = total_accrued_penalty + unpaid_penalty
        
        return Response({
            'loan_id': loan.id,
            'product': product.name,
            'outstanding_principal': str(round(outstanding_principal, 2)),
            'total_paid': str(round(total_paid, 2)),
            'remaining_balance': str(round(remaining_balance, 2)),
            'interest_rate': str(product.interest_rate),
            'estimated_monthly_interest': str(round(estimated_monthly_interest, 2)),
            'total_accrued_penalty': str(round(total_accrued_penalty, 2)),
            'unpaid_overdue_penalty': str(round(unpaid_penalty, 2)),
            'overdue_payment_count': overdue_payments,
            'penalty_rules': penalty_rules,
            'interest_rules': interest_rules,
        })


class WorkflowRequestViewSet(viewsets.ModelViewSet):
    """Handle withdrawal and exit requests"""
    permission_classes = [MemberPermission]
    
    def get_queryset(self):
        member = self.request.user.member_profile
        return WorkflowRequest.objects.filter(member=member)

    def get_serializer_class(self):
        if self.action == 'create':
            return WorkflowRequestCreateSerializer
        return WorkflowRequestSerializer

    def perform_create(self, serializer):
        member = self.request.user.member_profile
        serializer.save(member=member)

    @action(detail=False, methods=['post'])
    def request_withdrawal(self, request):
        """Request funds withdrawal"""
        data = {
            'request_type': 'withdrawal',
            'amount': request.data.get('amount'),
            'description': request.data.get('description', '')
        }
        serializer = WorkflowRequestCreateSerializer(data=data)
        if serializer.is_valid():
            member = request.user.member_profile
            serializer.save(member=member)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['post'])
    def request_exit(self, request):
        """Request membership exit"""
        data = {
            'request_type': 'exit',
            'description': request.data.get('reason', '')
        }
        serializer = WorkflowRequestCreateSerializer(data=data)
        if serializer.is_valid():
            member = request.user.member_profile
            serializer.save(member=member)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class MemberDashboardView(generics.RetrieveAPIView):
    """Member dashboard with aggregated financial position"""
    permission_classes = [MemberPermission]
    serializer_class = MemberDashboardSerializer

    def get_object(self):
        member = self.request.user.member_profile
        
        # Calculate totals
        total_contributions = TransactionRecord.objects.filter(
            member=member,
            transaction_type='contribution'
        ).aggregate(total=Sum('amount'))['total'] or 0
        
        total_shares = TransactionRecord.objects.filter(
            member=member,
            transaction_type='share_purchase'
        ).aggregate(total=Sum('amount'))['total'] or 0
        
        # Outstanding loans
        outstanding = LoanApplication.objects.filter(
            member=member,
            status__in=['approved', 'disbursed']
        ).aggregate(total=Sum('amount'))['total'] or 0
        
        # Pending requests
        pending = WorkflowRequest.objects.filter(
            member=member,
            status='pending'
        ).count()
        
        # Recent transactions
        recent_txns = TransactionRecord.objects.filter(
            member=member
        ).order_by('-created_at')[:5]
        
        # Active loans
        active_loans = LoanApplication.objects.filter(
            member=member,
            status__in=['approved', 'disbursed']
        )
        
        # Build aggregated object
        class DashboardData:
            def __init__(self):
                self.member_number = member.member_number
                self.full_name = member.user.full_name
                self.status = member.status
                self.joined_date = member.joined_date
                self.total_contributions = total_contributions
                self.total_shares = total_shares
                self.total_loans_outstanding = outstanding
                self.pending_requests = pending
                self.recent_transactions = recent_txns
                self.active_loans = active_loans
        
        return DashboardData()


class StatementsExportView(generics.RetrieveAPIView):
    """Download account statements"""
    permission_classes = [MemberPermission]

    def retrieve(self, request, *args, **kwargs):
        member = request.user.member_profile
        format_type = request.query_params.get('format', 'csv')
        
        transactions = TransactionRecord.objects.filter(member=member).order_by('-created_at')
        
        if format_type == 'csv':
            output = BytesIO()
            writer = csv.writer(output)
            writer.writerow(['Date', 'Type', 'Amount', 'Reference', 'Notes'])
            
            for txn in transactions:
                writer.writerow([
                    txn.created_at.strftime('%Y-%m-%d'),
                    txn.get_transaction_type_display(),
                    txn.amount,
                    txn.reference,
                    txn.notes
                ])
            
            output.seek(0)
            filename = f"statement_{member.member_number}_{datetime.now().strftime('%Y%m%d')}.csv"
            return FileResponse(output, as_attachment=True, filename=filename)
        
        return Response({'error': 'Format not supported'}, status=status.HTTP_400_BAD_REQUEST)
