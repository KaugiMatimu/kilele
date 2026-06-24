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
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-submitted_at']

    def __str__(self):
        return f"{self.product.name} application for {self.member.member_number} ({self.status})"


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
