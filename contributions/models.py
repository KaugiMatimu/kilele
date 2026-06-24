from django.conf import settings
from django.db import models

class ContributionPlan(models.Model):
    name = models.CharField(max_length=120)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    frequency = models.CharField(max_length=40, choices=[
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
        ('annual', 'Annual'),
    ])
    description = models.TextField(blank=True)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class ShareProduct(models.Model):
    name = models.CharField(max_length=120)
    price_per_share = models.DecimalField(max_digits=12, decimal_places=2)
    minimum_shares = models.PositiveIntegerField(default=1)
    description = models.TextField(blank=True)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class ContributionDeadline(models.Model):
    name = models.CharField(max_length=120)
    due_date = models.DateField()
    description = models.TextField(blank=True)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ['due_date']

    def __str__(self):
        return f"{self.name} — {self.due_date}"


class DividendRule(models.Model):
    name = models.CharField(max_length=120)
    percentage = models.DecimalField(max_digits=5, decimal_places=2)
    year = models.PositiveIntegerField()
    active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-year', 'name']

    def __str__(self):
        return f"{self.name} ({self.year})"


class TransactionRecord(models.Model):
    TRANSACTION_TYPE_CHOICES = [
        ('contribution', 'Contribution'),
        ('loan_payment', 'Loan Payment'),
        ('withdrawal', 'Withdrawal'),
        ('share_purchase', 'Share Purchase'),
        ('dividend', 'Dividend'),
    ]

    member = models.ForeignKey('members.Member', on_delete=models.CASCADE, related_name='transactions')
    transaction_type = models.CharField(max_length=30, choices=TRANSACTION_TYPE_CHOICES)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    reference = models.CharField(max_length=120, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.get_transaction_type_display()} — {self.member.member_number} — {self.amount}"


class AuditLog(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    action = models.CharField(max_length=200)
    content_object = models.CharField(max_length=200, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    extra_data = models.JSONField(blank=True, null=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.timestamp}: {self.action}"
