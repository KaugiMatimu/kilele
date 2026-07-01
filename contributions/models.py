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


class BusinessRule(models.Model):
    name = models.CharField(max_length=120)
    key = models.CharField(max_length=120, unique=True)
    value = models.JSONField(default=dict, blank=True, null=True)
    description = models.TextField(blank=True)
    active = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class TransactionRecord(models.Model):
    TRANSACTION_TYPE_CHOICES = [
        ('contribution', 'Contribution'),
        ('loan_payment', 'Loan Payment'),
        ('withdrawal', 'Withdrawal'),
        ('share_purchase', 'Share Purchase'),
        ('dividend', 'Dividend'),
    ]

    STATUS_CHOICES = [
        ('posted', 'Posted'),
        ('reversed', 'Reversed'),
        ('voided', 'Voided'),
        ('written_off', 'Written Off'),
    ]

    member = models.ForeignKey('members.Member', on_delete=models.CASCADE, related_name='transactions')
    transaction_type = models.CharField(max_length=30, choices=TRANSACTION_TYPE_CHOICES)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    reference = models.CharField(max_length=120, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='created_transactions')
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='posted')
    approval_history = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.get_transaction_type_display()} — {self.member.member_number} — {self.amount}"

    def save(self, *args, **kwargs):
        created = self._state.adding
        super().save(*args, **kwargs)
        if created and not self.ledger_entries.exists():
            entry_type = 'credit' if self.transaction_type in {'contribution', 'dividend', 'share_purchase'} else 'debit'
            self.record_ledger(
                entry_type,
                self.amount,
                self.amount,
                note=f"Initial {self.get_transaction_type_display().lower()} entry",
            )

    def mark_status(self, status, actor=None, reason=''):
        from django.utils import timezone

        self.status = status
        self.approval_history = list(self.approval_history or [])
        self.approval_history.append({
            'status': status,
            'actor': getattr(actor, 'email', None) if actor else None,
            'reason': reason,
            'changed_at': timezone.now().isoformat(),
        })
        self.save(update_fields=['status', 'approval_history'])

        if status == 'reversed':
            TransactionReversal.objects.create(
                transaction=self,
                reversed_by=actor,
                reason=reason,
            )
            LedgerEntry.objects.create(
                transaction=self,
                entry_type='reversal',
                amount=self.amount,
                balance_after=self.amount,
                note=reason or 'Transaction reversed',
            )
        return self

    def record_ledger(self, entry_type, amount, balance_after, note=''):
        LedgerEntry.objects.create(
            transaction=self,
            entry_type=entry_type,
            amount=amount,
            balance_after=balance_after,
            note=note,
        )



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


class LedgerEntry(models.Model):
    ENTRY_TYPE_CHOICES = [
        ('credit', 'Credit'),
        ('debit', 'Debit'),
        ('reversal', 'Reversal'),
        ('writeoff', 'Write Off'),
    ]

    transaction = models.ForeignKey('TransactionRecord', on_delete=models.CASCADE, related_name='ledger_entries')
    entry_type = models.CharField(max_length=20, choices=ENTRY_TYPE_CHOICES)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    balance_after = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at', 'id']

    def __str__(self):
        return f"{self.entry_type} — {self.transaction.reference}"


class TransactionReversal(models.Model):
    transaction = models.ForeignKey('TransactionRecord', on_delete=models.CASCADE, related_name='reversals')
    reversed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='reversed_transactions')
    reason = models.TextField(blank=True)
    reversed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-reversed_at']

    def __str__(self):
        return f"Reversal for {self.transaction.reference}"
