from rest_framework import mixins, viewsets, status, generics, views
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.db.models import Sum, Q, Count
from django.utils import timezone
from django.http import FileResponse
from decouple import config
from io import BytesIO, TextIOWrapper
from datetime import datetime, timedelta, date
from decimal import Decimal
import csv
import hashlib
import base64
import json
import os
import re
from urllib import request as urllib_request
from urllib.error import HTTPError, URLError

from members.models import Member, Branch
from contributions.models import (
    TransactionRecord, ContributionPlan, ShareProduct,
    DividendRule, ContributionDeadline, AuditLog, BusinessRule,
    LedgerEntry, TransactionReversal
)
from loans.models import LoanApplication, LoanPayment, LoanProduct
from notifications.models import NotificationTemplate
from members.serializers import (
    TransactionRecordSerializer, ContributionPlanSerializer,
    ShareProductSerializer
)
from contributions.serializers import (
    ContributionPlanDetailSerializer,
    ShareProductDetailSerializer,
    DividendRuleSerializer,
    ContributionDeadlineSerializer,
    LoanProductAdminSerializer,
    NotificationTemplateAdminSerializer,
    BusinessRuleSerializer,
    AuditLogSerializer,
    LedgerEntrySerializer,
    TransactionReversalSerializer,
)


def _normalize_phone_number(phone_number):
    value = re.sub(r'\D', '', str(phone_number or ''))
    if not value:
        return ''
    if value.startswith('254'):
        return value
    if value.startswith('0') and len(value) == 10:
        return '254' + value[1:]
    if value.startswith('7') and len(value) == 9:
        return '254' + value
    return value


def _initiate_mpesa_stk_push(amount, phone_number, reference, description='Contribution payment'):
    consumer_key = config('MPESA_CONSUMER_KEY', default='').strip()
    consumer_secret = config('MPESA_CONSUMER_SECRET', default='').strip()
    short_code = config('MPESA_SHORTCODE', default='').strip()
    passkey = config('MPESA_PASSKEY', default='').strip()
    callback_url = config('MPESA_CALLBACK_URL', default='').strip()

    if not all([consumer_key, consumer_secret, short_code, passkey]):
        raise RuntimeError('MPesa credentials are not configured. Set MPESA_CONSUMER_KEY, MPESA_CONSUMER_SECRET, MPESA_SHORTCODE, and MPESA_PASSKEY in your .env file or shell environment.')

    if not callback_url:
        raise RuntimeError('MPesa callback URL is not configured. Set MPESA_CALLBACK_URL to a publicly reachable HTTPS URL.')

    normalized_phone_number = _normalize_phone_number(phone_number)
    if not normalized_phone_number:
        raise RuntimeError('A valid phone number is required for MPesa payments.')

    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    password = base64.b64encode(f"{short_code}{passkey}{timestamp}".encode()).decode()
    auth_url = 'https://sandbox.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials'

    auth_req = urllib_request.Request(auth_url)
    auth_req.add_header('Authorization', 'Basic ' + base64.b64encode(f'{consumer_key}:{consumer_secret}'.encode()).decode())

    try:
        with urllib_request.urlopen(auth_req, timeout=20) as response:
            auth_data = json.loads(response.read().decode('utf-8'))
    except HTTPError as exc:
        body = exc.read().decode('utf-8', 'ignore')
        raise RuntimeError(f'MPesa auth failed: {exc.code} {body}') from exc
    except URLError as exc:
        raise RuntimeError(f'MPesa auth failed: {exc}') from exc

    access_token = auth_data.get('access_token')
    if not access_token:
        raise RuntimeError('MPesa authentication failed: no access token received')

    payload = {
        'BusinessShortCode': short_code,
        'Password': password,
        'Timestamp': timestamp,
        'TransactionType': 'CustomerPayBillOnline',
        'Amount': int(float(amount)),
        'PartyA': normalized_phone_number,
        'PartyB': short_code,
        'PhoneNumber': normalized_phone_number,
        'CallBackURL': callback_url,
        'AccountReference': reference,
        'TransactionDesc': description,
    }

    stk_req = urllib_request.Request(
        'https://sandbox.safaricom.co.ke/mpesa/stkpush/v1/processrequest',
        data=json.dumps(payload).encode('utf-8'),
        headers={
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json',
        },
        method='POST',
    )

    try:
        with urllib_request.urlopen(stk_req, timeout=20) as response:
            return json.loads(response.read().decode('utf-8'))
    except HTTPError as exc:
        body = exc.read().decode('utf-8', 'ignore')
        raise RuntimeError(f'MPesa STK push failed: {exc.code} {body}') from exc
    except URLError as exc:
        raise RuntimeError(f'MPesa STK push failed: {exc}') from exc


def _render_report_csv(headers, rows):
    output = BytesIO()
    text_output = TextIOWrapper(output, encoding='utf-8', newline='')
    writer = csv.writer(text_output)
    writer.writerow(headers)
    for row in rows:
        writer.writerow([str(value) if value is not None else '' for value in row])
    text_output.flush()
    text_output.detach()
    output.seek(0)
    return output


def _render_report_xlsx(title, headers, rows):
    try:
        from openpyxl import Workbook
    except ImportError:
        raise ImportError('openpyxl is required to export reports as Excel. Install openpyxl.')

    output = BytesIO()
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = title[:31]
    sheet.append(headers)

    for row in rows:
        sheet.append([str(value) if value is not None else '' for value in row])

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


def _render_report_pdf(title, headers, rows):
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.pdfgen import canvas
        from reportlab.lib.units import inch
    except ImportError:
        raise ImportError('reportlab is required to export reports as PDF. Install reportlab.')

    output = BytesIO()
    c = canvas.Canvas(output, pagesize=letter)
    width, height = letter
    margin = inch
    y = height - margin

    c.setFont('Helvetica-Bold', 14)
    c.drawString(margin, y, title)
    y -= 0.3 * inch

    c.setFont('Helvetica', 10)
    c.drawString(margin, y, f'Generated: {datetime.now().strftime("%Y-%m-%d")}')
    y -= 0.4 * inch

    c.setFont('Helvetica-Bold', 9)
    x_positions = [margin + i * 1.7 * inch for i in range(len(headers))]
    for idx, header in enumerate(headers):
        c.drawString(x_positions[idx], y, str(header))
    y -= 0.25 * inch
    c.setFont('Helvetica', 9)

    for row in rows:
        if y < margin + 0.5 * inch:
            c.showPage()
            y = height - margin
            c.setFont('Helvetica-Bold', 9)
            for idx, header in enumerate(headers):
                c.drawString(x_positions[idx], y, str(header))
            y -= 0.25 * inch
            c.setFont('Helvetica', 9)

        for idx, value in enumerate(row):
            text = str(value) if value is not None else ''
            if len(text) > 40:
                text = text[:37] + '...'
            c.drawString(x_positions[idx], y, text)
        y -= 0.22 * inch

    c.save()
    output.seek(0)
    return output


def _build_report_response(format_type, filename, title, headers, rows):
    format_type = (format_type or 'json').lower().strip().rstrip('/')
    if format_type == 'json':
        return None

    try:
        if format_type == 'csv':
            output = _render_report_csv(headers, rows)
            content_type = 'text/csv'
        elif format_type == 'xlsx':
            output = _render_report_xlsx(title, headers, rows)
            content_type = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        elif format_type == 'pdf':
            output = _render_report_pdf(title, headers, rows)
            content_type = 'application/pdf'
        else:
            return Response({'error': 'Format not supported. Use json, csv, xlsx, or pdf.'}, status=status.HTTP_400_BAD_REQUEST)
    except ImportError as exc:
        return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    return FileResponse(output, as_attachment=True, filename=filename, content_type=content_type)


class MemberPermission(IsAuthenticated):
    """Ensure user is an authenticated member"""
    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        return hasattr(request.user, 'member_profile')


class AdminOnlyPermission(IsAuthenticated):
    """Allow authenticated staff members with admin-like roles to manage configuration."""

    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        user = request.user
        return bool(user.is_staff or getattr(user, 'role', None) in ['admin', 'branch_manager', 'accountant'])


class AdminConfigurationView(views.APIView):
    """Expose editable configuration resources to administrators."""
    permission_classes = [AdminOnlyPermission]

    def get(self, request):
        return Response({
            'loan_products': LoanProductAdminSerializer(LoanProduct.objects.all(), many=True).data,
            'contribution_plans': ContributionPlanDetailSerializer(ContributionPlan.objects.all(), many=True).data,
            'deadlines': ContributionDeadlineSerializer(ContributionDeadline.objects.all(), many=True).data,
            'notification_templates': NotificationTemplateAdminSerializer(NotificationTemplate.objects.all(), many=True).data,
            'business_rules': BusinessRuleSerializer(BusinessRule.objects.all(), many=True).data,
        })

    def post(self, request):
        return self._handle_write(request, create=True)

    def put(self, request):
        return self._handle_write(request, create=False)

    def patch(self, request):
        return self._handle_write(request, create=False)

    def _handle_write(self, request, create=True):
        resource = request.data.get('resource')
        payload = request.data.copy()
        payload.pop('resource', None)

        serializer_class = self._get_serializer_class(resource)
        if serializer_class is None:
            return Response({'error': 'Unsupported resource'}, status=status.HTTP_400_BAD_REQUEST)

        instance = None
        if not create:
            instance_id = payload.pop('id', None)
            if instance_id is None and resource == 'business_rules':
                instance_id = payload.pop('key', None)
            if instance_id is not None:
                instance = self._get_instance(resource, instance_id)
                if instance is None:
                    return Response({'error': 'Resource not found'}, status=status.HTTP_404_NOT_FOUND)

        serializer = serializer_class(instance=instance, data=payload, partial=not create)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK if not create else status.HTTP_201_CREATED)

    def _get_instance(self, resource, instance_id):
        model_class = self._get_model_class(resource)
        if model_class is None:
            return None
        if resource == 'business_rules':
            return model_class.objects.filter(key=instance_id).first()
        try:
            return model_class.objects.get(id=instance_id)
        except model_class.DoesNotExist:
            return None

    def _get_model_class(self, resource):
        mapping = {
            'loan_products': LoanProduct,
            'contribution_plans': ContributionPlan,
            'deadlines': ContributionDeadline,
            'notification_templates': NotificationTemplate,
            'business_rules': BusinessRule,
        }
        return mapping.get(resource)

    def _get_serializer_class(self, resource):
        mapping = {
            'loan_products': LoanProductAdminSerializer,
            'contribution_plans': ContributionPlanDetailSerializer,
            'deadlines': ContributionDeadlineSerializer,
            'notification_templates': NotificationTemplateAdminSerializer,
            'business_rules': BusinessRuleSerializer,
        }
        return mapping.get(resource)


class AdminAuditView(views.APIView):
    """Return the audit trail, ledger activity, and reversal history for admins."""
    permission_classes = [AdminOnlyPermission]

    def get(self, request):
        limit = int(request.query_params.get('limit', 100))
        ledger_entries = LedgerEntry.objects.select_related('transaction').order_by('-created_at')[:limit]
        audit_logs = AuditLog.objects.select_related('user').order_by('-timestamp')[:limit]
        reversals = TransactionReversal.objects.select_related('transaction', 'reversed_by').order_by('-reversed_at')[:limit]

        return Response({
            'ledger_entries': LedgerEntrySerializer(ledger_entries, many=True).data,
            'audit_logs': AuditLogSerializer(audit_logs, many=True).data,
            'approval_history': [
                {
                    'reference': reversal.transaction.reference,
                    'status': reversal.transaction.status,
                    'approval_history': reversal.transaction.approval_history,
                    'reversed_by': reversal.reversed_by.email if reversal.reversed_by else None,
                    'reason': reversal.reason,
                    'reversed_at': reversal.reversed_at,
                }
                for reversal in reversals
            ],
        })


class ContributionSummaryView(views.APIView):
    """Get contribution summary for the member"""
    permission_classes = [MemberPermission]
    
    def get(self, request):
        member = request.user.member_profile
        
        total_contributed = TransactionRecord.objects.filter(
            member=member,
            transaction_type='contribution'
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
        
        this_year = TransactionRecord.objects.filter(
            member=member,
            transaction_type='contribution',
            created_at__year=datetime.now().year
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
        
        transaction_count = TransactionRecord.objects.filter(
            member=member,
            transaction_type__in=['contribution', 'dividend']
        ).count()
        
        # Calculate running balance
        contributions = TransactionRecord.objects.filter(
            member=member,
            transaction_type='contribution'
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
        
        withdrawals = TransactionRecord.objects.filter(
            member=member,
            transaction_type='withdrawal'
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
        
        running_balance = contributions - withdrawals
        
        return Response({
            'total_contributed': str(total_contributed),
            'contributed_this_year': str(this_year),
            'transaction_count': transaction_count,
            'running_balance': str(running_balance),
            'contributions': str(contributions),
            'withdrawals': str(withdrawals),
        })


class ContributionPlansView(views.APIView):
    """Get available contribution plans"""
    permission_classes = [MemberPermission]
    
    def get(self, request):
        plans = ContributionPlan.objects.filter(active=True)
        serializer = ContributionPlanSerializer(plans, many=True)
        return Response(serializer.data)


class ContributionViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """Member contribution history"""
    permission_classes = [MemberPermission]
    serializer_class = TransactionRecordSerializer
    http_method_names = ['get', 'post', 'head', 'options']

    def get_queryset(self):
        member = self.request.user.member_profile
        return TransactionRecord.objects.filter(
            member=member,
            transaction_type__in=['contribution', 'dividend']
        ).order_by('-created_at')

    def perform_create(self, serializer):
        member = self.request.user.member_profile
        serializer.save(member=member, transaction_type='contribution')

    @action(detail=False, methods=['post'])
    def pay(self, request):
        """Accept a contribution payment via cash or MPesa and record it."""
        member = request.user.member_profile
        payment_method = (request.data.get('payment_method') or 'cash').strip().lower()
        amount = request.data.get('amount')
        reference = request.data.get('reference') or f"CONTRIB-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        notes = request.data.get('notes') or ''

        try:
            amount_value = Decimal(str(amount))
        except Exception:
            return Response({'detail': 'amount must be a valid number.'}, status=status.HTTP_400_BAD_REQUEST)

        if amount_value <= 0:
            return Response({'detail': 'amount must be greater than zero.'}, status=status.HTTP_400_BAD_REQUEST)

        if payment_method == 'mpesa':
            phone_number = str(request.data.get('phone_number') or '').strip()
            if not phone_number:
                return Response({'detail': 'phone_number is required for MPesa payments.'}, status=status.HTTP_400_BAD_REQUEST)

            try:
                mpesa_response = _initiate_mpesa_stk_push(amount_value, phone_number, reference, notes or 'Contribution payment')
            except Exception as exc:
                TransactionRecord.objects.create(
                    member=member,
                    transaction_type='contribution',
                    amount=amount_value,
                    reference=reference,
                    notes=f"MPesa payment pending. {notes}".strip(),
                    status='posted',
                )
                return Response({
                    'status': 'pending',
                    'payment_method': 'mpesa',
                    'reference': reference,
                    'amount': str(amount_value),
                    'detail': str(exc),
                }, status=status.HTTP_200_OK)

            TransactionRecord.objects.create(
                member=member,
                transaction_type='contribution',
                amount=amount_value,
                reference=reference,
                notes=f"MPesa payment initiated. {notes}".strip(),
                status='posted',
            )
            return Response({
                'status': 'initiated',
                'payment_method': 'mpesa',
                'reference': reference,
                'amount': str(amount_value),
                'mpesa': mpesa_response,
            })

        TransactionRecord.objects.create(
            member=member,
            transaction_type='contribution',
            amount=amount_value,
            reference=reference,
            notes=f"Cash contribution. {notes}".strip(),
            status='posted',
        )
        return Response({
            'status': 'posted',
            'payment_method': 'cash',
            'reference': reference,
            'amount': str(amount_value),
        })


class ShareViewSet(viewsets.ViewSet):
    """Share holdings, purchases, and dividends"""
    permission_classes = [MemberPermission]
    
    @action(detail=False, methods=['get'])
    def holdings(self, request):
        """Get member's share holdings and balances"""
        member = request.user.member_profile
        
        # Calculate shares value
        shares_value = TransactionRecord.objects.filter(
            member=member,
            transaction_type='share_purchase'
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
        
        # Calculate current balance
        contributions = TransactionRecord.objects.filter(
            member=member,
            transaction_type='contribution'
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
        
        withdrawals = TransactionRecord.objects.filter(
            member=member,
            transaction_type='withdrawal'
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
        
        running_balance = contributions - withdrawals
        
        # Get available products
        available_products = ShareProduct.objects.filter(active=True)
        
        return Response({
            'total_shares_value': str(shares_value),
            'total_balance': str(running_balance),
            'contributions': str(contributions),
            'withdrawals': str(withdrawals),
            'available_products': ShareProductSerializer(available_products, many=True).data
        })
    
    @action(detail=False, methods=['get'])
    def transactions(self, request):
        """Get share transaction history"""
        member = request.user.member_profile
        transactions = TransactionRecord.objects.filter(
            member=member,
            transaction_type='share_purchase'
        ).order_by('-created_at')
        
        serializer = TransactionRecordSerializer(transactions, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['post'])
    def purchase(self, request):
        """Request share purchase"""
        member = request.user.member_profile
        product_id = request.data.get('product_id')
        quantity = request.data.get('quantity', 1)
        
        try:
            product = ShareProduct.objects.get(id=product_id, active=True)
        except ShareProduct.DoesNotExist:
            return Response(
                {'error': 'Share product not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        if quantity < product.minimum_shares:
            return Response(
                {'error': f'Minimum {product.minimum_shares} shares required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        amount = Decimal(str(quantity)) * product.price_per_share
        
        # Create pending transaction
        transaction = TransactionRecord.objects.create(
            member=member,
            transaction_type='share_purchase',
            amount=amount,
            reference=f"SHARE-{product.id}-{timezone.now().timestamp()}",
            notes=f"Share purchase: {quantity} x {product.name} @ KES {product.price_per_share}"
        )
        
        # Log the action
        AuditLog.objects.create(
            user=request.user,
            action=f'Member {member.member_number} purchased {quantity} shares',
            content_object=f'TransactionRecord:{transaction.id}',
            extra_data={'product_id': product_id, 'quantity': quantity}
        )
        
        return Response(
            TransactionRecordSerializer(transaction).data,
            status=status.HTTP_201_CREATED
        )


class AdminContributionViewSet(viewsets.ViewSet):
    """Admin endpoints for posting contributions and managing transactions"""
    
    @action(detail=False, methods=['post'])
    def post_contributions(self, request):
        """Post contributions in batch"""
        plan_id = request.data.get('plan_id')
        branch_id = request.data.get('branch_id')
        member_ids = request.data.get('member_ids')
        posted_date = request.data.get('posted_date', str(date.today()))
        
        try:
            plan = ContributionPlan.objects.get(id=plan_id)
        except ContributionPlan.DoesNotExist:
            return Response(
                {'error': 'Contribution plan not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Build member queryset
        if branch_id:
            members = Member.objects.filter(branch_id=branch_id, status='active')
        elif member_ids:
            members = Member.objects.filter(id__in=member_ids, status='active')
        else:
            members = Member.objects.filter(status='active')
        
        posted_transactions = []
        for member in members:
            transaction = TransactionRecord.objects.create(
                member=member,
                transaction_type='contribution',
                amount=plan.amount,
                reference=f"CONTRIB-{plan.id}-{posted_date}",
                notes=f"Contribution: {plan.name} ({plan.frequency})"
            )
            posted_transactions.append(transaction)
            
            # Log the action
            AuditLog.objects.create(
                user=request.user,
                action=f'Posted contribution for {member.member_number}',
                content_object=f'TransactionRecord:{transaction.id}',
                extra_data={'plan_id': plan_id, 'amount': str(plan.amount)}
            )
        
        return Response({
            'message': f'Posted {len(posted_transactions)} contributions',
            'count': len(posted_transactions),
            'plan': plan.name,
            'amount': str(plan.amount),
            'total': str(plan.amount * len(posted_transactions))
        })
    
    @action(detail=False, methods=['post'])
    def post_dividends(self, request):
        """Post dividend payments"""
        dividend_rule_id = request.data.get('dividend_rule_id')
        
        try:
            rule = DividendRule.objects.get(id=dividend_rule_id)
        except DividendRule.DoesNotExist:
            return Response(
                {'error': 'Dividend rule not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Calculate dividend for each active member
        posted_dividends = []
        active_members = Member.objects.filter(status='active')
        
        for member in active_members:
            # Get member's share value
            share_value = TransactionRecord.objects.filter(
                member=member,
                transaction_type='share_purchase'
            ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
            
            # Calculate dividend
            dividend_amount = share_value * (Decimal(str(rule.percentage)) / Decimal('100'))
            
            if dividend_amount > 0:
                transaction = TransactionRecord.objects.create(
                    member=member,
                    transaction_type='dividend',
                    amount=dividend_amount,
                    reference=f"DIV-{rule.id}-{rule.year}",
                    notes=f"Dividend: {rule.name} ({rule.year}) @ {rule.percentage}%"
                )
                posted_dividends.append(transaction)
                
                # Log the action
                AuditLog.objects.create(
                    user=request.user,
                    action=f'Posted dividend for {member.member_number}',
                    content_object=f'TransactionRecord:{transaction.id}',
                    extra_data={'rule_id': dividend_rule_id, 'amount': str(dividend_amount)}
                )
        
        total_dividend = sum(t.amount for t in posted_dividends)
        return Response({
            'message': f'Posted dividends to {len(posted_dividends)} members',
            'count': len(posted_dividends),
            'rule': rule.name,
            'percentage': str(rule.percentage),
            'total_posted': str(total_dividend)
        })


class AdminReportViewSet(viewsets.ViewSet):
    """Admin reporting and analytics"""

    def _export_data(self, request, title, filename_base, headers, rows, data):
        format_type = request.query_params.get('format', 'json').lower()
        if format_type == 'json':
            return Response(data)
        filename = f"{filename_base}_{datetime.now().strftime('%Y%m%d')}.{format_type}"
        return _build_report_response(format_type, filename, title, headers, rows)
    
    @action(detail=False, methods=['get'])
    def member_balance(self, request):
        """Get running balance for all members"""
        members = Member.objects.filter(status='active')
        
        balances = []
        rows = []
        for member in members:
            contributions = TransactionRecord.objects.filter(
                member=member,
                transaction_type='contribution'
            ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
            
            withdrawals = TransactionRecord.objects.filter(
                member=member,
                transaction_type='withdrawal'
            ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
            
            balance = contributions - withdrawals
            item = {
                'member_number': member.member_number,
                'member_name': member.user.full_name,
                'contributions': str(contributions),
                'withdrawals': str(withdrawals),
                'balance': str(balance)
            }
            balances.append(item)
            rows.append([item['member_number'], item['member_name'], item['contributions'], item['withdrawals'], item['balance']])
        
        return self._export_data(
            request,
            'Member Balances Report',
            'member_balances',
            ['Member Number', 'Member Name', 'Contributions', 'Withdrawals', 'Balance'],
            rows,
            balances
        )
    
    @action(detail=False, methods=['get'])
    def branch_summary(self, request):
        """Get branch-level contribution summary"""
        branch_id = request.query_params.get('branch_id')
        
        if branch_id:
            branches = Branch.objects.filter(id=branch_id)
        else:
            branches = Branch.objects.all()
        
        summary = []
        rows = []
        for branch in branches:
            members_count = Member.objects.filter(branch=branch, status='active').count()
            
            total_contributed = TransactionRecord.objects.filter(
                member__branch=branch,
                transaction_type='contribution'
            ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
            
            total_shares = TransactionRecord.objects.filter(
                member__branch=branch,
                transaction_type='share_purchase'
            ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
            
            total_loans = TransactionRecord.objects.filter(
                member__branch=branch,
                transaction_type='loan_payment'
            ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
            
            item = {
                'branch': branch.name,
                'location': branch.location,
                'active_members': members_count,
                'total_contributions': str(total_contributed),
                'total_shares': str(total_shares),
                'total_loan_payments': str(total_loans),
                'average_contribution': str(total_contributed / members_count) if members_count > 0 else '0'
            }
            summary.append(item)
            rows.append([item['branch'], item['location'], item['active_members'], item['total_contributions'], item['total_shares'], item['total_loan_payments'], item['average_contribution']])
        
        return self._export_data(
            request,
            'Branch Summary Report',
            'branch_summary',
            ['Branch', 'Location', 'Active Members', 'Total Contributions', 'Total Shares', 'Total Loan Payments', 'Average Contribution'],
            rows,
            summary
        )
    
    @action(detail=False, methods=['get'])
    def organization_summary(self, request):
        """Get organization-level summary"""
        total_members = Member.objects.filter(status='active').count()
        
        total_contributed = TransactionRecord.objects.filter(
            transaction_type='contribution'
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
        
        total_shares = TransactionRecord.objects.filter(
            transaction_type='share_purchase'
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
        
        total_dividends = TransactionRecord.objects.filter(
            transaction_type='dividend'
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
        
        total_loan_payments = TransactionRecord.objects.filter(
            transaction_type='loan_payment'
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
        
        thirty_days_ago = timezone.now() - timedelta(days=30)
        recent_contributions = TransactionRecord.objects.filter(
            transaction_type='contribution',
            created_at__gte=thirty_days_ago
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0')

        data = {
            'total_members': total_members,
            'total_contributed': str(total_contributed),
            'total_shares_value': str(total_shares),
            'total_dividends_paid': str(total_dividends),
            'total_loan_payments': str(total_loan_payments),
            'recent_contributions_30days': str(recent_contributions),
            'average_member_contribution': str(total_contributed / total_members) if total_members > 0 else '0',
            'member_breakdown': {
                'active': Member.objects.filter(status='active').count(),
                'inactive': Member.objects.filter(status='inactive').count(),
                'pending': Member.objects.filter(status='pending').count(),
            }
        }

        format_type = request.query_params.get('format', 'json').lower()
        if format_type == 'json':
            return Response(data)

        headers = ['Metric', 'Value']
        rows = [
            ['Total Members', data['total_members']],
            ['Total Contributed', data['total_contributed']],
            ['Total Shares Value', data['total_shares_value']],
            ['Total Dividends Paid', data['total_dividends_paid']],
            ['Total Loan Payments', data['total_loan_payments']],
            ['Recent Contributions (30d)', data['recent_contributions_30days']],
            ['Average Member Contribution', data['average_member_contribution']],
            ['Active Members', data['member_breakdown']['active']],
            ['Inactive Members', data['member_breakdown']['inactive']],
            ['Pending Members', data['member_breakdown']['pending']],
        ]

        return self._build_report_response(
            format_type,
            f'organization_summary_{datetime.now().strftime("%Y%m%d")}.{format_type}',
            'Organization Summary Report',
            headers,
            rows
        )
    
    @action(detail=False, methods=['get'])
    def loan_summary(self, request):
        """Get loan portfolio summary"""
        loan_applications = LoanApplication.objects.all()
        total_principal = loan_applications.aggregate(total=Sum('amount'))['total'] or Decimal('0')
        total_disbursed = loan_applications.filter(status='disbursed').aggregate(total=Sum('disbursed_amount'))['total'] or Decimal('0')
        total_outstanding = loan_applications.filter(status='disbursed').aggregate(total=Sum('amount'))['total'] or Decimal('0')
        loan_counts = {
            'pending': loan_applications.filter(status='pending').count(),
            'approved': loan_applications.filter(status='approved').count(),
            'disbursed': loan_applications.filter(status='disbursed').count(),
            'rejected': loan_applications.filter(status='rejected').count(),
        }
        data = {
            'total_loan_applications': loan_applications.count(),
            'total_principal_requested': str(total_principal),
            'total_disbursed_amount': str(total_disbursed),
            'total_outstanding_loan_requests': str(total_outstanding),
            'loan_counts': loan_counts,
        }

        format_type = request.query_params.get('format', 'json').lower()
        if format_type == 'json':
            return Response(data)

        headers = ['Metric', 'Value']
        rows = [
            ['Total Loan Applications', data['total_loan_applications']],
            ['Total Principal Requested', data['total_principal_requested']],
            ['Total Disbursed Amount', data['total_disbursed_amount']],
            ['Total Outstanding Loan Requests', data['total_outstanding_loan_requests']],
            ['Pending Loans', data['loan_counts']['pending']],
            ['Approved Loans', data['loan_counts']['approved']],
            ['Disbursed Loans', data['loan_counts']['disbursed']],
            ['Rejected Loans', data['loan_counts']['rejected']],
        ]

        return self._build_report_response(
            format_type,
            f'loan_summary_{datetime.now().strftime("%Y%m%d")}.{format_type}',
            'Loan Summary Report',
            headers,
            rows
        )

    @action(detail=False, methods=['get'])
    def interest_report(self, request):
        """Get interest earned across loan payments"""
        payments = LoanPayment.objects.all()
        total_interest_paid = payments.aggregate(total=Sum('interest'))['total'] or Decimal('0')
        total_principal_paid = payments.aggregate(total=Sum('principal'))['total'] or Decimal('0')
        total_penalties_paid = payments.aggregate(total=Sum('penalty_accrued'))['total'] or Decimal('0')
        disbursed_loans = LoanApplication.objects.filter(status='disbursed')
        total_disbursed = disbursed_loans.aggregate(total=Sum('disbursed_amount'))['total'] or Decimal('0')

        data = {
            'total_interest_paid': str(total_interest_paid),
            'total_principal_paid': str(total_principal_paid),
            'total_penalties_paid': str(total_penalties_paid),
            'total_disbursed_loans': disbursed_loans.count(),
            'total_disbursed_amount': str(total_disbursed),
        }
        format_type = request.query_params.get('format', 'json').lower()
        if format_type == 'json':
            return Response(data)

        headers = ['Metric', 'Value']
        rows = [
            ['Total Interest Paid', data['total_interest_paid']],
            ['Total Principal Paid', data['total_principal_paid']],
            ['Total Penalties Paid', data['total_penalties_paid']],
            ['Total Disbursed Loans', data['total_disbursed_loans']],
            ['Total Disbursed Amount', data['total_disbursed_amount']],
        ]
        return self._build_report_response(
            format_type,
            f'interest_report_{datetime.now().strftime("%Y%m%d")}.{format_type}',
            'Interest Report',
            headers,
            rows
        )

    @action(detail=False, methods=['get'])
    def penalty_report(self, request):
        """Get penalty accruals across loans"""
        total_penalties = LoanPayment.objects.aggregate(total=Sum('penalty_accrued'))['total'] or Decimal('0')
        data = {
            'total_penalty_accrued': str(total_penalties),
            'penalty_payment_count': LoanPayment.objects.filter(penalty_accrued__gt=0).count(),
        }
        format_type = request.query_params.get('format', 'json').lower()
        if format_type == 'json':
            return Response(data)

        headers = ['Metric', 'Value']
        rows = [
            ['Total Penalty Accrued', data['total_penalty_accrued']],
            ['Penalty Payment Count', data['penalty_payment_count']],
        ]
        return self._build_report_response(
            format_type,
            f'penalty_report_{datetime.now().strftime("%Y%m%d")}.{format_type}',
            'Penalty Report',
            headers,
            rows
        )

    @action(detail=False, methods=['get'])
    def transaction_audit(self, request):
        """Get audit log of all transactions"""
        limit = int(request.query_params.get('limit', 100))
        
        logs = AuditLog.objects.all().order_by('-timestamp')[:limit]
        
        data = []
        rows = []
        for log in logs:
            item = {
                'timestamp': log.timestamp,
                'user': log.user.email if log.user else 'System',
                'action': log.action,
                'content': log.content_object,
                'extra': log.extra_data
            }
            data.append(item)
            rows.append([item['timestamp'], item['user'], item['action'], item['content'], item['extra']])
        
        return self._export_data(
            request,
            'Transaction Audit Report',
            'transaction_audit',
            ['Timestamp', 'User', 'Action', 'Content', 'Extra'],
            rows,
            data
        )
