from django.conf import settings
from django.db import models

class LoanProduct(models.Model):
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    min_amount = models.DecimalField(max_digits=12, decimal_places=2)
    max_amount = models.DecimalField(max_digits=12, decimal_places=2)
    interest_rate = models.DecimalField(max_digits=5, decimal_places=2)
    duration_months = models.PositiveIntegerField()
    eligibility_criteria = models.TextField(blank=True)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    def get_active_interest_rule(self):
        return self.interest_rules.filter(active=True).order_by('id').first()

    def get_effective_interest_rate(self):
        active_rule = self.get_active_interest_rule()
        return active_rule.rate if active_rule else self.interest_rate

    def get_active_penalty_rules(self):
        return list(self.penalty_rules.filter(active=True).values('name', 'penalty_amount', 'description'))

    def get_active_allocation_rule(self):
        return self.allocation_rules.filter(active=True).order_by('id').first()

    def get_payment_allocation_sequence(self):
        rule = self.get_active_allocation_rule()
        return rule.get_sequence() if rule else ['penalty', 'interest', 'principal']


class InterestRateRule(models.Model):
    loan_product = models.ForeignKey(LoanProduct, on_delete=models.CASCADE, related_name='interest_rules')
    name = models.CharField(max_length=120)
    rate = models.DecimalField(max_digits=5, decimal_places=2)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ['loan_product', 'name']

    def __str__(self):
        return f"{self.name} — {self.loan_product.name}"


class PenaltyRule(models.Model):
    loan_product = models.ForeignKey(LoanProduct, on_delete=models.CASCADE, related_name='penalty_rules')
    name = models.CharField(max_length=120)
    penalty_amount = models.DecimalField(max_digits=12, decimal_places=2)
    description = models.TextField(blank=True)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ['loan_product', 'name']

    def __str__(self):
        return f"{self.name} — {self.loan_product.name}"


class PaymentAllocationRule(models.Model):
    ALLOCATION_CHOICES = ['penalty', 'interest', 'principal']

    loan_product = models.ForeignKey(LoanProduct, on_delete=models.CASCADE, related_name='allocation_rules')
    name = models.CharField(max_length=120)
    allocation_order = models.CharField(
        max_length=100,
        default='penalty,interest,principal',
        help_text='Comma-separated allocation order. Example: penalty,interest,principal'
    )
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ['loan_product', 'name']
        unique_together = [['loan_product', 'name']]

    def __str__(self):
        return f"{self.name} — {self.loan_product.name}"

    def get_sequence(self):
        parts = [part.strip() for part in self.allocation_order.split(',') if part.strip()]
        normalized = []
        for part in parts:
            if part in self.ALLOCATION_CHOICES and part not in normalized:
                normalized.append(part)
        for choice in self.ALLOCATION_CHOICES:
            if choice not in normalized:
                normalized.append(choice)
        return normalized


class LoanApplication(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('disbursed', 'Disbursed'),
    ]

    member = models.ForeignKey('members.Member', on_delete=models.CASCADE, related_name='loan_applications')
    product = models.ForeignKey(LoanProduct, on_delete=models.PROTECT, related_name='applications')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    term_months = models.PositiveIntegerField()
    purpose = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    submitted_at = models.DateTimeField(auto_now_add=True)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='reviewed_loan_applications')
    reviewed_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    disbursed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='disbursed_loan_applications')
    disbursed_at = models.DateTimeField(null=True, blank=True)
    disbursed_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    rejection_reason = models.TextField(blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-submitted_at']

    def __str__(self):
        return f"{self.product.name} application for {self.member.member_number} ({self.status})"

    def approve(self, reviewer, notes=''):
        from django.utils import timezone

        self.status = 'approved'
        self.reviewed_by = reviewer
        self.reviewed_at = timezone.now()
        self.approved_at = timezone.now()
        if notes:
            self.notes = notes
        self.save()
        return self

    def reject(self, reviewer, reason=''):
        from django.utils import timezone

        self.status = 'rejected'
        self.reviewed_by = reviewer
        self.reviewed_at = timezone.now()
        self.rejection_reason = reason
        self.save()
        return self

    def disburse(self, disbursed_by, amount=None, disbursed_at=None):
        from django.utils import timezone
        from decimal import Decimal

        if self.status != 'approved':
            raise ValueError('Only approved loans can be disbursed.')

        self.status = 'disbursed'
        self.disbursed_by = disbursed_by
        self.disbursed_at = disbursed_at or timezone.now()
        self.disbursed_amount = Decimal(str(amount)) if amount is not None else self.amount
        self.save()
        return self

    @property
    def total_paid(self):
        from django.db.models import Sum
        from decimal import Decimal

        return self.payments.aggregate(total=Sum('amount_paid'))['total'] or Decimal('0')

    @property
    def total_principal_paid(self):
        from django.db.models import Sum
        from decimal import Decimal

        return self.payments.filter(is_paid=True).aggregate(total=Sum('principal'))['total'] or Decimal('0')

    @property
    def total_interest_paid(self):
        from django.db.models import Sum
        from decimal import Decimal

        return self.payments.filter(is_paid=True).aggregate(total=Sum('interest'))['total'] or Decimal('0')

    @property
    def total_penalty_accrued(self):
        from django.db.models import Sum
        from decimal import Decimal

        return self.payments.aggregate(total=Sum('penalty_accrued'))['total'] or Decimal('0')

    @property
    def outstanding_principal(self):
        from decimal import Decimal

        outstanding = Decimal(str(self.amount)) - self.total_principal_paid
        return outstanding if outstanding >= 0 else Decimal('0')

    @property
    def remaining_interest_due(self):
        from decimal import Decimal

        if self.status != 'disbursed':
            return Decimal('0')

        schedule = self.get_amortization_schedule()
        return sum(
            Decimal(item['interest'])
            for item in schedule['schedule']
            if item['payment_status'] != 'paid'
        )

    @property
    def outstanding_balance(self):
        return self.outstanding_principal + self.remaining_interest_due + self.total_penalty_accrued

    def get_amortization_schedule(self, as_of_date=None):
        from datetime import date, timedelta
        from decimal import Decimal
        from .utils import calculate_monthly_payment, get_days_overdue, calculate_penalty_accrual

        if as_of_date is None:
            as_of_date = date.today()

        monthly_rate = Decimal(str(self.product.get_effective_interest_rate())) / Decimal('100') / Decimal('12')
        monthly_payment = calculate_monthly_payment(self.amount, self.product.get_effective_interest_rate(), self.term_months)
        balance = Decimal(str(self.amount))
        start_date = self.disbursed_at.date() if self.disbursed_at else self.submitted_at.date()
        schedule = []
        total_penalty = Decimal('0')
        total_paid = Decimal('0')

        for month in range(1, self.term_months + 1):
            interest = (balance * monthly_rate).quantize(Decimal('0.01'))
            principal_payment = (monthly_payment - interest).quantize(Decimal('0.01'))
            if month == self.term_months:
                principal_payment = balance
                monthly_payment = (principal_payment + interest).quantize(Decimal('0.01'))

            balance = (balance - principal_payment).quantize(Decimal('0.01'))
            due_date = start_date + timedelta(days=30 * month)
            payment_record = self.payments.filter(month=month).first()
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
                days_overdue = get_days_overdue(due_date, as_of_date)
                if days_overdue > 0:
                    penalty_rules = self.product.get_active_penalty_rules()
                    penalty = calculate_penalty_accrual(due_date, days_overdue, penalty_rules)

            if is_paid:
                total_paid += amount_paid
            total_penalty += penalty

            schedule.append({
                'month': month,
                'due_date': str(due_date),
                'principal': str(principal_payment),
                'interest': str(interest),
                'payment': str(monthly_payment),
                'balance': str(max(balance, Decimal('0'))),
                'is_paid': is_paid,
                'amount_paid': str(amount_paid),
                'paid_date': str(paid_date) if paid_date else None,
                'days_overdue': days_overdue,
                'penalty_accrued': str(penalty),
                'payment_status': 'paid' if is_paid else ('overdue' if days_overdue > 0 else 'pending')
            })

        return {
            'loan_id': self.id,
            'amount': str(self.amount),
            'interest_rate': str(self.product.get_effective_interest_rate()),
            'term_months': self.term_months,
            'monthly_payment': str(monthly_payment),
            'total_paid': str(total_paid),
            'total_penalty_accrued': str(total_penalty),
            'schedule': schedule
        }

    def apply_payment_allocation(self, amount, paid_date=None):
        from datetime import date, datetime
        from decimal import Decimal

        if isinstance(paid_date, str):
            paid_date = date.fromisoformat(paid_date)
        paid_date = paid_date or date.today()
        if not isinstance(paid_date, date):
            raise ValueError('paid_date must be a date or ISO date string.')

        amount = Decimal(str(amount))
        remaining_amount = amount
        sequence = self.product.get_payment_allocation_sequence()

        penalty_due = Decimal(str(self.get_penalty_summary(today=paid_date)['unpaid_overdue_penalty']))
        interest_due = self.remaining_interest_due
        principal_due = self.outstanding_principal

        if self.status != 'disbursed':
            raise ValueError('Payment allocation is only allowed for disbursed loans.')

        allocations = {'penalty': Decimal('0'), 'interest': Decimal('0'), 'principal': Decimal('0')}

        def allocate(category):
            nonlocal remaining_amount
            if category == 'penalty':
                target = penalty_due
            elif category == 'interest':
                target = interest_due
            elif category == 'principal':
                target = principal_due
            else:
                return Decimal('0')

            allocated = min(remaining_amount, target)
            allocations[category] += allocated
            remaining_amount -= allocated
            return allocated

        for category in sequence:
            allocate(category)
            if remaining_amount <= 0:
                break

        next_month = 1
        next_unpaid = self.payments.filter(is_paid=False).order_by('month').first()
        if next_unpaid:
            next_month = next_unpaid.month
        elif self.payments.exists():
            next_month = self.payments.latest('month').month + 1

        payment_record = LoanPayment.objects.create(
            loan_application=self,
            month=next_month,
            due_date=paid_date,
            scheduled_amount=amount,
            principal=allocations['principal'],
            interest=allocations['interest'],
            amount_paid=amount,
            paid_date=paid_date,
            is_paid=True,
            penalty_accrued=allocations['penalty'],
            days_overdue=0,
        )

        return {
            'payment_id': payment_record.id,
            'allocated': {k: str(v) for k, v in allocations.items()},
            'remaining_amount': str(remaining_amount)
        }

    def get_penalty_summary(self, today=None):
        from datetime import date, timedelta
        from decimal import Decimal
        from .utils import calculate_penalty_accrual, get_days_overdue

        if today is None:
            today = date.today()

        penalty_rules = list(self.product.penalty_rules.filter(active=True).values('name', 'penalty_amount', 'description'))
        payments = self.payments.all()
        total_accrued_penalty = self.total_penalty_accrued
        unpaid_overdue_penalty = Decimal('0')
        overdue_payment_count = 0
        total_paid = self.total_paid
        total_principal_paid = self.total_principal_paid
        remaining_balance = self.outstanding_principal

        start_date = self.disbursed_at.date() if self.disbursed_at else self.submitted_at.date()
        for month in range(1, self.term_months + 1):
            scheduled_due_date = start_date + timedelta(days=30 * month)
            payment_record = payments.filter(month=month).first()
            due_date = payment_record.due_date if payment_record else scheduled_due_date

            if due_date < today and (not payment_record or not payment_record.is_paid):
                overdue_payment_count += 1
                days_overdue = get_days_overdue(due_date, today)
                if days_overdue > 0:
                    unpaid_penalty = calculate_penalty_accrual(due_date, days_overdue, penalty_rules)
                    unpaid_overdue_penalty += unpaid_penalty

        return {
            'loan_id': self.id,
            'product': self.product.name,
            'outstanding_principal': str(remaining_balance),
            'total_paid': str(total_paid),
            'remaining_balance': str(remaining_balance),
            'interest_rate': str(self.product.interest_rate),
            'total_accrued_penalty': str(total_accrued_penalty + unpaid_overdue_penalty),
            'unpaid_overdue_penalty': str(unpaid_overdue_penalty),
            'overdue_payment_count': overdue_payment_count,
            'penalty_rules': penalty_rules,
            'interest_rate_rules': list(self.product.interest_rules.filter(active=True).values('name', 'rate')),
        }


class LoanPayment(models.Model):
    """Track individual loan payments against scheduled installments"""
    loan_application = models.ForeignKey(LoanApplication, on_delete=models.CASCADE, related_name='payments')
    month = models.PositiveIntegerField()  # Which month of the schedule
    due_date = models.DateField()
    scheduled_amount = models.DecimalField(max_digits=12, decimal_places=2)  # Scheduled payment amount
    principal = models.DecimalField(max_digits=12, decimal_places=2)
    interest = models.DecimalField(max_digits=12, decimal_places=2)
    
    # Payment details
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    paid_date = models.DateField(null=True, blank=True)
    is_paid = models.BooleanField(default=False)
    
    # Penalty tracking
    penalty_accrued = models.DecimalField(max_digits=12, decimal_places=2, default=0)  # Late payment penalties
    days_overdue = models.PositiveIntegerField(default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['loan_application', 'month']
        unique_together = ['loan_application', 'month']

    def __str__(self):
        return f"{self.loan_application.member.member_number} - Month {self.month}"

    def save(self, *args, **kwargs):
        from datetime import date
        from decimal import Decimal
        from .utils import calculate_penalty_accrual, get_days_overdue

        if self.is_paid and not self.paid_date:
            self.paid_date = date.today()

        today = self.paid_date if self.is_paid and self.paid_date else date.today()
        self.days_overdue = get_days_overdue(self.due_date, today)

        if self.days_overdue > 0 and self.penalty_accrued == Decimal('0'):
            penalty_rules = list(self.loan_application.product.penalty_rules.filter(active=True).values('name', 'penalty_amount'))
            self.penalty_accrued = calculate_penalty_accrual(self.due_date, self.days_overdue, penalty_rules)
        elif self.days_overdue <= 0 and self.penalty_accrued == Decimal('0'):
            self.penalty_accrued = Decimal('0')

        super().save(*args, **kwargs)
