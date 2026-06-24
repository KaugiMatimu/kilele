from rest_framework import serializers
from contributions.models import (
    ContributionPlan, ShareProduct, DividendRule,
    TransactionRecord, AuditLog, ContributionDeadline
)


class ContributionPlanDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContributionPlan
        fields = ['id', 'name', 'amount', 'frequency', 'description', 'active']


class ShareProductDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShareProduct
        fields = ['id', 'name', 'price_per_share', 'minimum_shares', 'description', 'active']


class DividendRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = DividendRule
        fields = ['id', 'name', 'percentage', 'year', 'notes', 'active']


class ContributionDeadlineSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContributionDeadline
        fields = ['id', 'name', 'due_date', 'description', 'active']


class TransactionRecordDetailSerializer(serializers.ModelSerializer):
    transaction_type_display = serializers.CharField(source='get_transaction_type_display', read_only=True)
    member_number = serializers.CharField(source='member.member_number', read_only=True)
    member_name = serializers.CharField(source='member.user.full_name', read_only=True)

    class Meta:
        model = TransactionRecord
        fields = [
            'id', 'member', 'member_number', 'member_name',
            'transaction_type', 'transaction_type_display',
            'amount', 'reference', 'created_at', 'notes'
        ]
        read_only_fields = ['created_at', 'member_number', 'member_name']


class PostContributionSerializer(serializers.Serializer):
    """Serializer for posting contributions in batch"""
    plan_id = serializers.IntegerField(required=True)
    branch_id = serializers.IntegerField(required=False, allow_null=True)
    member_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        allow_null=True
    )
    posted_date = serializers.DateField(required=False)


class PostDividendSerializer(serializers.Serializer):
    """Serializer for posting dividends"""
    dividend_rule_id = serializers.IntegerField(required=True)


class AuditLogSerializer(serializers.ModelSerializer):
    user_email = serializers.CharField(source='user.email', read_only=True, allow_null=True)

    class Meta:
        model = AuditLog
        fields = ['id', 'timestamp', 'user', 'user_email', 'action', 'content_object', 'extra_data']
        read_only_fields = ['timestamp']
