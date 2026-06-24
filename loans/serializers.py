from rest_framework import serializers
from .models import LoanPayment, LoanApplication, LoanProduct


class LoanPaymentSerializer(serializers.ModelSerializer):
    """Serialize loan payment records with status"""
    payment_status = serializers.SerializerMethodField()

    class Meta:
        model = LoanPayment
        fields = [
            'id', 'month', 'due_date', 'scheduled_amount', 'principal', 'interest',
            'amount_paid', 'paid_date', 'is_paid', 'penalty_accrued', 'days_overdue',
            'payment_status'
        ]
        read_only_fields = ['penalty_accrued', 'days_overdue', 'payment_status']

    def get_payment_status(self, obj):
        """Return payment status: paid, overdue, pending, upcoming"""
        if obj.is_paid:
            return 'paid'
        
        from datetime import date, datetime
        today = date.today()
        
        if obj.due_date < today:
            return 'overdue'
        elif obj.due_date == today:
            return 'due_today'
        else:
            return 'pending'
