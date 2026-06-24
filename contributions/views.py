from rest_framework import viewsets, status, generics, views
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.db.models import Sum, Q, Count
from django.utils import timezone
from decimal import Decimal
from datetime import datetime, timedelta, date

from members.models import Member, Branch
from contributions.models import (
    TransactionRecord, ContributionPlan, ShareProduct, 
    DividendRule, ContributionDeadline, AuditLog
)
from members.serializers import (
    TransactionRecordSerializer, ContributionPlanSerializer, 
    ShareProductSerializer
)


class MemberPermission(IsAuthenticated):
    """Ensure user is an authenticated member"""
    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        return hasattr(request.user, 'member_profile')


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


class ContributionViewSet(viewsets.ReadOnlyModelViewSet):
    """Member contribution history"""
    permission_classes = [MemberPermission]
    serializer_class = TransactionRecordSerializer
    
    def get_queryset(self):
        member = self.request.user.member_profile
        return TransactionRecord.objects.filter(
            member=member,
            transaction_type__in=['contribution', 'dividend']
        ).order_by('-created_at')


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
    
    @action(detail=False, methods=['get'])
    def member_balance(self, request):
        """Get running balance for all members"""
        members = Member.objects.filter(status='active')
        
        balances = []
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
            balances.append({
                'member_number': member.member_number,
                'member_name': member.user.full_name,
                'contributions': str(contributions),
                'withdrawals': str(withdrawals),
                'balance': str(balance)
            })
        
        return Response(balances)
    
    @action(detail=False, methods=['get'])
    def branch_summary(self, request):
        """Get branch-level contribution summary"""
        branch_id = request.query_params.get('branch_id')
        
        if branch_id:
            branches = Branch.objects.filter(id=branch_id)
        else:
            branches = Branch.objects.all()
        
        summary = []
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
            
            summary.append({
                'branch': branch.name,
                'location': branch.location,
                'active_members': members_count,
                'total_contributions': str(total_contributed),
                'total_shares': str(total_shares),
                'total_loan_payments': str(total_loans),
                'average_contribution': str(total_contributed / members_count) if members_count > 0 else '0'
            })
        
        return Response(summary)
    
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
        
        total_loans_outstanding = TransactionRecord.objects.filter(
            transaction_type='loan_payment'
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
        
        # Transaction trend (last 30 days)
        thirty_days_ago = timezone.now() - timedelta(days=30)
        recent_contributions = TransactionRecord.objects.filter(
            transaction_type='contribution',
            created_at__gte=thirty_days_ago
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
        
        return Response({
            'total_members': total_members,
            'total_contributed': str(total_contributed),
            'total_shares_value': str(total_shares),
            'total_dividends_paid': str(total_dividends),
            'total_loan_payments': str(total_loans_outstanding),
            'recent_contributions_30days': str(recent_contributions),
            'average_member_contribution': str(total_contributed / total_members) if total_members > 0 else '0',
            'member_breakdown': {
                'active': Member.objects.filter(status='active').count(),
                'inactive': Member.objects.filter(status='inactive').count(),
                'pending': Member.objects.filter(status='pending').count(),
            }
        })
    
    @action(detail=False, methods=['get'])
    def transaction_audit(self, request):
        """Get audit log of all transactions"""
        limit = int(request.query_params.get('limit', 100))
        
        logs = AuditLog.objects.all().order_by('-timestamp')[:limit]
        
        data = []
        for log in logs:
            data.append({
                'timestamp': log.timestamp,
                'user': log.user.email if log.user else 'System',
                'action': log.action,
                'content': log.content_object,
                'extra': log.extra_data
            })
        
        return Response(data)
