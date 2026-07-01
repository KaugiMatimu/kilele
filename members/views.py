from rest_framework import viewsets, status, generics
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from django.db.models import Sum, Q
from django.http import FileResponse
from django.core.exceptions import ObjectDoesNotExist
from io import BytesIO, StringIO
from datetime import datetime, timedelta, date
from decimal import Decimal
import csv


def _render_statement_xlsx(member, transactions):
    try:
        from openpyxl import Workbook
    except ImportError:
        raise ImportError('openpyxl is required to export statements as Excel. Install openpyxl.')

    output = BytesIO()
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = 'Statement'
    headers = ['Date', 'Type', 'Amount', 'Reference', 'Notes']
    sheet.append(headers)

    for txn in transactions:
        sheet.append([
            txn.created_at.strftime('%Y-%m-%d'),
            txn.get_transaction_type_display(),
            str(txn.amount),
            txn.reference,
            txn.notes,
        ])

    for col in sheet.columns:
        max_length = 0
        column = col[0].column_letter
        for cell in col:
            if cell.value is not None:
                max_length = max(max_length, len(str(cell.value)))
        sheet.column_dimensions[column].width = min(max_length + 2, 50)

    workbook.save(output)
    output.seek(0)
    return output


def _render_statement_pdf(member, transactions):
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.pdfgen import canvas
        from reportlab.lib.units import inch
    except ImportError:
        raise ImportError('reportlab is required to export statements as PDF. Install reportlab.')

    output = BytesIO()
    c = canvas.Canvas(output, pagesize=letter)
    width, height = letter
    margin = inch
    y = height - margin

    c.setFont('Helvetica-Bold', 14)
    c.drawString(margin, y, f'Statement for {member.user.full_name} ({member.member_number})')
    y -= 0.3 * inch

    c.setFont('Helvetica', 10)
    c.drawString(margin, y, f'Generated: {datetime.now().strftime("%Y-%m-%d")}')
    y -= 0.4 * inch

    headers = ['Date', 'Type', 'Amount', 'Reference', 'Notes']
    c.setFont('Helvetica-Bold', 9)
    x_positions = [margin, margin + 1.7 * inch, margin + 3.3 * inch, margin + 4.3 * inch, margin + 5.4 * inch]
    for idx, header in enumerate(headers):
        c.drawString(x_positions[idx], y, header)
    y -= 0.25 * inch
    c.setFont('Helvetica', 9)

    for txn in transactions:
        if y < margin + 0.5 * inch:
            c.showPage()
            y = height - margin
            c.setFont('Helvetica-Bold', 9)
            for idx, header in enumerate(headers):
                c.drawString(x_positions[idx], y, header)
            y -= 0.25 * inch
            c.setFont('Helvetica', 9)

        row = [
            txn.created_at.strftime('%Y-%m-%d'),
            txn.get_transaction_type_display(),
            str(txn.amount),
            txn.reference,
            txn.notes,
        ]
        for idx, value in enumerate(row):
            text = str(value) if value is not None else ''
            if idx == 4 and len(text) > 40:
                text = text[:37] + '...'
            c.drawString(x_positions[idx], y, text)
        y -= 0.22 * inch

    c.save()
    output.seek(0)
    return output

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
    LoanProductSerializer,
    LoanApplicationSerializer, LoanApplicationCreateSerializer,
    WorkflowRequestSerializer, WorkflowRequestCreateSerializer,
    MemberDashboardSerializer
)


class MemberPermission(IsAuthenticated):
    """Ensure user is an authenticated member"""
    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False

        try:
            return request.user.member_profile is not None
        except ObjectDoesNotExist:
            return False
        except AttributeError:
            return False


class MemberOrStaffPermission(IsAuthenticated):
    """Allow authenticated members or staff users to access loan workflows"""
    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False

        user = request.user
        try:
            if user.is_staff or getattr(user, 'role', None) in ['admin', 'branch_manager', 'accountant']:
                return True
            return user.member_profile is not None
        except (ObjectDoesNotExist, AttributeError):
            return False


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


class MemberReportSummaryView(generics.GenericAPIView):
    """Return a member-friendly report summary and allow download as CSV."""
    permission_classes = [MemberPermission]

    def get(self, request, *args, **kwargs):
        member = request.user.member_profile

        contributions = TransactionRecord.objects.filter(
            member=member,
            transaction_type='contribution'
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

        shares = TransactionRecord.objects.filter(
            member=member,
            transaction_type='share_purchase'
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

        withdrawals = TransactionRecord.objects.filter(
            member=member,
            transaction_type='withdrawal'
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

        current_balance = contributions - withdrawals
        def money(value):
            return format(value.quantize(Decimal('0.01')), '.2f') if isinstance(value, Decimal) else format(Decimal(str(value)).quantize(Decimal('0.01')), '.2f')

        summary = {
            'contributions': money(contributions),
            'shares': money(shares),
            'withdrawals': money(withdrawals),
            'current_balance': money(current_balance),
        }

        format_type = request.query_params.get('format', 'json').lower().strip().rstrip('/')
        if format_type == 'csv':
            output = BytesIO()
            text_output = StringIO()
            writer = csv.writer(text_output)
            writer.writerow(['Metric', 'Value'])
            writer.writerow(['Member Number', member.member_number])
            writer.writerow(['Member Name', member.user.full_name])
            writer.writerow(['Contributions', summary['contributions']])
            writer.writerow(['Shares', summary['shares']])
            writer.writerow(['Withdrawals', summary['withdrawals']])
            writer.writerow(['Current Balance', summary['current_balance']])
            output.write(text_output.getvalue().encode('utf-8'))
            output.seek(0)
            filename = f"report_summary_{member.member_number}_{datetime.now().strftime('%Y%m%d')}.csv"
            return FileResponse(output, as_attachment=True, filename=filename, content_type='text/csv')

        return Response({
            'member_number': member.member_number,
            'member_name': member.user.full_name,
            'summary': summary,
            'generated_at': datetime.now().isoformat(),
        })


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
    permission_classes = [MemberOrStaffPermission]
    
    def get_queryset(self):
        user = self.request.user
        if self._is_staff_or_finance(user):
            return LoanApplication.objects.all()
        member = user.member_profile
        return LoanApplication.objects.filter(member=member)

    def _is_staff_or_finance(self, user):
        return user.is_staff or getattr(user, 'role', None) in ['admin', 'branch_manager', 'accountant']

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
        return Response(loan.get_amortization_schedule())

    @action(detail=True, methods=['get'])
    def penalties(self, request, pk=None):
        """Return penalty and interest breakdown with accrued amounts"""
        loan = self.get_object()
        return Response(loan.get_penalty_summary())

    @action(detail=True, methods=['get'])
    def history(self, request, pk=None):
        """Return loan history and status changes"""
        loan = self.get_object()
        return Response({
            'loan_id': loan.id,
            'status': loan.status,
            'submitted_at': loan.submitted_at,
            'reviewed_by': loan.reviewed_by.full_name if loan.reviewed_by else None,
            'reviewed_at': loan.reviewed_at,
            'approved_at': loan.approved_at,
            'disbursed_by': loan.disbursed_by.full_name if loan.disbursed_by else None,
            'disbursed_at': loan.disbursed_at,
            'rejection_reason': loan.rejection_reason,
            'notes': loan.notes,
        })

    @action(detail=True, methods=['post'])
    def record_payment(self, request, pk=None):
        """Record a loan payment and allocate the amount according to configurable business rules."""
        loan = self.get_object()
        if loan.status != 'disbursed':
            return Response({'detail': 'Payments can only be recorded for disbursed loans.'}, status=status.HTTP_400_BAD_REQUEST)

        data = request.data
        amount = data.get('amount_paid') or data.get('amount')
        if amount is None:
            return Response({'detail': 'amount_paid is required.'}, status=status.HTTP_400_BAD_REQUEST)

        paid_date = data.get('paid_date')
        try:
            allocation_result = loan.apply_payment_allocation(amount, paid_date)
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response({
            'detail': 'Payment allocated.',
            'payment_id': allocation_result['payment_id'],
            'allocated': allocation_result['allocated'],
            'remaining_amount': allocation_result['remaining_amount'],
        }, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get'])
    def report(self, request, pk=None):
        """Return loan summary and outstanding status for reporting"""
        loan = self.get_object()
        return Response({
            'loan_id': loan.id,
            'member': loan.member.member_number,
            'product': loan.product.name,
            'status': loan.status,
            'amount': str(loan.amount),
            'term_months': loan.term_months,
            'disbursed_amount': str(loan.disbursed_amount) if loan.disbursed_amount else None,
            'outstanding_principal': str(loan.outstanding_principal),
            'outstanding_balance': str(loan.outstanding_balance),
            'total_paid': str(loan.total_paid),
            'total_penalty_accrued': str(loan.total_penalty_accrued),
        })

    @action(detail=False, methods=['get'])
    def loan_history(self, request):
        """Return loan history list for the authenticated member"""
        loans = self.get_queryset().order_by('-submitted_at')
        serializer = LoanApplicationSerializer(loans, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def outstanding(self, request):
        """Return outstanding loan balances for the authenticated member"""
        loans = self.get_queryset().filter(status__in=['approved', 'disbursed'])
        return Response([
            {
                'loan_id': loan.id,
                'product': loan.product.name,
                'status': loan.status,
                'outstanding_principal': str(loan.outstanding_principal),
                'outstanding_balance': str(loan.outstanding_balance),
            }
            for loan in loans
        ])

    @action(detail=False, methods=['get'])
    def active_loans(self, request):
        """Return active loan records for the authenticated member"""
        loans = self.get_queryset().filter(status__in=['approved', 'disbursed'])
        serializer = LoanApplicationSerializer(loans, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def loan_report(self, request):
        """Return aggregated loan status report for the authenticated member"""
        loans = self.get_queryset()
        total_applications = loans.count()
        total_disbursed = loans.filter(status='disbursed').count()
        total_outstanding = sum([loan.outstanding_balance for loan in loans if loan.status in ['approved', 'disbursed']])
        return Response({
            'total_applications': total_applications,
            'total_disbursed': total_disbursed,
            'total_outstanding_balance': str(total_outstanding),
        })

    @action(detail=False, methods=['get'])
    def options(self, request):
        """Return loan workflow options and statuses"""
        return Response({
            'statuses': [choice[0] for choice in LoanApplication.STATUS_CHOICES],
            'payment_statuses': ['paid', 'overdue', 'pending', 'upcoming'],
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
        format_type = request.query_params.get('format', 'csv').lower().strip().rstrip('/')
        
        transactions = TransactionRecord.objects.filter(member=member).order_by('-created_at')
        
        if format_type == 'csv':
            output = BytesIO()
            text_output = StringIO()
            writer = csv.writer(text_output)
            writer.writerow(['Date', 'Type', 'Amount', 'Reference', 'Notes'])
            
            for txn in transactions:
                writer.writerow([
                    txn.created_at.strftime('%Y-%m-%d'),
                    txn.get_transaction_type_display(),
                    txn.amount,
                    txn.reference,
                    txn.notes
                ])
            
            output.write(text_output.getvalue().encode('utf-8'))
            output.seek(0)
            filename = f"statement_{member.member_number}_{datetime.now().strftime('%Y%m%d')}.csv"
            return FileResponse(output, as_attachment=True, filename=filename, content_type='text/csv')

        if format_type == 'xlsx':
            try:
                output = _render_statement_xlsx(member, transactions)
            except ImportError as exc:
                return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

            filename = f"statement_{member.member_number}_{datetime.now().strftime('%Y%m%d')}.xlsx"
            return FileResponse(output, as_attachment=True, filename=filename, content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

        if format_type == 'pdf':
            try:
                output = _render_statement_pdf(member, transactions)
            except ImportError as exc:
                return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

            filename = f"statement_{member.member_number}_{datetime.now().strftime('%Y%m%d')}.pdf"
            return FileResponse(output, as_attachment=True, filename=filename, content_type='application/pdf')

        return Response({'error': 'Format not supported. Available formats are csv, xlsx, pdf.'}, status=status.HTTP_400_BAD_REQUEST)
