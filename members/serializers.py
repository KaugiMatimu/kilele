from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.db import IntegrityError
from members.models import Member, Branch, WorkflowRequest
from contributions.models import TransactionRecord, ContributionPlan, ShareProduct
from loans.models import LoanApplication, LoanProduct
from notifications.models import NotificationTemplate

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'email', 'full_name', 'role', 'date_joined']
        read_only_fields = ['date_joined']


class UserProfileUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['full_name', 'email']


class BranchSerializer(serializers.ModelSerializer):
    class Meta:
        model = Branch
        fields = ['id', 'name', 'location']


class MemberProfileSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    branch = BranchSerializer(read_only=True)

    class Meta:
        model = Member
        fields = ['id', 'user', 'member_number', 'branch', 'joined_date', 'status', 
                  'phone', 'address', 'date_of_birth', 'next_of_kin']
        read_only_fields = ['member_number', 'joined_date', 'status']


class MemberProfileUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Member
        fields = ['phone', 'address', 'date_of_birth', 'next_of_kin']


class MemberRegistrationSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(write_only=True)
    full_name = serializers.CharField(write_only=True)
    password = serializers.CharField(write_only=True, style={'input_type': 'password'})
    confirm_password = serializers.CharField(write_only=True, style={'input_type': 'password'})
    branch = serializers.PrimaryKeyRelatedField(queryset=Branch.objects.all(), required=False, allow_null=True)
    user = UserSerializer(read_only=True)

    class Meta:
        model = Member
        fields = [
            'id', 'member_number', 'status', 'branch', 'phone', 'address',
            'date_of_birth', 'next_of_kin', 'user',
            'email', 'full_name', 'password', 'confirm_password',
        ]
        read_only_fields = ['id', 'member_number', 'status', 'user']

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError('A user with this email already exists.')
        return value

    def validate(self, attrs):
        if attrs.get('password') != attrs.get('confirm_password'):
            raise serializers.ValidationError({'confirm_password': 'Passwords must match.'})
        return attrs

    def generate_member_number(self):
        timestamp = timezone.now().strftime('%Y%m%d%H%M%S')
        return f"MEM{timestamp}"

    def create(self, validated_data):
        password = validated_data.pop('password')
        validated_data.pop('confirm_password')
        email = validated_data.pop('email')
        full_name = validated_data.pop('full_name')

        branch = validated_data.pop('branch', None)
        try:
            user = User.objects.create_user(
                email=email,
                password=password,
                full_name=full_name,
                role='member'
            )
        except IntegrityError:
            raise serializers.ValidationError({'email': 'A user with this email already exists.'})

        member_number = self.generate_member_number()
        member = Member.objects.create(
            user=user,
            member_number=member_number,
            branch=branch,
            status='pending',
            **validated_data,
        )
        return member


class TransactionRecordSerializer(serializers.ModelSerializer):
    transaction_type_display = serializers.CharField(source='get_transaction_type_display', read_only=True)

    class Meta:
        model = TransactionRecord
        fields = ['id', 'transaction_type', 'transaction_type_display', 'amount', 'reference', 'created_at', 'notes']
        read_only_fields = ['created_at', 'transaction_type']


class ContributionPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContributionPlan
        fields = ['id', 'name', 'amount', 'frequency', 'description']


class ShareProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShareProduct
        fields = ['id', 'name', 'price_per_share', 'minimum_shares', 'description']


class LoanProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = LoanProduct
        fields = ['id', 'name', 'description', 'min_amount', 'max_amount', 'interest_rate', 'duration_months']


class LoanApplicationSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = LoanApplication
        fields = [
            'id', 'product', 'product_name', 'amount', 'term_months', 'purpose',
            'status', 'status_display', 'submitted_at', 'reviewed_at', 'approved_at',
            'disbursed_at', 'disbursed_amount', 'rejection_reason', 'notes'
        ]
        read_only_fields = [
            'submitted_at', 'reviewed_at', 'status', 'approved_at',
            'disbursed_at', 'disbursed_amount', 'rejection_reason', 'notes'
        ]


class LoanApplicationCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = LoanApplication
        fields = ['product', 'amount', 'term_months', 'purpose']

    def validate_amount(self, value):
        product = self.initial_data.get('product')
        if product:
            try:
                loan_product = LoanProduct.objects.get(id=product)
                if value < loan_product.min_amount or value > loan_product.max_amount:
                    raise serializers.ValidationError(
                        f"Amount must be between {loan_product.min_amount} and {loan_product.max_amount}."
                    )
            except LoanProduct.DoesNotExist:
                raise serializers.ValidationError('Selected loan product does not exist.')
        return value

    def validate_term_months(self, value):
        if value <= 0:
            raise serializers.ValidationError('Term must be a positive number of months.')
        product_id = self.initial_data.get('product')
        if product_id:
            try:
                loan_product = LoanProduct.objects.get(id=product_id)
                if value != loan_product.duration_months:
                    raise serializers.ValidationError(
                        f"Term must be exactly {loan_product.duration_months} months for this product."
                    )
            except LoanProduct.DoesNotExist:
                raise serializers.ValidationError('Selected loan product does not exist.')
        return value

    def validate(self, attrs):
        product = attrs.get('product')
        amount = attrs.get('amount')
        term_months = attrs.get('term_months')
        request = self.context.get('request')

        if not product:
            raise serializers.ValidationError({'product': 'Loan product is required.'})

        if not product.active:
            raise serializers.ValidationError({'product': 'Selected loan product is not currently active.'})

        if amount is None:
            raise serializers.ValidationError({'amount': 'Loan amount is required.'})

        if term_months is None:
            raise serializers.ValidationError({'term_months': 'Loan term is required.'})

        if request and hasattr(request, 'user'):
            user = request.user
            if getattr(user, 'member_profile', None) is None:
                raise serializers.ValidationError('Member profile not found.')

            member = user.member_profile
            if member.status != 'active':
                raise serializers.ValidationError('Only active members can apply for loans.')

            existing = LoanApplication.objects.filter(
                member=member,
                status__in=['pending', 'approved', 'disbursed']
            ).exists()
            if existing:
                raise serializers.ValidationError(
                    'You already have an active or pending loan application. Please complete or wait for a decision before applying again.'
                )

        return attrs


class WorkflowRequestSerializer(serializers.ModelSerializer):
    request_type_display = serializers.CharField(source='get_request_type_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = WorkflowRequest
        fields = ['id', 'request_type', 'request_type_display', 'amount', 'description', 
                  'status', 'status_display', 'submitted_at', 'reviewed_at', 'notes']
        read_only_fields = ['submitted_at', 'reviewed_at', 'status', 'notes']


class WorkflowRequestCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkflowRequest
        fields = ['request_type', 'amount', 'description']


class MemberDashboardSerializer(serializers.Serializer):
    """Aggregated member dashboard data"""
    member_number = serializers.CharField()
    full_name = serializers.CharField()
    status = serializers.CharField()
    joined_date = serializers.DateField()
    
    total_contributions = serializers.DecimalField(max_digits=14, decimal_places=2)
    total_shares = serializers.DecimalField(max_digits=14, decimal_places=2)
    total_loans_outstanding = serializers.DecimalField(max_digits=14, decimal_places=2)
    pending_requests = serializers.IntegerField()
    
    recent_transactions = TransactionRecordSerializer(many=True)
    active_loans = LoanApplicationSerializer(many=True)
